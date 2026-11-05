"""Build a small, reviewable source upload without private workspace artifacts."""
import hashlib
import json
import re
import shutil
import ssl
import tempfile
from pathlib import Path

import yaml


def deployment_config(root):
    entries = yaml.safe_load((root / "config/sources.yaml").read_text())["sources"]
    crons = [{"path": "/internal/jobs/policy/" + row["id"], "schedule": f"0 {2 + index // 4} * * *"}
             for index, row in enumerate(entries) if row.get("fetch_enabled")]
    crons += [{"path": "/internal/jobs/reminders", "schedule": "0 15 * * *"},
              {"path": "/internal/jobs/mail", "schedule": "0 14 * * *"},
              {"path": "/internal/jobs/assistant", "schedule": "0 16 * * *"}]
    return {
        "$schema": "https://openapi.vercel.sh/vercel.json",
        "services": {
            "web": {"root": "frontend", "framework": "nextjs", "bindings": [
                {"type": "service", "service": "api", "format": "url", "env": "BACKEND_URL"}]},
            "api": {"root": "backend", "framework": "fastapi", "entrypoint": "app.vercel_api:app",
                "buildCommand": "python ../scripts/package_runtime_config.py",
                "functions": {"app/vercel_api.py": {"maxDuration": 300, "includeFiles": "config/**"}}},
            "gateway": {"root": "backend", "framework": "fastapi", "entrypoint": "app.vercel_gateway:app",
                "buildCommand": "python ../scripts/package_runtime_config.py",
                "functions": {"app/vercel_gateway.py": {"maxDuration": 120, "includeFiles": "config/**"}}},
        },
        "rewrites": [
            {"source": "/tools/(.*)", "destination": {"service": "gateway"}},
            {"source": "/health", "destination": {"service": "gateway"}},
            {"source": "/internal/jobs/(.*)", "destination": {"service": "api"}},
            {"source": "/(.*)", "destination": {"service": "web"}},
        ],
        "crons": crons,
    }


def prepare(root, target, *, database_ca=None):
    root, target = Path(root).resolve(), Path(target).resolve()
    if target == root or root.is_relative_to(target) or target.is_relative_to(root / "frontend"):
        raise ValueError("Use a separate staging directory")
    target.mkdir(parents=True, exist_ok=True)
    if any(target.iterdir()):
        raise ValueError("Deployment staging directory must be empty")
    files = []

    def copy(source, relative):
        if source.is_symlink():
            raise ValueError("Symlinks are not allowed in the source upload")
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        files.append({"path": str(relative), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                      "bytes": destination.stat().st_size})

    for folder in ("app", "components", "hooks", "lib", "public"):
        directory = root / "frontend" / folder
        if not directory.is_dir():
            continue
        for source in sorted(directory.rglob("*")):
            if source.is_file() and not any(part.startswith(".") for part in source.relative_to(directory).parts):
                if source.suffix not in {".ts", ".tsx", ".js", ".mjs", ".css", ".svg", ".png", ".jpg", ".ico", ".woff2"}:
                    raise ValueError("Unexpected frontend upload file")
                copy(source, source.relative_to(root))
    for name in ("package.json", "package-lock.json", "tsconfig.json", "next-env.d.ts", "next.config.ts", "postcss.config.mjs"):
        source = root / "frontend" / name
        if source.is_file():
            copy(source, source.relative_to(root))
    for source in sorted((root / "backend/app").rglob("*.py")):
        if "__pycache__" not in source.parts:
            copy(source, source.relative_to(root))
    for name in ("pyproject.toml", "uv.lock"):
        copy(root / "backend" / name, Path("backend") / name)
    for name in ("sources.yaml", "schools/penn.yaml"):
        copy(root / "config" / name, Path("config") / name)
        copy(root / "config" / name, Path("backend/config") / name)
    copy(root / "scripts/package_runtime_config.py", Path("scripts/package_runtime_config.py"))
    if database_ca is not None:
        pem = Path(database_ca).read_text()
        if "PRIVATE KEY" in pem:
            raise ValueError("Only a public database CA certificate bundle can be packaged")
        certificates = re.findall(r"-----BEGIN CERTIFICATE-----\s+.*?-----END CERTIFICATE-----", pem, re.DOTALL)
        if not certificates:
            raise ValueError("Only a public database CA certificate bundle can be packaged")
        pem = "\n".join(certificates) + "\n"
        ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).load_verify_locations(cadata=pem)
        relative = Path("backend/config/database-ca.pem")
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(pem)
        files.append({"path": str(relative), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                      "bytes": destination.stat().st_size})
    (target / "backend/.python-version").write_text("3.13\n")
    config = deployment_config(root)
    (target / "vercel.json").write_text(json.dumps(config, indent=2) + "\n")
    # The CLI receives only this explicit source tree, never the repository root.
    (target / ".vercelignore").write_text(".env\n.env.*\n**/.env\n**/.env.*\n**/*.db\n**/__pycache__\nnode_modules\n**/node_modules\n.vercel/\n")
    return {"source_files": files, "file_count": len(files), "source_bytes": sum(row["bytes"] for row in files),
            "cron_jobs": len(config["crons"]), "private_env_uploaded": False}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-ca", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    directory = root / ".local/vercel"
    directory.mkdir(parents=True, exist_ok=True)
    target = Path(tempfile.mkdtemp(prefix="source-", dir=directory))
    report = prepare(root, target, database_ca=args.database_ca)
    (directory / "source-manifest.json").write_text(json.dumps({"directory": str(target), **report}, indent=2) + "\n")
    print(json.dumps({"directory": str(target), "file_count": report["file_count"],
                      "source_bytes": report["source_bytes"], "cron_jobs": report["cron_jobs"]}))
