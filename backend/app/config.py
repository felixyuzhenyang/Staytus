from functools import lru_cache
from secrets import token_urlsafe
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    app_environment: Literal["development", "testing", "staging", "production"] = "development"
    database_url: str = "sqlite:///./staytus-app.db"

    @model_validator(mode="after")
    def shared_database_requirements(self):
        if self.app_environment in {"staging", "production"}:
            url = make_url(self.database_url)
            if url.drivername != "postgresql+psycopg" or url.query.get("sslmode") != "verify-full":
                raise ValueError("Shared environments require PostgreSQL/Psycopg 3 with sslmode=verify-full")
        return self


class Settings(DatabaseSettings):
    app_name: str = "Staytus API"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    tool_key: str = Field(default="", validation_alias="ORCHESTRATE_TOOL_KEY")
    context_secret: str = Field(default_factory=lambda: token_urlsafe(48))
    session_hours: int = 8
    approval_minutes: int = 15
    watsonx_url: str = ""
    watsonx_api_key: str = ""
    watsonx_project_id: str = ""
    # Select IDs only after catalog discovery and an explicit project inference probe.
    watsonx_embedding_model: str = ""
    watsonx_generation_model: str = ""
    watsonx_api_version: str = "2024-05-31"
    auth_attempt_limit: int = 12
    auth_attempt_window_seconds: int = 600
    policy_worker_enabled: bool = True

    @field_validator("context_secret", mode="before")
    @classmethod
    def nonempty_context_secret(cls, value, info: ValidationInfo):
        # A copied .env.example with an empty value must never produce an empty HMAC key.
        if (not value or not value.strip()) and info.data.get("app_environment") in {"staging", "production"}:
            raise ValueError("Shared environments require an explicit signing secret")
        return value if value and value.strip() else token_urlsafe(48)

    @model_validator(mode="after")
    def shared_environment_requirements(self):
        if self.app_environment not in {"staging", "production"}:
            return self
        if "context_secret" not in self.model_fields_set or len(self.context_secret) < 32 or len(self.tool_key) < 32:
            raise ValueError("Shared environments require explicit independent signing and tool secrets")
        if self.context_secret == self.tool_key:
            raise ValueError("Signing and tool secrets must be independent")
        for origin in self.cors_origins.split(","):
            parsed = urlsplit(origin.strip())
            if parsed.scheme != "https" or not parsed.hostname or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username:
                raise ValueError("Shared environments require explicit HTTPS CORS origins")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
