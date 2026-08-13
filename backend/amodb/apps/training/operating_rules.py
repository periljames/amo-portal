"""Dependency-free rules used by Training Operating System workflows and tests."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Mapping


def decimal_value(value: Decimal | int | str | None, places: int = 6) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def converted_amount(amount: Decimal | int | str, rate: Decimal | int | str, places: int = 6) -> Decimal:
    parsed_rate = Decimal(str(rate))
    if parsed_rate <= 0:
        raise ValueError("exchange rate must be greater than zero")
    return decimal_value(Decimal(str(amount)) * parsed_rate, places)


def assessment_outcome(score: Decimal | int | str, threshold: Decimal | int | str) -> str:
    parsed_score = Decimal(str(score))
    parsed_threshold = Decimal(str(threshold))
    if not Decimal("0") <= parsed_score <= Decimal("100"):
        raise ValueError("score must be between 0 and 100")
    if not Decimal("0") <= parsed_threshold <= Decimal("100"):
        raise ValueError("threshold must be between 0 and 100")
    return "PASS" if parsed_score >= parsed_threshold else "FAIL"


PLAN_TRANSITIONS: Mapping[str, set[str]] = {
    "DRAFT": {"SUBMITTED"},
    "SUBMITTED": {"REVIEWED", "RETURNED"},
    "REVIEWED": {"APPROVED", "RETURNED"},
}

BUDGET_TRANSITIONS: Mapping[str, set[str]] = {
    "DRAFT": {"SUBMITTED"},
    "SUBMITTED": {"REVIEWED", "RETURNED"},
    "REVIEWED": {"APPROVED", "RETURNED"},
}


def plan_transition_allowed(source: str, target: str) -> bool:
    return target.upper() in PLAN_TRANSITIONS.get(source.upper(), set())


def budget_transition_allowed(source: str, target: str) -> bool:
    return target.upper() in BUDGET_TRANSITIONS.get(source.upper(), set())


def attendance_token_state(*, status: str, expires_at: datetime, now: datetime) -> str:
    if status.upper() != "OPEN":
        return status.upper()
    if expires_at <= now:
        return "EXPIRED"
    return "OPEN"


def readiness_status(
    *,
    blockers: Iterable[str],
    required_assessments: Iterable[str],
    passed_assessments: Iterable[str],
    committee_decisions: Iterable[str],
    required_committee_count: int,
) -> str:
    decisions = [value.upper() for value in committee_decisions]
    if "REJECT" in decisions:
        return "REJECTED"
    if "DEFER" in decisions:
        return "DEFERRED"
    if any(blockers):
        return "NOT_READY"
    if not set(required_assessments).issubset(set(passed_assessments)):
        return "ASSESSMENT_IN_PROGRESS"
    if len(decisions) >= required_committee_count and decisions and all(value == "APPROVE" for value in decisions):
        return "APPROVED"
    if decisions:
        return "DECISION_REQUIRED"
    return "READY_FOR_COMMITTEE"


def level_four_causation_allowed(*, causation_claimed: bool, evidence: Mapping[str, object], conclusion: str | None) -> bool:
    if not causation_claimed:
        return True
    return {"baseline", "comparison", "confounders", "method"}.issubset(evidence) and bool((conclusion or "").strip())
