"""Application accounts, opaque sessions and user-bound agent capabilities."""
import base64
import binascii
import hashlib
import hmac
import json
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta

from fastapi import Depends, Header, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Account, AuthSession, Profile, now

_attempts: dict[str, deque] = defaultdict(deque)
_attempt_lock = threading.Lock()


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_email(value: str) -> str:
    email = value.strip().casefold()
    if len(email) > 320 or email.count("@") != 1 or any(c.isspace() for c in email):
        raise HTTPException(422, "Enter a valid email address")
    local, domain = email.split("@")
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise HTTPException(422, "Enter a valid email address")
    return email


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    result = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${result.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if algorithm != "scrypt" or (n, r, p) != ("16384", "8", "1"):
            return False
        result = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(result.hex(), expected)
    except (ValueError, TypeError):
        return False


_DUMMY_PASSWORD = hash_password("not-a-real-account-password")


def check_auth_rate_limit(ip: str, email: str):
    """Small single-process limiter. Shared deployments need a distributed store."""
    settings = get_settings()
    stamp = time.monotonic()
    key = digest(f"{ip}\n{email}")
    with _attempt_lock:
        if len(_attempts) > 10000:
            for old_key in list(_attempts):
                if not _attempts[old_key] or _attempts[old_key][-1] < stamp - settings.auth_attempt_window_seconds:
                    del _attempts[old_key]
        bucket = _attempts[key]
        while bucket and bucket[0] < stamp - settings.auth_attempt_window_seconds:
            bucket.popleft()
        if len(bucket) >= settings.auth_attempt_limit:
            raise HTTPException(429, "Too many sign-in attempts; try again later", headers={"Retry-After": str(settings.auth_attempt_window_seconds)})
        bucket.append(stamp)


def clear_auth_rate_limits():
    """Test fixture support; never exposed as an application endpoint."""
    with _attempt_lock:
        _attempts.clear()


def create_session(db: Session, account: Account, profile_id: str | None = None):
    db.execute(delete(AuthSession).where(AuthSession.account_id == account.id))
    token = secrets.token_urlsafe(40)
    session = AuthSession(token_hash=digest(token), account_id=account.id, profile_id=profile_id,
                          role=account.role, expires_at=now() + timedelta(hours=get_settings().session_hours))
    db.add(session)
    db.flush()
    return token, session


def _validate_session(db: Session, session: AuthSession | None) -> AuthSession:
    if session is None or session.expires_at <= now():
        raise HTTPException(401, "Session expired or invalid")
    account = db.get(Account, session.account_id)
    if account is None:
        raise HTTPException(401, "Session expired or invalid")
    if session.profile_id:
        profile = db.get(Profile, session.profile_id)
        if profile is None or profile.account_id != account.id:
            raise HTTPException(401, "Session expired or invalid")
    session.role = account.role
    return session


def get_current_session(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> AuthSession:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in to continue")
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == digest(authorization[7:])))
    return _validate_session(db, session)


def require_profile_session(session: AuthSession = Depends(get_current_session)) -> AuthSession:
    if not session.profile_id:
        raise HTTPException(409, "profile_required")
    return session


def require_reviewer(session: AuthSession = Depends(require_profile_session)) -> AuthSession:
    if session.role != "reviewer":
        raise HTTPException(403, "A reviewer account is required")
    return session


def mint_tool_context(session: AuthSession, ttl: int = 300) -> str:
    if not session.profile_id:
        raise HTTPException(409, "profile_required")
    payload = base64.urlsafe_b64encode(json.dumps({"sid": session.id, "exp": int(time.time()) + ttl}, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(get_settings().context_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def get_tool_session(x_tool_key: str = Header(default=""), x_staytus_context: str = Header(default=""), db: Session = Depends(get_db)) -> AuthSession:
    configured_key = get_settings().tool_key
    if not configured_key or not hmac.compare_digest(configured_key, x_tool_key):
        raise HTTPException(401, "Tool service authentication failed")
    try:
        payload, sig = x_staytus_context.split(".", 1)
        expected = hmac.new(get_settings().context_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            raise ValueError("signature")
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if data["exp"] <= time.time():
            raise ValueError("expired")
        session = _validate_session(db, db.get(AuthSession, data["sid"]))
        if not session.profile_id:
            raise ValueError("profile")
        return session
    except (ValueError, KeyError, TypeError, binascii.Error, UnicodeError, HTTPException):
        raise HTTPException(401, "Tool requires a valid server-issued user context")
