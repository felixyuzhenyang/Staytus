"""Project-local loopback PostgreSQL. No system service, cloud resource or public port."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / ".local" / "postgres"
BIN = ROOT / ".local" / "postgres-runtime" / "embedded_postgres" / "pginstall" / "bin"
DATA = PRIVATE / "data"
PORT = 55432
SOCKET = Path("/private/tmp" if sys.platform == "darwin" else "/tmp") / ("staytus-pg-" + hashlib.sha256(str(ROOT).encode()).hexdigest()[:12])
sys.path.insert(0, str(ROOT / "backend"))


def private_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(content)
    path.chmod(0o600)


def state():
    return json.loads((PRIVATE / "credentials.json").read_text())


def run(binary, args, *, extra_env=None):
    result = subprocess.run([str(BIN / binary), *map(str, args)], capture_output=True, text=True,
                            env={**os.environ, **(extra_env or {})}, timeout=120)
    if result.returncode:
        raise RuntimeError(f"{binary} failed (exit {result.returncode}); inspect the private database log")
    return result


def connection(database="postgres", *, runtime=False):
    import psycopg
    saved = state()
    return psycopg.connect(host="127.0.0.1", port=PORT, dbname=database,
                           user="staytus_runtime" if runtime else "staytus_owner",
                           password=saved["runtime_password" if runtime else "owner_password"],
                           autocommit=True, connect_timeout=5)


def url(database, *, runtime=False):
    from sqlalchemy.engine import URL
    saved = state()
    return URL.create("postgresql+psycopg", username="staytus_runtime" if runtime else "staytus_owner",
                      password=saved["runtime_password" if runtime else "owner_password"],
                      host="127.0.0.1", port=PORT, database=database).render_as_string(hide_password=False)


def start():
    if not (BIN / "postgres").is_file():
        raise RuntimeError("Install the optional local runtime described in docs/DATABASE_AND_CONTAINERS.md first")
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    PRIVATE.chmod(0o700)
    SOCKET.mkdir(parents=True, exist_ok=True, mode=0o700)
    SOCKET.chmod(0o700)
    if not (PRIVATE / "credentials.json").exists():
        if (DATA / "PG_VERSION").exists():
            raise RuntimeError("Existing cluster has no matching private credentials; refusing to replace it")
        private_write(PRIVATE / "credentials.json", json.dumps({"owner_password": secrets.token_urlsafe(36),
                                                                "runtime_password": secrets.token_urlsafe(36)}))
    if not (DATA / "PG_VERSION").exists():
        pwfile = PRIVATE / "init-password"
        private_write(pwfile, state()["owner_password"] + "\n")
        try:
            run("initdb", ["-D", DATA, "--username=staytus_owner", "--pwfile", pwfile,
                           "--auth-local=trust", "--auth-host=scram-sha-256", "--encoding=UTF8", "--locale=C"])
        finally:
            pwfile.unlink(missing_ok=True)
        with (DATA / "postgresql.conf").open("a") as stream:
            stream.write(f"\nlisten_addresses = '127.0.0.1'\nport = {PORT}\nunix_socket_directories = '{SOCKET}'\n"
                         "log_statement = 'none'\nlog_min_error_statement = 'panic'\n"
                         "log_parameter_max_length_on_error = 0\nlog_error_verbosity = 'terse'\n")
    status = subprocess.run([str(BIN / "pg_ctl"), "-D", str(DATA), "status"], capture_output=True)
    if status.returncode:
        run("pg_ctl", ["-D", DATA, "-l", PRIVATE / "server.log", "-w", "start"])
    from psycopg import sql
    with connection() as conn:
        # Existing roles are never reset behind a user's back.
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='staytus_runtime'").fetchone():
            conn.execute(sql.SQL("CREATE ROLE staytus_runtime LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE").format(
                sql.Literal(state()["runtime_password"])))
        for name in ("staytus", "staytus_test"):
            if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
                conn.execute(sql.SQL("CREATE DATABASE {} OWNER staytus_owner").format(sql.Identifier(name)))
    for name, database, runtime in (("admin.env", "staytus", False), ("runtime.env", "staytus", True),
                                    ("test.env", "staytus_test", False)):
        private_write(PRIVATE / name, f"DATABASE_URL={url(database, runtime=runtime)}\n")
    print(json.dumps({"running": True, "host": "127.0.0.1", "port": PORT,
                      "system_service_installed": False, "public_listener": False}))


def grant_runtime():
    from app.database_migrations import grant_runtime_access
    from app.db import make_engine
    engine = make_engine(url("staytus"))
    try:
        grant_runtime_access(engine, "staytus_runtime")
    finally:
        engine.dispose()
    print(json.dumps({"runtime_data_access": True, "runtime_schema_create": False, "runtime_migration_write": False}))


def backup():
    folder = ROOT / ".local" / "backups"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder.chmod(0o700)
    path = folder / ("staytus-pg-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6] + ".dump")
    # Create mode before pg_dump writes any private data.
    private_write(path, "")
    run("pg_dump", ["-h", "127.0.0.1", "-p", PORT, "-U", "staytus_owner", "-d", "staytus", "-Fc", "-f", path],
        extra_env={"PGPASSWORD": state()["owner_password"]})
    print(json.dumps({"backup": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "mode": "0600"}))
    return path


def restore_check(path):
    from psycopg import sql
    path = path.resolve(strict=True)
    name = "staytus_restore_" + uuid4().hex[:12]
    with connection() as conn:
        conn.execute(sql.SQL("CREATE DATABASE {} OWNER staytus_owner").format(sql.Identifier(name)))
    try:
        run("pg_restore", ["--exit-on-error", "--no-owner", "--no-privileges", "-h", "127.0.0.1", "-p", PORT,
                           "-U", "staytus_owner", "-d", name, path], extra_env={"PGPASSWORD": state()["owner_password"]})
        from app.db import make_engine
        from app.database_migrations import require_current_schema
        from app.schema import metadata
        from sqlalchemy import select
        engines = [make_engine(url("staytus")), make_engine(url(name))]
        try:
            require_current_schema(engines[1])
            with engines[0].connect() as source, engines[1].connect() as restored:
                counts = {}
                for table in metadata().sorted_tables:
                    statement = select(table).order_by(*table.primary_key.columns)
                    original_rows = list(source.execute(statement).mappings())
                    restored_rows = list(restored.execute(statement).mappings())
                    from app.database_transfer import _same_value
                    if len(original_rows) != len(restored_rows) or any(
                        not _same_value(key, a[key], b[key]) for a, b in zip(original_rows, restored_rows) for key in a
                    ):
                        raise RuntimeError("Restored rows failed verification")
                    counts[table.name] = len(original_rows)
            report = {"restored": True, "values_verified": True, "tables": counts, "temporary_database_removed": True}
        finally:
            for engine in engines:
                engine.dispose()
    finally:
        with connection() as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
    private_write(PRIVATE / "restore-verification.json", json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["start", "stop", "status", "grant-runtime", "backup", "restore-check"])
    parser.add_argument("--backup", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "start":
            start()
        elif args.command == "grant-runtime":
            grant_runtime()
        elif args.command == "backup":
            backup()
        elif args.command == "restore-check":
            restore_check(args.backup or backup())
        elif args.command == "stop":
            run("pg_ctl", ["-D", DATA, "-m", "fast", "-w", "stop"])
            print('{"running":false}')
        else:
            with connection("staytus", runtime=True) as conn:
                conn.execute("SELECT 1")
            print('{"running":true,"runtime_authenticated":true,"public_listener":false}')
        return 0
    except Exception as error:
        print(f"Local PostgreSQL operation failed ({type(error).__name__}); no credentials were logged.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
