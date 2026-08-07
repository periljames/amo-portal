from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

from . import advanced_models, models, operational_sources
from .analytics_common import (
    CLOSED_ACTION_STATES, DELAY_EVENT_TYPES, DISPATCH_EVENT_TYPES, REPEAT_EVENT_TYPES,
    SHOP_EVENT_TYPES, UNSCHEDULED_REMOVAL_TYPES, OPEN_DEFERRAL_STATES, UTC,
    _bucket_key, _delta, _enum_value, _metric_status, _ratio,
    _safe_float, _event_totals, _utilisation_totals,
)
from .analytics_types import ChartPoint, DashboardMetric

def _component_reliability(
    events: list[models.ReliabilityEvent],
    total_flight_hours: float,
    total_flight_cycles: float,
) -> list[ChartPoint]:
    grouped: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for event in events:
        event_type = _enum_value(event.event_type)
        if event_type not in SHOP_EVENT_TYPES | {"UNSCHEDULED_REMOVAL", "SCHEDULED_REMOVAL"}:
            continue
        key = event.part_number or "UNALLOCATED"
        grouped[key]["shop_findings"] += int(event_type == "SHOP_FINDING")
        grouped[key]["nff"] += int(event_type == "NO_FAULT_FOUND")
        grouped[key]["unscheduled_removals"] += int(event_type == "UNSCHEDULED_REMOVAL")
        grouped[key]["scheduled_removals"] += int(event_type == "SCHEDULED_REMOVAL")
        grouped[key]["confirmed_failures"] += int(event.confirmed_failure is True)
    result: list[ChartPoint] = []
    for part_number, values in grouped.items():
        shop_total = values["shop_findings"] + values["nff"]
        removals = values["unscheduled_removals"]
        result.append(
            ChartPoint(
                key=part_number,
                label=part_number,
                metrics={
                    "shop_findings": int(values["shop_findings"]),
                    "nff": int(values["nff"]),
                    "nff_rate_pct": _ratio(values["nff"], shop_total, 100),
                    "confirmed_failures": int(values["confirmed_failures"]),
                    "unscheduled_removals": int(removals),
                    "scheduled_removals": int(values["scheduled_removals"]),
                    "removal_rate_per_1000_fh": _ratio(removals, total_flight_hours, 1000),
                    "removal_rate_per_1000_fc": _ratio(removals, total_flight_cycles, 1000),
                    "fleet_exposure_fh_per_unscheduled_removal": _ratio(total_flight_hours, removals, 1),
                    "fleet_exposure_fc_per_unscheduled_removal": _ratio(total_flight_cycles, removals, 1),
                },
                drilldown={"dimension": "component", "key": part_number},
            )
        )
    return sorted(
        result,
        key=lambda item: (
            item.metrics.get("unscheduled_removals") or 0,
            item.metrics.get("confirmed_failures") or 0,
            item.metrics.get("shop_findings") or 0,
        ),
        reverse=True,
    )[:30]
