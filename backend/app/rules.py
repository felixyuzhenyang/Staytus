"""Deterministic planning preferences; these offsets do not encode immigration law."""
from abc import ABC, abstractmethod
from datetime import timedelta
from hashlib import sha256
import json

from app.models import Profile, RuleVersion


class SchoolAdapter(ABC):
    @abstractmethod
    def metadata(self) -> dict: ...

    @abstractmethod
    def deadlines(self, profile: Profile, rule: RuleVersion | None = None) -> list[dict]: ...


class PennAdapter(SchoolAdapter):
    def configuration(self):
        from app.source_registry import load_school
        return load_school("penn")

    def metadata(self):
        config = self.configuration()
        return {
            "id": "penn", "school": config["name"], "supported": True,
            "office": config["office"], "url": config["office_url"],
            "portal_url": config["portal_url"], "portal_integration": "unavailable",
            "contact": "Find your assigned adviser through Penn ISSS / iPenn",
            "supported_statuses": config["supported_categories"],
            "documents": ["Review I-20 or DS-2019 program dates", "Confirm academic or program reason with adviser", "Check Penn's current workflow in iPenn"],
            "verification": "Official directory links; adviser-specific data requires authorized access",
        }

    def deadlines(self, profile: Profile, rule: RuleVersion | None = None):
        config = self.configuration()
        defaults = config["planning_defaults"]
        preparation_days = rule.preparation_days if rule else defaults["program_extension_prepare_days"]
        review_days = defaults["document_review_days"]
        travel_days = defaults["travel_prepare_days"]
        rule_id = rule.id if rule else "planning-" + sha256(json.dumps(defaults, sort_keys=True).encode()).hexdigest()[:16]
        source = {"title": "Penn ISSS (official reference; planning offsets are Staytus preferences)",
                  "url": config["office_url"], "verified_at": None}
        items = [
            ("program_extension", "Begin program-extension planning", profile.program_end - timedelta(days=preparation_days),
             [f"Profile document end: {profile.program_end.isoformat()}", f"Internal preparation buffer: {preparation_days} calendar days", "Reminder = document end minus internal buffer. This is not a filing deadline."]),
            ("document_review", "Review program documents with ISSS", profile.program_end - timedelta(days=review_days),
             [f"Profile document end: {profile.program_end.isoformat()}", f"Internal document-check reminder: {review_days} calendar days before program end", "No legal status or eligibility determination is made."]),
        ]
        if profile.travel_date:
            items.append(("travel_review", "Review travel documents with ISSS", profile.travel_date - timedelta(days=travel_days),
                          [f"Planned travel: {profile.travel_date.isoformat()}", f"Internal travel preparation buffer: {travel_days} calendar days", "Travel-signature validity depends on status and circumstances; consult ISSS."]))
        return [{"id": f"{profile.id}-{workflow}", "workflow": workflow, "title": title, "date": day.isoformat(),
                 "recommended_start": day.isoformat(), "rule_version": rule_id, "profile_version": profile.version,
                 "policy_version_id": rule.policy_version_id if rule else None, "trace": trace, "source": source,
                 "is_planning_buffer": True, "document_end": profile.program_end.isoformat()}
                for workflow, title, day, trace in items]


class PublicPolicyAdapter(SchoolAdapter):
    """Unknown schools retain public federal knowledge without invented school workflows."""
    def __init__(self, school: str):
        self.school = school

    def metadata(self):
        return {"id": "public-only", "school": self.school, "supported": False,
                "office": "Contact your university's international office", "url": "https://studyinthestates.dhs.gov/",
                "portal_url": None, "portal_integration": "unavailable", "contact": "No school-specific adviser directory is connected",
                "supported_statuses": ["F-1", "J-1 student", "J-1 scholar"], "documents": [],
                "verification": "Public federal information only; no school-specific deadlines or portal automation"}

    def deadlines(self, profile: Profile, rule: RuleVersion | None = None):
        return []


def adapter_for(profile: Profile) -> SchoolAdapter:
    return PennAdapter() if profile.school == "University of Pennsylvania" else PublicPolicyAdapter(profile.school)
