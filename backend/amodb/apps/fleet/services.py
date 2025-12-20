from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class UsageSnapshot:
    as_of_date: date | None
    airframe_hours: float | None
    airframe_cycles: float | None
    engine_hours: float | None
    engine_cycles: float | None
    prop_hours: float | None


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


def get_usage_snapshot(
    db: Session,
    serial_number: str,
    entry_date: date | None,
) -> UsageSnapshot:
    query = db.query(models.AircraftUsage).filter(
        models.AircraftUsage.aircraft_serial_number == serial_number
    )
    if entry_date:
        query = query.filter(models.AircraftUsage.date <= entry_date)
    latest_usage = (
        query.order_by(
            models.AircraftUsage.date.desc(),
            models.AircraftUsage.techlog_no.desc(),
        )
        .first()
    )
    if not latest_usage:
        return UsageSnapshot(
            as_of_date=entry_date,
            airframe_hours=None,
            airframe_cycles=None,
            engine_hours=None,
            engine_cycles=None,
            prop_hours=None,
        )

    return UsageSnapshot(
        as_of_date=latest_usage.date,
        airframe_hours=latest_usage.ttaf_after,
        airframe_cycles=latest_usage.tca_after,
        engine_hours=latest_usage.ttesn_after,
        engine_cycles=latest_usage.tcesn_after,
        prop_hours=latest_usage.pttsn_after,
    )


def _remaining_score(
    status: models.MaintenanceStatus,
    remaining: dict,
) -> tuple[date, float, float] | None:
    if remaining["remaining_days"] is not None:
        return (date.min, float(remaining["remaining_days"]), 0)
    if remaining["remaining_hours"] is not None:
        return (date.max, remaining["remaining_hours"], remaining["remaining_cycles"] or 0)
    if remaining["remaining_cycles"] is not None:
        return (date.max, float("inf"), remaining["remaining_cycles"])
    if status.next_due_date:
        return (status.next_due_date, status.next_due_hours or 0, status.next_due_cycles or 0)
    return None


def compute_remaining_fields(
    status: models.MaintenanceStatus,
    usage_snapshot: UsageSnapshot,
) -> dict:
    remaining_hours = status.remaining_hours
    remaining_cycles = status.remaining_cycles
    remaining_days = status.remaining_days

    category = status.program_item.category if status.program_item else None

    if remaining_days is None and status.next_due_date and usage_snapshot.as_of_date:
        remaining_days = (status.next_due_date - usage_snapshot.as_of_date).days

    if remaining_hours is None and status.next_due_hours is not None:
        current_hours = None
        if category == models.MaintenanceProgramCategoryEnum.ENGINE:
            current_hours = usage_snapshot.engine_hours
        elif category == models.MaintenanceProgramCategoryEnum.PROP:
            current_hours = usage_snapshot.prop_hours
        else:
            current_hours = usage_snapshot.airframe_hours
        if current_hours is not None:
            remaining_hours = status.next_due_hours - current_hours

    if remaining_cycles is None and status.next_due_cycles is not None:
        current_cycles = None
        if category == models.MaintenanceProgramCategoryEnum.ENGINE:
            current_cycles = usage_snapshot.engine_cycles
        else:
            current_cycles = usage_snapshot.airframe_cycles
        if current_cycles is not None:
            remaining_cycles = status.next_due_cycles - current_cycles

    return {
        "remaining_hours": remaining_hours,
        "remaining_cycles": remaining_cycles,
        "remaining_days": remaining_days,
    }


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
    usage_snapshot = get_usage_snapshot(db, serial_number, entry_date)
    statuses: Iterable[models.MaintenanceStatus] = (
        db.query(models.MaintenanceStatus)
        .filter(models.MaintenanceStatus.aircraft_serial_number == serial_number)
        .all()
    )
    hours_values: list[float] = []
    day_values: list[int] = []

    for status in statuses:
        remaining = compute_remaining_fields(status, usage_snapshot)
        if remaining["remaining_hours"] is not None:
            hours_values.append(remaining["remaining_hours"])
        if remaining["remaining_days"] is not None:
            day_values.append(remaining["remaining_days"])

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
    usage_snapshot = UsageSnapshot(
        as_of_date=latest_usage.date,
        airframe_hours=latest_usage.ttaf_after,
        airframe_cycles=latest_usage.tca_after,
        engine_hours=latest_usage.ttesn_after,
        engine_cycles=latest_usage.tcesn_after,
        prop_hours=latest_usage.pttsn_after,
    )

    next_due_status = None
    next_due_score = None
    for status in statuses:
        remaining = compute_remaining_fields(status, usage_snapshot)
        score = _remaining_score(status, remaining)
        if score is None:
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
