"""Synthetic accounts and dates; no live legal or eligibility assertions."""
from datetime import date, datetime

import pytest
from sqlalchemy import select, text

from app.business_planning import PLANNING_RULE_VERSION
from app.models import Profile
from app.profile_details import normalize_details
from app.rules import adapter_for
from app.workflow_guidance import build_workflow_guidance

TODAY = date(2026, 11, 3)


def workflows(db, profile):
    return {w["id"]: w for w in build_workflow_guidance(db, profile, today=TODAY)["workflows"]}


def test_first_use_profile_persists_typed_optional_details(env):
    client, _ = env
    registration = client.post("/api/v1/auth/register", json={"email": "planning-onboarding@example.invalid", "name": "Synthetic planning", "password": "synthetic-planning-password"})
    assert registration.status_code == 201, registration.text
    headers = {"Authorization": "Bearer " + registration.json()["access_token"]}
    response = client.post("/api/v1/profile", headers=headers, json={"status_type": "F-1", "program_start": "2026-08-01", "program_end": "2027-05-01",
        "planning_details": {"opt_stage": "preparing", "opt_type": "post_completion", "academic_completion_date": "2027-05-01"}})
    assert response.status_code == 201, response.text
    assert response.json()["planning_details"]["academic_completion_date"] == "2027-05-01"
    dashboard = client.get("/api/v1/dashboard", headers=headers).json()
    assert any(row["workflow"] == "opt_preparation" for row in dashboard["deadlines"])


def test_saved_details_roundtrip_patch_merge_and_explicit_clear(env, student):
    client, factory = env
    first = client.patch("/api/v1/profile", headers=student, json={"planning_details": {
        "opt_stage": "preparing", "opt_type": "post_completion", "ead_start": "2027-06-01",
        "ead_end": "2028-05-31", "i94_admission_type": "dated", "i94_admit_until_date": "2027-05-01"}})
    assert first.status_code == 200, first.text
    data = first.json()
    assert data["planning_details"]["opt_stage"] == "preparing"
    second = client.patch("/api/v1/profile", headers=student, json={"planning_details": {"opt_stage": "submitted", "opt_submitted_date": "2026-11-01", "i94_admit_until_date": "2027-05-02"}})
    assert second.status_code == 200, second.text
    assert second.json()["planning_details"]["ead_end"] == "2028-05-31"
    assert second.json()["version"] == data["version"] + 1
    with factory() as db:
        assert db.get(Profile, "mei-lin").planning_details["i94_admit_until_date"] == "2027-05-02"
    cleared = client.patch("/api/v1/profile", headers=student, json={"planning_details": None})
    assert cleared.status_code == 200 and cleared.json()["planning_details"] == {}


@pytest.mark.parametrize("details", [
    {"opt_stage": "invented-approved"},
    {"ead_start": "2027-06-01", "ead_end": "2027-05-01"},
    {"dso_recommendation_date": "2026-11-02", "opt_submitted_date": "2026-11-01"},
    {"i94_admission_type": "duration_of_status", "i94_admit_until_date": "2027-05-01"},
    {"j1_category": "research_scholar"},
    {"passport_number": "DO-NOT-COLLECT"},
    {"travel_destination": " "},
])
def test_invalid_or_inapplicable_details_do_not_mutate_profile(env, student, details):
    client, _ = env
    before = client.get("/api/v1/profile", headers=student).json()
    result = client.patch("/api/v1/profile", headers=student, json={"planning_details": details})
    assert result.status_code == 422, result.text
    assert client.get("/api/v1/profile", headers=student).json() == before


def test_partial_update_validates_against_saved_dates(env, student):
    client, _ = env
    assert client.patch("/api/v1/profile", headers=student, json={"travel_date": "2027-01-15", "planning_details": {"return_date": "2027-02-01", "ead_start": "2027-06-01"}}).status_code == 200
    assert client.patch("/api/v1/profile", headers=student, json={"travel_date": "2027-03-01"}).status_code == 422
    assert client.patch("/api/v1/profile", headers=student, json={"planning_details": {"ead_end": "2027-05-01"}}).status_code == 422


def test_category_change_clears_incompatible_facts_without_changing_other_account(env, student):
    client, factory = env
    client.patch("/api/v1/profile", headers=student, json={"planning_details": {"opt_stage": "preparing", "return_date": "2027-07-01"}})
    result = client.patch("/api/v1/profile", headers=student, json={"status_type": "J-1 scholar", "planning_details": {"j1_category": "professor", "sponsor_name": "Synthetic sponsor"}})
    assert result.status_code == 200, result.text
    saved = result.json()["planning_details"]
    assert "opt_stage" not in saved and saved["j1_category"] == "professor" and saved["return_date"] == "2027-07-01"
    with factory() as db:
        assert db.get(Profile, "sam-rivera").planning_details == {}


@pytest.mark.parametrize("stage,fragment", [
    ("not_planning", "No OPT application"), ("submitted", "receipt"),
    ("approved", "approval and EAD"), ("active", "reporting"),
    ("completed", "next program"), ("denied", "actual decision"), ("withdrawn", "withdrawal"),
])
def test_opt_stage_changes_actual_next_steps(env, stage, fragment):
    with env[1]() as db:
        profile = db.get(Profile, "mei-lin")
        profile.planning_details = {"opt_stage": stage}
        report = workflows(db, profile)["opt"]
        assert fragment in " ".join(report["checklist"])
        assert report["saved_stage"] == stage and report["planning_rule_version"] == PLANNING_RULE_VERSION
        if stage in {"submitted", "approved", "active"}:
            assert "Review the school's OPT recommendation procedure" not in " ".join(report["checklist"])
        assert report["legal_deadline"] is None and not report["eligibility_determined"]


def test_answered_questions_are_removed_but_adviser_review_is_not_inferred(env):
    with env[1]() as db:
        profile = db.get(Profile, "mei-lin")
        profile.planning_details = {"opt_stage": "preparing", "opt_type": "post_completion", "dso_recommendation_date": "2026-11-01",
            "academic_completion_date": "2027-05-01", "training_history_reviewed": False,
            "i94_admission_type": "duration_of_status"}
        report = workflows(db, profile)["opt"]
        missing = {q["field"] for q in report["missing_information"]}
        assert not {"opt_stage", "opt_type", "dso_recommendation_date", "academic_completion_date", "i94_admit_until_date"}.intersection(missing)
        assert "academic_and_training_history" in missing
        assert report["requires_adviser_review"] and not report["eligibility_determined"]


def test_travel_checks_use_return_date_and_separate_visa_from_status(env):
    with env[1]() as db:
        profile = db.get(Profile, "mei-lin")
        profile.program_end = date(2027, 5, 15)
        profile.travel_date = date(2027, 5, 1)
        profile.planning_details = {"return_date": "2027-06-01", "visa_expiry": "2027-05-20", "passport_expiry": "2028-01-01",
            "f1_activity": "post_completion_opt", "ead_end": "2027-05-25", "opt_stage": "submitted"}
        report = workflows(db, profile)["travel_reentry"]
        checks = {item["id"]: item for item in report["record_checks"]}
        assert {"visa_expiry_before_return", "return_on_or_after_document_end", "ead_end_before_return", "travel_during_pending_opt"}.issubset(checks)
        assert "passport_expiry_before_return" not in checks
        assert "does not determine US status" in checks["visa_expiry_before_return"]["message"]
        assert report["priority"] == "review_soon" and report["legal_deadline"] is None


def test_business_targets_and_submitted_application_dont_repeat_prepare_step(env):
    with env[1]() as db:
        profile = db.get(Profile, "mei-lin")
        profile.planning_details = {"opt_stage": "preparing", "opt_type": "post_completion", "academic_completion_date": "2027-05-01", "extension_stage": "not_needed"}
        rows = {row["workflow"]: row for row in adapter_for(profile).deadlines(profile)}
        assert "program_extension" not in rows and rows["opt_preparation"]["date"] == "2027-03-02"
        assert all(row["is_planning_buffer"] and row["legal_deadline"] is None for row in rows.values())
        profile.planning_details = {**profile.planning_details, "opt_stage": "submitted"}
        assert "opt_preparation" not in {row["workflow"] for row in adapter_for(profile).deadlines(profile)}


def test_stem_and_precompletion_preparation_use_their_own_reference_dates(env):
    with env[1]() as db:
        profile = db.get(Profile, "mei-lin")
        profile.planning_details = {"opt_stage": "preparing", "opt_type": "stem_extension", "academic_completion_date": "2025-05-01", "ead_end": "2027-05-01"}
        assert next(row for row in adapter_for(profile).deadlines(profile) if row["workflow"] == "opt_preparation")["date"] == "2027-03-02"
        profile.planning_details = {"opt_stage": "preparing", "opt_type": "pre_completion", "academic_completion_date": "2028-05-01", "opt_requested_start": "2027-05-01"}
        assert next(row for row in adapter_for(profile).deadlines(profile) if row["workflow"] == "opt_preparation")["date"] == "2027-03-02"


def test_ead_target_feeds_existing_reminders_and_is_superseded_when_removed(env):
    from app.notifications import preferences_for, sync_profile_reminders
    from app.notification_models import ReminderNotice
    with env[1]() as db:
        profile = db.get(Profile, "mei-lin")
        profile.planning_details = {"f1_activity": "post_completion_opt", "ead_end": "2026-12-03"}
        preference = preferences_for(db, profile.account_id)
        preference.timezone = "America/New_York"
        stamp = datetime(2026, 11, 3, 15)
        sync_profile_reminders(db, profile, preference, stamp)
        db.flush()
        notice = next(n for n in db.scalars(select(ReminderNotice)) if n.data.get("workflow") == "ead_review")
        assert notice.data["target_date"] == "2026-11-03" and notice.data["is_planning_buffer"]
        profile.planning_details = {}
        sync_profile_reminders(db, profile, preference, stamp)
        assert notice.superseded_at is not None


def test_j1_training_and_scholar_fields_are_separate(env):
    with env[1]() as db:
        profile = db.get(Profile, "sam-rivera")
        profile.planning_details = {"academic_training_stage": "active", "academic_training_start": "2026-10-01",
            "academic_training_end": "2027-04-01", "sponsor_authorized_on": "2026-09-15", "sponsor_name": "Synthetic sponsor"}
        report = workflows(db, profile)
        assert "opt" not in report and report["academic_training"]["saved_stage"] == "active"
        assert not report["academic_training"]["missing_information"]
        assert "academic_training_review" in {r["workflow"] for r in adapter_for(profile).deadlines(profile)}
    with pytest.raises(ValueError):
        normalize_details({"academic_training_stage": "active"}, "J-1 scholar", None)
    # Validating a scholar must not mutate the shared set of forbidden fields.
    assert normalize_details({"academic_training_stage": "active"}, "J-1 student", None)


def test_planning_changes_invalidate_existing_approval(env, student):
    client, _ = env
    proposal = client.post("/api/v1/approvals", headers=student, json={"kind": "calendar", "payload": {"title": "Synthetic review", "date": "2027-05-01"}})
    assert proposal.status_code in {200, 201}, proposal.text
    approval = proposal.json()
    preview = client.post(f"/api/v1/approvals/{approval['id']}/preview", headers=student)
    assert preview.status_code == 200, preview.text
    assert client.patch("/api/v1/profile", headers=student, json={"planning_details": {"opt_stage": "preparing"}}).status_code == 200
    result = client.post(f"/api/v1/approvals/{approval['id']}/approve", headers=student, json={"payload_hash": approval["payload_hash"]})
    assert result.status_code == 409, result.text


def test_baseline_to_new_revision_preserves_unknown_facts_and_existing_rows(tmp_path):
    from alembic import command
    from app.database_migrations import BASELINE_REVISION, migration_config, schema_differences, upgrade_database
    from app.db import make_engine
    engine = make_engine(f"sqlite:///{tmp_path}/historical.db")
    with engine.begin() as connection:
        config = migration_config(); config.attributes["connection"] = connection
        command.upgrade(config, BASELINE_REVISION)
        connection.execute(text("INSERT INTO user_profiles (id,name,school,status_type,program_start,program_end,notification_frequency,nationality,version,synthetic) VALUES ('synthetic','Synthetic','University of Pennsylvania','F-1','2026-08-20','2027-05-15','weekly','Not supplied',1,1)"))
    upgrade_database(engine)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT name FROM user_profiles WHERE id='synthetic'")) == "Synthetic"
        assert connection.scalar(select(Profile.planning_details).where(Profile.id == "synthetic")) == {}
        assert schema_differences(connection) == []
    engine.dispose()


def test_historical_sqlite_adoption_has_an_explicit_upgrade_path(tmp_path):
    from alembic import command
    from app.database_migrations import BASELINE_REVISION, adopt_sqlite_baseline, migration_config, schema_differences
    from app.db import make_engine
    engine = make_engine(f"sqlite:///{tmp_path}/unversioned-historical.db")
    with engine.begin() as connection:
        config = migration_config(); config.attributes["connection"] = connection
        command.upgrade(config, BASELINE_REVISION)
        connection.execute(text("DROP TABLE alembic_version"))
    adopt_sqlite_baseline(engine)
    with engine.connect() as connection:
        assert schema_differences(connection) == []
    engine.dispose()
