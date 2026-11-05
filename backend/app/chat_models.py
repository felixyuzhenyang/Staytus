"""Account-owned conversations; provider thread IDs never come from the browser."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import now, uid


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    thread_id: Mapped[str | None] = mapped_column(String, nullable=True)
    history: Mapped[list] = mapped_column(JSON, default=list)
    hide_assistant_updates: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    busy_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

