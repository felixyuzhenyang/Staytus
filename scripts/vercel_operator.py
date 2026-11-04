"""Explicit local release commands. Keep values on stdin and operator reports private."""
import argparse
import json
import os
import re
import subprocess
from pathlib import Path

from prepare_vercel_settings import SECRET_NAMES

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".local/vercel"
CLI = ROOT / ".local/vercel-cli/node_modules/.bin/vercel"
SCOPE = "felixyuzhenyangs-projects"


def private_report(name, value):
    path = STATE / name
    path.write_text(json.dumps(value, indent=2) + "\n")
    path.chmod(0o600)


def redact(message, values):
    from sqlalchemy.engine import make_url
    secrets = [values[name] for name in SECRET_NAMES if values.get(name)]
    if values.get("DATABASE_URL"):
        secrets.append(make_url(values["DATABASE_URL"]).password or "")
    for value in sorted(secrets, key=len, reverse=True):
        if value:
            message = message.replace(value, "[redacted]")
    return message


def upload_environment(values):
    completed = []
    for name, value in values.items():
        result = subprocess.run([str(CLI), "env", "add", name, "--environment", "production", "--project", "staytus",
            "--scope", SCOPE, "--yes", "--force", "--sensitive" if name in SECRET_NAMES else "--no-sensitive"],
            cwd=ROOT, input=value, text=True, capture_output=True, timeout=60, check=False)
        completed.append({"name": name, "secret": name in SECRET_NAMES, "saved": result.returncode == 0})
        private_report("environment-upload-status.json", completed)
        if result.returncode:
            private_report("environment-upload-error.json", {"name": name, "message": redact(result.stdout + result.stderr, values)})
            raise RuntimeError("Environment upload failed; inspect the redacted private report")
        print(json.dumps({"saved": name, "secret": name in SECRET_NAMES}), flush=True)


def deploy(values):
    manifest = json.loads((STATE / "source-manifest.json").read_text())
    stage = Path(manifest["directory"]).resolve()
    if not stage.is_relative_to(STATE) or not (stage / "vercel.json").is_file():
        raise ValueError("Only the prepared allowlisted source directory can be deployed")
    stdout, stderr = STATE / "deploy.stdout.log", STATE / "deploy.stderr.log"
    with stdout.open("w") as out, stderr.open("w") as err:
        stdout.chmod(0o600)
        stderr.chmod(0o600)
        process = subprocess.Popen([str(CLI), "deploy", "--prod", "--yes", "--scope", SCOPE],
            cwd=stage, stdout=out, stderr=err)
        private_report("deploy-process.json", {"pid": process.pid, "source_directory": str(stage)})
        status = process.wait(timeout=900)
    report = {"exit_code": status, "urls": list(dict.fromkeys(re.findall(r"https://[a-zA-Z0-9.-]+\.vercel\.app", stdout.read_text() + stderr.read_text())))}
    private_report("deploy-result.json", report)
    if status:
        private_report("deploy-error.json", {"message": redact(stdout.read_text() + stderr.read_text(), values)})
        raise RuntimeError("Deployment failed; inspect the redacted private report")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["upload-env", "deploy"])
    parser.add_argument("--confirm-production-release", action="store_true")
    args = parser.parse_args()
    if not args.confirm_production_release:
        raise SystemExit("Explicit release confirmation is required")
    os.umask(0o077)
    try:
        values = json.loads((STATE / "production-values.json").read_text())
        from dotenv import dotenv_values
        local = dotenv_values(ROOT / "backend/.env")
        for name in ("NOTIFICATION_SMTP_USERNAME", "NOTIFICATION_SMTP_PASSWORD", "NOTIFICATION_BREVO_API_KEY"):
            if local.get(name):
                values[name] = local[name]
        if args.action == "upload-env":
            upload_environment(values)
        else:
            deploy(values)
    except Exception as error:  # noqa: BLE001 - Credential-safe operator boundary.
        raise SystemExit(f"Vercel operation failed ({type(error).__name__}); no credentials were printed") from None
