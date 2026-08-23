from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256
from typing import Any


ALGORITHM_VERSION = "HYBRID_ASSURANCE_V1"

_LEVEL_SCORE = {
    "LOW": 20,
    "MEDIUM": 45,
    "HIGH": 75,
    "CRITICAL": 100,
}

# ISO/IATA define the assurance principles and risk-based approach, not a
# mandatory numeric formula. These weights are therefore deliberately visible,
# deterministic and versioned so a tenant can audit every recommendation.
WEIGHTS = {
    "compliance": 0.40,
    "risk": 0.35,
    "performance": 0.25,
}


def _clamp(value: int | float) -> int:
    return max(0, min(100, int(round(value))))


def _level(value: str | None) -> int:
    return _LEVEL_SCORE.get(str(value or "MEDIUM").upper(), 45)


def _performance_pressure(signals: dict[str, int]) -> int:
    """Convert adverse operating history into a bounded pressure score.

    Signals are additive but capped. Repeat/follow-up findings are intentionally
    stronger than isolated deferrals so recurring ineffectiveness drives more
    surveillance without ever reducing the compliance baseline.
    """

    return _clamp(
        int(signals.get("repeat_findings", 0)) * 22
        + int(signals.get("open_findings", 0)) * 10
        + int(signals.get("follow_up_required", 0)) * 18
        + int(signals.get("deferred_audits", 0)) * 8
        + int(signals.get("failed_controls", 0)) * 18
        + int(signals.get("adverse_trends", 0)) * 15
    )


def _interval_from_score(score: int) -> int:
    if score >= 90:
        return 30
    if score >= 75:
        return 90
    if score >= 60:
        return 180
    if score >= 40:
        return 365
    return 730


def _band(score: int) -> str:
    if score >= 90:
        return "CRITICAL"
    if score >= 75:
        return "HIGH"
    if score >= 60:
        return "ELEVATED"
    return "ROUTINE"


def score_surveillance(
    *,
    universe_item: Any,
    signals: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Score one auditable entity using a compliance floor + adaptive pressure.

    Mandatory/regulatory surveillance is a hard floor. Risk and performance can
    shorten the recommended interval or add surveillance; they cannot lengthen
    a mandatory minimum interval.
    """

    signals = signals or {}
    regulatory = _level(getattr(universe_item, "regulatory_criticality", None))
    inherent_risk = _level(getattr(universe_item, "risk_classification", None))
    mandatory = bool(getattr(universe_item, "mandatory_surveillance", False))
    compliance = max(regulatory, 85 if mandatory else 0)
    performance = _performance_pressure(signals)

    weighted = _clamp(
        compliance * WEIGHTS["compliance"]
        + inherent_risk * WEIGHTS["risk"]
        + performance * WEIGHTS["performance"]
    )
    priority = max(weighted, 80 if mandatory else 0)

    dynamic_interval = _interval_from_score(priority)
    minimum_interval = getattr(universe_item, "surveillance_interval_days", None)
    recommended_interval = min(dynamic_interval, int(minimum_interval)) if minimum_interval else dynamic_interval

    drivers: list[dict[str, Any]] = [
        {"factor": "COMPLIANCE", "score": compliance, "weight": WEIGHTS["compliance"]},
        {"factor": "RISK", "score": inherent_risk, "weight": WEIGHTS["risk"]},
        {"factor": "PERFORMANCE", "score": performance, "weight": WEIGHTS["performance"], "signals": signals},
    ]
    if mandatory:
        drivers.append({"factor": "MANDATORY_FLOOR", "score": 80, "effect": "priority_floor"})
    if minimum_interval:
        drivers.append({
            "factor": "MANDATORY_INTERVAL_CAP",
            "days": int(minimum_interval),
            "effect": "recommended_interval_cannot_exceed",
        })

    return {
        "algorithm": ALGORITHM_VERSION,
        "priority_score": priority,
        "priority_band": _band(priority),
        "recommended_interval_days": recommended_interval,
        "components": {
            "compliance": compliance,
            "risk": inherent_risk,
            "performance": performance,
        },
        "drivers": drivers,
        "mandatory_baseline": mandatory,
        "recommend_in_programme": mandatory or priority >= 40,
    }


def recommended_window(
    *,
    programme_start: date,
    programme_end: date,
    stable_key: str,
    priority_score: int,
    as_of: date | None = None,
) -> tuple[date, date]:
    """Spread recommendations deterministically inside a priority horizon.

    The hash only distributes workload; it never alters the priority score. High
    pressure produces a shorter horizon. Exact people/times remain Planner work.
    """

    anchor = max(programme_start, as_of or date.today())
    if anchor > programme_end:
        anchor = programme_start
    horizon = 30 if priority_score >= 90 else 90 if priority_score >= 75 else 180 if priority_score >= 60 else 365
    available = max(0, (programme_end - anchor).days)
    horizon = min(horizon, available)
    spread = int(sha256(stable_key.encode("utf-8")).hexdigest()[:8], 16) % max(1, horizon + 1)
    target_start = min(programme_end, anchor + timedelta(days=spread))
    target_end = min(programme_end, target_start + timedelta(days=14))
    return target_start, target_end
