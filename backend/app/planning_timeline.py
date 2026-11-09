"""Server-owned planning milestones with bounded model-selected context steps."""
from copy import deepcopy

from app.profile_details import details_for

TIMELINE_VERSION = "planning-timeline-v2"
CONTEXT_NODE_VERSION = "planning-context-node-v1"


CHECK_TITLES = {
    "active_before_saved_ead_start": "Resolve the OPT stage and saved EAD start-date conflict",
    "passport_expiry_before_return": "Review passport expiry before the planned return",
    "visa_expiry_before_return": "Review visa expiry before the planned return",
    "return_on_or_after_document_end": "Review re-entry after the saved program-document end",
    "ead_end_before_return": "Review travel after the saved EAD end",
    "travel_signature_needs_category_review": "Confirm the travel-signature requirement",
    "travel_during_pending_opt": "Review travel while OPT is pending",
    "dated_admission_review": "Review the saved I-94 admit-until date",
}


def _anchor(workflow, node_ids):
    preferred = {
        "travel": "documents",
        "opt": "adviser",
        "extension": "adviser",
        "academic_training": "adviser",
        "scholar": "adviser",
    }.get(workflow, "adviser")
    return preferred if preferred in node_ids else next(iter(node_ids))


def build_context_candidates(request, guidance, timeline):
    """Build a server-owned allowlist from this scenario's real checks/questions.

    The model may choose candidate IDs and explain them. Titles, placement,
    dependencies, sources, timing and calendar eligibility remain server-owned.
    """
    node_ids = {node["id"] for node in timeline["nodes"]}
    anchor = _anchor(request.workflow, node_ids)
    candidates = []

    def add(key, title, basis, reason, *, kind="to_confirm", when="To confirm"):
        candidate_id = f"context_{key}"
        if candidate_id in node_ids or any(row["id"] == candidate_id for row in candidates):
            return
        candidates.append({"id": candidate_id, "title": title, "date": None,
            "date_kind": kind, "time_label": when, "explanation": "", "basis": basis,
            # Sources are attached only after selection. Avoid repeating the
            # same source records in every private candidate and grounding turn.
            "depends_on": [anchor], "sources": [], "calendar_target": None,
            "rule_version": CONTEXT_NODE_VERSION, "node_role": "contextual",
            "selection_reason": reason, "insert_after": anchor})

    for check in guidance.get("record_checks", []):
        key = str(check.get("id", "record_check"))[:52]
        title = CHECK_TITLES.get(key, "Review the record issue identified for this plan")
        message = str(check.get("message", "Review the saved details with the responsible adviser."))[:500]
        fields = ", ".join(str(field) for field in check.get("fields", [])[:5])
        basis = [message] + ([f"Saved fields involved: {fields}."] if fields else [])
        add(key, title, basis,
            "Current saved or temporary details produced a scenario-specific record check.",
            kind="sequence", when="Before relying on this plan")

    # Missing-information candidates give the model bounded flexibility without
    # allowing it to invent a deadline or a new workflow. Cap the server list so
    # prompt size and the user-facing plan remain manageable.
    for item in guidance.get("missing_information", []):
        if len(candidates) >= 6:
            break
        field = str(item.get("field", "missing_detail"))[:44]
        question = str(item.get("question", "What information still needs confirmation?"))[:180]
        add(f"confirm_{field}", f"Confirm: {question.rstrip('?')}", [question],
            "This fact is missing from the current scenario and may change the appropriate next steps.")
    return candidates


def compile_context_nodes(plan, selections):
    """Insert only validated model selections into the immutable core sequence."""
    timeline = plan["timeline"]
    candidates = {row["id"]: row for row in plan.get("timeline_candidates", [])}
    selected = {row.id: row.explanation for row in selections}
    contextual = []
    for candidate in plan.get("timeline_candidates", []):
        if candidate["id"] not in selected:
            continue
        node = deepcopy(candidate)
        node.pop("insert_after", None)
        node["explanation"] = selected[node["id"]]
        node["sources"] = plan["sources"]
        contextual.append(node)

    by_anchor = {}
    for node in contextual:
        anchor = candidates[node["id"]]["insert_after"]
        by_anchor.setdefault(anchor, []).append(node)
    compiled = []
    for node in timeline["nodes"]:
        compiled.append(node)
        compiled.extend(by_anchor.get(node["id"], []))
    timeline["nodes"] = compiled
    timeline["notice"] = ("Core process steps stay server-controlled. Personalized steps are selected from "
        "backend-approved options supported by this scenario; sequence spacing is not to scale.")
    plan.pop("timeline_candidates", None)
    return plan


def build_timeline(profile, request, guidance, targets):
    details = details_for(profile)
    nodes = []
    sources = guidance["sources"]

    def add(key, title, *, day=None, kind="to_confirm", when="To confirm", basis=None, depends=None, target=None):
        nodes.append({"id": key, "title": title, "date": day, "date_kind": kind,
            "time_label": when, "explanation": "", "basis": basis or [],
            "depends_on": depends or [], "sources": sources,
            "calendar_target": target, "rule_version": target.get("rule_version") if target else TIMELINE_VERSION,
            "node_role": "core"})

    def preparation(workflows, title):
        target = next((row for row in targets if row["workflow"] in workflows), None)
        add("prepare", title, day=target["date"] if target else None,
            kind="preparation_target" if target else "to_confirm",
            basis=target["trace"] if target else ["A preparation date needs the relevant start or end date. Confirm the missing dates before calculating it."],
            depends=["adviser"], target=target)

    if request.workflow == "opt":
        stage = details.opt_stage
        if stage in {"approved", "active", "completed"}:
            add("adviser", "Review your authorization and reporting requirements", kind="sequence", when="Now",
                basis=[f"Saved application stage: {stage}. Saved records are user-supplied, not a provider verification."])
            if details.ead_start:
                add("ead_start", "EAD start on your saved record", day=details.ead_start.isoformat(), kind="saved_date",
                    basis=["Taken directly from the EAD start date entered in this plan or profile; not a new authorization decision."])
            preparation({"ead_review"}, "Review your EAD end date and next plan")
            add("ead_end", "EAD end on your saved record", day=details.ead_end.isoformat() if details.ead_end else None,
                kind="saved_date" if details.ead_end else "to_confirm", basis=["Use the end date on the actual EAD. No automatic extension is assumed."])
        elif stage in {"denied", "withdrawn", "not_planning"}:
            add("adviser", "Review your current plans with your adviser", kind="sequence", when="Now",
                basis=[f"Saved application stage: {stage}. A new application or filing date is not inferred from this stage."])
            add("next_plan", "Confirm the next applicable process", depends=["adviser"],
                basis=["Confirm the actual outcome, current records and intended activity before choosing another workflow."])
        else:
            add("adviser", "Confirm your OPT route and dates with your DSO", kind="sequence", when="Now",
                basis=["The intended internship start, requested OPT start and approved EAD start are separate facts.",
                       f"Saved OPT type: {details.opt_type}; stage: {stage}."])
            if stage != "submitted":
                preparation({"opt_preparation"}, "Prepare your OPT materials and adviser questions")
                add("recommendation", "Obtain and check the OPT-recommended I-20",
                    day=details.dso_recommendation_date.isoformat() if details.dso_recommendation_date else None,
                    kind="saved_date" if details.dso_recommendation_date else "to_confirm", depends=["prepare"],
                    basis=["A saved DSO recommendation date is shown only when supplied. Confirm the relevant date on the actual document with ISSS."])
            add("filing", "Confirm the filing window and submit your application" if stage != "submitted" else "Review your submitted application",
                day=details.opt_submitted_date.isoformat() if stage == "submitted" and details.opt_submitted_date else None,
                kind="saved_date" if stage == "submitted" and details.opt_submitted_date else "to_confirm",
                depends=["recommendation"] if stage != "submitted" else ["adviser"],
                basis=["A filing window is not calculated by the current preparation-buffer rules. Confirm the applicable OPT category, enrollment history and school/document dates against current official guidance."])
            add("decision", "Track the decision and check the approved dates", kind="sequence", when="After submission", depends=["filing"],
                basis=["No approval date or processing duration can be derived from the supplied facts. Submission alone is not work authorization."])
            goal = request.goal_date or details.opt_requested_start
            add("goal", "Your intended internship / employment start" if request.goal_date else "Requested OPT start to confirm",
                day=goal.isoformat() if goal else None, kind="user_goal" if goal else "to_confirm", depends=["decision"],
                basis=["User-entered planning goal; it does not establish the start date USCIS will approve."])
    elif request.workflow == "travel":
        add("adviser", "Review your travel and re-entry situation", kind="sequence", when="Now",
            basis=["Use the saved category, planned departure and return, and current study/training stage."])
        preparation({"travel_review"}, "Check your travel documents with ISSS")
        add("documents", "Confirm signature, passport and visa requirements", depends=["prepare"],
            basis=["Document expiration and endorsement dates need a category-specific review using the actual return date; this plan does not infer signature validity or permission to re-enter."])
        add("departure", "Planned departure from the United States", day=profile.travel_date.isoformat() if profile.travel_date else None,
            kind="user_goal" if profile.travel_date else "to_confirm", depends=["documents"], basis=["User-supplied departure date; no trip has been booked by this plan."])
        add("return", "Planned return and admission-record check", day=details.return_date.isoformat() if details.return_date else None,
            kind="user_goal" if details.return_date else "to_confirm", depends=["departure"], basis=["User-supplied return date. Review the actual admission record after entry."])
    elif request.workflow in {"extension", "scholar"}:
        complete = details.extension_stage in {"not_needed", "completed"}
        add("adviser", "Review your program or appointment plans", kind="sequence", when="Now",
            basis=[f"Saved extension stage: {details.extension_stage}. Confirm whether additional program time is needed."])
        if not complete:
            preparation({"program_extension", "document_review"}, "Prepare or follow up with the adviser / sponsor")
            add("request", "Confirm the school process and request timing", depends=["prepare"],
                basis=["School submission timing and any separate admission requirement need confirmation. An internal preparation target is not a filing deadline."])
        add("program_end", "Current program document end", day=profile.program_end.isoformat(), kind="saved_date",
            basis=["Taken from your saved I-20 / DS-2019 program end; the document itself has not been changed."])
        if details.extension_requested_end and not complete:
            add("new_end", "Proposed new end date", day=details.extension_requested_end.isoformat(), kind="user_goal", depends=["request"],
                basis=["This is the requested date, not an approved extension. Save the new document dates only after confirmation."])
    elif request.workflow == "academic_training":
        add("adviser", "Confirm Academic Training with your sponsor", kind="sequence", when="Now",
            basis=["J-1 student Academic Training uses sponsor authorization, separately from F-1 OPT."])
        preparation({"academic_training_review"}, "Prepare your sponsor review and next steps")
        add("authorization", "Confirm written sponsor authorization", day=details.sponsor_authorized_on.isoformat() if details.sponsor_authorized_on else None,
            kind="saved_date" if details.sponsor_authorized_on else "to_confirm", depends=["adviser"],
            basis=["Use the actual sponsor's written authorization; a submitted request is not authorization."])
        for key, title, day in (("training_start", "Proposed / authorized training start", details.academic_training_start),
                                ("training_end", "Proposed / authorized training end", details.academic_training_end)):
            add(key, title, day=day.isoformat() if day else None, kind="saved_date" if day else "to_confirm",
                depends=["authorization"], basis=["User-supplied Academic Training date. Confirm it against the written sponsor authorization."])
    # A label alone never makes an undated milestone eligible for calendar actions.
    return {"version": TIMELINE_VERSION, "layout": "sequence", "nodes": nodes,
        "notice": "Steps are arranged by process, not to scale. Preparation targets, personal goals and official filing dates have different meanings."}
