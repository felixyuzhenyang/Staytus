import hashlib
import json
from contextvars import ContextVar
from datetime import date, timedelta
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Account, Approval, AuditEvent, DeadlineResult, Notification, PolicySource, PolicyVersion, Profile, RuleVersion, now
from app.rules import adapter_for
from app.schemas import CalendarPayload, EmailPayload, ProfileUpdate

POLICY_STATUSES = ("current_effective", "announced_future", "proposed", "under_comment", "detected_pending_review", "postponed_or_enjoined", "superseded", "unverified_report")
request_correlation: ContextVar[str | None] = ContextVar("request_correlation", default=None)


def iso(value):
    return value.isoformat() + ("Z" if hasattr(value, "hour") else "") if value is not None else None


def payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def audit(db: Session, profile_id: str, action: str, detail: dict | None = None, correlation_id: str | None = None):
    db.add(AuditEvent(profile_id=profile_id, action=action, detail=detail or {}, correlation_id=correlation_id or request_correlation.get() or str(uuid4())))


def profile_json(p: Profile):
    return {"id": p.id, "name": p.name, "school": p.school, "status_type": p.status_type, "visa_type": p.status_type,
            "program_start": iso(p.program_start), "program_end": iso(p.program_end), "graduation_date": iso(p.graduation_date),
            "travel_date": iso(p.travel_date), "travel_signature_date": iso(p.travel_signature_date),
            "planning_details": p.planning_details or {},
            "notification_frequency": p.notification_frequency, "version": p.version,
            "nationality": p.nationality, "email": p.email, "program_level": "Scholar" if "scholar" in p.status_type else "Student", "synthetic": p.synthetic}


def update_profile(db: Session, p: Profile, body: ProfileUpdate):
    data = body.model_dump(exclude_unset=True)
    if any(data.get(k, "missing") is None for k in ("name", "school", "status_type", "nationality", "program_start", "program_end", "notification_frequency")):
        raise HTTPException(422, "Required profile fields cannot be cleared")
    for key in ("name", "school", "nationality"):
        if key in data:
            data[key] = data[key].strip()
            if not data[key]:
                raise HTTPException(422, f"{key} cannot be blank")
    if "school" in data and data["school"].casefold() in ("penn", "upenn", "university of pennsylvania"):
        data["school"] = "University of Pennsylvania"
    if not data:
        raise HTTPException(422, "Profile update cannot be empty")
    start, end = data.get("program_start", p.program_start), data.get("program_end", p.program_end)
    if start >= end:
        raise HTTPException(422, "Program end must be later than program start")
    from app.profile_details import normalize_details
    details = dict(p.planning_details or {})
    if "planning_details" in data:
        details = {} if data["planning_details"] is None else {**details, **data["planning_details"]}
    try:
        data["planning_details"] = normalize_details(details, data.get("status_type", p.status_type),
            data.get("travel_date", p.travel_date), category_changed=data.get("status_type", p.status_type) != p.status_type)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    for key, value in data.items():
        setattr(p, key, value)
    if "name" in data and p.account_id:
        db.get(Account, p.account_id).name = data["name"]
    p.version += 1
    audit(db, p.id, "profile.updated", {"fields": list(data), "version": p.version})
    db.flush()
    return profile_json(p)


def active_rule(db: Session, *, include_fixtures: bool = False):
    statement = select(RuleVersion).join(PolicyVersion).where(
        RuleVersion.effective_from <= now(), PolicyVersion.reviewed.is_(True),
        PolicyVersion.status == "current_effective")
    if not include_fixtures:
        statement = statement.where(PolicyVersion.fixture.is_(False))
    return db.scalar(statement.order_by(RuleVersion.version.desc()).limit(1))


def deadlines(db: Session, p: Profile):
    rule = active_rule(db, include_fixtures=bool(p.synthetic))
    results = adapter_for(p).deadlines(p, rule)
    # Configuration preferences work before any policy is ingested or reviewed.
    # Only reviewed, database-backed rule versions are persisted in this cache.
    for result in results if rule else []:
        cached = db.scalar(select(DeadlineResult).where(DeadlineResult.profile_id == p.id, DeadlineResult.workflow == result["workflow"], DeadlineResult.profile_version == p.version, DeadlineResult.rule_version_id == rule.id))
        if not cached:
            db.add(DeadlineResult(profile_id=p.id, workflow=result["workflow"], profile_version=p.version, rule_version_id=rule.id, result=result))
    db.flush()
    return results


def tasks_for(db: Session, p: Profile):
    calculated = deadlines(db, p)
    return [{"id": item["id"], "title": item["title"], "status": "planned", "due_date": item["date"], "workflow": item["workflow"]} for item in calculated]


def notification_json(n: Notification):
    return {"id": n.id, "title": n.title, "message": n.message, "data": n.data, "created_at": iso(n.created_at)}


def policy_json(db: Session, p: PolicyVersion):
    source = db.get(PolicySource, p.source_id)
    return {"id": p.id, "title": p.title, "text": p.text, "status": p.status, "reviewed": p.reviewed,
            "source_url": source.url, "source_title": source.title, "verified_at": iso(p.verified_at), "version": p.version,
            "created_at": iso(p.created_at), "fixture": p.fixture, "fictional": p.fixture, "visa_types": p.visa_types,
            "freshness": "demo_fixture_not_live_verified" if p.fixture else ("unverified" if not p.verified_at else "review_required"),
            "authority": "demo-authored summary" if p.fixture else "official source snapshot"}


def search_policies(db: Session, p: Profile, query: str = "", include_pending: bool = False):
    from app.retrieval import retrieve_for_profile

    return retrieve_for_profile(db, p, query, include_pending=include_pending)


def approval_json(a: Approval):
    target = a.payload.get("_connector_target")
    return {"id": a.id, "kind": a.kind, "status": a.status, "payload": a.payload, "payload_hash": a.payload_hash,
            "target_account": target.get("account_label") if isinstance(target, dict) else None,
            "expires_at": iso(a.expires_at), "created_at": iso(a.created_at), "receipt": a.receipt,
            "execution_mode": ({"calendar": "provider_calendar" if a.payload.get("provider", "export") != "export" else "file_export", "email": "provider", "profile_update": "local"}.get(a.kind, "unavailable")), "profile_version": a.profile_version}


def expire_approval(db: Session, a: Approval):
    if a.expires_at <= now() and a.status in ("PROPOSED", "PREVIEWED", "APPROVED"):
        a.status = "EXPIRED"
        audit(db, a.profile_id, "approval.expired", {"approval_id": a.id})
        db.flush()


def get_approval(db: Session, profile_id: str, approval_id: str):
    approval = db.scalar(select(Approval).where(Approval.id == approval_id, Approval.profile_id == profile_id))
    if not approval:
        raise HTTPException(404, "Approval not found")
    expire_approval(db, approval)
    return approval


def propose(db: Session, p: Profile, kind: str, payload: dict):
    validators = {"calendar": CalendarPayload, "email": EmailPayload, "profile_update": ProfileUpdate}
    if kind not in validators:
        raise HTTPException(422, "Unsupported approval kind")
    try:
        normalized = validators[kind].model_validate(payload).model_dump(mode="json", exclude_unset=kind == "profile_update")
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_context=False))
    if kind == "profile_update" and not normalized:
        raise HTTPException(422, "Profile update cannot be empty")
    if kind == "email" or (kind == "calendar" and normalized.get("provider") != "export"):
        if kind == "calendar" and normalized.get("provider") == "icloud":
            from app.integrations.icloud_calendar import approval_connector_target
            normalized["_connector_target"] = approval_connector_target(db, p)
        else:
            from app.integrations.connectors import approval_connector_target
            normalized["_connector_target"] = approval_connector_target(db, p, kind, normalized)
    a = Approval(profile_id=p.id, profile_version=p.version, kind=kind, payload=normalized, payload_hash=payload_hash(normalized), expires_at=now() + timedelta(minutes=get_settings().approval_minutes))
    db.add(a)
    db.flush()
    audit(db, p.id, "approval.proposed", {"approval_id": a.id, "kind": kind, "payload_hash": a.payload_hash})
    return a


def preview(db: Session, a: Approval):
    if a.status == "PROPOSED":
        a.status = "PREVIEWED"
        audit(db, a.profile_id, "approval.previewed", {"approval_id": a.id})
        db.flush()
    elif a.status != "PREVIEWED":
        raise HTTPException(409, f"Approval cannot be previewed in state {a.status}")
    return a


def execute(db: Session, p: Profile, a: Approval, expected_hash: str):
    if a.profile_version != p.version:
        raise HTTPException(409, "Profile changed after this preview; create and review a new preview")
    if expected_hash != a.payload_hash or payload_hash(a.payload) != expected_hash:
        raise HTTPException(409, "Preview content changed; create and review a new approval")
    if a.status != "PREVIEWED":
        raise HTTPException(409, f"Approval must be PREVIEWED and unused; current state {a.status}")
    # Compare-and-set ensures only one request can execute this approval, even concurrently.
    current_profile = select(Profile.id).where(Profile.id == a.profile_id,
        Profile.account_id == p.account_id, Profile.version == a.profile_version).exists()
    claimed = db.execute(update(Approval).where(Approval.id == a.id,
        Approval.profile_id == p.id, Approval.profile_version == a.profile_version,
        Approval.payload_hash == expected_hash, Approval.status == "PREVIEWED",
        Approval.expires_at > now(), current_profile).values(status="EXECUTING"))
    if claimed.rowcount != 1:
        raise HTTPException(409, "Approval expired or was already claimed")
    audit(db, p.id, "approval.approved", {"approval_id": a.id, "payload_hash": a.payload_hash})
    if a.kind == "profile_update":
        update_profile(db, p, ProfileUpdate.model_validate(a.payload))
        receipt = {"id": f"profile-{a.id}", "mode": "local", "message": "Profile updated", "profile_version": p.version}
    elif a.kind == "calendar":
        if a.payload.get("provider", "export") == "export":
            receipt = {"id": f"ics-{a.id}", "mode": "file_export", "message": "Calendar file ready to download and import; no remote calendar was changed", "created_at": iso(now())}
        else:
            if a.payload.get("provider") == "icloud":
                from app.integrations.icloud_calendar import execute_calendar
            else:
                from app.integrations.connectors import execute_calendar
            try:
                receipt = execute_calendar(db, a, p)
            except HTTPException as error:
                if error.status_code == 502:
                    a.status = "FAILED_UNCONFIRMED"
                    a.receipt = {"id": f"calendar-{a.id}", "mode": "provider_unconfirmed",
                        "message": "Calendar creation could not be confirmed. Check your calendar before creating a new preview."}
                    audit(db, p.id, "approval.unconfirmed", {"approval_id": a.id, "kind": a.kind})
                    db.commit()
                raise
            receipt.setdefault("id", f"calendar-{a.id}")
    elif a.kind == "email":
        from app.integrations.connectors import execute_email
        try:
            receipt = execute_email(db, a, p)
        except HTTPException as error:
            if error.status_code == 502:
                # A provider may have accepted a draft before its response was
                # lost. Persist a terminal state so retry cannot duplicate it.
                a.status = "FAILED_UNCONFIRMED"
                a.receipt = {"id": f"email-{a.id}", "mode": "provider_unconfirmed",
                             "message": "Draft creation could not be confirmed. Check your mailbox before creating a new preview."}
                audit(db, p.id, "approval.unconfirmed", {"approval_id": a.id, "kind": a.kind})
                db.commit()
            raise
        receipt.setdefault("id", f"email-{a.id}")
    else:
        raise HTTPException(422, "This action has no connected executor")
    a.status = "SUCCEEDED"
    a.receipt = receipt
    audit(db, p.id, "approval.succeeded", {"approval_id": a.id, "kind": a.kind, "receipt_id": receipt["id"]})
    db.flush()
    return a


def calendar_ics(a: Approval):
    def escape(value):
        return str(value).replace("\\", "\\\\").replace("\r", "").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")
    day = date.fromisoformat(a.payload["date"])
    minutes = int(a.payload.get("reminder_minutes", 1440))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Staytus//Planner//EN", "CALSCALE:GREGORIAN", "BEGIN:VEVENT",
        f"UID:{a.id}@staytus.local", f"DTSTAMP:{now().strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}", f"DTEND;VALUE=DATE:{(day + timedelta(days=1)).strftime('%Y%m%d')}",
        f"SUMMARY:{escape(a.payload['title'])}", f"DESCRIPTION:{escape(a.payload.get('description', 'Internal planning reminder; verify current requirements with ISSS.'))}",
        "BEGIN:VALARM", "ACTION:DISPLAY", f"TRIGGER:-PT{minutes}M", f"DESCRIPTION:{escape(a.payload['title'])}",
        "END:VALARM", "END:VEVENT", "END:VCALENDAR"]
    # RFC5545 uses octet lengths; preserve multibyte titles when folding.
    folded = []
    for line in lines:
        current = ""
        for char in line:
            if len((current + char).encode("utf-8")) > 75:
                folded.append(current)
                current = " "
            current += char
        folded.append(current)
    return "\r\n".join([*folded, ""])
