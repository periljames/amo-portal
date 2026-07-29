from __future__ import annotations

from datetime import date, datetime, timezone
import inspect
from types import SimpleNamespace

import pytest

from amodb.apps.rostering import automation_router, automation_service
from amodb.apps.rostering.automation_models import RosterAutomationFrequency
from amodb.jobs import rostering_automation


def policy(**overrides):
    values = {
        "enabled": True,
        "frequency": RosterAutomationFrequency.MONTHLY,
        "lead_periods": 1,
        "run_day": 15,
        "run_hour_local": 6,
        "timezone_name": "Africa/Nairobi",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_monthly_target_is_complete_future_month():
    start, end = automation_service._target_window(
        policy(),
        today=date(2026, 7, 28),
    )
    assert start == date(2026, 8, 1)
    assert end == date(2026, 8, 31)


def test_weekly_target_starts_on_future_monday():
    start, end = automation_service._target_window(
        policy(frequency=RosterAutomationFrequency.WEEKLY, run_day=1),
        today=date(2026, 7, 28),  # Tuesday
    )
    assert start == date(2026, 8, 3)
    assert end == date(2026, 8, 9)


def test_weekly_and_fortnightly_run_days_are_iso_weekdays():
    assert automation_service._validate_run_day(RosterAutomationFrequency.WEEKLY, 1) == 1
    assert automation_service._validate_run_day(RosterAutomationFrequency.FORTNIGHTLY, 7) == 7
    with pytest.raises(ValueError, match="ISO weekday"):
        automation_service._validate_run_day(RosterAutomationFrequency.WEEKLY, 15)
    with pytest.raises(ValueError, match="ISO weekday"):
        automation_service._validate_run_day(RosterAutomationFrequency.FORTNIGHTLY, 8)


def test_monthly_run_day_accepts_only_supported_calendar_days():
    assert automation_service._validate_run_day(RosterAutomationFrequency.MONTHLY, 28) == 28
    with pytest.raises(ValueError, match="1 to 28"):
        automation_service._validate_run_day(RosterAutomationFrequency.MONTHLY, 29)


def test_policy_name_tokens_are_deterministic():
    assert automation_service._render_pattern(
        "{YYYY}-{MM}",
        date(2026, 8, 1),
        date(2026, 8, 31),
    ) == "2026-08"
    assert automation_service._render_pattern(
        "{MMMM} {YYYY} duty roster",
        date(2026, 8, 1),
        date(2026, 8, 31),
    ) == "August 2026 duty roster"


def test_disabled_policy_has_no_scheduled_run():
    assert automation_service._next_run(
        policy(enabled=False),
        now=datetime(2026, 7, 28, 9, tzinfo=timezone.utc),
    ) is None


def test_automation_models_keep_tenant_and_idempotency_boundaries():
    from amodb.apps.rostering.automation_models import RosterGenerationPolicy, RosterGenerationRun

    assert "amo_id" in RosterGenerationPolicy.__table__.columns
    assert "state_revision" in RosterGenerationPolicy.__table__.columns
    assert "idempotency_key" in RosterGenerationRun.__table__.columns
    constraints = {constraint.name for constraint in RosterGenerationRun.__table__.constraints}
    assert "uq_roster_generation_run_idempotency" in constraints


def test_manual_failure_evidence_is_written_only_after_rollback():
    source = inspect.getsource(automation_router._record_failed_run)
    assert source.index("db.rollback()") < source.index("RosterGenerationRun(")
    assert '"operational_changes_committed": False' in source
    assert '"failure_recorded_after_rollback": True' in source


def test_database_conflicts_use_the_same_fail_closed_evidence_path():
    source = inspect.getsource(automation_router.run_roster_automation)
    integrity_branch = source[source.index("except IntegrityError"):source.index("except (ValueError, RuntimeError)")]
    assert "_record_failed_run(" in integrity_branch
    assert "failure_evidence_retained" in integrity_branch
    assert "HTTP_409_CONFLICT" in integrity_branch


def test_scheduled_failure_evidence_is_written_only_after_rollback():
    source = inspect.getsource(rostering_automation._record_failed_scheduled_run)
    assert source.index("db.rollback()") < source.index("RosterGenerationRun(")
    assert '"operational_changes_committed": False' in source
    assert '"scheduled_cycle_advanced": True' in source


def test_failed_idempotency_replay_is_not_returned_as_success():
    source = inspect.getsource(automation_service.run)
    assert "ROSTER_AUTOMATION_PREVIOUS_FAILURE" in source
    assert "ROSTER_AUTOMATION_ALREADY_RUNNING" in source


def test_period_only_automation_does_not_require_or_validate_a_draft():
    source = inspect.getsource(automation_service.run)
    assert 'if not draft and (should_create_draft or should_generate):' in source
    assert 'run_row.version_id = draft.id if draft else None' in source
    assert 'if should_generate and draft:' in source
    assert 'if policy.validate_after_generation and draft:' in source
    assert '"draft_created_or_reused": draft is not None' in source


def test_scheduled_worker_catches_unexpected_execution_errors():
    source = inspect.getsource(rostering_automation._run_policy)
    assert "except Exception as exc:" in source
    assert "_record_failed_scheduled_run(" in source


def test_one_tenant_failure_does_not_abort_later_due_policies():
    source = inspect.getsource(rostering_automation.run)
    assert "for policy_id in policy_ids:" in source
    assert "results.append(_run_policy(" in source
    assert '"evidence_retained": False' in source


def test_scheduled_no_owner_path_retains_immutable_evidence():
    source = inspect.getsource(rostering_automation._run_policy)
    no_owner = source[source.index("if not actor_user_id:"):source.index("try:", source.index("if not actor_user_id:"))]
    assert "_record_failed_scheduled_run(" in no_owner
    assert 'failure_kind="NO_ACCOUNTABLE_OWNER"' in no_owner
    assert '"evidence_retained": retained' in no_owner

def test_successful_idempotency_replay_rejects_changed_payloads():
    source = inspect.getsource(automation_service.run)
    assert "_request_fingerprint(payload, trigger)" in source
    assert "ROSTER_AUTOMATION_IDEMPOTENCY_PAYLOAD_MISMATCH" in source
    assert '"request_fingerprint": request_fingerprint' in source


def test_first_policy_creation_recovers_the_unique_race():
    source = inspect.getsource(automation_service.get_or_create_policy)
    assert "with db.begin_nested():" in source
    assert "except IntegrityError:" in source
    assert "if winner is not None:" in source


def test_no_owner_evidence_uses_skipped_status():
    source = inspect.getsource(rostering_automation._record_failed_scheduled_run)
    assert "RosterAutomationRunStatus.SKIPPED" in source
    assert '"skip_recorded_after_rollback": skipped' in source
