from datetime import datetime, timezone

from amodb.apps.rostering import automation_service
from amodb.apps.rostering.automation_models import (
    RosterAutomationFrequency,
    RosterGenerationPolicy,
)


def _policy(frequency: RosterAutomationFrequency, run_day: int) -> RosterGenerationPolicy:
    return RosterGenerationPolicy(
        enabled=True,
        frequency=frequency,
        timezone_name="UTC",
        run_day=run_day,
        run_hour_local=9,
    )


def test_monthly_overdue_schedule_advances_exactly_one_occurrence():
    previous = datetime(2026, 6, 15, 9, tzinfo=timezone.utc)
    current = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)

    result = automation_service._next_run(
        _policy(RosterAutomationFrequency.MONTHLY, 15),
        now=current,
        previous_scheduled_at=previous,
    )

    assert result == datetime(2026, 7, 15, 9, tzinfo=timezone.utc)
    assert result <= current


def test_fortnightly_overdue_schedule_preserves_each_due_cycle():
    previous = datetime(2026, 6, 1, 9, tzinfo=timezone.utc)
    current = datetime(2026, 7, 20, 12, tzinfo=timezone.utc)

    result = automation_service._next_run(
        _policy(RosterAutomationFrequency.FORTNIGHTLY, 1),
        now=current,
        previous_scheduled_at=previous,
    )

    assert result == datetime(2026, 6, 15, 9, tzinfo=timezone.utc)
    assert result <= current
