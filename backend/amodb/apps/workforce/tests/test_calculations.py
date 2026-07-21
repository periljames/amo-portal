from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from amodb.apps.workforce import calculations, models

UTC = timezone.utc


def attendance(event_type: models.AttendanceEventType, at: str, event_id: str, metadata=None):
    return SimpleNamespace(
        event_type=event_type,
        occurred_at=datetime.fromisoformat(at).replace(tzinfo=UTC),
        id=event_id,
        metadata_json=metadata,
    )


def test_attendance_pairing_subtracts_breaks_and_applies_adjustment():
    totals = calculations.calculate_attendance_totals([
        attendance(models.AttendanceEventType.CLOCK_IN, "2026-07-21T05:00:00", "1"),
        attendance(models.AttendanceEventType.BREAK_START, "2026-07-21T09:00:00", "2"),
        attendance(models.AttendanceEventType.BREAK_END, "2026-07-21T09:30:00", "3"),
        attendance(models.AttendanceEventType.CLOCK_OUT, "2026-07-21T14:00:00", "4"),
        attendance(models.AttendanceEventType.MANUAL_ADJUSTMENT, "2026-07-21T14:01:00", "5", {"minutes": 15}),
    ])
    assert totals.presence_minutes == 540
    assert totals.break_minutes == 30
    assert totals.paid_minutes == 525
    assert totals.incomplete is False
    assert totals.warnings == ()


def test_attendance_invalid_sequence_is_non_negative_and_reviewable():
    totals = calculations.calculate_attendance_totals([
        attendance(models.AttendanceEventType.CLOCK_OUT, "2026-07-21T05:00:00", "1"),
        attendance(models.AttendanceEventType.CLOCK_IN, "2026-07-21T06:00:00", "2"),
        attendance(models.AttendanceEventType.BREAK_END, "2026-07-21T07:00:00", "3"),
    ])
    assert totals.paid_minutes == 0
    assert totals.incomplete is True
    assert "Clock-out without clock-in ignored" in totals.warnings
    assert "Open clock-in requires correction" in totals.warnings


def test_overnight_shift_is_converted_from_amo_local_time_to_utc():
    starts_at, ends_at, minutes = calculations.local_shift_window_to_utc(
        work_date=date(2026, 7, 21),
        start_time_local="18:00",
        end_time_local="06:00",
        timezone_name="Africa/Nairobi",
        spans_next_day=True,
    )
    assert starts_at == datetime(2026, 7, 21, 15, 0, tzinfo=UTC)
    assert ends_at == datetime(2026, 7, 22, 3, 0, tzinfo=UTC)
    assert minutes == 720


def test_cycle_day_is_stable_before_and_after_anchor():
    anchor = date(2026, 7, 20)
    assert calculations.resolve_cycle_day(work_date=date(2026, 7, 20), cycle_anchor_date=anchor, cycle_length_days=4) == 0
    assert calculations.resolve_cycle_day(work_date=date(2026, 7, 23), cycle_anchor_date=anchor, cycle_length_days=4) == 3
    assert calculations.resolve_cycle_day(work_date=date(2026, 7, 19), cycle_anchor_date=anchor, cycle_length_days=4) == 3


def test_interval_overlap_uses_half_open_boundaries():
    first_start = datetime(2026, 7, 21, 5, tzinfo=UTC)
    first_end = datetime(2026, 7, 21, 13, tzinfo=UTC)
    second_start = first_end
    second_end = datetime(2026, 7, 21, 21, tzinfo=UTC)
    assert calculations.interval_overlaps(first_start, first_end, second_start, second_end) is False
    assert calculations.overlap_minutes(first_start, first_end, second_start, second_end) == 0
