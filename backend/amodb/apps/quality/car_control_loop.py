from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping


MILESTONE_ORDER: tuple[str, ...] = (
    "RCA_SUBMISSION",
    "CAP_APPROVAL",
    "IMPLEMENTATION_COMPLETE",
    "EVIDENCE_COMPLETE",
    "EFFECTIVENESS_REVIEW",
)

TERMINAL_MILESTONE_STATUSES = {"ACCEPTED", "COMPLETED", "WAIVED"}
ACTIVE_MILESTONE_STATUSES = {"PLANNED", "IN_PROGRESS", "SUBMITTED", "REJECTED", "BLOCKED"}
CLOSED_CAR_STATUSES = {"CLOSED", "CANCELLED"}


@dataclass(frozen=True)
class CARHealth:
    state: str
    risk_score: int
    factors: tuple[dict[str, Any], ...]
    next_action: str
    days_to_final_due: int | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "risk_score": self.risk_score,
            "factors": list(self.factors),
            "next_action": self.next_action,
            "days_to_final_due": self.days_to_final_due,
        }


def _value(item: Mapping[str, Any] | object, key: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def _iso(value: date | None) -> str | None:
    return value.isoformat() if isinstance(value, date) else None


def compute_car_health(
    *,
    today: date,
    car_status: str,
    final_due_date: date | None,
    accountable_owner_user_id: str | None,
    milestones: Iterable[Mapping[str, Any] | object],
    dependencies: Iterable[Mapping[str, Any] | object],
    effectiveness_required: bool | None = None,
) -> CARHealth:
    normalized_status = str(getattr(car_status, "value", car_status) or "").upper()
    days_to_final_due = (final_due_date - today).days if final_due_date else None
    if normalized_status in CLOSED_CAR_STATUSES:
        return CARHealth(
            state="CLOSED",
            risk_score=0,
            factors=(),
            next_action="No active corrective-action control is required.",
            days_to_final_due=days_to_final_due,
        )

    score = 0
    factors: list[dict[str, Any]] = []
    critical = False
    any_overdue = False

    def add_factor(code: str, points: int, message: str, *, severity: str = "WATCH", **extra: Any) -> None:
        nonlocal score
        score += points
        factors.append({"code": code, "severity": severity, "message": message, **extra})

    if not accountable_owner_user_id:
        add_factor(
            "ACCOUNTABLE_OWNER_MISSING",
            20,
            "The CAR has no accountable lead owner.",
            severity="AT_RISK",
        )

    if final_due_date:
        if days_to_final_due is not None and days_to_final_due < 0:
            any_overdue = True
            overdue_days = abs(days_to_final_due)
            add_factor(
                "FINAL_DUE_OVERDUE",
                35 if overdue_days <= 7 else 50,
                f"The controlled CAR deadline is overdue by {overdue_days} day(s).",
                severity="CRITICAL" if overdue_days > 7 else "OVERDUE",
                due_date=_iso(final_due_date),
                overdue_days=overdue_days,
            )
            if overdue_days > 7:
                critical = True
        elif days_to_final_due is not None and days_to_final_due <= 7:
            add_factor(
                "FINAL_DUE_IMMINENT",
                20,
                f"The controlled CAR deadline is due in {days_to_final_due} day(s).",
                severity="AT_RISK",
                due_date=_iso(final_due_date),
            )
        elif days_to_final_due is not None and days_to_final_due <= 14:
            add_factor(
                "FINAL_DUE_APPROACHING",
                10,
                f"The controlled CAR deadline is due in {days_to_final_due} day(s).",
                due_date=_iso(final_due_date),
            )
    else:
        add_factor(
            "FINAL_DUE_MISSING",
            20,
            "The CAR has no controlled final deadline.",
            severity="AT_RISK",
        )

    next_milestone: tuple[int, str, str] | None = None
    for milestone in milestones:
        status = str(_value(milestone, "status", "PLANNED") or "PLANNED").upper()
        key = str(_value(milestone, "milestone_key", "UNKNOWN") or "UNKNOWN").upper()
        owner = _value(milestone, "owner_user_id")
        due_date = _value(milestone, "current_due_date")

        if key == "EFFECTIVENESS_REVIEW":
            gate_required = effectiveness_required
            if gate_required is None:
                milestone_profile = _value(milestone, "profile")
                gate_required = (
                    bool(_value(milestone_profile, "effectiveness_required", True))
                    if milestone_profile is not None
                    else True
                )
            if not gate_required:
                continue

        if status in TERMINAL_MILESTONE_STATUSES:
            continue

        if not owner:
            add_factor(
                "MILESTONE_OWNER_MISSING",
                8,
                f"{key.replace('_', ' ').title()} has no responsible owner.",
                severity="AT_RISK",
                milestone_key=key,
            )

        if status == "REJECTED":
            add_factor(
                "MILESTONE_REJECTED",
                25,
                f"{key.replace('_', ' ').title()} was rejected and requires rework.",
                severity="AT_RISK",
                milestone_key=key,
            )
        elif status == "BLOCKED":
            add_factor(
                "MILESTONE_BLOCKED",
                30,
                f"{key.replace('_', ' ').title()} is blocked.",
                severity="AT_RISK",
                milestone_key=key,
            )

        if isinstance(due_date, date):
            days = (due_date - today).days
            if next_milestone is None or days < next_milestone[0]:
                next_milestone = (days, key, status)
            if days < 0:
                any_overdue = True
                overdue_days = abs(days)
                add_factor(
                    "MILESTONE_OVERDUE",
                    25 if overdue_days <= 7 else 40,
                    f"{key.replace('_', ' ').title()} is overdue by {overdue_days} day(s).",
                    severity="CRITICAL" if overdue_days > 7 else "OVERDUE",
                    milestone_key=key,
                    due_date=_iso(due_date),
                    overdue_days=overdue_days,
                )
                if overdue_days > 7:
                    critical = True
            elif days <= 3:
                add_factor(
                    "MILESTONE_DUE_IMMINENT",
                    15,
                    f"{key.replace('_', ' ').title()} is due in {days} day(s).",
                    severity="AT_RISK",
                    milestone_key=key,
                    due_date=_iso(due_date),
                )
            elif days <= 7:
                add_factor(
                    "MILESTONE_DUE_SOON",
                    8,
                    f"{key.replace('_', ' ').title()} is due in {days} day(s).",
                    milestone_key=key,
                    due_date=_iso(due_date),
                )
        else:
            add_factor(
                "MILESTONE_DUE_MISSING",
                10,
                f"{key.replace('_', ' ').title()} has no controlled deadline.",
                severity="AT_RISK",
                milestone_key=key,
            )

    for dependency in dependencies:
        status = str(_value(dependency, "status", "OPEN") or "OPEN").upper()
        if status in {"RESOLVED", "MITIGATED", "ACCEPTED_RISK", "CANCELLED"}:
            continue
        risk_level = str(_value(dependency, "risk_level", "MEDIUM") or "MEDIUM").upper()
        blocks_closure = bool(_value(dependency, "blocks_closure", False))
        title = str(_value(dependency, "title", "Dependency") or "Dependency")
        dependency_id = str(_value(dependency, "id", ""))
        due_date = _value(dependency, "due_date")
        points = {"LOW": 4, "MEDIUM": 10, "HIGH": 20, "CRITICAL": 35}.get(risk_level, 10)
        if blocks_closure:
            points += 10
        severity = "CRITICAL" if risk_level == "CRITICAL" else "AT_RISK" if risk_level == "HIGH" or blocks_closure else "WATCH"
        add_factor(
            "OPEN_DEPENDENCY",
            points,
            f"Open dependency: {title}.",
            severity=severity,
            dependency_id=dependency_id,
            risk_level=risk_level,
            blocks_closure=blocks_closure,
            due_date=_iso(due_date) if isinstance(due_date, date) else None,
        )
        if risk_level == "CRITICAL":
            critical = True

        if isinstance(due_date, date):
            days = (due_date - today).days
            if days < 0:
                any_overdue = True
                overdue_days = abs(days)
                add_factor(
                    "DEPENDENCY_OVERDUE",
                    15 if overdue_days <= 7 else 25,
                    f"Dependency {title} is overdue by {overdue_days} day(s).",
                    severity="OVERDUE",
                    dependency_id=dependency_id,
                    risk_level=risk_level,
                    due_date=_iso(due_date),
                    overdue_days=overdue_days,
                )
            elif days <= 3:
                add_factor(
                    "DEPENDENCY_DUE_IMMINENT",
                    10,
                    f"Dependency {title} is due in {days} day(s).",
                    severity="AT_RISK",
                    dependency_id=dependency_id,
                    risk_level=risk_level,
                    due_date=_iso(due_date),
                )
            elif days <= 7:
                add_factor(
                    "DEPENDENCY_DUE_SOON",
                    6,
                    f"Dependency {title} is due in {days} day(s).",
                    dependency_id=dependency_id,
                    risk_level=risk_level,
                    due_date=_iso(due_date),
                )

    score = min(100, score)
    if critical:
        state = "CRITICAL"
    elif any_overdue:
        state = "OVERDUE"
    elif score >= 50:
        state = "AT_RISK"
    elif score >= 20:
        state = "WATCH"
    else:
        state = "HEALTHY"

    if factors:
        priority = {"CRITICAL": 5, "OVERDUE": 4, "AT_RISK": 3, "WATCH": 2, "INFO": 1}
        top = max(factors, key=lambda item: (priority.get(str(item.get("severity")), 0), int(item.get("overdue_days", 0) or 0)))
        next_action = str(top["message"])
    elif next_milestone:
        days, key, _status = next_milestone
        next_action = f"Progress {key.replace('_', ' ').title()} ({days} day(s) to deadline)."
    else:
        next_action = "Maintain the CAR control plan and complete the remaining governed milestones."

    return CARHealth(
        state=state,
        risk_score=score,
        factors=tuple(factors),
        next_action=next_action,
        days_to_final_due=days_to_final_due,
    )


def closure_readiness(
    *,
    milestones: Iterable[Mapping[str, Any] | object],
    dependencies: Iterable[Mapping[str, Any] | object],
    effectiveness_required: bool,
) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    for milestone in milestones:
        key = str(_value(milestone, "milestone_key", "UNKNOWN") or "UNKNOWN").upper()
        seen_keys.add(key)
        status = str(_value(milestone, "status", "PLANNED") or "PLANNED").upper()
        evidence_ref = str(_value(milestone, "evidence_ref", "") or "").strip()
        required = key != "EFFECTIVENESS_REVIEW" or effectiveness_required
        if not required:
            continue
        if status not in TERMINAL_MILESTONE_STATUSES:
            blockers.append({
                "code": "MILESTONE_INCOMPLETE",
                "milestone_key": key,
                "message": f"{key.replace('_', ' ').title()} is not accepted or complete.",
            })
        if key in {"EVIDENCE_COMPLETE", "EFFECTIVENESS_REVIEW"} and status != "WAIVED" and not evidence_ref:
            blockers.append({
                "code": "MILESTONE_EVIDENCE_MISSING",
                "milestone_key": key,
                "message": f"{key.replace('_', ' ').title()} requires evidence before closure.",
            })

    for required_key in MILESTONE_ORDER:
        if required_key == "EFFECTIVENESS_REVIEW" and not effectiveness_required:
            continue
        if required_key not in seen_keys:
            blockers.append({
                "code": "MILESTONE_MISSING",
                "milestone_key": required_key,
                "message": f"Required milestone {required_key.replace('_', ' ').title()} is missing.",
            })

    for dependency in dependencies:
        status = str(_value(dependency, "status", "OPEN") or "OPEN").upper()
        if bool(_value(dependency, "blocks_closure", False)) and status not in {"RESOLVED", "MITIGATED", "ACCEPTED_RISK", "CANCELLED"}:
            blockers.append({
                "code": "BLOCKING_DEPENDENCY_OPEN",
                "dependency_id": str(_value(dependency, "id", "")),
                "message": f"Blocking dependency remains open: {_value(dependency, 'title', 'Dependency')}.",
            })

    return {"ready": not blockers, "blockers": blockers}
