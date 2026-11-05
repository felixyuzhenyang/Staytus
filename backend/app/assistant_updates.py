"""Event-driven, text-only LLM messages with durable claims and account isolation."""
import hashlib
import json
import re
from datetime import UTC, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.assistant_update_models import AssistantUpdate, AssistantUpdateEvent
from app.auth import require_profile_session
from app.db import SessionLocal, get_db
from app.guided_planning import plan_text_issues
from app.models import AuthSession, PolicySource, PolicyVersion, Profile, now, uid
from app.notification_models import NotificationPreference, ReminderNotice
from app.notifications import preferences_for, sync_profile_reminders
from app.services import audit, deadlines, iso, profile_json

router = APIRouter(prefix="/api/v1/assistant-updates", tags=["Proactive assistant"])


def enabled(pref, profile):
    return bool(pref and pref.assistant_enabled and pref.in_app_enabled and profile.notification_frequency != "off")


def event_data(notice):
    # Explicit projection prevents mailbox data or arbitrary notice payloads
    # from entering background model requests.
    allowed = ("workflow", "target_date", "stage", "source_id", "policy_version_id", "previous_version_id", "review_status")
    return {"id": notice.id, "kind": notice.kind, "title": notice.title,
        "created_at": iso(notice.created_at), "data": {key: notice.data[key] for key in allowed if key in notice.data}}


def fingerprint(events):
    return hashlib.sha256(json.dumps(events, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def queue_updates(db, *, stamp, account_id=None):
    count = 0
    query = select(Profile).where(Profile.account_id.is_not(None)).order_by(Profile.id).limit(1000)
    if account_id:
        query = query.where(Profile.account_id == account_id)
    for profile in db.scalars(query):
        pref = preferences_for(db, profile.account_id)
        if not enabled(pref, profile):
            continue
        sync_profile_reminders(db, profile, pref, stamp)
        local_day = stamp.replace(tzinfo=UTC).astimezone(ZoneInfo(pref.timezone)).date().isoformat()
        batch_key = f"{local_day}:{profile.version}"
        if db.scalar(select(AssistantUpdate.id).where(AssistantUpdate.account_id == profile.account_id, AssistantUpdate.batch_key == batch_key)):
            continue
        reserved = select(AssistantUpdateEvent.notice_id).where(AssistantUpdateEvent.profile_version == profile.version)
        notices = list(db.scalars(select(ReminderNotice).where(ReminderNotice.account_id == profile.account_id,
            ReminderNotice.profile_id == profile.id, ReminderNotice.kind.in_(("planning", "policy_update")),
            ReminderNotice.superseded_at.is_(None), ReminderNotice.created_at >= stamp - timedelta(days=7),
            ReminderNotice.created_at <= stamp, ReminderNotice.id.not_in(reserved))
            .order_by(ReminderNotice.created_at, ReminderNotice.id).limit(5)))
        if not notices:
            continue
        try:
            with db.begin_nested():
                row = AssistantUpdate(account_id=profile.account_id, profile_id=profile.id, profile_version=profile.version,
                    batch_key=batch_key, events=[event_data(notice) for notice in notices], language=pref.assistant_language,
                    created_at=stamp, next_attempt_at=stamp)
                db.add(row)
                db.flush()
                db.add_all(AssistantUpdateEvent(notice_id=notice.id, profile_version=profile.version, update_id=row.id) for notice in notices)
                db.flush()
            count += 1
        except IntegrityError:
            continue  # Another worker reserved this event/batch.
    return count


def inputs_current(db, row):
    profile = db.get(Profile, row.profile_id)
    pref = db.get(NotificationPreference, row.account_id)
    if not profile or profile.account_id != row.account_id or profile.version != row.profile_version or not enabled(pref, profile) or pref.assistant_language != row.language:
        return False
    notices = [db.get(ReminderNotice, event["id"]) for event in row.events]
    if any(not notice or notice.account_id != row.account_id or notice.profile_id != row.profile_id
           or notice.superseded_at is not None for notice in notices):
        return False
    if fingerprint([event_data(notice) for notice in notices]) != fingerprint(row.events):
        return False
    for event in row.events:
        if event["kind"] == "policy_update":
            version = db.get(PolicyVersion, event["data"].get("policy_version_id"))
            if not version or version.fixture or profile.status_type not in version.visa_types:
                return False
            latest = db.scalar(select(PolicyVersion.id).where(PolicyVersion.source_id == version.source_id,
                PolicyVersion.fixture.is_(False)).order_by(PolicyVersion.version.desc()).limit(1))
            if latest != version.id:
                return False
    return True


def generation_context(db, row):
    from app.retrieval import retrieve_for_profile
    profile = db.get(Profile, row.profile_id)
    pref = db.get(NotificationPreference, row.account_id)
    query = " ".join(event["title"] + " " + event["data"].get("workflow", "") for event in row.events)
    results = retrieve_for_profile(db, profile, query, include_pending=True, limit=3)
    evidence = [{"title": item["title"], "status": item["status"], "review_required": item.get("review_required", True),
        "excerpt": item.get("text", "")[:1800]} for item in results]
    citations = [{key: item.get(key) for key in ("title", "source_url", "status", "captured_at", "version")} for item in results]
    for event in row.events:
        if event["kind"] != "policy_update":
            continue
        data = event["data"]
        version = db.get(PolicyVersion, data.get("policy_version_id"))
        previous = db.get(PolicyVersion, data.get("previous_version_id"))
        source = db.get(PolicySource, version.source_id)
        if previous and previous.source_id != version.source_id:
            previous = None
        evidence.append({"title": version.title, "status": version.status,
            "review_required": not version.reviewed, "previous_excerpt": previous.text[:2000] if previous else None,
            "current_excerpt": version.text[:2000], "notice": "Detected text change; personal legal impact is unverified."})
        citations.append({"title": version.title, "source_url": source.url, "status": version.status, "version": version.version})
    # No account IDs, addresses, identifying document numbers or mailbox content.
    facts = profile_json(profile)
    facts = {key: value for key, value in facts.items() if key not in {"id", "name", "email", "synthetic"}}
    facts["program_document"] = "I-20" if profile.status_type == "F-1" else "DS-2019"
    triggered = {event["data"].get("workflow") for event in row.events if event["kind"] == "planning"}
    targets = [{"workflow": target["workflow"], "date": target["date"],
        "origin": "Staytus internal preparation preference; NOT a meeting, appointment or school deadline"}
        for target in deadlines(db, profile) if target["workflow"] in triggered]
    events = []
    for event in row.events:
        clean = {key: value for key, value in event.items() if key not in {"id", "title"}}
        if event["kind"] == "planning":
            clean["meaning"] = "An internal preparation reminder became due or is approaching; no appointment exists."
        else:
            clean["meaning"] = "An official source's captured text changed; legal/personal impact remains unverified."
        events.append(clean)
    return {"language": row.language, "profile": facts, "timezone": pref.timezone,
        "local_today": now().replace(tzinfo=UTC).astimezone(ZoneInfo(pref.timezone)).date().isoformat(),
        "events": events,
        "preparation_targets": targets, "official_evidence": evidence}, citations


class GeneratedUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=1800)
    why_it_matters: str = Field(min_length=1, max_length=1800)
    next_steps: list[str] = Field(min_length=1, max_length=4)
    questions: list[str] = Field(default_factory=list, max_length=3)


def validate_generated(value, context):
    # Only these text fields can be published. Extra provider metadata cannot
    # add actions, URLs or authorization to the result.
    result = GeneratedUpdate.model_validate({key: value[key] for key in GeneratedUpdate.model_fields if key in value}).model_dump()
    guard_context = {"profile": context["profile"], "guided_plan": {"calendar_targets": context["preparation_targets"]}}
    omitted = False
    for field in ("next_steps", "questions"):
        original = result[field]
        result[field] = [item for item in original if not plan_text_issues(item, guard_context)]
        omitted = omitted or len(original) != len(result[field])
    if not result["next_steps"]:
        raise ValueError("No grounded next step remained in the model draft")
    parts = [result["title"], result["summary"], result["why_it_matters"], *result["next_steps"], *result["questions"]]
    if any(not text.strip() or len(text) > 1800 for text in parts):
        raise ValueError("Unbounded text")
    text = "\n".join(parts)
    if context.get("language") == "zh" and len(re.findall(r"[\u3400-\u9fff]", text)) < 20:
        raise ValueError("Requested Chinese response was not produced")
    if re.search(r"已(?:计划|安排|预约).{0,40}(?:审查|审核|会面|见面|预约)", text):
        raise ValueError("No personal appointment or review has been planned")
    if re.search(r"\b(?:your|the|an|ISSS) (?:[\w-]+ ){0,5}(?:review|meeting|appointment|session) (?:is |was |has been )?(?:scheduled|booked)\b|\b(?:attend|join)\b.{0,35}\b(?:session|review|appointment|meeting)\b|已安排.{0,12}(?:面谈|会议|预约|审查)|参加.{0,12}(?:审查活动|审核会)", text, re.IGNORECASE):
        raise ValueError("Preparation target is not a booked event")
    if re.search(r"https?://|<[^>]+>", text):
        raise ValueError("Generated URLs/HTML are not accepted")
    issues = plan_text_issues(text, guard_context)
    if issues:
        raise ValueError(" ".join(issues))
    return {**result, "omitted_unverified_details": omitted}


def run_assistant_once(factory=SessionLocal, *, provider=None, stamp=None, account_id=None, max_messages=3):
    """A small persisted batch; leases/reservations work across processes."""
    from app.policy_pipeline import optional_policy_models
    stamp = stamp or now()
    result = {"queued": 0, "generated": 0, "failed": 0, "stale": 0}
    with factory() as db:
        result["queued"] = queue_updates(db, stamp=stamp, account_id=account_id)
        expired = update(AssistantUpdate).where(AssistantUpdate.state == "GENERATING",
            AssistantUpdate.claimed_at < stamp - timedelta(minutes=10))
        db.execute(expired.where(AssistantUpdate.attempts < 3).values(state="QUEUED", lease_token=None))
        db.execute(expired.where(AssistantUpdate.attempts >= 3).values(state="FAILED", lease_token=None, error_code="lease_expired"))
        db.commit()
    with optional_policy_models() as configured:
        model = provider or configured
        if not model or not getattr(model.config, "generation_model", ""):
            return {**result, "model_configured": False}
        for _ in range(max(0, min(max_messages, 3))):
            with factory() as db:
                query = select(AssistantUpdate).where(AssistantUpdate.state == "QUEUED",
                    AssistantUpdate.attempts < 3, AssistantUpdate.next_attempt_at <= stamp).order_by(AssistantUpdate.created_at).limit(1)
                if account_id:
                    query = query.where(AssistantUpdate.account_id == account_id)
                row = db.scalar(query)
                if not row:
                    break
                identity, token = row.id, uid()
                claimed = db.execute(update(AssistantUpdate).where(AssistantUpdate.id == identity, AssistantUpdate.state == "QUEUED",
                    AssistantUpdate.attempts == row.attempts).values(state="GENERATING", lease_token=token,
                    claimed_at=stamp, attempts=AssistantUpdate.attempts + 1))
                db.commit()
                if claimed.rowcount != 1:
                    continue
                db.expire_all()
                row = db.get(AssistantUpdate, identity)
                if not inputs_current(db, row):
                    row.state, row.lease_token = "STALE", None
                    db.commit()
                    result["stale"] += 1
                    continue
                context, citations = generation_context(db, row)
            try:
                draft = model.generate_assistant_update(context)
                passes = 1
                try:
                    content = validate_generated(draft, context)
                except ValueError as error:
                    # One bounded content correction, not a provider/network retry.
                    # The correction stays in memory; invalid drafts never become messages.
                    from pydantic import ValidationError
                    issue = "The JSON fields or lengths do not match the required schema." if isinstance(error, ValidationError) else str(error)
                    corrected = {**context, "revision_request": {"issue": issue, "previous_draft": draft}}
                    passes = 2
                    content = validate_generated(model.generate_assistant_update(corrected), context)
                failure = False
            except Exception:  # noqa: BLE001 - Persist only safe failure codes, never model/profile/provider text.
                content, failure = None, True
            with factory() as db:
                row = db.get(AssistantUpdate, identity)
                if not row or row.state != "GENERATING" or row.lease_token != token:
                    continue
                values = {"lease_token": None}
                if not inputs_current(db, row):
                    values["state"] = "STALE"
                    outcome = "stale"
                elif failure:
                    values.update(state="FAILED" if row.attempts >= 3 else "QUEUED",
                        error_code="generation_unavailable_or_invalid", next_attempt_at=stamp + timedelta(hours=6))
                    outcome = "failed"
                else:
                    values.update(state="READY", content=content, citations=citations,
                        model_id=model.config.generation_model, generated_at=now(), error_code=None)
                    outcome = "generated"
                saved = db.execute(update(AssistantUpdate).where(AssistantUpdate.id == identity,
                    AssistantUpdate.state == "GENERATING", AssistantUpdate.lease_token == token).values(**values))
                if saved.rowcount == 1 and outcome == "generated":
                    audit(db, row.profile_id, "assistant.proactive_generated", {"update_id": row.id,
                        "event_count": len(row.events), "profile_version": row.profile_version,
                        "model": model.config.generation_model, "model_passes": passes})
                if saved.rowcount == 1:
                    result[outcome] += 1
                db.commit()
    return result


def list_updates(db, session, *, limit=20):
    rows = db.scalars(select(AssistantUpdate).where(AssistantUpdate.account_id == session.account_id,
        AssistantUpdate.profile_id == session.profile_id, AssistantUpdate.state == "READY")
        .order_by(AssistantUpdate.generated_at.desc(), AssistantUpdate.id.desc()).limit(limit)).all()
    return [{"id": row.id, "content": row.content, "citations": row.citations, "created_at": iso(row.generated_at),
        "read_at": iso(row.read_at), "profile_version": row.profile_version, "outdated": not inputs_current(db, row),
        "trigger_kinds": sorted({event["kind"] for event in row.events}), "generated_by": "watsonx.ai",
        "model": row.model_id} for row in reversed(rows)]


@router.get("")
def get_updates(session: AuthSession = Depends(require_profile_session), db=Depends(get_db)):
    return {"updates": list_updates(db, session)}


class AssistantPreferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    language: str = Field(default="en", pattern=r"^(en|zh)$")


@router.get("/preferences")
def get_preferences(session: AuthSession = Depends(require_profile_session), db=Depends(get_db)):
    pref = preferences_for(db, session.account_id)
    return {"enabled": pref.assistant_enabled, "language": pref.assistant_language,
        "active": enabled(pref, db.get(Profile, session.profile_id)), "schedule": "daily_batch"}


@router.post("/check")
def check_updates(session: AuthSession = Depends(require_profile_session), db=Depends(get_db)):
    factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    account_id = session.account_id
    db.commit()
    result = run_assistant_once(factory, account_id=account_id, max_messages=1)
    return result


@router.patch("/preferences")
def set_preferences(body: AssistantPreferenceInput, session: AuthSession = Depends(require_profile_session), db=Depends(get_db)):
    pref = preferences_for(db, session.account_id)
    pref.assistant_enabled, pref.assistant_language = body.enabled, body.language
    if not body.enabled:
        db.execute(update(AssistantUpdate).where(AssistantUpdate.account_id == session.account_id,
            AssistantUpdate.state.in_(("QUEUED", "GENERATING"))).values(state="STALE", lease_token=None))
    audit(db, session.profile_id, "assistant.preferences_updated", body.model_dump())
    return {"enabled": pref.assistant_enabled, "language": pref.assistant_language,
        "active": enabled(pref, db.get(Profile, session.profile_id)), "schedule": "daily_batch"}


@router.post("/{update_id}/read")
def mark_read(update_id: str, session: AuthSession = Depends(require_profile_session), db=Depends(get_db)):
    row = db.scalar(select(AssistantUpdate).where(AssistantUpdate.id == update_id,
        AssistantUpdate.account_id == session.account_id, AssistantUpdate.profile_id == session.profile_id, AssistantUpdate.state == "READY"))
    if row is None:
        raise HTTPException(404, "Assistant update not found")
    if row.read_at is None:
        row.read_at = now()
    return {"id": row.id, "read_at": iso(row.read_at)}
