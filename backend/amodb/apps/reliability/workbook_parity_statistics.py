from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_write_db
from amodb.security import get_current_active_user
from . import models as reliability_models
from .workbook_parity import ReliabilityStatisticalAlertResult, ReliabilityWorkbookRecord, StatisticalAlertRequest, WorkbookRecordStatus, _decimal

UTC = timezone.utc
MAX_SCAN = 50_000


def _amo_id(user: account_models.User) -> str:
    amo_id = user.effective_amo_id
    if not amo_id:
        raise HTTPException(status_code=403, detail="A tenant context is required.")
    return str(amo_id)


def bucket_start(value: date, bucket: str) -> date:
    return value - timedelta(days=value.weekday()) if bucket == "WEEK" else value.replace(day=1)


def next_bucket(value: date, bucket: str) -> date:
    if bucket == "WEEK":
        return value + timedelta(days=7)
    return value.replace(year=value.year + 1, month=1, day=1) if value.month == 12 else value.replace(month=value.month + 1, day=1)


def complete_bucket_sequence(period_start: date, period_end: date, bucket: str) -> list[date]:
    current, end = bucket_start(period_start, bucket), bucket_start(period_end, bucket)
    result: list[date] = []
    while current <= end:
        result.append(current)
        current = next_bucket(current, bucket)
    return result


def load_complete_series(db: Session, amo_id: str, request: StatisticalAlertRequest) -> list[dict[str, Any]]:
    sequence = complete_bucket_sequence(request.period_start, request.period_end, request.bucket)
    values: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
    if request.source_kind.startswith("EVENT"):
        query = db.query(reliability_models.ReliabilityEvent).filter(
            reliability_models.ReliabilityEvent.amo_id == amo_id,
            reliability_models.ReliabilityEvent.occurred_at >= datetime.combine(request.period_start, time.min, tzinfo=UTC),
            reliability_models.ReliabilityEvent.occurred_at <= datetime.combine(request.period_end, time.max, tzinfo=UTC),
        )
        if request.aircraft_serial_number:
            query = query.filter(reliability_models.ReliabilityEvent.aircraft_serial_number == request.aircraft_serial_number)
        if request.ata_chapter:
            query = query.filter(reliability_models.ReliabilityEvent.ata_chapter == request.ata_chapter)
        if request.event_types:
            query = query.filter(reliability_models.ReliabilityEvent.event_type.in_(request.event_types))
        rows = query.order_by(reliability_models.ReliabilityEvent.occurred_at.asc()).limit(MAX_SCAN + 1).all()
        if len(rows) > MAX_SCAN:
            raise HTTPException(status_code=422, detail="The statistical event scan exceeded 50,000 records. Narrow the period or scope.")
        for row in rows:
            values[bucket_start(row.occurred_at.date(), request.bucket)] += Decimal("1")
        if request.source_kind == "EVENT_COUNT":
            return [{"period": key.isoformat(), "value": float(values[key])} for key in sequence]
        hours: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
        utilisation = db.query(reliability_models.AircraftUtilizationDaily).filter(
            reliability_models.AircraftUtilizationDaily.amo_id == amo_id,
            reliability_models.AircraftUtilizationDaily.date >= request.period_start,
            reliability_models.AircraftUtilizationDaily.date <= request.period_end,
        )
        if request.aircraft_serial_number:
            utilisation = utilisation.filter(reliability_models.AircraftUtilizationDaily.aircraft_serial_number == request.aircraft_serial_number)
        exposure_rows = utilisation.order_by(reliability_models.AircraftUtilizationDaily.date.asc()).limit(MAX_SCAN + 1).all()
        if len(exposure_rows) > MAX_SCAN:
            raise HTTPException(status_code=422, detail="The utilisation scan exceeded 50,000 records. Narrow the period or scope.")
        for row in exposure_rows:
            hours[bucket_start(row.date, request.bucket)] += Decimal(str(row.flight_hours or 0))
        return [{"period": key.isoformat(), "numerator": float(values[key]), "denominator": float(hours[key]), "value": float(values[key] / hours[key] * Decimal("100")) if hours[key] > 0 else None} for key in sequence]

    query = db.query(ReliabilityWorkbookRecord).filter(
        ReliabilityWorkbookRecord.amo_id == amo_id,
        ReliabilityWorkbookRecord.dataset_code == request.dataset_code.value,
        ReliabilityWorkbookRecord.status.in_([WorkbookRecordStatus.APPROVED.value, WorkbookRecordStatus.CLOSED.value]),
        ReliabilityWorkbookRecord.event_date >= request.period_start,
        ReliabilityWorkbookRecord.event_date <= request.period_end,
    )
    if request.aircraft_serial_number:
        query = query.filter(ReliabilityWorkbookRecord.aircraft_serial_number == request.aircraft_serial_number)
    if request.ata_chapter:
        query = query.filter(ReliabilityWorkbookRecord.ata_chapter == request.ata_chapter)
    rows = query.order_by(ReliabilityWorkbookRecord.event_date.asc()).limit(MAX_SCAN + 1).all()
    if len(rows) > MAX_SCAN:
        raise HTTPException(status_code=422, detail="The workbook-register scan exceeded 50,000 records. Narrow the period or scope.")
    for row in rows:
        key = bucket_start(row.event_date, request.bucket)
        if request.source_kind == "DATASET_COUNT":
            values[key] += Decimal("1")
        else:
            raw = row.derived_values.get(request.metric_field) if request.metric_field in row.derived_values else row.payload.get(request.metric_field)
            if raw not in (None, ""):
                values[key] += _decimal(raw, request.metric_field, minimum=None)
    return [{"period": key.isoformat(), "value": float(values[key])} for key in sequence]


def calculate_levels(series: list[dict[str, Any]], warning_multiplier: Decimal, alert_multiplier: Decimal) -> dict[str, Any]:
    values = [float(row["value"]) for row in series if row.get("value") is not None and math.isfinite(float(row["value"]))]
    if len(values) < 2:
        raise HTTPException(status_code=422, detail="At least two analytical periods with valid values are required to calculate sample standard deviation.")
    mean_value = Decimal(str(statistics.fmean(values)))
    stddev = Decimal(str(statistics.stdev(values)))
    return {"sample_size": len(values), "mean": mean_value, "sample_stddev": stddev, "warning_level": mean_value + warning_multiplier * stddev, "alert_level": mean_value + alert_multiplier * stddev}


def register(router: APIRouter) -> None:
    @router.post("/workbook-parity/statistical-alerts/calculate", status_code=201)
    def calculate_statistical_alert(request: StatisticalAlertRequest, current_user: account_models.User = Depends(get_current_active_user), db: Session = Depends(get_write_db)):
        amo_id = _amo_id(current_user)
        series = load_complete_series(db, amo_id, request)
        levels = calculate_levels(series, request.warning_multiplier, request.alert_multiplier)
        formula = f"warning = arithmetic mean + {request.warning_multiplier} × sample standard deviation; alert = arithmetic mean + {request.alert_multiplier} × sample standard deviation"
        result = ReliabilityStatisticalAlertResult(
            amo_id=amo_id, metric_code=request.metric_code, metric_label=request.metric_label, source_kind=request.source_kind,
            dataset_code=request.dataset_code.value if request.dataset_code else None, metric_field=request.metric_field,
            scope_type="AIRCRAFT" if request.aircraft_serial_number else "ATA" if request.ata_chapter else "FLEET",
            scope_value=request.aircraft_serial_number or request.ata_chapter, period_start=request.period_start, period_end=request.period_end,
            bucket=request.bucket, sample_size=levels["sample_size"], mean_value=levels["mean"], sample_stddev=levels["sample_stddev"],
            warning_multiplier=request.warning_multiplier, alert_multiplier=request.alert_multiplier, warning_level=levels["warning_level"],
            alert_level=levels["alert_level"], formula=formula, series=series, generated_by_user_id=current_user.id,
        )
        db.add(result)
        db.commit()
        db.refresh(result)
        return {"id": result.id, "metric_code": result.metric_code, "metric_label": result.metric_label, "source_kind": result.source_kind, "dataset_code": result.dataset_code, "scope_type": result.scope_type, "scope_value": result.scope_value, "period_start": result.period_start, "period_end": result.period_end, "bucket": result.bucket, "sample_size": result.sample_size, "mean": float(result.mean_value), "sample_stddev": float(result.sample_stddev), "warning_level": float(result.warning_level), "alert_level": float(result.alert_level), "formula": result.formula, "series": result.series, "generated_at": result.generated_at}
