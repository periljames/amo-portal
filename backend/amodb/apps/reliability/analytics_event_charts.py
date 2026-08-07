from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from . import advanced_models, models, operational_sources
from .analytics_common import (
    CANCELLATION_EVENT_TYPES, CLOSED_ACTION_STATES, DELAY_EVENT_TYPES, DISPATCH_EVENT_TYPES, REPEAT_EVENT_TYPES,
    SHOP_EVENT_TYPES, UNSCHEDULED_REMOVAL_TYPES, OPEN_DEFERRAL_STATES, UTC,
    _bucket_key, _delta, _enum_value, _metric_status, _normalise_date, _ratio,
    _safe_float, _event_totals, _utilisation_totals,
)
from .analytics_types import ChartPoint, DashboardMetric

def _time_series(
    events: list[models.ReliabilityEvent],
    utilisation: list[models.AircraftUtilizationDaily],
    bucket: str,
) -> list[ChartPoint]:
    event_buckets: dict[str, dict[str, Any]] = {}
    labels: dict[str, str] = {}
    for event in events:
        occurred = _normalise_date(event.occurred_at)
        if not occurred:
            continue
        key, label = _bucket_key(occurred, bucket)
        labels[key] = label
        row = event_buckets.setdefault(key, defaultdict(float))
        event_type = _enum_value(event.event_type)
        row["events"] += 1
        row["delay_minutes"] += max(int(event.delay_minutes or 0), 0)
        if event_type in DISPATCH_EVENT_TYPES:
            row["dispatch_events"] += 1
        if event_type in DELAY_EVENT_TYPES:
            row["delays"] += 1
        if event_type in CANCELLATION_EVENT_TYPES:
            row["cancellations"] += 1
        if event_type in REPEAT_EVENT_TYPES:
            row["repeat_defects"] += 1
        if event_type in UNSCHEDULED_REMOVAL_TYPES:
            row["unscheduled_removals"] += 1
        if event_type == "SCHEDULED_REMOVAL":
            row["scheduled_removals"] += 1
        if event_type == "SHOP_FINDING":
            row["shop_findings"] += 1
        if event_type == "NO_FAULT_FOUND":
            row["nff"] += 1

    exposure_buckets: dict[str, dict[str, float]] = {}
    for row in utilisation:
        key, label = _bucket_key(row.date, bucket)
        labels[key] = label
        exposure = exposure_buckets.setdefault(key, defaultdict(float))
        exposure["flight_hours"] += _safe_float(row.flight_hours)
        exposure["flight_cycles"] += _safe_float(row.cycles)

    points: list[ChartPoint] = []
    for key in sorted(set(event_buckets) | set(exposure_buckets)):
        event_values = event_buckets.get(key, {})
        exposure = exposure_buckets.get(key, {})
        events_count = float(event_values.get("events", 0))
        dispatch = float(event_values.get("dispatch_events", 0))
        fh = float(exposure.get("flight_hours", 0))
        fc = float(exposure.get("flight_cycles", 0))
        points.append(
            ChartPoint(
                key=key,
                label=labels.get(key, key),
                metrics={
                    "events": int(events_count),
                    "dispatch_events": int(dispatch),
                    "delays": int(event_values.get("delays", 0)),
                    "cancellations": int(event_values.get("cancellations", 0)),
                    "repeat_defects": int(event_values.get("repeat_defects", 0)),
                    "unscheduled_removals": int(event_values.get("unscheduled_removals", 0)),
                    "scheduled_removals": int(event_values.get("scheduled_removals", 0)),
                    "shop_findings": int(event_values.get("shop_findings", 0)),
                    "nff": int(event_values.get("nff", 0)),
                    "delay_minutes": int(event_values.get("delay_minutes", 0)),
                    "flight_hours": round(fh, 3),
                    "flight_cycles": round(fc, 3),
                    "event_rate_per_100_fh": _ratio(events_count, fh, 100),
                    "dispatch_reliability_pct": _ratio(max(fc - dispatch, 0), fc, 100),
                },
                drilldown={"dimension": "period", "key": key, "bucket": bucket},
            )
        )
    return points

def _event_mix(events: list[models.ReliabilityEvent]) -> list[ChartPoint]:
    counts = Counter(_enum_value(event.event_type) for event in events)
    delays: dict[str, int] = defaultdict(int)
    for event in events:
        delays[_enum_value(event.event_type)] += max(int(event.delay_minutes or 0), 0)
    return [
        ChartPoint(
            key=event_type,
            label=event_type.replace("_", " ").title(),
            metrics={"count": count, "delay_minutes": delays[event_type]},
            drilldown={"dimension": "event_type", "key": event_type},
        )
        for event_type, count in counts.most_common()
    ]

def _ata_pareto(events: list[models.ReliabilityEvent]) -> list[ChartPoint]:
    counts = Counter((event.ata_chapter or "UNALLOCATED") for event in events)
    delay_minutes: dict[str, int] = defaultdict(int)
    repeat_defects: dict[str, int] = defaultdict(int)
    for event in events:
        key = event.ata_chapter or "UNALLOCATED"
        delay_minutes[key] += max(int(event.delay_minutes or 0), 0)
        repeat_defects[key] += int(_enum_value(event.event_type) == "REPEAT_DEFECT")
    total = sum(counts.values()) or 1
    cumulative = 0
    result: list[ChartPoint] = []
    for ata, count in counts.most_common(20):
        cumulative += count
        result.append(
            ChartPoint(
                key=ata,
                label=f"ATA {ata}" if ata != "UNALLOCATED" else "Unallocated ATA",
                metrics={
                    "count": count,
                    "delay_minutes": delay_minutes[ata],
                    "repeat_defects": repeat_defects[ata],
                    "cumulative_pct": round((cumulative / total) * 100, 2),
                },
                drilldown={"dimension": "ata", "key": ata},
            )
        )
    return result

def _aircraft_performance(
    events: list[models.ReliabilityEvent],
    utilisation: list[models.AircraftUtilizationDaily],
) -> list[ChartPoint]:
    grouped: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for event in events:
        key = event.aircraft_serial_number or "FLEET/UNALLOCATED"
        event_type = _enum_value(event.event_type)
        grouped[key]["events"] += 1
        grouped[key]["delay_minutes"] += max(int(event.delay_minutes or 0), 0)
        grouped[key]["dispatch_events"] += int(event_type in DISPATCH_EVENT_TYPES)
        grouped[key]["repeat_defects"] += int(event_type == "REPEAT_DEFECT")
        grouped[key]["unscheduled_removals"] += int(event_type == "UNSCHEDULED_REMOVAL")
    for row in utilisation:
        grouped[row.aircraft_serial_number]["flight_hours"] += _safe_float(row.flight_hours)
        grouped[row.aircraft_serial_number]["flight_cycles"] += _safe_float(row.cycles)
    result: list[ChartPoint] = []
    for aircraft, values in grouped.items():
        fh = values.get("flight_hours", 0)
        fc = values.get("flight_cycles", 0)
        events_count = values.get("events", 0)
        dispatch = values.get("dispatch_events", 0)
        result.append(
            ChartPoint(
                key=aircraft,
                label=aircraft,
                metrics={
                    "events": int(events_count),
                    "delay_minutes": int(values.get("delay_minutes", 0)),
                    "repeat_defects": int(values.get("repeat_defects", 0)),
                    "unscheduled_removals": int(values.get("unscheduled_removals", 0)),
                    "flight_hours": round(fh, 3),
                    "flight_cycles": round(fc, 3),
                    "event_rate_per_100_fh": _ratio(events_count, fh, 100),
                    "dispatch_reliability_pct": _ratio(max(fc - dispatch, 0), fc, 100),
                },
                drilldown={"dimension": "aircraft", "key": aircraft},
            )
        )
    return sorted(result, key=lambda item: (item.metrics.get("event_rate_per_100_fh") or 0, item.metrics.get("events") or 0), reverse=True)

def _station_delay(events: list[models.ReliabilityEvent]) -> list[ChartPoint]:
    grouped: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for event in events:
        if _enum_value(event.event_type) not in DISPATCH_EVENT_TYPES:
            continue
        station = event.origin_station or "UNALLOCATED"
        grouped[station]["events"] += 1
        grouped[station]["delay_minutes"] += max(int(event.delay_minutes or 0), 0)
        grouped[station]["cancellations"] += int(_enum_value(event.event_type) == "TECHNICAL_CANCELLATION")
    result = []
    for station, values in grouped.items():
        result.append(
            ChartPoint(
                key=station,
                label=station,
                metrics={
                    "events": int(values["events"]),
                    "delay_minutes": int(values["delay_minutes"]),
                    "average_delay_minutes": _ratio(values["delay_minutes"], values["events"], 1),
                    "cancellations": int(values["cancellations"]),
                },
                drilldown={"dimension": "station", "key": station},
            )
        )
    return sorted(result, key=lambda item: item.metrics.get("delay_minutes") or 0, reverse=True)[:20]

def _route_delay(events: list[models.ReliabilityEvent]) -> list[ChartPoint]:
    grouped: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for event in events:
        event_type = _enum_value(event.event_type)
        if event_type not in DISPATCH_EVENT_TYPES:
            continue
        origin = event.origin_station or "UNALLOCATED"
        destination = event.destination_station or "UNALLOCATED"
        key = f"{origin}|{destination}"
        grouped[key]["events"] += 1
        grouped[key]["delay_minutes"] += max(int(event.delay_minutes or 0), 0)
        grouped[key]["cancellations"] += int(event_type == "TECHNICAL_CANCELLATION")
    points = []
    for key, values in grouped.items():
        origin, destination = key.split("|", 1)
        points.append(
            ChartPoint(
                key=key,
                label=f"{origin} → {destination}",
                metrics={
                    "events": int(values["events"]),
                    "delay_minutes": int(values["delay_minutes"]),
                    "average_delay_minutes": _ratio(values["delay_minutes"], values["events"], 1),
                    "cancellations": int(values["cancellations"]),
                },
                drilldown={"dimension": "route", "key": key},
            )
        )
    return sorted(points, key=lambda item: item.metrics.get("delay_minutes") or 0, reverse=True)[:20]
