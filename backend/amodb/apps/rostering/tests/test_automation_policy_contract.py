from __future__ import annotations

from datetime import date, datetime, timezone
import inspect
from types import SimpleNamespace

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
        policy(frequency=RosterAutomationFrequency.WEEKLY),
        today=date(2026, 7, 28),  # Tuesday
    )
    assert start == date(2026, 8, 3)
    assert end == date(2026, 8, 9)


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


def test_scheduled_failure_evidence_is_written_only_after_rollback():
    source = inspect.getsource(rostering_automation._record_failed_scheduled_run)
    assert source.index("db.rollback()") < source.index("RosterGenerationRun(")
    assert '"operational_changes_committed": False' in source
    assert '"scheduled_cycle_advanced": True' in source
