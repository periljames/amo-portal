from __future__ import annotations

from datetime import datetime, timedelta, timezone

from amodb.apps.rostering import compliance_policy, protected_rest_exact_policy

UTC = timezone.utc


def _at(origin: datetime, minutes: int) -> datetime:
    return origin + timedelta(minutes=minutes)


def _duty(origin: datetime, start: int, end: int, name: str):
    return compliance_policy.DutyInterval(
        starts_at=_at(origin, start),
        ends_at=_at(origin, end),
        assignment_ids=(name,),
    )


def test_exact_evaluator_catches_violation_between_duty_boundary_candidates():
    """Regression for a sliding-window miss in boundary-candidate sampling.

    The first non-compliant seven-day window starts 398 minutes after the
    evaluation origin. Its longest free interval is exactly 1,439 minutes, so
    sampling only starts derived from duty boundaries incorrectly reported PASS.
    """

    origin = datetime(2026, 8, 1, tzinfo=UTC)
    intervals = [
        _duty(origin, 1837, 2702, "a"),
        _duty(origin, 3409, 4116, "b"),
        _duty(origin, 4550, 5481, "c"),
        _duty(origin, 6804, 7379, "d"),
        _duty(origin, 8390, 9139, "e"),
    ]

    violation = protected_rest_exact_policy.protected_rest_violation(
        intervals,
        evaluation_start=origin,
        evaluation_end=origin + timedelta(days=14),
        window=timedelta(days=7),
        required_rest=timedelta(hours=24),
    )

    assert violation is not None
    assert violation["window_start"] == _at(origin, 398).isoformat()
    assert violation["longest_rest_minutes"] == 1439
    assert violation["required_rest_minutes"] == 1440


def test_exact_evaluator_accepts_exactly_24_hours_and_rejects_one_minute_less():
    origin = datetime(2026, 8, 1, tzinfo=UTC)
    exact = [
        _duty(origin, 0, 2 * 24 * 60, "before"),
        _duty(origin, 3 * 24 * 60, 7 * 24 * 60, "after"),
    ]
    short = [
        _duty(origin, 0, 2 * 24 * 60 + 1, "before"),
        _duty(origin, 3 * 24 * 60, 7 * 24 * 60, "after"),
    ]

    assert protected_rest_exact_policy.protected_rest_violation(
        exact,
        evaluation_start=origin,
        evaluation_end=origin,
    ) is None
    violation = protected_rest_exact_policy.protected_rest_violation(
        short,
        evaluation_start=origin,
        evaluation_end=origin,
    )
    assert violation is not None
    assert violation["longest_rest_minutes"] == 1439
