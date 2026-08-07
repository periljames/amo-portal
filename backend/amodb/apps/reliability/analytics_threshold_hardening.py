from __future__ import annotations

from typing import Any

from . import analytics_common


ZERO_TOLERANCE_OPERATIONAL_COUNTS = {
    "overdue_deferrals",
    "overdue_actions",
    "critical_alerts",
    "engine_shifts",
    "data_quality_open",
}


def governed_metric_status(code: str, value: float | int | None) -> str:
    """Classify only states with an explicit non-arbitrary operational rule.

    Rate and percentage thresholds must come from an approved programme metric
    threshold version. The analytics landing page must not invent generic
    fleet-wide cut-offs for dispatch reliability, NFF, action completion or
    effectiveness.
    """

    if value is None:
        return "NO_DATA"
    if code in ZERO_TOLERANCE_OPERATIONAL_COUNTS:
        return "GOOD" if float(value) == 0 else "ALERT"
    return "NEUTRAL"


def apply() -> None:
    if getattr(analytics_common, "_reliability_threshold_hardening_applied", False):
        return
    analytics_common._metric_status = governed_metric_status
    analytics_common._reliability_threshold_hardening_applied = True


apply()
