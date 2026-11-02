"""Narrow server-to-server tool gateway for an explicitly authorized HTTPS edge.

Start the main API once to initialize/migrate the database before this process.
This app exposes no login, profile API, OAuth callback, approval execution, docs,
schema or scheduler routes. It reuses the signed-context tool gateway only.
"""
from contextlib import asynccontextmanager
import hmac
from uuid import uuid4

from fastapi import FastAPI, Request
from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import get_settings
from app.services import request_correlation
from app.tools import router as tool_router


class GatewaySecrets(BaseSettings):
    """Explicit configuration, deliberately without the app's random fallback."""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    tool_key: str = Field(default="", validation_alias="ORCHESTRATE_TOOL_KEY", repr=False)
    context_secret: str = Field(default="", validation_alias="CONTEXT_SECRET", repr=False)

    @field_validator("tool_key", "context_secret")
    @classmethod
    def strong_explicit_secret(cls, value):
        if len(value) < 32 or any(char.isspace() or not 33 <= ord(char) <= 126 for char in value):
            raise ValueError("A strong explicitly configured secret is required")
        return value

    @model_validator(mode="after")
    def independent_secrets(self):
        if hmac.compare_digest(self.tool_key, self.context_secret):
            raise ValueError("Use independent service and signing secrets")
        return self


def read_explicit_gateway_secrets():
    return GatewaySecrets()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        explicit = read_explicit_gateway_secrets()
    except ValidationError:
        raise RuntimeError("Tool gateway startup requires independent, explicitly configured ORCHESTRATE_TOOL_KEY and CONTEXT_SECRET of at least 32 characters") from None
    effective = get_settings()
    if not (hmac.compare_digest(explicit.tool_key, effective.tool_key)
            and hmac.compare_digest(explicit.context_secret, effective.context_secret)):
        raise RuntimeError("Tool gateway and main application settings must use the same explicit secrets; restart with the shared server configuration")
    # Deliberately no schema bootstrap, database migration, background worker,
    # user-session creation, provider request or public-network binding here.
    yield


app = FastAPI(title="Staytus tool gateway", version="0.1.0", lifespan=lifespan,
    docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def request_context(request: Request, call_next):
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
    return {"status": "ok", "service": "staytus-tool-gateway", "version": "0.1.0"}


app.include_router(tool_router)
