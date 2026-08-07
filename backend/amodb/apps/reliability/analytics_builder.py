from __future__ import annotations

from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from . import advanced_models, models, operational_sources
from .analytics_common import (
    UTC,
    _bucket_for_window,
    _comparison_period,
    _end,
    _load_events,
    _load_utilisation,
    _resolve_aircraft_selection,
    _start,
    _utilisation_totals,
)
from .analytics_component_charts import _component_reliability
from .analytics_component_extended import _oil_consumption_points, _removal_age_distribution, _shop_visit_trend
from .analytics_deferrals import _deferral_charts
from .analytics_event_charts import _aircraft_performance, _ata_pareto, _event_mix, _route_delay, _station_delay, _time_series
from .analytics_formulae import build_formula_catalog
from .analytics_fracas import _fracas_action_charts, _fracas_charts
from .analytics_health import _data_quality_points, _engine_metric_options, _engine_status_points, _filter_options, _source_health_points
from .analytics_metrics import _summary_metrics
from .analytics_types import DashboardResponse


def build_dashboard(
    db: Session,
    *,
    amo_id: str,
    period_start: date,
    period_end: date,
    bucket_requested: str,
    aircraft: list[str],
    aircraft_types: list[str],
    ata_chapters: list[str],
    stations: list[str],
    event_types: list[str],
    severities: list[str],
    source_systems: list[str],
) -> DashboardResponse:
    if period_end < period_start:
        raise HTTPException(status_code=422, detail="Period end must be on or after period start.")
    if (period_end - period_start).days > 730:
        raise HTTPException(status_code=422, detail="Dashboard windows are limited to 731 days.")

    now = datetime.now(UTC)
    comparison_start, comparison_end = _comparison_period(period_start, period_end)
    bucket = _bucket_for_window(period_start, period_end, bucket_requested)
    selected_aircraft, aircraft_rows = _resolve_aircraft_selection(
        db, amo_id=amo_id, aircraft=aircraft, aircraft_types=aircraft_types
    )
    selected_ata = set(ata_chapters)
    selected_stations = set(stations)
    selected_types = set(event_types)
    selected_severities = set(severities)
    selected_sources = set(source_systems)

    current_events = _load_events(
        db,
        amo_id=amo_id,
        period_start=period_start,
        period_end=period_end,
        aircraft=selected_aircraft,
        ata_chapters=selected_ata,
        stations=selected_stations,
        event_types=selected_types,
        severities=selected_severities,
        source_systems=selected_sources,
    )
    previous_events = _load_events(
        db,
        amo_id=amo_id,
        period_start=comparison_start,
        period_end=comparison_end,
        aircraft=selected_aircraft,
        ata_chapters=selected_ata,
        stations=selected_stations,
        event_types=selected_types,
        severities=selected_severities,
        source_systems=selected_sources,
    )
    current_utilisation = _load_utilisation(
        db, amo_id=amo_id, period_start=period_start, period_end=period_end, aircraft=selected_aircraft
    )
    previous_utilisation = _load_utilisation(
        db, amo_id=amo_id, period_start=comparison_start, period_end=comparison_end, aircraft=selected_aircraft
    )

    deferral_query = db.query(operational_sources.ReliabilityMelCdlDeferral).filter(
        operational_sources.ReliabilityMelCdlDeferral.amo_id == amo_id,
        operational_sources.ReliabilityMelCdlDeferral.applied_at <= _end(period_end),
    )
    if selected_aircraft:
        deferral_query = deferral_query.filter(
            operational_sources.ReliabilityMelCdlDeferral.aircraft_serial_number.in_(sorted(selected_aircraft))
        )
    if selected_ata:
        deferral_query = deferral_query.filter(
            operational_sources.ReliabilityMelCdlDeferral.ata_chapter.in_(sorted(selected_ata))
        )
    deferrals = deferral_query.all()

    case_query = db.query(models.FRACASCase).filter(
        models.FRACASCase.amo_id == amo_id,
        models.FRACASCase.opened_at <= _end(period_end),
        or_(models.FRACASCase.closed_at.is_(None), models.FRACASCase.closed_at >= _start(period_start)),
    )
    if selected_aircraft:
        case_query = case_query.filter(models.FRACASCase.aircraft_serial_number.in_(sorted(selected_aircraft)))
    fracas_cases = case_query.all()
    case_ids = [row.id for row in fracas_cases]
    fracas_actions = (
        db.query(models.FRACASAction).filter(models.FRACASAction.fracas_case_id.in_(case_ids)).all()
        if case_ids else []
    )
    lifecycles = (
        db.query(advanced_models.ReliabilityFracasLifecycle).filter(
            advanced_models.ReliabilityFracasLifecycle.amo_id == amo_id,
            advanced_models.ReliabilityFracasLifecycle.fracas_case_id.in_(case_ids),
        ).all()
        if case_ids else []
    )
    lifecycle_ids = [row.id for row in lifecycles]
    effectiveness_reviews = (
        db.query(advanced_models.ReliabilityEffectivenessReview).filter(
            advanced_models.ReliabilityEffectivenessReview.amo_id == amo_id,
            advanced_models.ReliabilityEffectivenessReview.lifecycle_id.in_(lifecycle_ids),
            advanced_models.ReliabilityEffectivenessReview.review_date >= period_start,
            advanced_models.ReliabilityEffectivenessReview.review_date <= period_end,
        ).all()
        if lifecycle_ids else []
    )

    engine_query = db.query(models.EngineTrendStatus).filter(models.EngineTrendStatus.amo_id == amo_id)
    if selected_aircraft:
        engine_query = engine_query.filter(models.EngineTrendStatus.aircraft_serial_number.in_(sorted(selected_aircraft)))
    engine_statuses = engine_query.all()

    snapshot_query = db.query(models.EngineFlightSnapshot).filter(
        models.EngineFlightSnapshot.amo_id == amo_id,
        models.EngineFlightSnapshot.flight_date >= period_start,
        models.EngineFlightSnapshot.flight_date <= period_end,
    )
    if selected_aircraft:
        snapshot_query = snapshot_query.filter(
            models.EngineFlightSnapshot.aircraft_serial_number.in_(sorted(selected_aircraft))
        )
    snapshots = snapshot_query.limit(20_000).all()
    engine_metrics = _engine_metric_options(snapshots)

    removal_query = db.query(models.RemovalEvent).filter(
        models.RemovalEvent.amo_id == amo_id,
        models.RemovalEvent.removed_at >= _start(period_start),
        models.RemovalEvent.removed_at <= _end(period_end),
    )
    if selected_aircraft:
        removal_query = removal_query.filter(models.RemovalEvent.aircraft_serial_number.in_(sorted(selected_aircraft)))
    removal_events = removal_query.order_by(models.RemovalEvent.removed_at.asc()).all()

    shop_visits = db.query(models.ShopVisit).filter(
        models.ShopVisit.amo_id == amo_id,
        models.ShopVisit.created_at >= _start(period_start),
        models.ShopVisit.created_at <= _end(period_end),
    ).order_by(models.ShopVisit.created_at.asc()).all()

    oil_query = db.query(models.OilConsumptionRate).filter(
        models.OilConsumptionRate.amo_id == amo_id,
        models.OilConsumptionRate.window_end >= period_start,
        models.OilConsumptionRate.window_start <= period_end,
    )
    if selected_aircraft:
        oil_query = oil_query.filter(models.OilConsumptionRate.aircraft_serial_number.in_(sorted(selected_aircraft)))
    oil_rates = oil_query.order_by(models.OilConsumptionRate.window_end.asc()).all()

    sources = db.query(advanced_models.ReliabilitySource).filter(
        advanced_models.ReliabilitySource.amo_id == amo_id
    ).all()
    source_ids = [row.id for row in sources]
    batches = (
        db.query(advanced_models.ReliabilityIngestionBatch).filter(
            advanced_models.ReliabilityIngestionBatch.amo_id == amo_id,
            advanced_models.ReliabilityIngestionBatch.source_id.in_(source_ids),
            advanced_models.ReliabilityIngestionBatch.received_at >= _start(period_start),
            advanced_models.ReliabilityIngestionBatch.received_at <= _end(period_end),
        ).all()
        if source_ids else []
    )
    data_quality_issues = db.query(advanced_models.ReliabilityDataQualityIssue).filter(
        advanced_models.ReliabilityDataQualityIssue.amo_id == amo_id,
        advanced_models.ReliabilityDataQualityIssue.created_at <= _end(period_end),
        or_(
            advanced_models.ReliabilityDataQualityIssue.resolved_at.is_(None),
            advanced_models.ReliabilityDataQualityIssue.resolved_at >= _start(period_start),
        ),
    ).all()
    metric_definitions = db.query(advanced_models.ReliabilityMetricDefinition).filter(
        advanced_models.ReliabilityMetricDefinition.amo_id == amo_id,
        advanced_models.ReliabilityMetricDefinition.active.is_(True),
    ).order_by(advanced_models.ReliabilityMetricDefinition.code.asc()).limit(500).all()

    (
        deferral_status,
        deferral_expiry,
        deferral_categories,
        deferral_extensions,
        deferral_repeats,
        deferral_closure,
    ) = _deferral_charts(deferrals, now)
    fracas_stages, fracas_ageing, root_causes, effectiveness = _fracas_charts(
        fracas_cases, lifecycles, effectiveness_reviews, now
    )
    fracas_action_status, fracas_action_trend, fracas_reopened = _fracas_action_charts(
        fracas_actions,
        lifecycles,
        period_start=period_start,
        period_end=period_end,
        bucket=bucket,
        now=now,
    )
    utilisation_totals = _utilisation_totals(current_utilisation)
    total_fh = utilisation_totals["flight_hours"]
    total_fc = utilisation_totals["flight_cycles"]

    warnings: list[str] = []
    if not current_utilisation:
        warnings.append(
            "No aircraft utilisation exposure is available for the selected period. "
            "Normalised rates and dispatch reliability are withheld."
        )
    if len(snapshots) >= 20_000:
        warnings.append(
            "Engine metric discovery reached the 20,000-snapshot scan cap. "
            "Narrow the date or aircraft filters for complete metric options."
        )
    if any(row.aircraft_serial_number is None for row in current_events):
        warnings.append("Some events are not allocated to an aircraft and appear under Fleet/Unallocated.")
    if any(not row.ata_chapter for row in current_events):
        warnings.append("Some events do not have an ATA chapter and appear under Unallocated ATA.")

    return DashboardResponse(
        generated_at=now,
        period_start=period_start,
        period_end=period_end,
        comparison_start=comparison_start,
        comparison_end=comparison_end,
        bucket=bucket,
        filters=_filter_options(
            events=current_events,
            aircraft_rows=aircraft_rows,
            engine_statuses=engine_statuses,
            engine_metrics=engine_metrics,
        ),
        formulae=build_formula_catalog(metric_definitions),
        summary=_summary_metrics(
            current_events=current_events,
            previous_events=previous_events,
            current_utilisation=current_utilisation,
            previous_utilisation=previous_utilisation,
            deferrals=deferrals,
            fracas_cases=fracas_cases,
            fracas_actions=fracas_actions,
            engine_statuses=engine_statuses,
            data_quality_issues=data_quality_issues,
            effectiveness_reviews=effectiveness_reviews,
            now=now,
        ),
        time_series=_time_series(current_events, current_utilisation, bucket),
        event_mix=_event_mix(current_events),
        ata_pareto=_ata_pareto(current_events),
        aircraft_performance=_aircraft_performance(current_events, current_utilisation),
        station_delay=_station_delay(current_events),
        route_delay=_route_delay(current_events),
        component_reliability=_component_reliability(current_events, total_fh, total_fc),
        component_removal_age=_removal_age_distribution(removal_events),
        shop_visit_trend=_shop_visit_trend(shop_visits, bucket),
        oil_consumption=_oil_consumption_points(oil_rates),
        deferral_status=deferral_status,
        deferral_expiry=deferral_expiry,
        deferral_categories=deferral_categories,
        deferral_extensions=deferral_extensions,
        deferral_repeats=deferral_repeats,
        deferral_closure=deferral_closure,
        fracas_stages=fracas_stages,
        fracas_ageing=fracas_ageing,
        root_causes=root_causes,
        effectiveness=effectiveness,
        fracas_actions=fracas_action_status,
        fracas_action_trend=fracas_action_trend,
        fracas_reopened=fracas_reopened,
        engine_status=_engine_status_points(engine_statuses),
        source_health=_source_health_points(sources, batches, now),
        data_quality=_data_quality_points(data_quality_issues),
        warnings=warnings,
    )
