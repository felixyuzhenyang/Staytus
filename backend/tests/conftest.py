import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db import Base, get_db
from database_support import isolated_engine
from app.main import app
from app.auth import clear_auth_rate_limits
from app.models import Account
from support import FIXTURE_PASSWORD, seed_fixtures


@pytest.fixture
def env(tmp_path, request):
    engine = isolated_engine(tmp_path, "test", request)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        seed_fixtures(db)

    def dependency():
        with factory() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    app.dependency_overrides[get_db] = dependency
    settings = get_settings()
    original = settings.tool_key
    model_fields = ("watsonx_url", "watsonx_api_key", "watsonx_project_id", "watsonx_embedding_model", "watsonx_generation_model")
    original_models = {name: getattr(settings, name) for name in model_fields}
    for name in model_fields:
        setattr(settings, name, "")
    settings.tool_key = "test-tool-key"
    clear_auth_rate_limits()
    client = TestClient(app)
    client.fixture_factory = factory
    yield client, factory
    settings.tool_key = original
    for name, value in original_models.items():
        setattr(settings, name, value)
    app.dependency_overrides.clear()
    engine.dispose()


def login(client, profile="mei-lin", reviewer=False):
    if reviewer:
        # Trusted test setup, never an end-user privilege-setting parameter.
        with client.fixture_factory() as db:
            db.get(Account, "account-" + profile).role = "reviewer"
            db.commit()
    response = client.post("/api/v1/auth/login", json={"email": profile + "@example.invalid", "password": FIXTURE_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


@pytest.fixture
def student(env):
    return login(env[0])


@pytest.fixture
def reviewer(env):
    return login(env[0], reviewer=True)
