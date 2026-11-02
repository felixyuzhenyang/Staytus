from contextlib import asynccontextmanager
from threading import Event, Thread
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import router as api_router
from app.config import get_settings
from app.db import Base, SessionLocal, engine, get_db
from app import policy_models, chat_models, notification_models  # noqa: F401 - Register tables before create_all.
from app.integrations import connection_models  # noqa: F401 - Register OAuth tables.
from app.identity import router as identity_router
from app.chat import router as chat_router
from app.policy_routes import router as policy_router
from app.source_registry import sync_source_registry
from app.policy_pipeline import run_worker
from app.tools import router as tool_router
from app.integrations.connectors import router as connector_router
from app.services import request_correlation
from app.notifications import router as notification_router, run_notifications_worker, NotificationSettings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # An injected database owns its setup/worker lifecycle. In particular, a
    # TestClient with a synthetic get_db override must never touch the operator
    # database, crawl real sources or start an outbound email worker.
    owns_database = get_db not in app.dependency_overrides
    if owns_database:
        if engine.dialect.name == "postgresql":
            with engine.begin() as connection:
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            sync_source_registry(db)
            db.commit()
    stop = Event()
    worker = None
    reminder_worker = None
    if owns_database and get_settings().policy_worker_enabled:
        worker = Thread(target=run_worker, args=(stop,), name="staytus-policy-worker", daemon=True)
        worker.start()
    if owns_database and NotificationSettings().notification_worker_enabled:
        reminder_worker = Thread(target=run_notifications_worker, args=(stop,), name="staytus-reminder-worker", daemon=True)
        reminder_worker.start()
    try:
        yield
    finally:
        stop.set()
        if worker:
            worker.join(timeout=2)
        if reminder_worker:
            reminder_worker.join(timeout=2)


app = FastAPI(title="Staytus API", version="0.2.0", description="Account-owned international-student planning and policy tools for IBM Orchestrate", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins.split(","), allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type", "X-Request-ID"], expose_headers=["X-Request-ID"])


@app.middleware("http")
async def request_context(request: Request, call_next):
    # Client values are not trusted as identity or authorization.
    request.state.correlation_id = str(uuid4())
    correlation_token = request_correlation.set(request.state.correlation_id)
    try:
        response = await call_next(request)
    finally:
        request_correlation.reset(correlation_token)
    response.headers["X-Request-ID"] = request.state.correlation_id
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/health")
def health():
    return {"status": "ok", "service": "staytus-api", "version": "0.2.0"}


app.include_router(api_router)
app.include_router(identity_router)
app.include_router(chat_router)
app.include_router(policy_router)
app.include_router(tool_router)
app.include_router(connector_router)
app.include_router(notification_router)
