"""Local operator preparation only. Never upload this output or privileged keys as source."""
import json
import tempfile
from pathlib import Path
from secrets import token_urlsafe

from dotenv import dotenv_values
from prepare_vercel_deploy import prepare
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
SECRET_NAMES = {"DATABASE_URL", "CONTEXT_SECRET", "ORCHESTRATE_TOOL_KEY", "CONNECTOR_TOKEN_KEY",
                "ORCHESTRATE_API_KEY", "WATSONX_API_KEY", "GOOGLE_CLIENT_SECRET", "MICROSOFT_CLIENT_SECRET", "CRON_SECRET"}


def main():
    base = ROOT / ".local/vercel"
    base.mkdir(parents=True, exist_ok=True)
    values = dotenv_values(ROOT / "backend/.env")
    url = make_url(values["DATABASE_URL"])
    if url.username.split(".")[0] != "staytus_runtime" or url.query.get("sslmode") != "verify-full":
        raise RuntimeError("Use the existing limited, verified runtime database connection")
    target = Path(tempfile.mkdtemp(prefix="source-", dir=base))
    report = prepare(ROOT, target, database_ca=Path(url.query["sslrootcert"]))
    (target / ".vercel").mkdir()
    (target / ".vercel/project.json").write_text((ROOT / ".vercel/project.json").read_text())
    (base / "source-manifest.json").write_text(json.dumps({"directory": str(target), **report}, indent=2) + "\n")
    allowed = ["DATABASE_URL", "CONTEXT_SECRET", "ORCHESTRATE_TOOL_KEY", "CONNECTOR_TOKEN_KEY",
        "ORCHESTRATE_SERVICE_URL", "ORCHESTRATE_API_KEY", "ORCHESTRATE_AGENT_ID", "ORCHESTRATE_TIMEOUT_SECONDS",
        "WATSONX_API_KEY", "WATSONX_PROJECT_ID", "WATSONX_URL", "WATSONX_API_VERSION", "WATSONX_EMBEDDING_MODEL",
        "WATSONX_GENERATION_MODEL", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "MICROSOFT_CLIENT_ID",
        "MICROSOFT_CLIENT_SECRET", "MICROSOFT_TENANT"]
    cloud = {name: str(values[name]) for name in allowed if values.get(name)}
    previous = base / "production-values.json"
    saved = json.loads(previous.read_text()) if previous.is_file() else {}
    cloud.update(APP_ENVIRONMENT="production", CORS_ORIGINS="https://mystaytus.vercel.app",
        APP_ORIGIN="https://mystaytus.vercel.app", FRONTEND_URL="https://mystaytus.vercel.app",
        OAUTH_CALLBACK_BASE="https://mystaytus.vercel.app/api/backend", ORCHESTRATE_CONTEXT_VERIFIED="false",
        POLICY_WORKER_ENABLED="false", NOTIFICATION_WORKER_ENABLED="false", MAIL_MONITOR_WORKER_ENABLED="false",
        NOTIFICATION_EMAIL_ENABLED="false", CRON_SECRET=saved.get("CRON_SECRET") or token_urlsafe(48))
    cloud["DATABASE_URL"] = url.update_query_dict({"sslrootcert": "/tmp/staytus-database-ca.pem"}).render_as_string(hide_password=False)
    for name in ("CONTEXT_SECRET", "ORCHESTRATE_TOOL_KEY", "CONNECTOR_TOKEN_KEY", "ORCHESTRATE_API_KEY", "WATSONX_API_KEY"):
        if not cloud.get(name):
            raise RuntimeError("A required existing runtime credential is missing")
    for path in target.rglob("*"):
        if path.is_file() and path.suffix not in {".png", ".jpg", ".ico", ".woff2"}:
            content = path.read_text(errors="ignore")
            if any(cloud.get(name) and len(cloud[name]) >= 16 and cloud[name] in content for name in SECRET_NAMES):
                raise RuntimeError("A runtime secret was detected in the source upload; preparation refused")
    previous.write_text(json.dumps(cloud))
    previous.chmod(0o600)
    review = {"project": "staytus", "domain": "mystaytus.vercel.app",
        "secret_variable_names": sorted(SECRET_NAMES.intersection(cloud)),
        "nonsecret_variable_names": sorted(set(cloud) - SECRET_NAMES), "source_files": report["file_count"],
        "source_bytes": report["source_bytes"], "daily_jobs": report["cron_jobs"],
        "authoring_key_uploaded": False, "database_owner_uploaded": False, "private_artifacts_in_source": False,
        "context_gate_enabled": False}
    (base / "deployment-review.json").write_text(json.dumps(review, indent=2) + "\n")
    print(json.dumps(review, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001 - Credential-safe operator boundary.
        raise SystemExit(f"Deployment preparation failed ({type(error).__name__}); no credentials were printed") from None
