"""Authenticated source status and bounded refresh; no credentials or student data are returned."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import get_current_session
from app.db import get_db
from app.models import AuthSession
from app.policy_pipeline import (
    RefreshThrottled,
    optional_policy_models,
    refresh_sources,
    reserve_manual_refresh,
    source_statuses,
)

router = APIRouter(prefix="/api/v1", tags=["official sources"])


class RefreshBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str | None = Field(default=None, max_length=64)


@router.get("/sources")
def sources(session: Annotated[AuthSession, Depends(get_current_session)], db: Annotated[Session, Depends(get_db)]):
    return {"sources": source_statuses(db), "notice": "Official-page capture status; pending snapshots require review."}


@router.post("/policies/refresh")
def refresh(session: Annotated[AuthSession, Depends(get_current_session)], db: Annotated[Session, Depends(get_db)],
            body: RefreshBody | None = None):
    source_id = body.source_id if body else None
    try:
        reserve_manual_refresh(db, session.account_id, source_id)
    except RefreshThrottled as error:
        raise HTTPException(429, "Source refresh was requested recently; try again after the cooldown.",
                            headers={"Retry-After": str(error.seconds)}) from error
    except ValueError as error:
        raise HTTPException(422, "Unknown registered source") from error
    with optional_policy_models() as embedder:
        result = refresh_sources(db, source_id, embedder=embedder, manual=True, max_sources=3)
    return {**result, "sources": source_statuses(db)}
