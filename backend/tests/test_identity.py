from datetime import timedelta

from sqlalchemy import func, select

from app.auth import digest, verify_password
from app.config import get_settings
from app.models import Account, Approval, AuthSession, PolicyVersion, Profile, RuleVersion, now

PASSWORD = "a-real-test-password"
PROFILE = {"school": "University of Pennsylvania", "status_type": "F-1", "nationality": "Canada",
           "program_start": "2026-08-20", "program_end": "2027-05-15", "notification_frequency": "weekly"}


def register(client, email="new-student@example.edu", **extra):
    return client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD,
                                                   "name": "New Student", **extra})


def bearer(response):
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def test_registration_onboarding_and_profile_are_real_account_owned(env):
    client, factory = env
    response = register(client, email="  New-Student@EXAMPLE.EDU  ")
    assert response.status_code == 201, response.text
    data, headers = response.json(), bearer(response)
    assert data["account"]["email"] == "new-student@example.edu"
    assert data["needs_onboarding"] is True and data["profile"] is None
    assert data["role"] == "student"
    for route in ("/profile", "/dashboard", "/approvals", "/audit", "/school", "/policies"):
        result = client.get("/api/v1" + route, headers=headers)
        assert result.status_code == 409, (route, result.text)
        assert result.json()["detail"] == "profile_required"
    assert client.get("/api/v1/auth/me", headers=headers).json()["needs_onboarding"] is True
    created = client.post("/api/v1/profile", headers=headers, json=PROFILE)
    assert created.status_code == 201, created.text
    assert created.json()["synthetic"] is False
    assert created.json()["email"] == data["account"]["email"]
    assert client.get("/api/v1/auth/me", headers=headers).json()["needs_onboarding"] is False
    assert client.post("/api/v1/profile", headers=headers, json=PROFILE).status_code == 409
    dashboard = client.get("/api/v1/dashboard", headers=headers)
    assert dashboard.status_code == 200, dashboard.text
    assert len(dashboard.json()["deadlines"]) == 2  # No invented travel date.
    assert dashboard.json()["deadlines"][0]["policy_version_id"] is None
    with factory() as db:
        account = db.get(Account, data["account"]["id"])
        assert account.password_hash != PASSWORD and verify_password(PASSWORD, account.password_hash)
        session = db.scalar(select(AuthSession).where(AuthSession.account_id == account.id))
        assert session.token_hash == digest(data["access_token"])
        assert session.token_hash != data["access_token"]
        profile = db.get(Profile, created.json()["id"])
        assert profile.account_id == account.id


def test_unique_normalized_email_and_no_self_assigned_reviewer(env):
    client, _ = env
    assert register(client).status_code == 201
    assert register(client, "NEW-STUDENT@EXAMPLE.EDU").status_code == 409
    assert register(client, "other@example.edu", role="reviewer").status_code == 422
    assert register(client, "other@example.edu", password="short").status_code == 422
    assert register(client, "not-an-email").status_code == 422
    assert register(client, "other@example.edu", name="   ").status_code == 422


def test_login_errors_rotation_and_logout(env):
    client, _ = env
    initial = register(client)
    first_headers = bearer(initial)
    wrong = client.post("/api/v1/auth/login", json={"email": "new-student@example.edu", "password": "wrong"})
    unknown = client.post("/api/v1/auth/login", json={"email": "missing@example.edu", "password": "wrong"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid email or password"}
    signed_in = client.post("/api/v1/auth/login", json={"email": "New-Student@Example.edu", "password": PASSWORD})
    assert signed_in.status_code == 200
    assert client.get("/api/v1/auth/me", headers=first_headers).status_code == 401
    headers = bearer(signed_in)
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_account_cannot_bind_another_students_profile(env):
    client, _ = env
    headers = bearer(register(client))
    assert client.post("/api/v1/profile", headers=headers, json={**PROFILE, "id": "mei-lin"}).status_code == 422
    assert client.post("/api/v1/profile", headers=headers, json={**PROFILE, "account_id": "account-mei-lin"}).status_code == 422
    created = client.post("/api/v1/profile", headers=headers, json=PROFILE).json()
    assert created["id"] != "mei-lin"
    assert client.patch("/api/v1/profile", headers=headers, json={"id": "mei-lin"}).status_code == 422
    assert client.get("/api/v1/profile", headers=headers).json()["id"] == created["id"]


def test_other_school_keeps_public_information_without_penn_workflow(env):
    client, _ = env
    headers = bearer(register(client))
    response = client.post("/api/v1/profile", headers=headers, json={**PROFILE, "school": "Another University"})
    assert response.status_code == 201
    dashboard = client.get("/api/v1/dashboard", headers=headers).json()
    assert dashboard["deadlines"] == [] and dashboard["tasks"] == []
    adapter = client.get("/api/v1/school", headers=headers).json()
    assert adapter["supported"] is False and adapter["portal_url"] is None
    assert client.get("/api/v1/policies", headers=headers).status_code == 200


def test_profile_validation_and_account_name_update(env):
    client, _ = env
    headers = bearer(register(client))
    assert client.post("/api/v1/profile", headers=headers, json={**PROFILE, "program_end": "2020-01-01"}).status_code == 422
    assert client.post("/api/v1/profile", headers=headers, json={**PROFILE, "status_type": "tourist"}).status_code == 422
    assert client.post("/api/v1/profile", headers=headers, json=PROFILE).status_code == 201
    for invalid in ({"status_type": None}, {"school": " "}, {"program_end": None}, {}):
        assert client.patch("/api/v1/profile", headers=headers, json=invalid).status_code == 422
    updated = client.patch("/api/v1/profile", headers=headers, json={"name": "New Name", "school": "upenn"})
    assert updated.status_code == 200
    assert updated.json()["school"] == "University of Pennsylvania"
    assert client.get("/api/v1/auth/me", headers=headers).json()["account"]["name"] == "New Name"


def test_expired_account_session_fails(env):
    client, factory = env
    response = register(client)
    with factory() as db:
        session = db.scalar(select(AuthSession).where(AuthSession.token_hash == digest(response.json()["access_token"])))
        session.expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/v1/auth/me", headers=bearer(response)).status_code == 401


def test_basic_login_rate_limit(env):
    client, _ = env
    settings = get_settings()
    for _ in range(settings.auth_attempt_limit):
        result = client.post("/api/v1/auth/login", json={"email": "rate-limit@example.edu", "password": "wrong"})
        assert result.status_code == 401
    result = client.post("/api/v1/auth/login", json={"email": "rate-limit@example.edu", "password": "wrong"})
    assert result.status_code == 429 and result.headers["Retry-After"]


def test_no_mock_submission_or_disconnected_email_success(env, student, monkeypatch):
    client, factory = env
    assert client.post("/api/v1/approvals", headers=student, json={"kind": "mock_submission", "payload": {}}).status_code == 422
    from fastapi import HTTPException
    from app.integrations import connectors
    def unavailable(*_):
        raise HTTPException(503, "Connect your email account first")
    monkeypatch.setattr(connectors, "execute_email", unavailable)
    result = client.post("/api/v1/approvals", headers=student, json={"kind": "email", "payload": {"to": "adviser@example.edu", "subject": "Document question", "body": "Please review my documents."}})
    item = result.json()
    url = "/api/v1/approvals/" + item["id"]
    assert client.post(url + "/preview", headers=student).status_code == 200
    assert client.post(url + "/approve", headers=student, json={"payload_hash": item["payload_hash"]}).status_code == 503
    with factory() as db:
        approval = db.get(Approval, item["id"])
        assert approval.status == "PREVIEWED" and approval.receipt is None


def test_new_database_registry_contains_no_sample_accounts_or_policies(tmp_path):
    from app.db import Base, make_engine
    from app.source_registry import sync_source_registry
    from sqlalchemy.orm import Session
    engine = make_engine(f"sqlite:///{tmp_path}/fresh.db")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        sync_source_registry(db)
        for model in (Profile, Account, PolicyVersion, RuleVersion):
            assert db.scalar(select(func.count()).select_from(model)) == 0
    engine.dispose()
