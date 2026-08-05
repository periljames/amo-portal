from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_write_db
from amodb.security import get_current_active_user

from . import models
from .analytics_builder import build_dashboard
from .analytics_common import UTC, _end, _enum_value, _normalise_date, _start, _tenant_id
from .analytics_drilldown_endpoint import _drilldown_endpoint
from .analytics_types import DashboardResponse, DrilldownResponse, EngineMarker, EngineSeriesPoint, EngineSeriesResponse, EngineThreshold

def _dashboard_endpoint(
    period_start: date = Query(),
    period_end: date = Query(),
    bucket: str = Query(default="AUTO", pattern="^(AUTO|DAY|WEEK|MONTH)$"),
    aircraft: Optional[list[str]] = Query(default=None),
    aircraft_types: Optional[list[str]] = Query(default=None),
    ata_chapters: Optional[list[str]] = Query(default=None),
    stations: Optional[list[str]] = Query(default=None),
    event_types: Optional[list[str]] = Query(default=None),
    severities: Optional[list[str]] = Query(default=None),
    source_systems: Optional[list[str]] = Query(default=None),
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
) -> DashboardResponse:
    return build_dashboard(
        db,
        amo_id=_tenant_id(current_user),
        period_start=period_start,
        period_end=period_end,
        bucket_requested=bucket,
        aircraft=aircraft or [],
        aircraft_types=aircraft_types or [],
        ata_chapters=ata_chapters or [],
        stations=stations or [],
        event_types=event_types or [],
        severities=severities or [],
        source_systems=source_systems or [],
    )

def _engine_series_endpoint(
    period_start: date = Query(),
    period_end: date = Query(),
    metric: str = Query(min_length=1, max_length=120),
    aircraft: Optional[list[str]] = Query(default=None),
    engine_positions: Optional[list[str]] = Query(default=None),
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
) -> EngineSeriesResponse:
    if period_end < period_start:
        raise HTTPException(status_code=422, detail="Period end must be on or after period start.")
    if (period_end - period_start).days > 730:
        raise HTTPException(status_code=422, detail="Engine chart windows are limited to 731 days.")
    amo_id = _tenant_id(current_user)
    query = db.query(models.EngineFlightSnapshot).filter(
        models.EngineFlightSnapshot.amo_id == amo_id,
        models.EngineFlightSnapshot.flight_date >= period_start,
        models.EngineFlightSnapshot.flight_date <= period_end,
    )
    if aircraft:
        query = query.filter(models.EngineFlightSnapshot.aircraft_serial_number.in_(aircraft))
    if engine_positions:
        query = query.filter(models.EngineFlightSnapshot.engine_position.in_(engine_positions))
    rows = query.order_by(models.EngineFlightSnapshot.flight_date.asc()).limit(50_000).all()
    series: dict[str, list[EngineSeriesPoint]] = defaultdict(list)
    unit: str | None = None
    for row in rows:
        payload = row.metrics or {}
        value = payload.get(metric)
        if not isinstance(value, (int, float, Decimal)) or isinstance(value, bool):
            continue
        series_key = f"{row.aircraft_serial_number} · {row.engine_position}"
        series[series_key].append(
            EngineSeriesPoint(
                timestamp=datetime.combine(row.flight_date, time.min, tzinfo=UTC).isoformat(),
                value=float(value),
                aircraft_serial_number=row.aircraft_serial_number,
                engine_position=row.engine_position,
                engine_serial_number=row.engine_serial_number,
            )
        )
        candidate_unit = payload.get(f"{metric}_unit") or payload.get("unit")
        if isinstance(candidate_unit, str) and candidate_unit.strip():
            unit = candidate_unit.strip()
    threshold_sets = db.query(models.ThresholdSet).filter(models.ThresholdSet.amo_id == amo_id).all()
    threshold_by_id = {row.id: row for row in threshold_sets}
    threshold_ids = list(threshold_by_id)
    rules = (
        db.query(models.AlertRule)
        .filter(
            models.AlertRule.threshold_set_id.in_(threshold_ids),
            models.AlertRule.kpi_code == metric,
            models.AlertRule.enabled.is_(True),
        )
        .all()
        if threshold_ids
        else []
    )
    thresholds = []
    for rule in rules:
        threshold_set = threshold_by_id.get(rule.threshold_set_id)
        scope = threshold_set.scope_value if threshold_set else None
        if threshold_set and _enum_value(threshold_set.scope_type) not in {"ENGINE", "FLEET", "AIRCRAFT"}:
            continue
        thresholds.append(
            EngineThreshold(
                label=f"{_enum_value(rule.severity).title()} {metric}",
                value=float(rule.threshold_value),
                comparator=_enum_value(rule.comparator),
                severity=_enum_value(rule.severity),
                scope=scope,
            )
        )

    status_query = db.query(models.EngineTrendStatus).filter(models.EngineTrendStatus.amo_id == amo_id)
    if aircraft:
        status_query = status_query.filter(models.EngineTrendStatus.aircraft_serial_number.in_(aircraft))
    if engine_positions:
        status_query = status_query.filter(models.EngineTrendStatus.engine_position.in_(engine_positions))
    markers = []
    for row in status_query.all():
        marker_date = _normalise_date(row.last_trend_date)
        if not marker_date or marker_date < period_start or marker_date > period_end:
            continue
        status_value = _enum_value(row.current_status) or "NOT_EVALUATED"
        markers.append(
            EngineMarker(
                timestamp=marker_date.isoformat(),
                label=f"{row.aircraft_serial_number} · {row.engine_position}: {status_value}",
                status=status_value,
                aircraft_serial_number=row.aircraft_serial_number,
                engine_position=row.engine_position,
            )
        )

    return EngineSeriesResponse(
        generated_at=datetime.now(UTC),
        period_start=period_start,
        period_end=period_end,
        metric=metric,
        unit=unit,
        series=dict(series),
        thresholds=thresholds,
        markers=markers,
    )

def register(router: APIRouter) -> None:
    router.add_api_route(
        "/analytics-dashboard",
        _dashboard_endpoint,
        methods=["GET"],
        response_model=DashboardResponse,
        summary="Build denominator-aware Reliability dashboard analytics",
    )
    router.add_api_route(
        "/analytics-dashboard/engine-series",
        _engine_series_endpoint,
        methods=["GET"],
        response_model=EngineSeriesResponse,
        summary="Read a selected engine parameter time series",
    )
    router.add_api_route(
        "/analytics-dashboard/drilldown",
        _drilldown_endpoint,
        methods=["GET"],
        response_model=DrilldownResponse,
        summary="Resolve chart selections to supporting controlled records",
    )
