"""Stage-aware planning, not legal eligibility or an automated filing-window engine."""
from datetime import date, timedelta

from app.profile_details import details_for

PLANNING_RULE_VERSION = "business-planning-2026-11-03-v1"
PRE_APPLICATION = {"considering", "preparing"}
AUTHORIZED = {"approved", "active"}


def preparation_targets(profile, defaults=None):
    """Internal buffers only; dates are never represented as legal deadlines."""
    details = details_for(profile)
    defaults = defaults or {}
    opt_buffer = defaults.get("opt_prepare_days", 60)
    ead_buffer = defaults.get("ead_review_days", 30)
    training_buffer = defaults.get("academic_training_review_days", 30)
    targets = []
    if profile.status_type == "F-1":
        basis = {"pre_completion": (details.opt_requested_start, "requested employment start"),
                 "post_completion": (details.academic_completion_date, "academic completion"),
                 "stem_extension": (details.ead_end, "current EAD end")}.get(details.opt_type, (None, "unknown application type"))
        if details.opt_stage in PRE_APPLICATION and basis[0]:
            targets.append(("opt_preparation", "Review OPT preparation with your DSO",
                basis[0] - timedelta(days=opt_buffer),
                [f"Saved {basis[1]}: {basis[0].isoformat()}",
                 f"Internal preparation buffer: {opt_buffer} days; not the earliest or latest filing date."], "penn-opt"))
        if details.ead_end and (details.f1_activity in {"post_completion_opt", "stem_opt"} or details.opt_stage in AUTHORIZED):
            targets.append(("ead_review", "Review EAD end date and your next plan",
                details.ead_end - timedelta(days=ead_buffer),
                [f"Saved EAD end: {details.ead_end.isoformat()}",
                 f"Internal review buffer: {ead_buffer} days; no extension or work authorization is inferred."], "uscis-opt"))
    if profile.status_type == "J-1 student" and details.academic_training_end and details.academic_training_stage in {"authorized", "active"}:
        targets.append(("academic_training_review", "Review Academic Training end with your sponsor",
            details.academic_training_end - timedelta(days=training_buffer),
            [f"Saved training end: {details.academic_training_end.isoformat()}",
             f"Internal sponsor-review buffer: {training_buffer} days; not a new authorization or legal deadline."], "penn-academic-training"))
    return targets


def personalize_workflow(workflow, profile, today: date):
    """Filter answered questions and select next steps from explicit saved facts."""
    details = details_for(profile)
    key = workflow["id"]
    known = details.model_dump(mode="json")
    known.update(travel_date=profile.travel_date, travel_signature_date=profile.travel_signature_date,
                 graduation_date=details.academic_completion_date or profile.graduation_date)
    aliases = {
        "current_opt_and_ead_end": bool(details.f1_activity in {"post_completion_opt", "stem_opt"} and details.ead_end),
        "employment_authorization_stage": (details.f1_activity != "unknown" if profile.status_type == "F-1" else details.academic_training_stage != "unknown" if profile.status_type == "J-1 student" else details.j1_category != "unknown"),
        "visa_passport_validity": bool(details.passport_expiry and details.visa_expiry),
        "academic_and_training_history": details.training_history_reviewed is True,
        "stem_degree_cip": details.stem_eligibility_reviewed is True,
        "needs_program_extension": details.extension_stage != "unknown",
        "extension_reason": details.extension_stage in {"not_needed", "completed"},
        "exact_j1_scholar_category": details.j1_category != "unknown",
        "sponsor_and_host": bool(details.sponsor_name and details.host_department),
        "program_sponsor": bool(details.sponsor_name),
        "academic_training_plan": details.academic_training_stage != "unknown",
        "training_offer_and_dates": bool(details.academic_training_start and details.academic_training_end),
    }

    def answered(field):
        if field == "i94_admit_until_date" and details.i94_admission_type == "duration_of_status":
            return True
        if field in aliases:
            return aliases[field]
        return known.get(field) not in (None, "", "unknown")

    workflow["missing_information"] = [q for q in workflow["missing_information"] if not answered(q["field"])]
    checks = []

    def check(code, message, fields, *, attention=False):
        checks.append({"id": code, "message": message, "fields": fields,
                       "state": "review_required" if attention else "information_needed"})

    def ask(field, question):
        if not answered(field) and field not in {q["field"] for q in workflow["missing_information"]}:
            workflow["missing_information"].append({"field": field, "question": question, "required_for": "individual_advice"})

    if key == "program_extension":
        workflow["saved_stage"] = details.extension_stage
        if details.extension_stage in {"not_needed", "completed"}:
            workflow.update(applicability="not_currently_needed" if details.extension_stage == "not_needed" else "recorded_complete",
                checklist=["Keep the current program document dates accurate; revisit this workflow if your plans change."], missing_information=[])
        elif details.extension_stage == "submitted":
            workflow["checklist"] = ["Track the submitted request and any adviser follow-up.",
                "Submission does not itself extend your program or admission; confirm the outcome with your adviser.",
                "After approval, save the dates from the new document and mark this process completed."]
            workflow["missing_information"] = []
        elif details.extension_stage in PRE_APPLICATION:
            ask("extension_requested_end", "What new program end date are you asking your adviser to review?")

    if key == "opt":
        workflow["saved_stage"] = details.opt_stage
        stage_steps = {
            "not_planning": ["No OPT application is currently planned. Update this choice if your plans change."],
            "submitted": ["Check the USCIS receipt and application progress; keep the submitted application details accurate.",
                "Review any request for evidence or decision notice with your DSO.",
                "A pending application is not itself proof of permission to work or re-enter."],
            "approved": ["Check the approval and EAD for the correct dates and details.",
                "Confirm when employment is authorized and review reporting obligations with your DSO."],
            "active": ["Keep the current EAD dates and activity accurate.",
                "Review reporting obligations and the next plan with your DSO; travel requires a separate document review."],
            "completed": ["Confirm the completed authorization and your next program, transfer, departure or other plan with your DSO."],
            "denied": ["Review the actual decision and any response options promptly with your DSO or qualified adviser. Do not assume a new filing is available."],
            "withdrawn": ["Review the withdrawal outcome and next steps with your DSO before making work or travel plans."],
        }
        if details.opt_stage in stage_steps:
            workflow["checklist"] = stage_steps[details.opt_stage]
            workflow["missing_information"] = []
        if details.opt_stage == "not_planning":
            workflow["applicability"] = "not_planned"
        if details.opt_stage in PRE_APPLICATION or details.opt_stage == "submitted":
            ask("opt_type", "Which OPT application is this: pre-completion, post-completion, or STEM extension?")
            ask("dso_recommendation_date", "What DSO recommendation date applies to this application?")
        if details.opt_stage in PRE_APPLICATION:
            if details.opt_type == "stem_extension":
                ask("ead_end", "What end date is on the current OPT EAD for this STEM extension review?")
            elif details.opt_type == "pre_completion":
                ask("opt_requested_start", "What employment start date are you considering?")
            else:
                ask("academic_completion_date", "What academic completion date has your school confirmed (not the ceremony date)?")
        if details.opt_stage == "submitted":
            ask("opt_submitted_date", "When was this OPT application submitted?")
        if details.opt_stage in AUTHORIZED:
            ask("ead_start", "What start date appears on the EAD?")
            ask("ead_end", "What end date appears on the EAD?")
        if details.opt_stage == "active" and details.ead_start and details.ead_start > today:
            check("active_before_saved_ead_start", "The application is marked active but the saved EAD start is in the future. Confirm these records; this is not an authorization decision.", ["opt_stage", "ead_start"], attention=True)
        if details.opt_stage in {"submitted", "denied"}:
            workflow["priority"] = "review_soon"

    if key == "post_completion" and details.post_completion_plan not in {"unknown", "undecided"}:
        plans = {"opt": "Review the OPT workflow and school-confirmed academic completion date with your DSO.",
                 "stem_opt": "Review the current EAD, STEM qualifications and training plan with your DSO.",
                 "transfer": "Confirm the new school, transfer timing and responsible advisers before changing your program.",
                 "new_program": "Confirm the new program and document transition with the responsible advisers.",
                 "departure": "Confirm departure, completion and required reporting with your adviser.",
                 "other": "Discuss your intended next step with a qualified adviser before relying on a status timeline."}
        workflow["checklist"] = [plans[details.post_completion_plan],
            "No universal grace-period or departure deadline is inferred from these saved dates."]

    if key == "stem_opt":
        if details.opt_stage == "not_planning" and details.f1_activity not in {"post_completion_opt", "stem_opt"}:
            workflow.update(applicability="not_planned", checklist=["No OPT or STEM process is currently planned. Revisit if your activity or plans change."], missing_information=[])
        elif details.opt_type == "stem_extension":
            workflow["saved_stage"] = details.opt_stage
            if details.opt_stage in {"submitted", "approved", "active", "completed", "denied", "withdrawn"}:
                workflow["checklist"] = ["Follow the saved STEM application stage in the OPT workflow.",
                    "Review STEM reporting and employer/training-plan obligations with your DSO.",
                    "No automatic employment extension or STEM eligibility is inferred from a submitted application."]

    if key == "academic_training":
        workflow["saved_stage"] = details.academic_training_stage
        if details.academic_training_stage == "not_planning":
            workflow.update(applicability="not_planned", checklist=["No Academic Training is currently planned. Update this choice if needed."], missing_information=[])
        elif details.academic_training_stage in {"submitted", "authorized", "active", "completed"}:
            workflow["checklist"] = (["Follow up with the sponsor on the submitted request; submission is not authorization."]
                if details.academic_training_stage == "submitted" else ["Check the written sponsor authorization and its activity dates.",
                "Keep reporting, travel and end-of-training plans consistent with the sponsor's instructions."])
            workflow["missing_information"] = []
            ask("academic_training_start", "What is the proposed or authorized Academic Training start date?")
            ask("academic_training_end", "What is the proposed or authorized Academic Training end date?")
            if details.academic_training_stage in {"authorized", "active"}:
                ask("sponsor_authorized_on", "When did the sponsor issue written authorization?")
            if details.academic_training_stage == "completed":
                workflow["missing_information"] = []

    if key == "travel_reentry":
        ask("travel_destination", "Which country or countries will you visit?")
        ask("passport_expiry", "When does your passport expire? Do not enter its number.")
        ask("visa_expiry", "When does your US entry visa expire, if applicable? Do not enter its number.")
        if details.return_date:
            for field, label in (("passport_expiry", "passport"), ("visa_expiry", "US entry visa")):
                expiry = getattr(details, field)
                if expiry and expiry < details.return_date:
                    check(f"{field}_before_return", f"The saved {label} expires before the planned return. Review renewal or applicable exceptions with your adviser; visa expiry alone does not determine US status.", [field, "return_date"], attention=True)
            if details.return_date >= profile.program_end:
                check("return_on_or_after_document_end", "Return is on or after the saved program document end. Review the actual study/training and re-entry documents with your adviser.", ["return_date", "program_end"], attention=True)
            if details.ead_end and details.f1_activity in {"post_completion_opt", "stem_opt"} and details.ead_end < details.return_date:
                check("ead_end_before_return", "The saved EAD ends before the planned return. Request an individualized travel review; no automatic extension is assumed.", ["ead_end", "return_date"], attention=True)
        if profile.travel_signature_date:
            check("travel_signature_needs_category_review", "An endorsement date is saved. Its relevance depends on the return date, current activity and document type; confirm the current signature requirement with ISSS.", ["travel_signature_date", "return_date", "f1_activity"])
        if profile.status_type == "F-1" and details.opt_stage == "submitted":
            check("travel_during_pending_opt", "An OPT application is pending. Ask your DSO to review the application stage and re-entry documents before departure.", ["opt_stage", "travel_date"], attention=True)

    if key == "admission_record" and details.i94_admission_type == "dated" and details.i94_admit_until_date:
        if details.i94_admit_until_date <= today + timedelta(days=30):
            check("dated_admission_review", "The recorded I-94 date is within the internal 30-day review buffer or has passed. Confirm the actual record and next step promptly with your adviser.", ["i94_admit_until_date"], attention=True)

    workflow["record_checks"] = checks
    workflow["planning_rule_version"] = PLANNING_RULE_VERSION
    if any(item["state"] == "review_required" for item in checks):
        workflow["priority"] = "review_soon"
    return workflow
