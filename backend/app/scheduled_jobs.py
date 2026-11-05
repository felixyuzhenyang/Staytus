"""Bounded daily jobs for a serverless host; no unauthenticated maintenance actions."""
import hashlib
import hmac
import logging
import os
from contextlib import contextmanager

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import text

from app.assistant_updates import run_assistant_once
from app.db import engine
from app.mail_monitor import run_mail_monitor_once
from app.notifications import run_notifications_once
from app.policy_pipeline import run_worker_once
from app.source_registry import source_entry

router = APIRouter(prefix="/internal/jobs", include_in_schema=False)
logger = logging.getLogger(__name__)


def require_scheduler(authorization):
    secret = os.environ.get("CRON_SECRET", "")
    if len(secret) < 32:
        raise HTTPException(503, "Scheduler authorization is not configured")
    if not hmac.compare_digest(authorization.encode(), ("Bearer " + secret).encode()):
        raise HTTPException(401, "Scheduler authorization required")


@contextmanager
def job_lock(name, *, database=None):
    """One connection owns a transaction lock across processes; rollback releases it."""
    database = database if database is not None else engine
    if database.dialect.name != "postgresql":
        raise HTTPException(503, "Cloud scheduled jobs require shared PostgreSQL")
    key = int.from_bytes(hashlib.sha256(("staytus-job:" + name).encode()).digest()[:8], "big", signed=True)
    with database.connect() as connection, connection.begin():
        acquired = connection.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key})
        yield bool(acquired)


def execute_job(name, operation):
    try:
        with job_lock(name) as acquired:
            if not acquired:
                return {"status": "busy", "job": name}
            result = operation()
        # Do not return mailbox metadata, profile data, tokens or raw exceptions
        # through the public cron URL or provider logs.
        logger.info("Scheduled job completed: %s", name)
        return {"status": "completed", "job": name, "ran": bool(result is not None)}
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - Public boundary must not disclose provider/database errors.
        logger.error("Scheduled job failed: %s", name)
        raise HTTPException(503, "Scheduled job could not complete; inspect private operation records") from None


@router.get("/policy/{source_id}")
def policy_job(source_id: str, authorization: str = Header(default="")):
    require_scheduler(authorization)
    try:
        source_entry(source_id)
    except ValueError:
        raise HTTPException(404, "Unknown registered source") from None
    return execute_job("policy:" + source_id, lambda: run_worker_once(source_id=source_id))


@router.get("/reminders")
def reminders_job(authorization: str = Header(default="")):
    require_scheduler(authorization)
    return execute_job("reminders", run_notifications_once)


@router.get("/mail")
def mail_job(authorization: str = Header(default="")):
    require_scheduler(authorization)
    return execute_job("mail", run_mail_monitor_once)


@router.get("/assistant")
def assistant_job(authorization: str = Header(default="")):
    require_scheduler(authorization)
    return execute_job("assistant", run_assistant_once)
