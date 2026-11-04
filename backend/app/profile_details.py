"""Typed, optional business facts. Unknown is never treated as no or approved."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PlanningDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    f1_activity: Literal["unknown", "studying", "post_completion_opt", "stem_opt", "other"] = "unknown"
    opt_stage: Literal["unknown", "not_planning", "considering", "preparing", "submitted", "approved", "active", "completed", "denied", "withdrawn"] = "unknown"
    opt_type: Literal["unknown", "pre_completion", "post_completion", "stem_extension"] = "unknown"
    academic_completion_date: date | None = None
    dso_recommendation_date: date | None = None
    opt_submitted_date: date | None = None
    opt_requested_start: date | None = None
    ead_start: date | None = None
    ead_end: date | None = None
    training_history_reviewed: bool | None = None
    stem_eligibility_reviewed: bool | None = None
    post_completion_plan: Literal["unknown", "undecided", "opt", "stem_opt", "transfer", "new_program", "departure", "other"] = "unknown"

    i94_admission_type: Literal["unknown", "duration_of_status", "dated"] = "unknown"
    i94_admit_until_date: date | None = None
    passport_expiry: date | None = None
    visa_expiry: date | None = None
    return_date: date | None = None
    travel_destination: str | None = Field(default=None, min_length=1, max_length=80)
    visa_renewal_planned: bool | None = None

    extension_stage: Literal["unknown", "not_needed", "considering", "preparing", "submitted", "completed"] = "unknown"
    extension_requested_end: date | None = None

    j1_category: Literal["unknown", "student", "research_scholar", "professor", "short_term_scholar", "other"] = "unknown"
    sponsor_name: str | None = Field(default=None, min_length=1, max_length=120)
    host_department: str | None = Field(default=None, min_length=1, max_length=120)
    academic_training_stage: Literal["unknown", "not_planning", "considering", "preparing", "submitted", "authorized", "active", "completed"] = "unknown"
    academic_training_start: date | None = None
    academic_training_end: date | None = None
    sponsor_authorized_on: date | None = None

    @model_validator(mode="after")
    def consistent_records(self):
        for start, end, label in ((self.ead_start, self.ead_end, "EAD"),
                                  (self.academic_training_start, self.academic_training_end, "Academic Training")):
            if start and end and end < start:
                raise ValueError(f"{label} end must not precede its start")
        if self.i94_admit_until_date and "i94_admission_type" in self.model_fields_set and self.i94_admission_type != "dated":
            raise ValueError("An Admit Until Date requires the dated I-94 option")
        if self.dso_recommendation_date and self.opt_submitted_date and self.opt_submitted_date < self.dso_recommendation_date:
            raise ValueError("OPT submission cannot precede the saved recommendation for that application")
        for name in ("travel_destination", "sponsor_name", "host_department"):
            value = getattr(self, name)
            if value is not None:
                if not value.strip():
                    raise ValueError(f"{name} cannot be blank")
                setattr(self, name, value.strip())
        return self


F1_FIELDS = {"f1_activity", "opt_stage", "opt_type", "dso_recommendation_date", "opt_submitted_date",
             "opt_requested_start", "ead_start", "ead_end", "training_history_reviewed", "stem_eligibility_reviewed"}
J1_FIELDS = {"j1_category", "sponsor_name", "host_department", "academic_training_stage",
             "academic_training_start", "academic_training_end", "sponsor_authorized_on"}
AT_FIELDS = {"academic_training_stage", "academic_training_start", "academic_training_end", "sponsor_authorized_on"}


def normalize_details(values, status_type: str, travel_date: date | None, *, category_changed=False) -> dict:
    values = dict(values or {})
    forbidden = set(J1_FIELDS if status_type == "F-1" else F1_FIELDS)
    if status_type == "J-1 scholar":
        forbidden |= AT_FIELDS
    if category_changed:
        values = {key: value for key, value in values.items() if key not in forbidden}
        if status_type == "J-1 scholar" and values.get("j1_category") == "student":
            values.pop("j1_category")
        if status_type == "J-1 student":
            values.pop("j1_category", None)
        if status_type != "F-1" and values.get("post_completion_plan") in {"opt", "stem_opt"}:
            values.pop("post_completion_plan")
    details = PlanningDetails.model_validate(values)
    if details.i94_admit_until_date and details.i94_admission_type != "dated":
        raise ValueError("An Admit Until Date requires the dated I-94 option")
    compact = details.model_dump(mode="json", exclude_defaults=True)
    if forbidden.intersection(compact):
        raise ValueError("Some planning details do not apply to the selected category")
    if status_type == "J-1 student" and details.j1_category not in {"unknown", "student"}:
        raise ValueError("A J-1 student profile cannot use a scholar category")
    if status_type == "J-1 scholar" and details.j1_category == "student":
        raise ValueError("Choose a scholar category for a J-1 scholar profile")
    if status_type != "F-1" and details.post_completion_plan in {"opt", "stem_opt"}:
        raise ValueError("OPT planning applies to an F-1 profile; J-1 training is a separate workflow")
    if details.return_date and travel_date and details.return_date < travel_date:
        raise ValueError("Return date must not precede departure")
    return compact


def details_for(profile) -> PlanningDetails:
    return PlanningDetails.model_validate(getattr(profile, "planning_details", None) or {})
