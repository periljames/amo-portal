from __future__ import annotations

from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Optional


class DutyPayClassification(str, Enum):
    NORMAL_DUTY = "Normal Duty"
    ORDINARY_OT = "Ordinary OT"
    REST_DAY_WORK = "Rest-Day Work"
    PUBLIC_HOLIDAY_WORK = "Public-Holiday Work"


# Statutory floors are policy constraints, not roster shift defaults. A tenant
# or contract may be more generous; it may never configure a lower entitlement.
LEGAL_MINIMUM_MULTIPLIERS: dict[DutyPayClassification, Decimal] = {
    DutyPayClassification.NORMAL_DUTY: Decimal("1.00"),
    DutyPayClassification.ORDINARY_OT: Decimal("1.50"),
    DutyPayClassification.REST_DAY_WORK: Decimal("2.00"),
    DutyPayClassification.PUBLIC_HOLIDAY_WORK: Decimal("2.00"),
}


def _decimal(value: Decimal | float | int | str | None, *, fallback: Decimal) -> Decimal:
    if value is None:
        return fallback
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Multiplier must be a valid decimal number") from exc


def minimum_multiplier(
    classification: DutyPayClassification,
    *,
    contractual_minimum: Decimal | float | int | str | None = None,
) -> Decimal:
    legal = LEGAL_MINIMUM_MULTIPLIERS[classification]
    contractual = _decimal(contractual_minimum, fallback=legal)
    if contractual <= 0:
        raise ValueError("Contractual multiplier must be greater than zero")
    return max(legal, contractual)


def enforce_multiplier(
    classification: DutyPayClassification,
    *,
    requested_multiplier: Decimal | float | int | str | None,
    contractual_minimum: Decimal | float | int | str | None = None,
) -> Decimal:
    floor = minimum_multiplier(classification, contractual_minimum=contractual_minimum)
    if requested_multiplier is None:
        return floor
    requested = _decimal(requested_multiplier, fallback=floor)
    if requested < floor:
        raise ValueError(
            f"{classification.value} cannot be paid below the applicable minimum multiplier of {floor}."
        )
    return requested


def classify_work(
    *,
    is_public_holiday: bool,
    is_protected_rest_day: bool,
    ordinary_minutes_before: int,
    worked_minutes: int,
    contractual_normal_weekly_minutes: Optional[int],
    statutory_normal_weekly_minutes: int = 52 * 60,
) -> DutyPayClassification:
    """Resolve pay reason without treating Sunday itself as a pay code.

    Public-holiday and protected-rest work take precedence. Otherwise overtime
    starts after the lower of the employee's contractual normal hours and the
    statutory normal-hours threshold. The separate total-hours ceiling remains
    a roster compliance rule, not a pay classification.
    """

    if is_public_holiday:
        return DutyPayClassification.PUBLIC_HOLIDAY_WORK
    if is_protected_rest_day:
        return DutyPayClassification.REST_DAY_WORK

    normal_limit = statutory_normal_weekly_minutes
    if contractual_normal_weekly_minutes is not None and contractual_normal_weekly_minutes >= 0:
        normal_limit = min(normal_limit, contractual_normal_weekly_minutes)
    if ordinary_minutes_before + max(0, worked_minutes) > normal_limit:
        return DutyPayClassification.ORDINARY_OT
    return DutyPayClassification.NORMAL_DUTY


__all__ = [
    "DutyPayClassification",
    "LEGAL_MINIMUM_MULTIPLIERS",
    "classify_work",
    "enforce_multiplier",
    "minimum_multiplier",
]
