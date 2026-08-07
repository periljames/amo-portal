from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.fleet import models as fleet_models

from . import advanced_models, models, operational_sources
from .analytics_common import CLOSED_ACTION_STATES, OPEN_DEFERRAL_STATES, UTC, _aircraft_type_label, _bucket_key, _enum_value, _safe_float
from .analytics_types import ChartPoint, DashboardFilterOptions

def _deferral_charts(
    rows: list[operational_sources.ReliabilityMelCdlDeferral],
    now: datetime,
) -> tuple[list[ChartPoint], list[ChartPoint], list[ChartPoint], list[ChartPoint], list[ChartPoint], list[ChartPoint]]:
    status_counts = Counter(row.status for row in rows)
    status_points = [
        ChartPoint(
            key=key,
            label=key.replace("_", " ").title(),
            metrics={"count": count},
            drilldown={"dimension": "deferral_status", "key": key},
        )
        for key, count in status_counts.most_common()
    ]

    expiry_counts = {"OVERDUE": 0, "0_7_DAYS": 0, "8_14_DAYS": 0, "15_30_DAYS": 0, "OVER_30_DAYS": 0}
    category_counts: Counter[str] = Counter()
    extension_counts: Counter[str] = Counter()
    repeat_groups: Counter[tuple[str, str, str]] = Counter()
    closure_days: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row.status in OPEN_DEFERRAL_STATES:
            category_counts[(row.category or "UNCLASSIFIED").upper()] += 1
        repeat_groups[(row.aircraft_serial_number or "UNALLOCATED", row.item_reference or "UNALLOCATED", row.ata_chapter or "UNALLOCATED")] += 1
        for item in list(row.extension_history_json or []):
            if not isinstance(item, dict):
                continue
            reason = str(item.get("reason") or "UNCLASSIFIED").strip() or "UNCLASSIFIED"
            extension_counts[reason] += 1
        if row.closed_at and row.applied_at:
            category = (row.category or "UNCLASSIFIED").upper()
            applied = row.applied_at if row.applied_at.tzinfo else row.applied_at.replace(tzinfo=UTC)
            closed = row.closed_at if row.closed_at.tzinfo else row.closed_at.replace(tzinfo=UTC)
            closure_days[category].append(max((closed - applied).total_seconds() / 86400, 0))
        if row.status not in OPEN_DEFERRAL_STATES or not row.expires_at:
            continue
        delta_days = (row.expires_at.date() - now.date()).days
        if delta_days < 0:
            expiry_counts["OVERDUE"] += 1
        elif delta_days <= 7:
            expiry_counts["0_7_DAYS"] += 1
        elif delta_days <= 14:
            expiry_counts["8_14_DAYS"] += 1
        elif delta_days <= 30:
            expiry_counts["15_30_DAYS"] += 1
        else:
            expiry_counts["OVER_30_DAYS"] += 1
    labels = {
        "OVERDUE": "Overdue",
        "0_7_DAYS": "Due in 0–7 days",
        "8_14_DAYS": "Due in 8–14 days",
        "15_30_DAYS": "Due in 15–30 days",
        "OVER_30_DAYS": "More than 30 days",
    }
    expiry_points = [
        ChartPoint(
            key=key,
            label=labels[key],
            metrics={"count": value},
            drilldown={"dimension": "deferral_expiry", "key": key},
        )
        for key, value in expiry_counts.items()
    ]
    category_points = [
        ChartPoint(
            key=key,
            label=key.replace("_", " ").title(),
            metrics={"count": count},
            drilldown={"dimension": "deferral_category", "key": key},
        )
        for key, count in category_counts.most_common()
    ]
    extension_points = [
        ChartPoint(
            key=key,
            label=key[:100],
            metrics={"count": count},
            drilldown={"dimension": "deferral_extension", "key": key},
        )
        for key, count in extension_counts.most_common(15)
    ]
    repeat_points = [
        ChartPoint(
            key="|".join(group),
            label=f"{group[0]} · {group[1]}",
            metrics={"count": count},
            drilldown={"dimension": "deferral_repeat", "key": "|".join(group)},
        )
        for group, count in sorted(repeat_groups.items(), key=lambda item: item[1], reverse=True)
        if count > 1
    ][:20]
    closure_points = [
        ChartPoint(
            key=category,
            label=category.replace("_", " ").title(),
            metrics={
                "average_days": round(sum(values) / len(values), 2),
                "closed_deferrals": len(values),
            },
            drilldown={"dimension": "deferral_closure", "key": category},
        )
        for category, values in sorted(closure_days.items(), key=lambda item: sum(item[1]) / len(item[1]), reverse=True)
        if values
    ]
    return status_points, expiry_points, category_points, extension_points, repeat_points, closure_points
