from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.profile_details import PlanningDetails, normalize_details


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterInput(StrictModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=256)
    name: str = Field(min_length=1, max_length=100)


class LoginInput(StrictModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class ProfileCreate(StrictModel):
    school: str = Field(default="University of Pennsylvania", min_length=1, max_length=100)
    status_type: Literal["F-1", "J-1 student", "J-1 scholar"]
    nationality: str = Field(default="Not supplied", min_length=1, max_length=64)
    program_start: date
    program_end: date
    graduation_date: date | None = None
    travel_date: date | None = None
    travel_signature_date: date | None = None
    notification_frequency: Literal["daily", "weekly", "monthly", "off"] = "weekly"
    planning_details: PlanningDetails = Field(default_factory=PlanningDetails)

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.program_start >= self.program_end:
            raise ValueError("Program end must be later than program start")
        normalize_details(self.planning_details.model_dump(mode="json"), self.status_type, self.travel_date)
        return self


class ProfileUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    school: str | None = Field(default=None, min_length=1, max_length=100)
    status_type: Literal["F-1", "J-1 student", "J-1 scholar"] | None = None
    nationality: str | None = Field(default=None, min_length=1, max_length=64)
    program_start: date | None = None
    program_end: date | None = None
    graduation_date: date | None = None
    travel_date: date | None = None
    travel_signature_date: date | None = None
    notification_frequency: Literal["daily", "weekly", "monthly", "off"] | None = None
    planning_details: PlanningDetails | None = None


class ApprovalInput(StrictModel):
    kind: Literal["calendar", "email", "profile_update"]
    payload: dict = Field(default_factory=dict)


class ApprovalConfirm(StrictModel):
    payload_hash: str = Field(min_length=64, max_length=64)


class ChatInput(StrictModel):
    message: str = Field(min_length=1, max_length=4000)


class EmptyTool(StrictModel):
    pass


class SearchTool(StrictModel):
    query: str = Field(default="", max_length=1000)
    include_pending: bool = False


class DeadlineTool(StrictModel):
    workflow: Literal["program_extension", "travel_review", "document_review", "opt_preparation", "ead_review", "academic_training_review"] = "program_extension"


class PolicyTool(StrictModel):
    policy_version_id: str


class EscalationTool(StrictModel):
    reason: str = Field(default="Review this question with an ISSS adviser", max_length=1000)


class PreviewTool(StrictModel):
    payload: dict


class CalendarPayload(StrictModel):
    title: str = Field(min_length=1, max_length=160)
    date: date
    description: str = Field(default="", max_length=3000)
    provider: Literal["export", "google", "microsoft", "icloud"] = "export"
    reminder_minutes: int = Field(default=1440, ge=0, le=40320)


class EmailPayload(StrictModel):
    to: str = Field(default="Review adviser address before sending", max_length=320)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)


