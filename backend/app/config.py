from functools import lru_cache
from secrets import token_urlsafe

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "Staytus API"
    database_url: str = "sqlite:///./staytus-app.db"
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
    def nonempty_context_secret(cls, value):
        # A copied .env.example with an empty value must never produce an empty HMAC key.
        return value if value and value.strip() else token_urlsafe(48)


@lru_cache
def get_settings() -> Settings:
    return Settings()
