"""Deployment-specific auth, lifecycle and packaging boundaries, using synthetic data."""
import importlib.util
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from app import scheduled_jobs as jobs
from app.vercel_environment import prepare_environment


def certificate():
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic test CA")])
    stamp = datetime.now(UTC)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(stamp - timedelta(days=1))
            .not_valid_after(stamp + timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
            .sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def test_serverless_disables_threads_and_preserves_verified_database_tls(tmp_path):
    env = {"DATABASE_CA_PEM": certificate(),
           "DATABASE_URL": "postgresql+psycopg://synthetic:only-test@db.invalid/db?sslmode=verify-full&sslrootcert=/old/local.pem",
           "POLICY_WORKER_ENABLED": "true", "NOTIFICATION_WORKER_ENABLED": "true", "MAIL_MONITOR_WORKER_ENABLED": "true"}
    prepare_environment(env, certificate_directory=tmp_path)
    url = make_url(env["DATABASE_URL"])
    assert url.password == "only-test" and url.query["sslmode"] == "verify-full"
    assert Path(url.query["sslrootcert"]).read_text() == env["DATABASE_CA_PEM"]
    assert all(env[name] == "false" for name in ("POLICY_WORKER_ENABLED", "NOTIFICATION_WORKER_ENABLED", "MAIL_MONITOR_WORKER_ENABLED"))
    prepare_environment(env, certificate_directory=tmp_path)
    assert len(list(tmp_path.iterdir())) == 1


def test_serverless_uses_packaged_public_ca_without_operator_local_path(tmp_path, monkeypatch):
    from app import vercel_environment
    backend = tmp_path / "backend"
    (backend / "config").mkdir(parents=True)
    pem = certificate()
    (backend / "config/database-ca.pem").write_text(pem)
    monkeypatch.setattr(vercel_environment, "__file__", str(backend / "app/vercel_environment.py"))
    temporary = tmp_path / "runtime-tmp"
    temporary.mkdir()
    env = {"DATABASE_URL": "postgresql+psycopg://u:synthetic@db.invalid/db?sslmode=verify-full"}
    prepare_environment(env, certificate_directory=temporary)
    assert Path(make_url(env["DATABASE_URL"]).query["sslrootcert"]).read_text() == pem
    assert env["STAYTUS_CONFIG_DIR"] == str(backend / "config")


@pytest.mark.parametrize("url", ["not-a-url", "sqlite:///wrong.db", "postgresql+psycopg://u:only-test@db.invalid/db?sslmode=require"])
def test_serverless_rejects_unverified_database_without_disclosing_credentials(tmp_path, url):
    with pytest.raises(RuntimeError) as failure:
        prepare_environment({"DATABASE_CA_PEM": certificate(), "DATABASE_URL": url}, certificate_directory=tmp_path)
    assert "only-test" not in str(failure.value)
    assert not list(tmp_path.iterdir())


def test_scheduler_needs_independent_secret_before_any_action(monkeypatch):
    app = FastAPI()
    app.include_router(jobs.router)
    monkeypatch.delenv("CRON_SECRET", raising=False)
    monkeypatch.setattr(jobs, "execute_job", lambda *args: pytest.fail("Unauthorized job ran"))
    with TestClient(app) as client:
        assert client.get("/internal/jobs/reminders").status_code == 503
        monkeypatch.setenv("CRON_SECRET", "x" * 48)
        assert client.get("/internal/jobs/reminders").status_code == 401
        assert client.get("/internal/jobs/mail", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.post("/internal/jobs/reminders", headers={"Authorization": "Bearer " + "x" * 48}).status_code == 405


def test_scheduler_deduplicates_and_redacts_results_and_failures(monkeypatch):
    calls = []

    @contextmanager
    def busy(name):
        yield False

    @contextmanager
    def acquired(name):
        yield True

    monkeypatch.setattr(jobs, "job_lock", busy)
    assert jobs.execute_job("mail", lambda: calls.append(1))["status"] == "busy"
    assert not calls
    monkeypatch.setattr(jobs, "job_lock", acquired)
    assert "private-mail" not in str(jobs.execute_job("mail", lambda: {"body": "private-mail"}))
    with pytest.raises(jobs.HTTPException) as failure:
        jobs.execute_job("mail", lambda: (_ for _ in ()).throw(ValueError("private-credential")))
    assert "private-credential" not in str(failure.value.detail)


def test_unknown_source_cannot_become_an_arbitrary_fetch(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "x" * 48)
    monkeypatch.setattr(jobs, "execute_job", lambda *args: pytest.fail("Unknown source ran"))
    app = FastAPI()
    app.include_router(jobs.router)
    with TestClient(app) as client:
        result = client.get("/internal/jobs/policy/not-registered", headers={"Authorization": "Bearer " + "x" * 48})
        assert result.status_code == 404


def test_source_upload_excludes_private_env_and_artifacts(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts/prepare_vercel_deploy.py"
    spec = importlib.util.spec_from_file_location("prepare_vercel_deploy", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root, target = tmp_path / "repository", tmp_path / "upload"
    fixtures = {"frontend/app/page.tsx": "export default function Page(){return null}",
        "frontend/app/.env": "PRIVATE=sensitive-marker", "frontend/.env": "PRIVATE=sensitive-marker",
        "frontend/package.json": "{}", "backend/app/main.py": "app = None", "backend/.env": "PRIVATE=sensitive-marker",
        "backend/pyproject.toml": "[project]\nname='test'\n", "backend/uv.lock": "version = 1\n",
        "config/sources.yaml": "sources:\n  - id: official-test\n    fetch_enabled: true\n",
        "config/schools/penn.yaml": "id: penn\n", "scripts/package_runtime_config.py": "pass\n",
        "bob_sessions/private.txt": "sensitive-marker", ".local/private.db": "sensitive-marker"}
    for relative, content in fixtures.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    report = module.prepare(root, target)
    assert report["cron_jobs"] == 3
    assert not any("sensitive-marker" in path.read_text() for path in target.rglob("*") if path.is_file())
    config = module.deployment_config(root)
    assert config["services"]["web"]["bindings"][0]["env"] == "BACKEND_URL"
    assert config["rewrites"][0] == {"source": "/tools/(.*)", "destination": {"service": "gateway"}}
    assert not any(row["source"] == "/api/v1/(.*)" for row in config["rewrites"])
    with pytest.raises(ValueError, match="empty"):
        module.prepare(root, target)


@pytest.mark.skipif(not __import__("os").environ.get("STAYTUS_TEST_DATABASE_URL"), reason="Dedicated PostgreSQL required")
def test_scheduled_lock_is_shared_across_independent_connections(tmp_path, request):
    from database_support import isolated_engine
    database = isolated_engine(tmp_path, "scheduler-lock", request)
    with jobs.job_lock("synthetic-job", database=database) as first:
        assert first
        with jobs.job_lock("synthetic-job", database=database) as second:
            assert not second
    with jobs.job_lock("synthetic-job", database=database) as next_attempt:
        assert next_attempt
