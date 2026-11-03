"""Profile-scoped preparation workflows grounded in capture metadata.

This module selects relevant questions and checklists, not legal eligibility.
Capture/review/failed-fetch states stay visible. An effective source does not,
on its own, authorize a filing-date calculation or an application submission.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PolicyVersion, Profile, now
from app.policy_models import PolicySnapshot, SourceCapture
from app.source_registry import load_sources


def _question(field: str, question: str) -> dict:
    return {"field": field, "question": question, "required_for": "individual_advice"}


def _sources(db: Session, ids: list[str], profile: Profile, today: date) -> list[dict]:
    registry = {entry["id"]: entry for entry in load_sources()}
    result = []
    for source_id in ids:
        entry = registry.get(source_id)
        if not entry or profile.status_type not in entry.get("categories", []):
            continue
        if entry.get("school_id") == "penn" and profile.school != "University of Pennsylvania":
            continue
        version = db.scalar(select(PolicyVersion).where(PolicyVersion.source_id == source_id,
            PolicyVersion.fixture.is_(False)).order_by(PolicyVersion.version.desc(), PolicyVersion.created_at.desc()).limit(1))
        capture = db.get(SourceCapture, source_id)
        snapshot = db.get(PolicySnapshot, version.id) if version else None
        captured_at = snapshot.captured_at if snapshot else None
        # A successful unchanged/304 check refreshes retrieval freshness without
        # pretending that the historical content was newly published/captured.
        checked_at = capture.last_success_at if capture and version and capture.latest_version_id == version.id else None
        checked_at = checked_at or captured_at
        age = (today - checked_at.date()).days if checked_at else None
        stale = age is None or not 0 <= age <= entry.get("staleness_days", 2) or bool(captured_at and captured_at.date() > today)
        failed = bool(capture and capture.last_error)
        reviewed = bool(version and version.reviewed and version.status == "current_effective")
        state = ("capture_failed" if failed else "not_captured" if not snapshot else
                 "stale" if stale else "reviewed_current" if reviewed else
                 "reviewed_noncurrent" if version and version.reviewed else "pending_review")
        result.append({"source_id": source_id, "title": entry["title"], "url": entry["url"],
            "capture_state": state, "http_status": capture.http_status if capture else None,
            "captured_at": captured_at.isoformat() + "Z" if captured_at else None,
            "last_successful_check_at": checked_at.isoformat() + "Z" if checked_at else None,
            "policy_version_id": version.id if version else None,
            "policy_status": version.status if version else None,
            "reviewed": bool(version and version.reviewed), "stale": stale,
            "usable_as_current_authority": reviewed and not stale and not failed,
            "poll_interval_minutes": entry.get("poll_interval_minutes", 720)})
    return result


def build_workflow_guidance(db: Session, profile: Profile, *, today: date | None = None) -> dict:
    """Call only after caller has authenticated ownership of ``profile``.

    No network/model call, mutation, new schema, or inferred sensitive identity.
    Missing I-94 information means the admission *type/date*, never its number.
    """
    today = today or now().date()
    status = profile.status_type
    if status not in {"F-1", "J-1 student", "J-1 scholar"}:
        return {"profile_version": profile.version, "generated_on": today.isoformat(),
            "workflows": [], "scope": "Unsupported category; consult the institution or sponsor."}

    document = "I-20" if status == "F-1" else "DS-2019"
    admission_questions = [
        _question("i94_admission_type", "Does your latest I-94 show D/S or a specific Admit Until Date? Do not enter its identifying number."),
        _question("i94_admit_until_date", "If a specific Admit Until Date is shown, what is that date?"),
    ]
    workflows = []

    def add(key, title, why, steps, questions, source_ids, *, relevance="potential", date_value=None):
        evidence = _sources(db, source_ids, profile, today)
        timing_signals = []
        if profile.program_end < today:
            timing_signals.append("saved_program_document_end_has_passed_requires_adviser_review")
        if key == "travel_reentry" and profile.travel_date:
            if profile.travel_date <= today + timedelta(days=30):
                timing_signals.append("planned_departure_within_internal_30_day_preparation_buffer_or_past")
            if profile.travel_date >= profile.program_end:
                timing_signals.append("planned_departure_on_or_after_saved_program_end_requires_training_and_reentry_review")
        if key in {"opt", "post_completion"} and profile.graduation_date and profile.graduation_date != profile.program_end:
            timing_signals.append("academic_completion_and_document_end_differ_confirm_correct_date")
        workflows.append({"id": key, "title": title, "category": status,
            "applicability": relevance, "reason": why,
            "priority": "review_soon" if timing_signals or profile.program_end <= today + timedelta(days=60) else "plan_ahead",
            "timing_signals": timing_signals,
            "checklist": steps, "missing_information": questions,
            "profile_dates": {"document_end": profile.program_end.isoformat(),
                              "graduation_date": profile.graduation_date.isoformat() if profile.graduation_date else None,
                              "travel_date": profile.travel_date.isoformat() if profile.travel_date else None},
            "planning_target": date_value,
            "legal_deadline": None, "eligibility_determined": False,
            "requires_adviser_review": True,
            "evidence_state": "reviewed_sources_available" if evidence and all(e["usable_as_current_authority"] for e in evidence) else "verification_required",
            "sources": evidence})

    add("admission_record", "Review admission record and policy updates",
        "The document end date, visa expiration and authorized admission are different facts.",
        ["Check the latest I-94 classification and D/S or Admit Until Date after entry.",
         "Compare the admission record with the current program document; ask an adviser about discrepancies.",
         "Check dated implementation/litigation updates before relying on a general policy summary."],
        admission_questions,
        ["penn-i94", "penn-final-rule", "penn-policy-updates", "dhs-maintaining-status", "dos-j1-extensions"],
        relevance="profile_review")
    add("program_extension", f"Plan {document} program extension",
        f"Your saved {document} end date is {profile.program_end.isoformat()}; an extension is relevant only if more program time is needed.",
        ["Confirm whether academic or research activities will continue beyond the saved document end date.",
         "Discuss the reason, supporting academic/department recommendation and funding evidence with the responsible adviser or sponsor.",
         "Check the current school's submission procedure and distinguish document extension from any admission/extension-of-stay requirement.",
         "Use the official portal personally once the adviser confirms the correct request; no application is submitted by this checklist."],
        [_question("needs_program_extension", "Will you need additional time to complete the program or appointment?"),
         _question("extension_reason", "What academic or research reason and proposed new completion date should your adviser review?")] + admission_questions,
        ["penn-extension", "penn-deadlines", "penn-current-scholars" if status == "J-1 scholar" else "penn-current-students",
         "dhs-maintaining-status" if status == "F-1" else "dos-j1-extensions", "penn-final-rule-planning"])

    travel_questions = []
    if not profile.travel_date:
        travel_questions.append(_question("travel_date", "When do you plan to depart, and when do you expect to return?"))
    else:
        travel_questions.append(_question("return_date", "When do you expect to return to the United States?"))
    if not profile.travel_signature_date:
        travel_questions.append(_question("travel_signature_date", f"What is the most recent travel endorsement date on your {document}?"))
    travel_questions += [
        _question("visa_passport_validity", "Are the passport and entry visa valid for the planned return, or is a visa appointment needed? Do not enter document numbers."),
        _question("employment_authorization_stage", "Are you studying, on OPT/STEM OPT, on Academic Training, or in a scholar appointment?"),
    ] + admission_questions
    add("travel_reentry", "Prepare travel, visa and re-entry review",
        "A travel signature or visa alone does not establish permission to re-enter.",
        [f"Inspect the current {document}, travel endorsement, passport, visa and latest I-94.",
         "Ask the adviser to assess signature validity using the actual return date and study/training category.",
         "Review travel during pending applications or after program completion before booking.",
         "After re-entry, retrieve the new I-94 and check classification and admission information."],
        travel_questions, ["penn-travel", "penn-i94", "penn-final-rule-planning", "dos-j1-extensions"],
        relevance="planned_travel" if profile.travel_date else "if_travel_planned")

    if status == "F-1":
        completion_questions = [] if profile.graduation_date else [_question("graduation_date", "What is your expected academic completion date, separately from the ceremony date?")]
        completion_questions += [_question("post_completion_plan", "After completion, are you considering OPT, another program/transfer, departure, or a different status?")] + admission_questions
        add("post_completion", "Plan academic completion and next status steps",
            "Next steps depend on actual academic completion, authorized training and admission facts.",
            ["Confirm actual completion and current I-20 dates with the school.",
             "Compare the relevant official completion, OPT, transfer and departure guidance for your chosen next step.",
             "Have the adviser confirm any applicable filing or departure date; no universal grace-period countdown is inferred here."],
            completion_questions, ["penn-current-students", "dhs-maintaining-status", "penn-final-rule-planning"])
        add("opt", "Review F-1 OPT preparation",
            "F-1 status makes OPT a topic to assess, not an automatic eligibility finding.",
            ["Clarify pre-completion versus post-completion OPT and prior practical-training history.",
             "Review the school's OPT recommendation procedure and current USCIS I-765 instructions.",
             "Check the DSO recommendation date, actual completion date and requested employment dates before calculating any filing window.",
             "Confirm authorization and approved dates before starting employment."],
            [_question("opt_stage", "Is this pre-completion, initial post-completion, current OPT or a different training request?"),
             _question("academic_and_training_history", "Has your adviser verified the enrollment requirement and any prior CPT/OPT at this degree level?"),
             _question("dso_recommendation_date", "Has an OPT-recommended I-20 been issued, and what recommendation date does it show?")] + completion_questions,
            ["penn-opt", "uscis-opt", "uscis-student-employment", "penn-final-rule-planning"])
        add("stem_opt", "Check whether a STEM OPT review is relevant",
            "Nationality or a degree title does not establish STEM OPT eligibility.",
            ["First establish whether you hold current post-completion OPT and its EAD end date.",
             "Check the degree/CIP qualification, employer requirements, training plan and DSO recommendation against current official guidance.",
             "If eligible, plan both application and continuing reporting obligations with the adviser."],
            [_question("current_opt_and_ead_end", "Are you currently on post-completion OPT, and when does the EAD expire?"),
             _question("stem_degree_cip", "Has your DSO confirmed the qualifying degree/CIP and any prior STEM extension use?"),
             _question("stem_employer_training_plan", "Has the employer/training-plan requirement been reviewed with your DSO?")],
            ["penn-stem-opt", "uscis-stem-opt"], relevance="conditional_on_current_opt")
    elif status == "J-1 student":
        add("academic_training", "Review J-1 student Academic Training",
            "The J-1 student training workflow is separate from F-1 OPT.",
            ["Check the DS-2019 sponsor and the proposed activity's relationship to the academic program.",
             "Prepare employer/activity dates, academic adviser recommendation and funding information where applicable.",
             "Obtain the responsible officer's written authorization before beginning the activity.",
             "Review completion and travel plans with the sponsor before departure or an extension request."],
            [_question("academic_training_plan", "Do you intend pre-completion or post-completion Academic Training?"),
             _question("training_offer_and_dates", "Do you have a specific proposed activity/employer, start/end dates and academic adviser recommendation?"),
             _question("program_sponsor", "Which organization is the sponsor on your DS-2019?"),
             _question("academic_completion_date", "What is the actual academic completion date and current training authorization, if any?")] + admission_questions,
            ["penn-academic-training", "dos-j1-students", "penn-deadlines", "dos-j1-extensions"])
    else:
        add("scholar_program", "Coordinate J-1 scholar appointment and sponsor review",
            "Research-scholar/professor/short-term-scholar category and sponsor history matter; student OPT or Academic Training is not assumed.",
            ["Confirm the exact DS-2019 category and sponsor with the hosting department.",
             "Review appointment continuation, funding and any extension/transfer with the host department and responsible officer.",
             "Ask the sponsor to review proposed outside lectures/consultations, travel and category/history restrictions.",
             "Review end-of-program arrangements and any insurance/reporting requirements with the sponsor."],
            [_question("exact_j1_scholar_category", "What exact scholar category appears on your DS-2019?"),
             _question("sponsor_and_host", "Which sponsor and host department manage your appointment?"),
             _question("appointment_plan_and_history", "Will the appointment continue or transfer, and has the sponsor reviewed relevant prior J-program history?")] + admission_questions,
            ["penn-current-scholars", "dos-j1-scholars", "dos-j1-extensions", "penn-deadlines"])

    return {"profile_version": profile.version, "generated_on": today.isoformat(),
        "scope": "Preparation guidance; selected by saved category/dates. Missing facts and current official evidence require review before a legal deadline or eligibility decision.",
        "workflows": workflows}
