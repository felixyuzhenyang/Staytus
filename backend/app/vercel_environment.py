"""Prepare the explicitly selected serverless entrypoints before importing DB code."""
import hashlib
import os
import ssl
import tempfile
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


def prepare_environment(environ=None, *, certificate_directory=None):
    env = os.environ if environ is None else environ
    env["STAYTUS_CONFIG_DIR"] = str(Path(__file__).resolve().parents[1] / "config")
    # A request-scoped instance cannot own an always-running scheduler.
    for name in ("POLICY_WORKER_ENABLED", "NOTIFICATION_WORKER_ENABLED", "MAIL_MONITOR_WORKER_ENABLED"):
        env[name] = "false"
    pem = env.get("DATABASE_CA_PEM", "")
    bundled = Path(__file__).resolve().parents[1] / "config/database-ca.pem"
    if not pem and bundled.is_file():
        pem = bundled.read_text()
    if not pem:
        raise RuntimeError("Serverless deployment requires the configured database CA certificate")
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=pem)
        url = make_url(env.get("DATABASE_URL", ""))
        if url.drivername != "postgresql+psycopg" or url.query.get("sslmode") != "verify-full":
            raise ValueError("Invalid verified PostgreSQL configuration")
    except (ArgumentError, ValueError, ssl.SSLError):
        raise RuntimeError("Serverless database TLS configuration is invalid") from None
    directory = Path(certificate_directory or tempfile.gettempdir())
    target = directory / ("staytus-db-ca-" + hashlib.sha256(pem.encode()).hexdigest() + ".pem")
    # The certificate is public trust material, not a database credential. Atomic
    # replacement also avoids partial files during concurrent cold starts.
    if not target.is_file() or target.read_text() != pem:
        fd, temporary = tempfile.mkstemp(prefix="staytus-db-ca-", dir=directory)
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(pem)
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
    env["DATABASE_URL"] = url.update_query_dict({"sslrootcert": str(target)}).render_as_string(hide_password=False)
