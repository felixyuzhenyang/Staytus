"""Real local account registration and account-owned profile onboarding."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import services as svc
from app.auth import (_DUMMY_PASSWORD, check_auth_rate_limit, create_session, get_current_session,
                      hash_password, normalize_email, verify_password)
from app.db import get_db
from app.models import Account, AuthSession, Profile, uid
from app.schemas import LoginInput, ProfileCreate, RegisterInput

router = APIRouter(prefix="/api/v1", tags=["accounts"])


def account_json(account: Account):
    return {"id": account.id, "email": account.email, "name": account.name}


def session_response(db: Session, account: Account, token: str | None = None):
    profile = db.scalar(select(Profile).where(Profile.account_id == account.id))
    result = {"account": account_json(account), "profile": svc.profile_json(profile) if profile else None,
              "needs_onboarding": profile is None, "role": account.role}
    if token:
        result["access_token"] = token
    return result


@router.post("/auth/register", status_code=201)
def register(body: RegisterInput, request: Request, db: Session = Depends(get_db)):
    email = normalize_email(body.email)
    check_auth_rate_limit(request.client.host if request.client else "unknown", email)
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Name is required")
    if db.scalar(select(Account.id).where(Account.email == email)):
        raise HTTPException(409, "An account cannot be created with these details; try signing in")
    account = Account(email=email, name=name, password_hash=hash_password(body.password), role="student")
    db.add(account)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account cannot be created with these details; try signing in")
    token, _ = create_session(db, account)
    return session_response(db, account, token)


@router.post("/auth/login")
def login(body: LoginInput, request: Request, db: Session = Depends(get_db)):
    email = normalize_email(body.email)
    check_auth_rate_limit(request.client.host if request.client else "unknown", email)
    account = db.scalar(select(Account).where(Account.email == email))
    valid = verify_password(body.password, account.password_hash if account else _DUMMY_PASSWORD)
    if account is None or not valid:
        raise HTTPException(401, "Invalid email or password")
    profile = db.scalar(select(Profile).where(Profile.account_id == account.id))
    token, _ = create_session(db, account, profile.id if profile else None)
    return session_response(db, account, token)


@router.get("/auth/me")
def me(session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    return session_response(db, db.get(Account, session.account_id))


@router.post("/profile", status_code=201)
def create_profile(body: ProfileCreate, session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    if db.scalar(select(Profile.id).where(Profile.account_id == session.account_id)):
        raise HTTPException(409, "Profile already exists; edit your existing profile")
    account = db.get(Account, session.account_id)
    data = body.model_dump()
    from app.profile_details import normalize_details
    data["planning_details"] = normalize_details(data["planning_details"], body.status_type, body.travel_date)
    data["school"] = body.school.strip()
    if not data["school"]:
        raise HTTPException(422, "School is required")
    if data["school"].casefold() in ("penn", "upenn", "university of pennsylvania"):
        data["school"] = "University of Pennsylvania"
    profile = Profile(id=uid(), account_id=account.id, name=account.name, email=account.email,
                      synthetic=False, **data)
    db.add(profile)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Profile already exists; edit your existing profile")
    db.execute(update(AuthSession).where(AuthSession.account_id == account.id).values(profile_id=profile.id))
    session.profile_id = profile.id
    svc.audit(db, profile.id, "profile.created", {"school": profile.school, "status_type": profile.status_type})
    return svc.profile_json(profile)
