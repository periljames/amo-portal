from __future__ import annotations

from collections import defaultdict

from . import models
from .analytics_common import _bucket_key, _safe_float
from .analytics_types import ChartPoint


def _removal_age_distribution(rows: list[models.RemovalEvent]) -> list[ChartPoint]:
    buckets = {
        "UNDER_100_FH": {"label": "Under 100 FH", "count": 0},
        "100_499_FH": {"label": "100–499 FH", "count": 0},
        "500_999_FH": {"label": "500–999 FH", "count": 0},
        "1000_2999_FH": {"label": "1,000–2,999 FH", "count": 0},
        "3000_PLUS_FH": {"label": "3,000+ FH", "count": 0},
        "UNKNOWN": {"label": "Hours not recorded", "count": 0},
    }
    for row in rows:
        hours = _safe_float(row.hours_at_removal) if row.hours_at_removal is not None else None
        if hours is None:
            key = "UNKNOWN"
        elif hours < 100:
            key = "UNDER_100_FH"
        elif hours < 500:
            key = "100_499_FH"
        elif hours < 1000:
            key = "500_999_FH"
        elif hours < 3000:
            key = "1000_2999_FH"
        else:
            key = "3000_PLUS_FH"
        buckets[key]["count"] += 1
    return [
        ChartPoint(
            key=key,
            label=str(values["label"]),
            metrics={"count": int(values["count"])},
            drilldown={"dimension": "component_age", "key": key},
        )
        for key, values in buckets.items()
    ]


def _shop_visit_trend(rows: list[models.ShopVisit], bucket: str) -> list[ChartPoint]:
    grouped: dict[str, int] = defaultdict(int)
    labels: dict[str, str] = {}
    for row in rows:
        created = row.created_at.date()
        key, label = _bucket_key(created, bucket)
        labels[key] = label
        grouped[key] += 1
    return [
        ChartPoint(
            key=key,
            label=labels.get(key, key),
            metrics={"shop_visits": count},
            drilldown={"dimension": "shop_visit_period", "key": key, "bucket": bucket},
        )
        for key, count in sorted(grouped.items())
    ]


def _oil_consumption_points(rows: list[models.OilConsumptionRate]) -> list[ChartPoint]:
    grouped: dict[str, list[models.OilConsumptionRate]] = defaultdict(list)
    for row in rows:
        key = f"{row.aircraft_serial_number}|{row.engine_position or 'UNALLOCATED'}"
        grouped[key].append(row)
    result: list[ChartPoint] = []
    for key, values in grouped.items():
        aircraft, position = key.split("|", 1)
        valid_rates = [_safe_float(row.rate_qt_per_hour) for row in values if row.rate_qt_per_hour is not None]
        latest = max(values, key=lambda row: row.window_end)
        result.append(
            ChartPoint(
                key=key,
                label=f"{aircraft} · {position}",
                metrics={
                    "average_qt_per_hour": round(sum(valid_rates) / len(valid_rates), 4) if valid_rates else None,
                    "latest_qt_per_hour": _safe_float(latest.rate_qt_per_hour) if latest.rate_qt_per_hour is not None else None,
                    "oil_used_quarts": round(sum(_safe_float(row.oil_used_quarts) for row in values), 3),
                    "flight_hours": round(sum(_safe_float(row.flight_hours) for row in values), 3),
                    "windows": len(values),
                },
                drilldown={"dimension": "oil_consumption", "key": key},
            )
        )
    return sorted(result, key=lambda item: item.metrics.get("latest_qt_per_hour") or 0, reverse=True)
