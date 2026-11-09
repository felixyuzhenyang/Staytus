"""Explicitly authorized, bounded email-content analysis with no raw-body persistence."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from cryptography.fernet import InvalidToken
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import get_current_session, require_profile_session
from app.db import get_db
from app.integrations.connection_models import MailAgentPermission, ProviderConnection
from app.integrations.connectors import (ConnectorSettings, _cipher, _connection, read_matching_message_contents,
    read_recent_messages, _provider, _relevant)
from app.integrations.watsonx import ProviderError
from app.mail_analysis_models import MailMessageAnalysis
from app.models import AuthSession, Profile, now
from app.notification_models import NotificationPreference
from app.policy_pipeline import optional_policy_models
from app.services import audit

router = APIRouter(prefix="/api/v1/connections", tags=["Private email analysis"])
RETENTION_DAYS = 90
Provider = Literal["google", "microsoft"]


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=5, ge=1, le=5)


class MailAnalysisTool(AnalysisRequest):
    provider: Literal["google", "microsoft"]


class MailActionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=500)
    due_date: date | None = None
    needs_confirmation: bool = True


class MailDate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date_text: str = Field(min_length=1, max_length=120)
    meaning: str = Field(min_length=1, max_length=400)
    exact_quote: str = Field(min_length=1, max_length=300)


class GeneratedMailSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_key: str = Field(pattern=r"^m[1-5]$")
    summary: str = Field(min_length=1, max_length=1600)
    why_relevant: str = Field(min_length=1, max_length=900)
    action_items: list[MailActionItem] = Field(default_factory=list, max_length=4)
    dates: list[MailDate] = Field(default_factory=list, max_length=5)
    questions_to_confirm: list[str] = Field(default_factory=list, max_length=3)
    needs_human_review: bool = True


class GeneratedMailBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messages: list[GeneratedMailSummary] = Field(min_length=1, max_length=5)


def _safe_generated_text(value):
    texts = [value.summary, value.why_relevant, *value.questions_to_confirm]
    texts.extend(item.text for item in value.action_items)
    texts.extend(text for item in value.dates for text in (item.date_text, item.meaning, item.exact_quote))
    joined = "\n".join(texts)
    if re.search(r"https?://|<[^>]+>|\b(?:api[_ -]?key|access[_ -]?token|session[_ -]?token|password)\b", joined, re.IGNORECASE):
        raise ValueError("Generated email analysis contains disallowed URLs, markup, or credential language")
    if re.search(r"\bStaytus\b.{0,45}\b(?:sent|filed|submitted|scheduled|completed|approved)\b", joined, re.IGNORECASE):
        raise ValueError("Generated email analysis claims an action was completed")


def _parsed_dates(value: str) -> set[date]:
    """Parse only explicit calendar dates; relative or ambiguous dates remain text."""
    month = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)")
    patterns = [
        (r"\b\d{4}-\d{1,2}-\d{1,2}\b", ("%Y-%m-%d",)),
        (r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", ("%m/%d/%Y", "%m/%d/%y")),
        (rf"\b{month}\s+\d{{1,2}}(?:st|nd|rd|th)?[,]?\s+\d{{4}}\b", ("%B %d %Y", "%b %d %Y")),
        (rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{month}\s+\d{{4}}\b", ("%d %B %Y", "%d %b %Y")),
    ]
    output = set()
    for pattern, formats in patterns:
        for match in re.finditer(pattern, value, re.IGNORECASE):
            text = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", match.group(), flags=re.IGNORECASE)
            text = text.replace(",", "")
            for format_ in formats:
                try:
                    output.add(datetime.strptime(text, format_).date())
                    break
                except ValueError:
                    continue
    return output


def validate_mail_summary(value: dict, messages: list[dict]) -> list[dict]:
    parsed = GeneratedMailBatch.model_validate(value)
    expected = {f"m{index}": message for index, message in enumerate(messages, 1)}
    if len(parsed.messages) != len(messages) or {item.message_key for item in parsed.messages} != set(expected):
        raise ValueError("The model did not return exactly one result for each message")
    output = []
    for item in parsed.messages:
        _safe_generated_text(item)
        if item.needs_human_review is not True or any(action.needs_confirmation is not True for action in item.action_items):
            raise ValueError("Email-derived guidance must remain explicitly subject to human confirmation")
        source = expected[item.message_key]
        normalized_body = re.sub(r"\s+", " ", source["content"]).casefold()
        grounded_dates = set()
        for mentioned in item.dates:
            quote = re.sub(r"\s+", " ", mentioned.exact_quote).strip().casefold()
            if len(quote) < 4 or quote not in normalized_body:
                raise ValueError("A summarized date is not grounded in an exact email quote")
            quote_dates = _parsed_dates(mentioned.exact_quote)
            label_dates = _parsed_dates(mentioned.date_text)
            if label_dates and not label_dates.intersection(quote_dates):
                raise ValueError("A summarized date label differs from its exact email quote")
            if not label_dates and mentioned.date_text.casefold() not in mentioned.exact_quote.casefold():
                raise ValueError("A non-normalized date label must appear in its exact email quote")
            grounded_dates.update(quote_dates)
        if any(action.due_date and action.due_date not in grounded_dates for action in item.action_items):
            raise ValueError("Every normalized action date must match an explicit quoted email date")
        output.append({**item.model_dump(mode="json"), "message_key": item.message_key})
    return sorted(output, key=lambda row: int(row["message_key"][1:]))


def _private_payload(row: MailMessageAnalysis) -> dict | None:
    try:
        result = json.loads(_cipher(ConnectorSettings()).decrypt(row.encrypted_result.encode()))
        if not isinstance(result, dict):
            return None
        return {"id": row.id, "provider": row.provider, "generated_at": row.generated_at.isoformat() + "Z",
            "expires_at": row.expires_at.isoformat() + "Z", "model": row.model_id, **result}
    except (ValueError, TypeError, json.JSONDecodeError, InvalidToken):
        return None


def list_analyses(db: Session, account_id: str, provider: str, *, limit=20) -> list[dict]:
    _provider(provider, ConnectorSettings())
    connection = _connection(db, account_id, provider)
    permission = db.get(MailAgentPermission, (account_id, provider))
    if connection is None or not (permission and permission.content_analysis_enabled):
        return []
    profile_version = db.scalar(select(Profile.version).where(Profile.account_id == account_id))
    if profile_version is None:
        return []
    rows = db.scalars(select(MailMessageAnalysis).where(MailMessageAnalysis.account_id == account_id,
        MailMessageAnalysis.provider == provider, MailMessageAnalysis.connection_id == connection.id,
        MailMessageAnalysis.profile_version == profile_version, MailMessageAnalysis.expires_at > now())
        .order_by(MailMessageAnalysis.generated_at.desc()).limit(limit)).all()
    return [value for row in rows if (value := _private_payload(row)) is not None]


def purge_expired_analyses(db: Session, stamp=None) -> int:
    """Physically delete expired encrypted summaries; the daily mail job calls this globally."""
    result = db.execute(delete(MailMessageAnalysis).where(MailMessageAnalysis.expires_at <= (stamp or now())))
    return result.rowcount or 0


def _profile_context(profile: Profile, language: str):
    return {"status_type": profile.status_type, "school": profile.school,
        "program_end": profile.program_end.isoformat() if profile.program_end else None,
        "graduation_date": profile.graduation_date.isoformat() if profile.graduation_date else None,
        "language": language}


def _consent_current(db, account_id, provider, connection_id, permission_stamp):
    current_connection = _connection(db, account_id, provider)
    current_permission = db.get(MailAgentPermission, (account_id, provider))
    return bool(current_connection and current_connection.id == connection_id and current_permission
        and current_permission.content_analysis_enabled
        and current_permission.content_analysis_updated_at == permission_stamp)


def _lock_current_consent(db, account_id, provider, connection_id, permission_stamp):
    """Start the final write transaction and serialize it with disable/relink operations."""
    db.rollback()
    connection = db.scalar(select(ProviderConnection).where(
        ProviderConnection.account_id == account_id, ProviderConnection.provider == provider).with_for_update())
    permission = db.scalar(select(MailAgentPermission).where(
        MailAgentPermission.account_id == account_id, MailAgentPermission.provider == provider).with_for_update())
    return bool(connection and connection.id == connection_id and permission
        and permission.content_analysis_enabled
        and permission.content_analysis_updated_at == permission_stamp)


def _message_hash(provider: str, connection_id: str, message_id: str) -> str:
    return hashlib.sha256((provider + "\0" + connection_id + "\0" + message_id).encode()).hexdigest()


def _generate(model, profile: Profile, language: str, messages: list[dict]):
    context = {"profile": _profile_context(profile, language), "messages": messages, "language": language}
    try:
        draft = model.summarize_mail(context)
    except ProviderError as error:
        # A model may wrap otherwise requested JSON in prose. The transport
        # parser handles complete embedded objects; only a remaining JSON-shape
        # failure receives one correction pass. Authentication, timeout and
        # service failures are deliberately not retried here.
        if str(error) != "Email analysis returned invalid or incomplete JSON":
            raise
        corrected = {**context, "revision_request": {
            "issue": "The previous response was not one complete JSON object. Return only the required JSON schema."}}
        return validate_mail_summary(model.summarize_mail(corrected), messages), 2
    try:
        return validate_mail_summary(draft, messages), 1
    except (ValidationError, ValueError):
        corrected = {**context, "revision_request": {
            "issue": "Return the exact required JSON schema and ground every mentioned date in an exact quote.",
            "previous_draft": draft}}
        return validate_mail_summary(model.summarize_mail(corrected), messages), 2


def _analyze_with_model(db: Session, account_id: str, profile: Profile, provider: str, *, connection_id: str,
                        permission_stamp, previews: list[dict], configured, consent_check=None) -> list[dict]:
    model_id = getattr(configured.config, "generation_model", "")
    if not model_id:
        raise HTTPException(503, "Email analysis requires the configured watsonx.ai generation model")
    stamp = now()
    selected = [item for item in previews if isinstance(item, dict) and isinstance(item.get("id"), str)
        and _relevant(item.get("from", ""), item.get("subject", ""))]
    hashes = {_message_hash(provider, connection_id, item["id"]): item for item in selected}
    cached = {}
    if hashes:
        rows = db.scalars(select(MailMessageAnalysis).where(
            MailMessageAnalysis.account_id == account_id, MailMessageAnalysis.provider == provider,
            MailMessageAnalysis.connection_id == connection_id, MailMessageAnalysis.message_hash.in_(hashes),
            MailMessageAnalysis.profile_version == profile.version, MailMessageAnalysis.model_id == model_id,
            MailMessageAnalysis.expires_at > stamp)).all()
        for row in rows:
            if value := _private_payload(row):
                cached[row.message_hash] = value
    uncached = [item for item in selected if _message_hash(provider, connection_id, item["id"]) not in cached]
    if not uncached:
        if (not _lock_current_consent(db, account_id, provider, connection_id, permission_stamp)
                or (consent_check is not None and not consent_check(db))):
            db.rollback()
            raise HTTPException(409, "Email-content permission changed; cached results were not returned")
        output = [cached[hashed] for hashed in hashes if hashed in cached]
        db.commit()
        return output
    contents = read_matching_message_contents(db, account_id, provider, previews=uncached, limit=len(uncached))["messages"]
    if not contents:
        if not cached:
            return []
        if (not _lock_current_consent(db, account_id, provider, connection_id, permission_stamp)
                or (consent_check is not None and not consent_check(db))):
            db.rollback()
            raise HTTPException(409, "Email-content permission changed; cached results were not returned")
        output = [cached[hashed] for hashed in hashes if hashed in cached]
        db.commit()
        return output
    # Persist a provider token refresh before model access; no raw content enters the transaction.
    db.commit()
    db.expire_all()
    if (not _consent_current(db, account_id, provider, connection_id, permission_stamp)
            or (consent_check is not None and not consent_check(db))):
        raise HTTPException(409, "Email-content permission changed; analysis was cancelled before model access")
    preference = db.get(NotificationPreference, account_id)
    language = preference.assistant_language if preference and preference.assistant_language in {"en", "zh"} else "en"
    try:
        generated, passes = _generate(configured, profile, language, contents)
    except (ProviderError, ValidationError, ValueError) as error:
        raise HTTPException(502, "Email analysis is temporarily unavailable; no email body was retained") from error
    if (not _lock_current_consent(db, account_id, provider, connection_id, permission_stamp)
            or (consent_check is not None and not consent_check(db))):
        db.rollback()
        raise HTTPException(409, "Email-content permission changed; analysis results were discarded")
    by_key = {row["message_key"]: row for row in generated}
    cipher, saved = _cipher(ConnectorSettings()), []
    purge_expired_analyses(db, stamp)
    for index, message in enumerate(contents, 1):
        content = by_key[f"m{index}"]
        content.pop("message_key", None)
        payload = {"subject": message["subject"], "from": message["from"],
            "received_at": message["received_at"], "analysis": content}
        hashed = _message_hash(provider, connection_id, message["id"])
        row = db.scalar(select(MailMessageAnalysis).where(MailMessageAnalysis.account_id == account_id,
            MailMessageAnalysis.provider == provider, MailMessageAnalysis.connection_id == connection_id,
            MailMessageAnalysis.message_hash == hashed))
        encrypted = cipher.encrypt(json.dumps(payload, ensure_ascii=False).encode()).decode()
        if row is None:
            row = MailMessageAnalysis(account_id=account_id, profile_id=profile.id, profile_version=profile.version,
                provider=provider, connection_id=connection_id, message_hash=hashed, encrypted_result=encrypted,
                model_id=model_id, generated_at=stamp, expires_at=stamp + timedelta(days=RETENTION_DAYS))
            db.add(row)
        else:
            row.profile_id, row.profile_version, row.encrypted_result = profile.id, profile.version, encrypted
            row.model_id, row.generated_at, row.expires_at = model_id, stamp, stamp + timedelta(days=RETENTION_DAYS)
        db.flush()
        value = {"id": row.id, "provider": provider, "generated_at": stamp.isoformat() + "Z",
            "expires_at": row.expires_at.isoformat() + "Z", "model": model_id, **payload}
        saved.append(value)
        cached[hashed] = value
    audit(db, profile.id, "mail.content_analyzed", {"provider": provider, "message_count": len(saved),
        "model": model_id, "model_passes": passes, "raw_body_retained": False})
    db.commit()
    return [cached[hashed] for hashed in hashes if hashed in cached]


def analyze_matching_messages(db: Session, account_id: str, profile: Profile, provider: str, *, limit=5,
                              previews=None, model=None, consent_check=None) -> list[dict]:
    """Read matched body text in memory, summarize, then persist only encrypted structured output."""
    _provider(provider, ConnectorSettings())
    connection = _connection(db, account_id, provider)
    permission = db.get(MailAgentPermission, (account_id, provider))
    if connection is None or not (permission and permission.content_analysis_enabled
            and permission.content_analysis_updated_at):
        raise HTTPException(403, "Enable matching email-content analysis in Connections first")
    connection_id, permission_stamp = connection.id, permission.content_analysis_updated_at
    if previews is None:
        previews = read_recent_messages(db, account_id, provider, limit=limit, inbox_only=True)["messages"]
    previews = previews[:limit]
    if not previews:
        return []
    # Persist any token refresh performed by the metadata-only read before a
    # later consent-lock transaction rolls back its own read snapshot.
    db.commit()
    db.expire_all()
    if (not _consent_current(db, account_id, provider, connection_id, permission_stamp)
            or (consent_check is not None and not consent_check(db))):
        raise HTTPException(409, "Email-content permission changed; analysis was cancelled")
    if model is not None:
        return _analyze_with_model(db, account_id, profile, provider, connection_id=connection_id,
            permission_stamp=permission_stamp, previews=previews, configured=model, consent_check=consent_check)
    with optional_policy_models() as configured:
        if not configured:
            raise HTTPException(503, "Email analysis requires the configured watsonx.ai generation model")
        return _analyze_with_model(db, account_id, profile, provider, connection_id=connection_id,
            permission_stamp=permission_stamp, previews=previews, configured=configured, consent_check=consent_check)


@router.get("/{provider}/analyses")
def analyses(provider: Provider, session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    return {"provider": provider, "analyses": list_analyses(db, session.account_id, provider),
        "raw_bodies_retained": False}


@router.post("/{provider}/analyze")
def analyze(provider: Provider, body: AnalysisRequest = AnalysisRequest(),
            session: AuthSession = Depends(require_profile_session), db: Session = Depends(get_db)):
    profile = db.get(Profile, session.profile_id)
    return {"provider": provider,
        "analyses": analyze_matching_messages(db, session.account_id, profile, provider, limit=body.limit),
        "raw_bodies_retained": False,
        "notice": "Email summaries are planning aids. Verify dates and required actions in the original mailbox and official sources."}
