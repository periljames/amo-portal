from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

from sqlalchemy.orm import Session

from . import models


HOURS_BASED_FIELDS: tuple[str, ...] = (
    "ttesn_after",
    "ttsoh_after",
    "ttshsi_after",
    "pttsn_after",
    "pttso_after",
    "tscoa_after",
)

CYCLES_BASED_FIELDS: tuple[str, ...] = ("tcesn_after", "tcsoh_after")


def get_previous_usage(
    db: Session,
    serial_number: str,
    entry_date: date,
) -> models.AircraftUsage | None:
    return (
        db.query(models.AircraftUsage)
        .filter(
            models.AircraftUsage.aircraft_serial_number == serial_number,
            models.AircraftUsage.date < entry_date,
        )
        .order_by(
            models.AircraftUsage.date.desc(),
            models.AircraftUsage.techlog_no.desc(),
        )
        .first()
    )


def _increment_field(
    data: dict,
    previous_value: float | None,
    field: str,
    delta: float,
) -> None:
    if data.get(field) is not None:
        return
    if previous_value is None:
        return
    data[field] = previous_value + delta


def apply_usage_calculations(
    data: dict,
    previous_usage: models.AircraftUsage | None,
) -> None:
    block_hours = data.get("block_hours") or 0
    cycles = data.get("cycles") or 0

    previous_ttaf = previous_usage.ttaf_after if previous_usage else 0
    previous_tca = previous_usage.tca_after if previous_usage else 0

    if data.get("ttaf_after") is None:
        data["ttaf_after"] = (previous_ttaf or 0) + block_hours
    if data.get("tca_after") is None:
        data["tca_after"] = (previous_tca or 0) + cycles

    if previous_usage:
        for field in HOURS_BASED_FIELDS:
            _increment_field(data, getattr(previous_usage, field), field, block_hours)
        for field in CYCLES_BASED_FIELDS:
            _increment_field(data, getattr(previous_usage, field), field, cycles)


def update_maintenance_remaining(
    db: Session,
    serial_number: str,
    entry_date: date,
    data: dict,
) -> None:
    statuses: Iterable[models.MaintenanceStatus] = (
        db.query(models.MaintenanceStatus)
        .filter(models.MaintenanceStatus.aircraft_serial_number == serial_number)
        .all()
    )
    hours_values: list[float] = []
    day_values: list[int] = []

    for status in statuses:
        if status.remaining_hours is not None:
            hours_values.append(status.remaining_hours)
        if status.remaining_days is not None:
            day_values.append(status.remaining_days)
        if status.remaining_days is None and status.next_due_date is not None:
            delta_days = (status.next_due_date - entry_date).days
            day_values.append(delta_days)

    if data.get("hours_to_mx") is None and hours_values:
        data["hours_to_mx"] = min(hours_values)
    if data.get("days_to_mx") is None and day_values:
        data["days_to_mx"] = min(day_values)


def build_usage_summary(
    db: Session,
    serial_number: str,
) -> dict:
    latest_usage = (
        db.query(models.AircraftUsage)
        .filter(models.AircraftUsage.aircraft_serial_number == serial_number)
        .order_by(
            models.AircraftUsage.date.desc(),
            models.AircraftUsage.techlog_no.desc(),
        )
        .first()
    )

    if not latest_usage:
        return {
            "aircraft_serial_number": serial_number,
            "total_hours": None,
            "total_cycles": None,
            "seven_day_daily_average_hours": None,
            "next_due_program_item_id": None,
            "next_due_task_code": None,
            "next_due_date": None,
            "next_due_hours": None,
            "next_due_cycles": None,
        }

    latest_date = latest_usage.date
    range_start = latest_date - timedelta(days=6)

    recent_entries = (
        db.query(models.AircraftUsage)
        .filter(
            models.AircraftUsage.aircraft_serial_number == serial_number,
            models.AircraftUsage.date >= range_start,
            models.AircraftUsage.date <= latest_date,
        )
        .all()
    )
    total_recent_hours = sum(entry.block_hours for entry in recent_entries)
    seven_day_average = total_recent_hours / 7 if recent_entries else None

    statuses: Iterable[models.MaintenanceStatus] = (
        db.query(models.MaintenanceStatus)
        .filter(models.MaintenanceStatus.aircraft_serial_number == serial_number)
        .all()
    )

    next_due_status = None
    next_due_score = None
    for status in statuses:
        if status.next_due_date:
            score = (status.next_due_date, status.next_due_hours or 0, status.next_due_cycles or 0)
        elif status.next_due_hours is not None:
            score = (date.max, status.next_due_hours, status.next_due_cycles or 0)
        elif status.next_due_cycles is not None:
            score = (date.max, float("inf"), status.next_due_cycles)
        else:
            continue
        if next_due_score is None or score < next_due_score:
            next_due_score = score
            next_due_status = status

    next_due_item = next_due_status.program_item if next_due_status else None

    return {
        "aircraft_serial_number": serial_number,
        "total_hours": latest_usage.ttaf_after,
        "total_cycles": latest_usage.tca_after,
        "seven_day_daily_average_hours": seven_day_average,
        "next_due_program_item_id": next_due_status.program_item_id if next_due_status else None,
        "next_due_task_code": next_due_item.task_code if next_due_item else None,
        "next_due_date": next_due_status.next_due_date if next_due_status else None,
        "next_due_hours": next_due_status.next_due_hours if next_due_status else None,
        "next_due_cycles": next_due_status.next_due_cycles if next_due_status else None,
    }