from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable

from fastapi import HTTPException
from sqlalchemy import inspect as sa_inspect, or_
from sqlalchemy.orm import Session

from . import advanced_models, formal_reporting as core, models, operational_sources
from . import workbook_parity as wp
from .analytics_common import (
    _comparison_period,
    _end,
    _load_events,
    _load_utilisation,
    _resolve_aircraft_selection,
    _start,
)
from .formal_reporting_models import ReliabilityFormalReportSource


MAX_SOURCE_ROWS = core.MAX_SOURCE_ROWS


SOURCE_KIND = {
    "aircraft": "AIRCRAFT",
    "events": "RELIABILITY_EVENT",
    "utilisation": "AIRCRAFT_UTILISATION",
    "deferrals": "MEL_CDL_DEFERRAL",
    "fracas_cases": "FRACAS_CASE",
    "fracas_actions": "FRACAS_ACTION",
    "fracas_lifecycles": "FRACAS_LIFECYCLE",
    "effectiveness_reviews": "EFFECTIVENESS_REVIEW",
    "engine_statuses": "ENGINE_TREND_STATUS",
    "engine_snapshots": "ENGINE_FLIGHT_SNAPSHOT",
    "removals": "REMOVAL_EVENT",
    "shop_visits": "SHOP_VISIT",
    "oil_rates": "OIL_CONSUMPTION_RATE",
    "sources": "RELIABILITY_SOURCE",
    "batches": "INGESTION_BATCH",
    "data_quality": "DATA_QUALITY_ISSUE",
    "metric_definitions": "METRIC_DEFINITION",
    "workbook": "WORKBOOK_RECORD",
}

# This set mirrors every ORM source family read by analytics_builder.build_dashboard.
# A contract test keeps the list explicit so adding a new dashboard family requires a
# conscious formal-publication evidence decision rather than silently escaping the
# frozen source population.
DASHBOARD_SOURCE_FAMILIES = frozenset(
    {
        "aircraft",
        "events",
        "utilisation",
        "deferrals",
        "fracas_cases",
        "fracas_actions",
        "fracas_lifecycles",
        "effectiveness_reviews",
        "engine_statuses",
        "engine_snapshots",
        "removals",
        "shop_visits",
        "oil_rates",
        "sources",
        "batches",
        "data_quality",
        "metric_definitions",
    }
)


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_value(item) for item in value]
    return str(value)


def _row_snapshot_hash(row: Any) -> str:
    mapper = sa_inspect(row.__class__).mapper
    payload = {
        attribute.key: _json_value(getattr(row, attribute.key))
        for attribute in mapper.column_attrs
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _row_identity(row: Any) -> str:
    value = getattr(row, "id", None)
    if value not in (None, ""):
        return str(value)
    state = sa_inspect(row)
    if state.identity:
        return ":".join(str(item) for item in state.identity)
    raise HTTPException(status_code=422, detail=f"Formal source row {row.__class__.__name__} has no stable identity.")


def _row_hash(row: Any) -> str:
    for attribute in ("source_hash", "source_payload_hash", "payload_hash", "record_hash", "snapshot_hash"):
        value = getattr(row, attribute, None)
        if isinstance(value, str) and len(value) == 64:
            return value
    return _row_snapshot_hash(row)


def _source_date(row: Any) -> date | None:
    for attribute in (
        "event_date",
        "date",
        "occurred_at",
        "flight_date",
        "applied_at",
        "opened_at",
        "review_date",
        "removed_at",
        "window_end",
        "received_at",
        "created_at",
        "updated_at",
    ):
        value = getattr(row, attribute, None)
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
    return None


def _aircraft_serial(row: Any) -> str | None:
    value = getattr(row, "aircraft_serial_number", None)
    if value:
        return str(value)
    if row.__class__.__name__ == "Aircraft":
        value = getattr(row, "serial_number", None)
        return str(value) if value else None
    return None


def _reference_code(row: Any) -> str | None:
    for attribute in (
        "reference_code",
        "record_number",
        "case_number",
        "code",
        "external_id",
        "source_external_id",
        "flight_number",
        "serial_number",
    ):
        value = getattr(row, attribute, None)
        if value not in (None, ""):
            return str(value)[:128]
    return None


def _bounded(rows: Iterable[Any], family: str) -> list[Any]:
    materialised = list(rows)
    if len(materialised) > MAX_SOURCE_ROWS:
        raise HTTPException(
            status_code=422,
            detail=f"Controlled {family} population exceeds the {MAX_SOURCE_ROWS:,}-row formal freeze limit.",
        )
    return materialised


def _bounded_query(query, family: str) -> list[Any]:
    rows = query.limit(MAX_SOURCE_ROWS + 1).all()
    return _bounded(rows, family)


def _capture_rows(
    db: Session,
    report,
    rows: Iterable[Any],
    *,
    source_kind: str,
    seen: set[tuple[str, str]],
    dataset_code: str | None = None,
) -> None:
    for row in _bounded(rows, source_kind.lower()):
        source_id = _row_identity(row)
        key = (source_kind, source_id)
        if key in seen:
            continue
        seen.add(key)
        row_dataset = getattr(row, "dataset_code", None)
        db.add(
            ReliabilityFormalReportSource(
                amo_id=report.amo_id,
                report_id=report.id,
                source_kind=source_kind,
                source_id=source_id,
                source_hash=_row_hash(row),
                source_date=_source_date(row),
                dataset_code=(str(row_dataset)[:32] if row_dataset else dataset_code),
                aircraft_serial_number=_aircraft_serial(row),
                reference_code=_reference_code(row),
            )
        )


def _capture_dashboard_inputs(
    db: Session,
    report,
    *,
    selected_aircraft: set[str],
    aircraft_rows: list[Any],
    comparison_start: date,
    comparison_end: date,
    seen: set[tuple[str, str]],
) -> tuple[int, int]:
    amo_id = report.amo_id
    current_events = _load_events(
        db,
        amo_id=amo_id,
        period_start=report.period_start,
        period_end=report.period_end,
        aircraft=selected_aircraft,
        ata_chapters=set(),
        stations=set(),
        event_types=set(),
        severities=set(),
        source_systems=set(),
    )
    previous_events = _load_events(
        db,
        amo_id=amo_id,
        period_start=comparison_start,
        period_end=comparison_end,
        aircraft=selected_aircraft,
        ata_chapters=set(),
        stations=set(),
        event_types=set(),
        severities=set(),
        source_systems=set(),
    )
    current_utilisation = _load_utilisation(
        db,
        amo_id=amo_id,
        period_start=report.period_start,
        period_end=report.period_end,
        aircraft=selected_aircraft,
    )
    previous_utilisation = _load_utilisation(
        db,
        amo_id=amo_id,
        period_start=comparison_start,
        period_end=comparison_end,
        aircraft=selected_aircraft,
    )

    _capture_rows(db, report, aircraft_rows, source_kind=SOURCE_KIND["aircraft"], seen=seen, dataset_code="AIRCRAFT")
    _capture_rows(db, report, [*current_events, *previous_events], source_kind=SOURCE_KIND["events"], seen=seen, dataset_code="EVENT")
    _capture_rows(db, report, [*current_utilisation, *previous_utilisation], source_kind=SOURCE_KIND["utilisation"], seen=seen, dataset_code="UTILISATION")

    deferral_query = db.query(operational_sources.ReliabilityMelCdlDeferral).filter(
        operational_sources.ReliabilityMelCdlDeferral.amo_id == amo_id,
        operational_sources.ReliabilityMelCdlDeferral.applied_at <= _end(report.period_end),
    )
    if selected_aircraft:
        deferral_query = deferral_query.filter(
            operational_sources.ReliabilityMelCdlDeferral.aircraft_serial_number.in_(sorted(selected_aircraft))
        )
    deferrals = _bounded_query(deferral_query, "MEL/CDL deferral")
    _capture_rows(db, report, deferrals, source_kind=SOURCE_KIND["deferrals"], seen=seen, dataset_code="DEFERRAL")

    case_query = db.query(models.FRACASCase).filter(
        models.FRACASCase.amo_id == amo_id,
        models.FRACASCase.opened_at <= _end(report.period_end),
        or_(models.FRACASCase.closed_at.is_(None), models.FRACASCase.closed_at >= _start(report.period_start)),
    )
    if selected_aircraft:
        case_query = case_query.filter(models.FRACASCase.aircraft_serial_number.in_(sorted(selected_aircraft)))
    fracas_cases = _bounded_query(case_query, "FRACAS case")
    _capture_rows(db, report, fracas_cases, source_kind=SOURCE_KIND["fracas_cases"], seen=seen, dataset_code="FRACAS")

    case_ids = [row.id for row in fracas_cases]
    fracas_actions = (
        _bounded_query(db.query(models.FRACASAction).filter(models.FRACASAction.fracas_case_id.in_(case_ids)), "FRACAS action")
        if case_ids else []
    )
    _capture_rows(db, report, fracas_actions, source_kind=SOURCE_KIND["fracas_actions"], seen=seen, dataset_code="FRACAS")

    lifecycles = (
        _bounded_query(
            db.query(advanced_models.ReliabilityFracasLifecycle).filter(
                advanced_models.ReliabilityFracasLifecycle.amo_id == amo_id,
                advanced_models.ReliabilityFracasLifecycle.fracas_case_id.in_(case_ids),
            ),
            "FRACAS lifecycle",
        )
        if case_ids else []
    )
    _capture_rows(db, report, lifecycles, source_kind=SOURCE_KIND["fracas_lifecycles"], seen=seen, dataset_code="FRACAS")

    lifecycle_ids = [row.id for row in lifecycles]
    effectiveness_reviews = (
        _bounded_query(
            db.query(advanced_models.ReliabilityEffectivenessReview).filter(
                advanced_models.ReliabilityEffectivenessReview.amo_id == amo_id,
                advanced_models.ReliabilityEffectivenessReview.lifecycle_id.in_(lifecycle_ids),
                advanced_models.ReliabilityEffectivenessReview.review_date >= report.period_start,
                advanced_models.ReliabilityEffectivenessReview.review_date <= report.period_end,
            ),
            "effectiveness review",
        )
        if lifecycle_ids else []
    )
    _capture_rows(db, report, effectiveness_reviews, source_kind=SOURCE_KIND["effectiveness_reviews"], seen=seen, dataset_code="FRACAS")

    engine_query = db.query(models.EngineTrendStatus).filter(models.EngineTrendStatus.amo_id == amo_id)
    if selected_aircraft:
        engine_query = engine_query.filter(models.EngineTrendStatus.aircraft_serial_number.in_(sorted(selected_aircraft)))
    engine_statuses = _bounded_query(engine_query, "engine status")
    _capture_rows(db, report, engine_statuses, source_kind=SOURCE_KIND["engine_statuses"], seen=seen, dataset_code="ENGINE")

    snapshot_query = db.query(models.EngineFlightSnapshot).filter(
        models.EngineFlightSnapshot.amo_id == amo_id,
        models.EngineFlightSnapshot.flight_date >= report.period_start,
        models.EngineFlightSnapshot.flight_date <= report.period_end,
    )
    if selected_aircraft:
        snapshot_query = snapshot_query.filter(models.EngineFlightSnapshot.aircraft_serial_number.in_(sorted(selected_aircraft)))
    snapshots = snapshot_query.limit(20_000).all()
    _capture_rows(db, report, snapshots, source_kind=SOURCE_KIND["engine_snapshots"], seen=seen, dataset_code="ENGINE")

    removal_query = db.query(models.RemovalEvent).filter(
        models.RemovalEvent.amo_id == amo_id,
        models.RemovalEvent.removed_at >= _start(report.period_start),
        models.RemovalEvent.removed_at <= _end(report.period_end),
    )
    if selected_aircraft:
        removal_query = removal_query.filter(models.RemovalEvent.aircraft_serial_number.in_(sorted(selected_aircraft)))
    removals = _bounded_query(removal_query.order_by(models.RemovalEvent.removed_at.asc()), "removal event")
    _capture_rows(db, report, removals, source_kind=SOURCE_KIND["removals"], seen=seen, dataset_code="COMPONENT")

    shop_visits = _bounded_query(
        db.query(models.ShopVisit).filter(
            models.ShopVisit.amo_id == amo_id,
            models.ShopVisit.created_at >= _start(report.period_start),
            models.ShopVisit.created_at <= _end(report.period_end),
        ).order_by(models.ShopVisit.created_at.asc()),
        "shop visit",
    )
    _capture_rows(db, report, shop_visits, source_kind=SOURCE_KIND["shop_visits"], seen=seen, dataset_code="COMPONENT")

    oil_query = db.query(models.OilConsumptionRate).filter(
        models.OilConsumptionRate.amo_id == amo_id,
        models.OilConsumptionRate.window_end >= report.period_start,
        models.OilConsumptionRate.window_start <= report.period_end,
    )
    if selected_aircraft:
        oil_query = oil_query.filter(models.OilConsumptionRate.aircraft_serial_number.in_(sorted(selected_aircraft)))
    oil_rates = _bounded_query(oil_query.order_by(models.OilConsumptionRate.window_end.asc()), "oil consumption")
    _capture_rows(db, report, oil_rates, source_kind=SOURCE_KIND["oil_rates"], seen=seen, dataset_code="ENGINE")

    sources = _bounded_query(
        db.query(advanced_models.ReliabilitySource).filter(advanced_models.ReliabilitySource.amo_id == amo_id),
        "Reliability source configuration",
    )
    _capture_rows(db, report, sources, source_kind=SOURCE_KIND["sources"], seen=seen, dataset_code="SOURCE")

    source_ids = [row.id for row in sources]
    batches = (
        _bounded_query(
            db.query(advanced_models.ReliabilityIngestionBatch).filter(
                advanced_models.ReliabilityIngestionBatch.amo_id == amo_id,
                advanced_models.ReliabilityIngestionBatch.source_id.in_(source_ids),
                advanced_models.ReliabilityIngestionBatch.received_at >= _start(report.period_start),
                advanced_models.ReliabilityIngestionBatch.received_at <= _end(report.period_end),
            ),
            "Reliability ingestion batch",
        )
        if source_ids else []
    )
    _capture_rows(db, report, batches, source_kind=SOURCE_KIND["batches"], seen=seen, dataset_code="SOURCE")

    quality_issues = _bounded_query(
        db.query(advanced_models.ReliabilityDataQualityIssue).filter(
            advanced_models.ReliabilityDataQualityIssue.amo_id == amo_id,
            advanced_models.ReliabilityDataQualityIssue.created_at <= _end(report.period_end),
            or_(
                advanced_models.ReliabilityDataQualityIssue.resolved_at.is_(None),
                advanced_models.ReliabilityDataQualityIssue.resolved_at >= _start(report.period_start),
            ),
        ),
        "Reliability data-quality issue",
    )
    _capture_rows(db, report, quality_issues, source_kind=SOURCE_KIND["data_quality"], seen=seen, dataset_code="QUALITY")

    metric_definitions = db.query(advanced_models.ReliabilityMetricDefinition).filter(
        advanced_models.ReliabilityMetricDefinition.amo_id == amo_id,
        advanced_models.ReliabilityMetricDefinition.active.is_(True),
    ).order_by(advanced_models.ReliabilityMetricDefinition.code.asc()).limit(500).all()
    _capture_rows(db, report, metric_definitions, source_kind=SOURCE_KIND["metric_definitions"], seen=seen, dataset_code="FORMULA")

    return len(previous_events), len(previous_utilisation)


def freeze_sources(db: Session, report, selected_aircraft: set[str]) -> dict[str, Any]:
    aircraft_types = {
        str(item).strip()
        for item in (report.effectivity_json or {}).get("aircraft_types", [])
        if str(item).strip()
    }
    effective_aircraft, aircraft_rows = _resolve_aircraft_selection(
        db,
        amo_id=report.amo_id,
        aircraft=selected_aircraft,
        aircraft_types=aircraft_types,
    )

    # Preserve the existing workbook/canonical source capture, but feed it the
    # resolved aircraft set so type-only effectivity cannot accidentally hash the
    # whole fleet while the dashboard calculates a narrower selection.
    population = _ORIGINAL_FREEZE(db, report, effective_aircraft)
    db.flush()

    existing = db.query(ReliabilityFormalReportSource).filter(
        ReliabilityFormalReportSource.report_id == report.id,
        ReliabilityFormalReportSource.amo_id == report.amo_id,
    ).all()
    seen = {(row.source_kind, row.source_id) for row in existing}

    comparison_start, comparison_end = _comparison_period(report.period_start, report.period_end)

    # Workbook records are provenance for canonical events. Retain both the
    # current and comparison windows even though dashboard arithmetic consumes
    # the canonical/event tables rather than raw workbook rows directly.
    cutoff = core._source_cutoff(report)
    workbook_query = db.query(wp.ReliabilityWorkbookRecord).filter(
        wp.ReliabilityWorkbookRecord.amo_id == report.amo_id,
        wp.ReliabilityWorkbookRecord.event_date >= comparison_start,
        wp.ReliabilityWorkbookRecord.event_date <= report.period_end,
        wp.ReliabilityWorkbookRecord.created_at <= cutoff,
        wp.ReliabilityWorkbookRecord.status.in_(["APPROVED", "CLOSED"]),
    )
    if effective_aircraft:
        workbook_query = workbook_query.filter(
            wp.ReliabilityWorkbookRecord.aircraft_serial_number.in_(sorted(effective_aircraft))
        )
    workbook_rows = _bounded_query(
        workbook_query.order_by(wp.ReliabilityWorkbookRecord.event_date, wp.ReliabilityWorkbookRecord.id),
        "workbook comparison/current",
    )
    _capture_rows(
        db,
        report,
        workbook_rows,
        source_kind=SOURCE_KIND["workbook"],
        seen=seen,
    )

    previous_event_count, previous_utilisation_count = _capture_dashboard_inputs(
        db,
        report,
        selected_aircraft=effective_aircraft,
        aircraft_rows=aircraft_rows,
        comparison_start=comparison_start,
        comparison_end=comparison_end,
        seen=seen,
    )
    db.flush()

    identity_rows = db.query(
        ReliabilityFormalReportSource.source_kind,
        ReliabilityFormalReportSource.source_id,
        ReliabilityFormalReportSource.source_hash,
    ).filter(
        ReliabilityFormalReportSource.report_id == report.id,
        ReliabilityFormalReportSource.amo_id == report.amo_id,
    ).all()
    identities = [
        f"{row.source_kind}:{row.source_id}:{row.source_hash or ''}"
        for row in identity_rows
    ]
    population_hash = hashlib.sha256("\n".join(sorted(identities)).encode("utf-8")).hexdigest()

    count_rows = db.query(
        ReliabilityFormalReportSource.source_kind,
        ReliabilityFormalReportSource.id,
    ).filter(
        ReliabilityFormalReportSource.report_id == report.id,
        ReliabilityFormalReportSource.amo_id == report.amo_id,
    ).all()
    family_counts: dict[str, int] = {}
    for row in count_rows:
        family_counts[row.source_kind] = family_counts.get(row.source_kind, 0) + 1

    return {
        **population,
        "source_identity_sha256": population_hash,
        "source_record_count": len(identity_rows),
        "source_family_counts": dict(sorted(family_counts.items())),
        "comparison_period_start": comparison_start.isoformat(),
        "comparison_period_end": comparison_end.isoformat(),
        "comparison_canonical_event_count": previous_event_count,
        "comparison_utilisation_record_count": previous_utilisation_count,
        "effective_aircraft_serial_numbers": sorted(effective_aircraft),
        "dashboard_source_family_contract": sorted(DASHBOARD_SOURCE_FAMILIES),
        "evidence_scope": "CURRENT_AND_COMPARISON_DASHBOARD_INPUTS",
    }


_ORIGINAL_FREEZE = core._freeze_sources


def apply() -> None:
    if getattr(core, "_formal_source_capture_applied", False):
        return
    core._freeze_sources = freeze_sources
    core._formal_source_capture_applied = True
