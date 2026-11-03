"""Business guidance tests use isolated DB records, never live legal assertions."""
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import PolicyVersion, Profile, RuleVersion
from app.policy_models import PolicySnapshot, SourceCapture
from app.rules import adapter_for
from app.source_registry import load_sources, sync_source_registry
from app.workflow_guidance import build_workflow_guidance


TODAY = date(2026, 11, 3)


def indexed(report):
    return {workflow["id"]: workflow for workflow in report["workflows"]}


@pytest.mark.parametrize("profile_id,expected,excluded", [
    ("mei-lin", {"opt", "stem_opt", "post_completion"}, {"academic_training", "scholar_program"}),
    ("sam-rivera", {"academic_training"}, {"opt", "stem_opt", "scholar_program"}),
    ("amina-ali", {"scholar_program"}, {"opt", "stem_opt", "academic_training", "post_completion"}),
])
def test_category_routes_to_separate_business_workflows(env, profile_id, expected, excluded):
    with env[1]() as db:
        profile = db.get(Profile, profile_id)
        report = build_workflow_guidance(db, profile, today=TODAY)
        workflows = indexed(report)
        assert expected.issubset(workflows) and not excluded.intersection(workflows)
        assert {"admission_record", "program_extension", "travel_reentry"}.issubset(workflows)
        assert all(not w["eligibility_determined"] and w["legal_deadline"] is None for w in workflows.values())
        assert all(w["requires_adviser_review"] for w in workflows.values())
        assert not db.new and not db.dirty and not db.deleted


def test_missing_dates_and_training_stage_are_questions_not_inferred_from_nationality(env):
    with env[1]() as db:
        profile = db.get(Profile, "mei-lin")
        profile.travel_date = profile.travel_signature_date = profile.graduation_date = None
        profile.nationality = "United Kingdom"
        workflows = indexed(build_workflow_guidance(db, profile, today=TODAY))
        travel_fields = {q["field"] for q in workflows["travel_reentry"]["missing_information"]}
        assert {"travel_date", "travel_signature_date", "visa_passport_validity", "i94_admission_type"}.issubset(travel_fields)
        assert workflows["travel_reentry"]["applicability"] == "if_travel_planned"
        assert "graduation_date" in {q["field"] for q in workflows["post_completion"]["missing_information"]}
        assert workflows["stem_opt"]["applicability"] == "conditional_on_current_opt"


def test_other_school_uses_federal_sources_without_penn_workflow_claims(env):
    with env[1]() as db:
        profile = db.get(Profile, "sam-rivera")
        profile.school = "Another University"
        workflows = build_workflow_guidance(db, profile, today=TODAY)["workflows"]
        assert all(not source["source_id"].startswith("penn-") for w in workflows for source in w["sources"])
        assert all(w["legal_deadline"] is None for w in workflows)


def test_date_conflicts_prompt_review_without_determining_status(env):
    with env[1]() as db:
        profile = db.get(Profile, "mei-lin")
        profile.program_end = TODAY - timedelta(days=1)
        profile.travel_date = TODAY + timedelta(days=3)
        profile.graduation_date = TODAY + timedelta(days=20)
        workflows = indexed(build_workflow_guidance(db, profile, today=TODAY))
        assert workflows["travel_reentry"]["priority"] == "review_soon"
        assert "planned_departure_on_or_after_saved_program_end_requires_training_and_reentry_review" in workflows["travel_reentry"]["timing_signals"]
        assert "academic_completion_and_document_end_differ_confirm_correct_date" in workflows["post_completion"]["timing_signals"]
        assert all(not w["eligibility_determined"] and w["legal_deadline"] is None for w in workflows.values())


def test_capture_pending_review_failed_and_stale_remain_explicit(env):
    with env[1]() as db:
        sync_source_registry(db)
        profile = db.get(Profile, "mei-lin")
        version = PolicyVersion(id="actual-policy", source_id="penn-opt", title="Synthetic capture in isolated test",
            text="An unreviewed source snapshot", content_hash="a" * 64, status="detected_pending_review",
            reviewed=False, fixture=False, version=1, visa_types=["F-1"])
        db.add(version); db.flush()
        snapshot = PolicySnapshot(policy_version_id=version.id, requested_url="https://global.upenn.edu/isss/opt/",
            final_url="https://global.upenn.edu/isss/opt/", captured_at=datetime.combine(TODAY, datetime.min.time()))
        capture = SourceCapture(source_id="penn-opt", latest_version_id=version.id, http_status=200)
        db.add_all([snapshot, capture]); db.flush()
        def evidence():
            return next(s for s in indexed(build_workflow_guidance(db, profile, today=TODAY))["opt"]["sources"] if s["source_id"] == "penn-opt")
        assert evidence()["capture_state"] == "pending_review"
        assert evidence()["usable_as_current_authority"] is False
        version.reviewed = True; version.status = "current_effective"; db.flush()
        assert evidence()["usable_as_current_authority"] is True
        assert indexed(build_workflow_guidance(db, profile, today=TODAY))["opt"]["legal_deadline"] is None
        for status in ("announced_future", "proposed", "under_comment", "detected_pending_review", "postponed_or_enjoined", "superseded", "unverified_report"):
            version.status = status; db.flush()
            assert evidence()["policy_status"] == status
            assert evidence()["capture_state"] == "reviewed_noncurrent"
            assert not evidence()["usable_as_current_authority"]
        version.status = "current_effective"
        capture.last_error = "http_403"; capture.http_status = 403; db.flush()
        assert evidence()["capture_state"] == "capture_failed" and not evidence()["usable_as_current_authority"]
        capture.last_error = None
        snapshot.captured_at -= timedelta(days=10); db.flush()
        assert evidence()["capture_state"] == "stale" and not evidence()["usable_as_current_authority"]
        capture.last_success_at = datetime.combine(TODAY, datetime.min.time()); db.flush()
        assert evidence()["capture_state"] == "reviewed_current"
        assert evidence()["captured_at"] != evidence()["last_successful_check_at"]
        snapshot.captured_at = datetime.combine(TODAY + timedelta(days=1), datetime.min.time()); db.flush()
        assert evidence()["stale"] is True


def test_fixture_policy_cannot_establish_guidance_authority_or_mutate_rules(env):
    with env[1]() as db:
        sync_source_registry(db)
        before = db.scalar(select(func.count()).select_from(RuleVersion))
        profile = db.get(Profile, "mei-lin")
        report = build_workflow_guidance(db, profile, today=TODAY)
        assert all(s["policy_version_id"] != "demo-extension" for w in report["workflows"] for s in w["sources"])
        assert all(w["evidence_state"] == "verification_required" for w in report["workflows"])
        assert db.scalar(select(func.count()).select_from(RuleVersion)) == before


def test_planning_metadata_distinguishes_documents_and_does_not_change_dates(env):
    with env[1]() as db:
        f1, j1 = db.get(Profile, "mei-lin"), db.get(Profile, "sam-rivera")
        f1_rows, j1_rows = adapter_for(f1).deadlines(f1), adapter_for(j1).deadlines(j1)
        assert f1_rows[0]["date"] == (f1.program_end - timedelta(days=60)).isoformat()
        assert f1_rows[0]["document_type"] == "I-20" and j1_rows[0]["document_type"] == "DS-2019"
        assert all(row["is_planning_buffer"] and row["legal_deadline"] is None for row in f1_rows + j1_rows)


def test_topic_registry_has_bounded_official_periodic_resources():
    sources = load_sources()
    ids = {entry["id"] for entry in sources}
    assert {"penn-extension", "penn-i94", "penn-stem-opt", "penn-academic-training",
            "penn-final-rule", "uscis-opt", "uscis-stem-opt", "dos-j1-scholars"}.issubset(ids)
    assert len(ids) == len(sources)
    assert all(360 <= entry["poll_interval_minutes"] <= 1440 for entry in sources)
    assert all(entry["terms_review"] == "public_read_only_robots_required" for entry in sources)
