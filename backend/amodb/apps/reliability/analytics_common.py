from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable, Literal
from urllib.parse import urlencode

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.fleet import models as fleet_models

from . import models

UTC = timezone.utc
MAX_EVENT_SCAN = 50_000
DISPATCH_EVENT_TYPES = {
    "TECHNICAL_DELAY", "TECHNICAL_CANCELLATION", "RETURN_TO_GATE", "AIR_TURNBACK",
    "DIVERSION", "IN_FLIGHT_SHUTDOWN", "ABORTED_TAKEOFF",
}
DELAY_EVENT_TYPES = {"TECHNICAL_DELAY"}
CANCELLATION_EVENT_TYPES = {"TECHNICAL_CANCELLATION"}
REPEAT_EVENT_TYPES = {"REPEAT_DEFECT"}
UNSCHEDULED_REMOVAL_TYPES = {"UNSCHEDULED_REMOVAL"}
SHOP_EVENT_TYPES = {"SHOP_FINDING", "NO_FAULT_FOUND"}
OPEN_DEFERRAL_STATES = {"OPEN", "APPROVED", "EXTENDED", "EXPIRED"}
CLOSED_ACTION_STATES = {"DONE", "VERIFIED", "CANCELLED"}

def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value or ""))


def _tenant_id(current_user: account_models.User) -> str:
    amo_id = current_user.effective_amo_id
    if not amo_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A tenant context is required.",
        )
    return str(amo_id)


def _aircraft_type_label(row: fleet_models.Aircraft) -> str:
    value = " ".join(part.strip() for part in (row.make or "", row.model or "") if part and part.strip())
    return value or "Unclassified aircraft type"


def _resolve_aircraft_selection(
    db: Session,
    *,
    amo_id: str,
    aircraft: Iterable[str],
    aircraft_types: Iterable[str],
) -> tuple[set[str], list[fleet_models.Aircraft]]:
    rows = db.query(fleet_models.Aircraft).filter(fleet_models.Aircraft.amo_id == amo_id).all()
    selected = set(aircraft)
    selected_types = set(aircraft_types)
    if selected_types:
        by_type = {row.serial_number for row in rows if _aircraft_type_label(row) in selected_types}
        selected = selected & by_type if selected else by_type
    return selected, rows


def _start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


def _end(value: date) -> datetime:
    return datetime.combine(value, time.max, tzinfo=UTC)


def _normalise_date(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).date()
    return value


def _bucket_for_window(period_start: date, period_end: date, requested: str) -> Literal["DAY", "WEEK", "MONTH"]:
    if requested in {"DAY", "WEEK", "MONTH"}:
        return requested  # type: ignore[return-value]
    days = (period_end - period_start).days + 1
    if days <= 45:
        return "DAY"
    if days <= 180:
        return "WEEK"
    return "MONTH"


def _bucket_key(value: date, bucket: str) -> tuple[str, str]:
    if bucket == "DAY":
        return value.isoformat(), value.strftime("%d %b")
    if bucket == "WEEK":
        monday = value - timedelta(days=value.weekday())
        return monday.isoformat(), f"Wk {monday.strftime('%d %b')}"
    month = value.replace(day=1)
    return month.isoformat(), month.strftime("%b %Y")


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _ratio(numerator: float, denominator: float, multiplier: float = 1.0) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator / denominator) * multiplier, 3)


def _delta(current: float | int | None, previous: float | int | None) -> tuple[float | None, str]:
    if current is None or previous is None:
        return None, "UNKNOWN"
    current_value = float(current)
    previous_value = float(previous)
    if previous_value == 0:
        if current_value == 0:
            return 0.0, "FLAT"
        return None, "UNKNOWN"
    value = round(((current_value - previous_value) / abs(previous_value)) * 100, 1)
    if abs(value) < 0.05:
        return value, "FLAT"
    return value, "UP" if value > 0 else "DOWN"


def _metric_status(code: str, value: float | int | None) -> str:
    if value is None:
        return "NO_DATA"
    if code in {"dispatch_reliability_pct", "effectiveness_pass_pct", "action_completion_pct"}:
        if float(value) >= 99:
            return "GOOD"
        if float(value) >= 97:
            return "WATCH"
        return "ALERT"
    if code in {"overdue_deferrals", "overdue_actions", "critical_alerts", "engine_shifts", "data_quality_open"}:
        return "GOOD" if float(value) == 0 else "ALERT"
    if code in {"nff_rate_pct"}:
        if float(value) <= 10:
            return "GOOD"
        if float(value) <= 25:
            return "WATCH"
        return "ALERT"
    return "NEUTRAL"


def _query_string(values: dict[str, Any]) -> str:
    encoded = urlencode([(key, item) for key, value in values.items() for item in (value if isinstance(value, list) else [value]) if item not in (None, "")])
    return f"?{encoded}" if encoded else ""


def _comparison_period(period_start: date, period_end: date) -> tuple[date, date]:
    span = (period_end - period_start).days + 1
    previous_end = period_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=span - 1)
    return previous_start, previous_end


def _event_matches(
    event: models.ReliabilityEvent,
    *,
    aircraft: set[str],
    ata_chapters: set[str],
    stations: set[str],
    event_types: set[str],
    severities: set[str],
    source_systems: set[str],
) -> bool:
    event_type = _enum_value(event.event_type)
    severity = _enum_value(event.severity)
    if aircraft and (event.aircraft_serial_number or "") not in aircraft:
        return False
    if ata_chapters and (event.ata_chapter or "") not in ata_chapters:
        return False
    if event_types and event_type not in event_types:
        return False
    if severities and severity not in severities:
        return False
    if source_systems and (event.source_system or "") not in source_systems:
        return False
    if stations and not ({event.origin_station or "", event.destination_station or ""} & stations):
        return False
    return True


def _load_events(
    db: Session,
    *,
    amo_id: str,
    period_start: date,
    period_end: date,
    aircraft: set[str],
    ata_chapters: set[str],
    stations: set[str],
    event_types: set[str],
    severities: set[str],
    source_systems: set[str],
) -> list[models.ReliabilityEvent]:
    query = db.query(models.ReliabilityEvent).filter(
        models.ReliabilityEvent.amo_id == amo_id,
        models.ReliabilityEvent.occurred_at >= _start(period_start),
        models.ReliabilityEvent.occurred_at <= _end(period_end),
    )
    if aircraft:
        query = query.filter(models.ReliabilityEvent.aircraft_serial_number.in_(sorted(aircraft)))
    if ata_chapters:
        query = query.filter(models.ReliabilityEvent.ata_chapter.in_(sorted(ata_chapters)))
    if event_types:
        query = query.filter(models.ReliabilityEvent.event_type.in_(sorted(event_types)))
    if severities:
        query = query.filter(models.ReliabilityEvent.severity.in_(sorted(severities)))
    if source_systems:
        query = query.filter(models.ReliabilityEvent.source_system.in_(sorted(source_systems)))
    if stations:
        query = query.filter(
            or_(
                models.ReliabilityEvent.origin_station.in_(sorted(stations)),
                models.ReliabilityEvent.destination_station.in_(sorted(stations)),
            )
        )
    rows = query.order_by(models.ReliabilityEvent.occurred_at.asc()).limit(MAX_EVENT_SCAN + 1).all()
    if len(rows) > MAX_EVENT_SCAN:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"The selected window contains more than {MAX_EVENT_SCAN:,} reliability events. Narrow the period or filters.",
        )
    return rows


def _load_utilisation(
    db: Session,
    *,
    amo_id: str,
    period_start: date,
    period_end: date,
    aircraft: set[str],
) -> list[models.AircraftUtilizationDaily]:
    query = db.query(models.AircraftUtilizationDaily).filter(
        models.AircraftUtilizationDaily.amo_id == amo_id,
        models.AircraftUtilizationDaily.date >= period_start,
        models.AircraftUtilizationDaily.date <= period_end,
    )
    if aircraft:
        query = query.filter(models.AircraftUtilizationDaily.aircraft_serial_number.in_(sorted(aircraft)))
    return query.order_by(models.AircraftUtilizationDaily.date.asc()).all()


def _event_totals(events: Iterable[models.ReliabilityEvent]) -> dict[str, float]:
    rows = list(events)
    event_types = [_enum_value(row.event_type) for row in rows]
    total_delay = sum(max(int(row.delay_minutes or 0), 0) for row in rows)
    dispatch = sum(event_type in DISPATCH_EVENT_TYPES for event_type in event_types)
    shop = sum(event_type in SHOP_EVENT_TYPES for event_type in event_types)
    nff = sum(event_type == "NO_FAULT_FOUND" for event_type in event_types)
    return {
        "events": float(len(rows)),
        "dispatch_events": float(dispatch),
        "delays": float(sum(event_type in DELAY_EVENT_TYPES for event_type in event_types)),
        "cancellations": float(sum(event_type in CANCELLATION_EVENT_TYPES for event_type in event_types)),
        "repeat_defects": float(sum(event_type in REPEAT_EVENT_TYPES for event_type in event_types)),
        "unscheduled_removals": float(sum(event_type in UNSCHEDULED_REMOVAL_TYPES for event_type in event_types)),
        "delay_minutes": float(total_delay),
        "shop_events": float(shop),
        "nff": float(nff),
    }


def _utilisation_totals(rows: Iterable[models.AircraftUtilizationDaily]) -> dict[str, float]:
    values = list(rows)
    return {
        "flight_hours": round(sum(_safe_float(row.flight_hours) for row in values), 3),
        "flight_cycles": round(sum(_safe_float(row.cycles) for row in values), 3),
    }
