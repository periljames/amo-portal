from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.fleet import models as fleet_models

from . import advanced_models, models, operational_sources
from .analytics_common import CLOSED_ACTION_STATES, OPEN_DEFERRAL_STATES, UTC, _aircraft_type_label, _bucket_key, _enum_value, _ratio, _safe_float
from .analytics_types import ChartPoint, DashboardFilterOptions

def _engine_status_points(rows: list[models.EngineTrendStatus]) -> list[ChartPoint]:
    counts = Counter(_enum_value(row.current_status) or "NOT_EVALUATED" for row in rows)
    return [
        ChartPoint(
            key=key,
            label=key.replace("_", " "),
            metrics={"count": count},
            drilldown={"dimension": "engine_status", "key": key},
        )
        for key, count in counts.most_common()
    ]

def _source_health_points(
    sources: list[advanced_models.ReliabilitySource],
    batches: list[advanced_models.ReliabilityIngestionBatch],
    now: datetime,
) -> list[ChartPoint]:
    batch_by_source: dict[str, list[advanced_models.ReliabilityIngestionBatch]] = defaultdict(list)
    for batch in batches:
        batch_by_source[batch.source_id].append(batch)
    points: list[ChartPoint] = []
    for source in sources:
        source_batches = batch_by_source.get(source.id, [])
        invalid = sum(int(row.invalid_count or 0) for row in source_batches)
        received = sum(int(row.record_count or 0) for row in source_batches)
        last = source.last_success_at or source.last_received_at
        age_days = None
        if last:
            if last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
            age_days = max((now - last).total_seconds() / 86400, 0)
        points.append(
            ChartPoint(
                key=source.code,
                label=source.name,
                metrics={
                    "records": received,
                    "invalid_records": invalid,
                    "invalid_rate_pct": _ratio(invalid, received, 100),
                    "age_days": None if age_days is None else round(age_days, 2),
                    "failed_batches": sum(row.status == "FAILED" for row in source_batches),
                },
                drilldown={"dimension": "source", "key": source.code},
            )
        )
    return points

def _data_quality_points(rows: list[advanced_models.ReliabilityDataQualityIssue]) -> list[ChartPoint]:
    counts = Counter((row.issue_code or "UNCLASSIFIED", row.severity or "MEDIUM", row.status or "OPEN") for row in rows)
    grouped: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for (code, severity, issue_status), count in counts.items():
        grouped[code]["count"] += count
        grouped[code][severity.lower()] += count
        grouped[code]["open"] += count if issue_status not in {"RESOLVED", "CLOSED"} else 0
    return [
        ChartPoint(
            key=code,
            label=code.replace("_", " ").title(),
            metrics=dict(values),
            drilldown={"dimension": "data_quality", "key": code},
        )
        for code, values in sorted(grouped.items(), key=lambda item: item[1]["open"], reverse=True)
    ]

def _engine_metric_options(snapshots: list[models.EngineFlightSnapshot]) -> list[str]:
    frequency: Counter[str] = Counter()
    for snapshot in snapshots:
        for key, value in (snapshot.metrics or {}).items():
            if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
                frequency[str(key)] += 1
    return [key for key, _ in frequency.most_common(50)]

def _filter_options(
    *,
    events: list[models.ReliabilityEvent],
    aircraft_rows: list[fleet_models.Aircraft],
    engine_statuses: list[models.EngineTrendStatus],
    engine_metrics: list[str],
) -> DashboardFilterOptions:
    return DashboardFilterOptions(
        aircraft=sorted({row.serial_number for row in aircraft_rows if row.serial_number} | {row.aircraft_serial_number for row in events if row.aircraft_serial_number} | {row.aircraft_serial_number for row in engine_statuses if row.aircraft_serial_number}),
        aircraft_types=sorted({_aircraft_type_label(row) for row in aircraft_rows}),
        ata_chapters=sorted({row.ata_chapter for row in events if row.ata_chapter}),
        stations=sorted({value for row in events for value in (row.origin_station, row.destination_station) if value}),
        event_types=sorted({_enum_value(row.event_type) for row in events}),
        severities=sorted({_enum_value(row.severity) for row in events if row.severity}),
        source_systems=sorted({row.source_system for row in events if row.source_system}),
        engine_positions=sorted({row.engine_position for row in engine_statuses if row.engine_position}),
        engine_metrics=engine_metrics,
    )
