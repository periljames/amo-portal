from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from typing import Iterable

HOURS_QUANTUM = Decimal("0.01")
CONTROLLED_ROLES = {"ENGINE", "PROPELLER", "APU", "OTHER"}
SHARED_TARGETS = {"ENGINE", "PROPELLER"}


def as_hours(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(HOURS_QUANTUM, rounding=ROUND_HALF_UP)


def as_cycles(value) -> int | None:
    if value is None:
        return None
    parsed = Decimal(str(value))
    if parsed != parsed.to_integral_value():
        raise ValueError(f"cycle baseline must be a whole number, got {value!r}")
    return int(parsed)


@dataclass(frozen=True)
class ComponentState:
    component_id: int
    position: str
    description: str | None
    role: str
    current_hours: Decimal | None
    current_cycles: int | None


@dataclass(frozen=True)
class Override:
    component_id: int
    hours_delta: Decimal | None
    cycles_delta: int | None
    reason: str


@dataclass(frozen=True)
class Exposure:
    target_type: str
    component_id: int | None
    component_position: str
    component_description: str | None
    derivation: str
    hours_delta: Decimal
    cycles_delta: int
    before_hours: Decimal | None
    before_cycles: int | None
    after_hours: Decimal | None
    after_cycles: int | None
    baseline_missing: bool
    override_reason: str | None


def _controlled_role(value: str) -> str:
    role = str(value or "").strip().upper()
    if role not in CONTROLLED_ROLES:
        raise ValueError(f"component utilisation role is not controlled: {value!r}")
    return "COMPONENT" if role == "OTHER" else role


def _exposure(
    *,
    target_type: str,
    component_id: int | None,
    position: str,
    description: str | None,
    default_hours: Decimal,
    default_cycles: int,
    before_hours: Decimal | None,
    before_cycles: int | None,
    override: Override | None,
) -> Exposure:
    if override is None:
        hours_delta = default_hours
        cycles_delta = default_cycles
        derivation = (
            "SHARED_DAILY"
            if target_type in SHARED_TARGETS or target_type == "AIRFRAME"
            else "ZERO_DEFAULT"
        )
        reason = None
    else:
        hours_delta = as_hours(
            override.hours_delta if override.hours_delta is not None else default_hours
        ) or Decimal("0.00")
        cycles_delta = (
            override.cycles_delta
            if override.cycles_delta is not None
            else default_cycles
        )
        derivation = "OVERRIDE"
        reason = override.reason.strip()

    baseline_missing = (
        (hours_delta > 0 and before_hours is None)
        or (cycles_delta > 0 and before_cycles is None)
    )
    after_hours = None if before_hours is None else before_hours + hours_delta
    after_cycles = None if before_cycles is None else before_cycles + cycles_delta
    return Exposure(
        target_type=target_type,
        component_id=component_id,
        component_position=position,
        component_description=description,
        derivation=derivation,
        hours_delta=hours_delta,
        cycles_delta=cycles_delta,
        before_hours=before_hours,
        before_cycles=before_cycles,
        after_hours=after_hours,
        after_cycles=after_cycles,
        baseline_missing=baseline_missing,
        override_reason=reason,
    )


def build_exposures(
    *,
    daily_hours: Decimal,
    daily_cycles: int,
    airframe_hours: Decimal | None,
    airframe_cycles: int | None,
    components: Iterable[ComponentState],
    overrides: Iterable[Override] = (),
) -> list[Exposure]:
    hours = as_hours(daily_hours) or Decimal("0.00")
    override_map = {item.component_id: item for item in overrides}
    component_rows = list(components)
    known_ids = {item.component_id for item in component_rows}
    unknown = set(override_map) - known_ids
    if unknown:
        raise ValueError(
            f"component overrides are not installed on this aircraft: {sorted(unknown)}"
        )

    exposures = [
        _exposure(
            target_type="AIRFRAME",
            component_id=None,
            position="AIRFRAME",
            description="Aircraft airframe",
            default_hours=hours,
            default_cycles=daily_cycles,
            before_hours=airframe_hours,
            before_cycles=airframe_cycles,
            override=None,
        )
    ]
    for component in sorted(
        component_rows,
        key=lambda item: (item.position, item.component_id),
    ):
        target_type = _controlled_role(component.role)
        if target_type in SHARED_TARGETS:
            default_hours, default_cycles = hours, daily_cycles
        else:
            default_hours, default_cycles = Decimal("0.00"), 0
        exposures.append(
            _exposure(
                target_type=target_type,
                component_id=component.component_id,
                position=component.position,
                description=component.description,
                default_hours=default_hours,
                default_cycles=default_cycles,
                before_hours=component.current_hours,
                before_cycles=component.current_cycles,
                override=override_map.get(component.component_id),
            )
        )
    return exposures


def blockers_for(exposures: Iterable[Exposure]) -> list[str]:
    blockers = []
    for item in exposures:
        if item.baseline_missing:
            blockers.append(
                f"{item.component_position} has no approved utilisation baseline "
                "for the requested increment"
            )
    return blockers


def content_hash(payload: dict) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def default_idempotency_key(
    serial_number: str,
    operation_date: date,
    techlog_no: str,
) -> str:
    return (
        f"MANUAL:{serial_number}:{operation_date.isoformat()}:"
        f"{techlog_no.strip().upper()}"
    )
