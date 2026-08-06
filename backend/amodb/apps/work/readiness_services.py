from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
import hashlib
import json
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import User
from amodb.apps.audit import schemas as audit_schemas
from amodb.apps.audit import services as audit_services
from amodb.apps.maintenance_program import service as maintenance_program_service

from . import package_services
from .readiness_models import (
    PlanningForecastScenario,
    PlanningForecastScenarioItem,
    WorkPackageFreeze,
    WorkPackageReadinessAssessment,
    WorkPackageReadinessRequirement,
)
from .readiness_schemas import (
    ForecastScenarioCreate,
    ForecastScenarioRead,
    ForecastScenarioUpdate,
    PackageFreezeCreate,
    PackageFreezeRead,
    ReadinessAssessmentRead,
    ReadinessDashboardRead,
    ReadinessRequirementCreate,
    ReadinessRequirementRead,
    ReadinessRequirementUpdate,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _json_default(value: Any):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "value"):
        return value.value
    raise TypeError(f"Unsupported value {type(value)!r}")


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default)


def _hash(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _audit(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str | None,
    entity_type: str,
    entity_id: str,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    audit_services.create_audit_event(
        db,
        amo_id=amo_id,
        data=audit_schemas.AuditEventCreate(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json=after,
        ),
    )


def _get_scenario(db: Session, *, amo_id: str, scenario_id: str) -> PlanningForecastScenario:
    scenario = (
        db.query(PlanningForecastScenario)
        .filter(PlanningForecastScenario.amo_id == amo_id, PlanningForecastScenario.id == scenario_id)
        .first()
    )
    if not scenario:
        raise HTTPException(status_code=404, detail="Forecast scenario not found")
    return scenario


def _scenario_read(scenario: PlanningForecastScenario) -> ForecastScenarioRead:
    return ForecastScenarioRead.model_validate(scenario)


def list_scenarios(db: Session, *, amo_id: str) -> list[ForecastScenarioRead]:
    rows = (
        db.query(PlanningForecastScenario)
        .filter(PlanningForecastScenario.amo_id == amo_id)
        .order_by(PlanningForecastScenario.updated_at.desc())
        .all()
    )
    return [_scenario_read(row) for row in rows]


def create_scenario(
    db: Session,
    *,
    amo_id: str,
    payload: ForecastScenarioCreate,
    actor: User,
) -> PlanningForecastScenario:
    duplicate = db.query(PlanningForecastScenario).filter(
        PlanningForecastScenario.amo_id == amo_id,
        PlanningForecastScenario.name == payload.name,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="Forecast scenario name already exists")
    scenario = PlanningForecastScenario(
        amo_id=amo_id,
        name=payload.name,
        status="DRAFT",
        start_date=payload.start_date,
        horizon_days=payload.horizon_days,
        default_daily_hours=payload.default_daily_hours,
        default_daily_cycles=payload.default_daily_cycles,
        aircraft_assumptions_json=payload.aircraft_assumptions_json,
        summary_json={},
        created_by_user_id=actor.id,
    )
    db.add(scenario)
    db.flush()
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor.id,
        entity_type="PlanningForecastScenario",
        entity_id=scenario.id,
        action="create",
        after={"name": scenario.name, "horizon_days": scenario.horizon_days},
    )
    return scenario


def update_scenario(
    db: Session,
    *,
    scenario: PlanningForecastScenario,
    payload: ForecastScenarioUpdate,
    actor: User,
) -> PlanningForecastScenario:
    if scenario.status not in {"DRAFT", "COMPLETE"}:
        raise HTTPException(status_code=409, detail="This scenario cannot be edited in its current state")
    before = _scenario_read(scenario).model_dump(mode="json")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(scenario, field, value)
    scenario.status = "DRAFT"
    scenario.generated_at = None
    db.add(scenario)
    _audit(
        db,
        amo_id=scenario.amo_id,
        actor_user_id=actor.id,
        entity_type="PlanningForecastScenario",
        entity_id=scenario.id,
        action="update",
        before=before,
        after=_scenario_read(scenario).model_dump(mode="json"),
    )
    return scenario


def _assumption(scenario: PlanningForecastScenario, serial_number: str) -> tuple[float, float]:
    values = (scenario.aircraft_assumptions_json or {}).get(serial_number, {})
    return (
        float(values.get("daily_hours", scenario.default_daily_hours or 0)),
        float(values.get("daily_cycles", scenario.default_daily_cycles or 0)),
    )


def _projected_days(
    *,
    remaining_days: Optional[float],
    remaining_hours: Optional[float],
    remaining_cycles: Optional[float],
    daily_hours: float,
    daily_cycles: float,
) -> tuple[Optional[float], Optional[str]]:
    candidates: list[tuple[float, str]] = []
    if remaining_days is not None:
        candidates.append((remaining_days, "CALENDAR"))
    if remaining_hours is not None and daily_hours > 0:
        candidates.append((remaining_hours / daily_hours, "HOURS"))
    if remaining_cycles is not None and daily_cycles > 0:
        candidates.append((remaining_cycles / daily_cycles, "CYCLES"))
    if not candidates:
        return None, None
    return min(candidates, key=lambda item: item[0])


def run_scenario(
    db: Session,
    *,
    scenario: PlanningForecastScenario,
    actor: User,
) -> PlanningForecastScenario:
    scenario.status = "RUNNING"
    db.query(PlanningForecastScenarioItem).filter(
        PlanningForecastScenarioItem.scenario_id == scenario.id
    ).delete(synchronize_session=False)
    db.flush()
    overview = maintenance_program_service.get_fleet_planning_overview(
        db,
        amo_id=scenario.amo_id,
        horizon_days=max(scenario.horizon_days, 1095),
        limit=10000,
    )
    status_counter: Counter = Counter()
    trigger_counter: Counter = Counter()
    inside_horizon = 0
    for source_item in overview.due_items:
        daily_hours, daily_cycles = _assumption(scenario, source_item.aircraft_serial_number)
        projected_days, trigger = _projected_days(
            remaining_days=float(source_item.remaining_days) if source_item.remaining_days is not None else None,
            remaining_hours=float(source_item.remaining_hours) if source_item.remaining_hours is not None else None,
            remaining_cycles=float(source_item.remaining_cycles) if source_item.remaining_cycles is not None else None,
            daily_hours=daily_hours,
            daily_cycles=daily_cycles,
        )
        projected_due_date = None
        if projected_days is not None:
            projected_due_date = scenario.start_date + timedelta(days=max(int(projected_days), 0))
        if projected_days is None:
            status_value = "NO_PROJECTION"
        elif projected_days < 0:
            status_value = "OVERDUE"
        elif projected_days <= scenario.horizon_days:
            status_value = "DUE_IN_SCENARIO"
            inside_horizon += 1
        else:
            status_value = "OUTSIDE_HORIZON"
        status_counter[status_value] += 1
        if trigger:
            trigger_counter[trigger] += 1
        db.add(
            PlanningForecastScenarioItem(
                amo_id=scenario.amo_id,
                scenario_id=scenario.id,
                aircraft_serial_number=source_item.aircraft_serial_number,
                registration=source_item.registration,
                program_item_id=source_item.program_item_id,
                aircraft_program_item_id=source_item.api_id,
                task_code=source_item.task_code,
                task_title=source_item.task_title,
                status=status_value,
                projected_due_date=projected_due_date,
                projected_trigger=trigger,
                projected_days=projected_days,
                remaining_hours=source_item.remaining_hours,
                remaining_cycles=source_item.remaining_cycles,
                remaining_days=source_item.remaining_days,
                daily_hours=daily_hours,
                daily_cycles=daily_cycles,
                source_snapshot_json=source_item.model_dump(mode="json"),
            )
        )
    scenario.status = "COMPLETE"
    scenario.generated_at = _utcnow()
    scenario.summary_json = {
        "items": len(overview.due_items),
        "inside_horizon": inside_horizon,
        "status": dict(status_counter),
        "triggers": dict(trigger_counter),
        "fleet_aircraft": overview.summary.fleet_aircraft,
    }
    db.add(scenario)
    db.flush()
    _audit(
        db,
        amo_id=scenario.amo_id,
        actor_user_id=actor.id,
        entity_type="PlanningForecastScenario",
        entity_id=scenario.id,
        action="run",
        after=scenario.summary_json,
    )
    return scenario


def list_requirements(db: Session, *, amo_id: str, package_id: int) -> list[ReadinessRequirementRead]:
    package_services._get_package(db, amo_id=amo_id, package_id=package_id)
    rows = (
        db.query(WorkPackageReadinessRequirement)
        .filter(
            WorkPackageReadinessRequirement.amo_id == amo_id,
            WorkPackageReadinessRequirement.work_package_id == package_id,
        )
        .order_by(WorkPackageReadinessRequirement.category.asc(), WorkPackageReadinessRequirement.created_at.asc())
        .all()
    )
    return [ReadinessRequirementRead.model_validate(row) for row in rows]


def create_requirement(
    db: Session,
    *,
    amo_id: str,
    package_id: int,
    payload: ReadinessRequirementCreate,
    actor: User,
) -> WorkPackageReadinessRequirement:
    package = package_services._get_package(db, amo_id=amo_id, package_id=package_id)
    if package.status not in {"DRAFT", "REVIEW", "READY"}:
        raise HTTPException(status_code=409, detail="Resource requirements cannot be added after package release")
    status_value = payload.status
    if status_value != "WAIVED":
        status_value = "CONFIRMED" if payload.quantity_confirmed >= payload.quantity_required else "SHORTAGE"
    row = WorkPackageReadinessRequirement(
        amo_id=amo_id,
        work_package_id=package_id,
        category=payload.category,
        reference=payload.reference,
        description=payload.description,
        quantity_required=payload.quantity_required,
        quantity_confirmed=payload.quantity_confirmed,
        status=status_value,
        required_by=payload.required_by,
        owner_user_id=payload.owner_user_id,
        evidence_json=payload.evidence_json,
        notes=payload.notes,
        created_by_user_id=actor.id,
    )
    db.add(row)
    db.flush()
    return row


def update_requirement(
    db: Session,
    *,
    amo_id: str,
    requirement_id: str,
    payload: ReadinessRequirementUpdate,
    actor: User,
) -> WorkPackageReadinessRequirement:
    row = (
        db.query(WorkPackageReadinessRequirement)
        .filter(
            WorkPackageReadinessRequirement.amo_id == amo_id,
            WorkPackageReadinessRequirement.id == requirement_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Package readiness requirement not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    if row.status != "WAIVED":
        row.status = "CONFIRMED" if float(row.quantity_confirmed or 0) >= float(row.quantity_required or 0) else "SHORTAGE"
    db.add(row)
    db.flush()
    return row


def assess_package(
    db: Session,
    *,
    amo_id: str,
    package_id: int,
    actor: User,
) -> WorkPackageReadinessAssessment:
    package = package_services._get_package(db, amo_id=amo_id, package_id=package_id)
    base = package_services.calculate_readiness(db, package=package)
    requirements = (
        db.query(WorkPackageReadinessRequirement)
        .filter(
            WorkPackageReadinessRequirement.amo_id == amo_id,
            WorkPackageReadinessRequirement.work_package_id == package_id,
        )
        .all()
    )
    blockers = list(base.blockers)
    warnings = list(base.warnings)
    shortages = [row for row in requirements if row.status in {"REQUIRED", "SHORTAGE"}]
    for row in shortages:
        blockers.append(
            f"{row.category}: {row.description} ({float(row.quantity_confirmed or 0):g}/{float(row.quantity_required or 0):g} confirmed)."
        )
    missing_categories = {
        "MANPOWER", "AUTHORIZATION", "MATERIAL", "TOOL", "FACILITY", "DOCUMENT", "SLOT"
    } - {row.category for row in requirements}
    if missing_categories:
        warnings.append(f"No explicit requirements recorded for: {', '.join(sorted(missing_categories))}.")
    status_value = "BLOCKED" if blockers else ("ATTENTION" if warnings else "READY")
    version = (
        db.query(WorkPackageReadinessAssessment)
        .filter(WorkPackageReadinessAssessment.work_package_id == package_id)
        .count()
        + 1
    )
    metrics = {
        **base.metrics,
        "requirements": len(requirements),
        "confirmed_requirements": sum(1 for row in requirements if row.status in {"CONFIRMED", "WAIVED"}),
        "shortages": len(shortages),
        "missing_categories": sorted(missing_categories),
    }
    assessment = WorkPackageReadinessAssessment(
        amo_id=amo_id,
        work_package_id=package_id,
        version=version,
        status=status_value,
        blockers_json=blockers,
        warnings_json=warnings,
        metrics_json=metrics,
        assessed_by_user_id=actor.id,
        assessed_at=_utcnow(),
    )
    package.readiness_status = status_value
    package.readiness_json = {
        "blockers": blockers,
        "warnings": warnings,
        "metrics": metrics,
        "assessment_version": version,
        "generated_at": assessment.assessed_at.isoformat(),
    }
    db.add(package)
    db.add(assessment)
    db.flush()
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor.id,
        entity_type="WorkPackageReadinessAssessment",
        entity_id=assessment.id,
        action="assess",
        after={"package_id": package_id, "status": status_value, "version": version},
    )
    return assessment


def _package_manifest(db: Session, *, package_id: int, amo_id: str) -> dict[str, Any]:
    package = package_services._get_package(db, amo_id=amo_id, package_id=package_id)
    package_payload = package_services.package_read(package).model_dump(mode="json")
    requirements = [
        ReadinessRequirementRead.model_validate(row).model_dump(mode="json")
        for row in db.query(WorkPackageReadinessRequirement).filter(
            WorkPackageReadinessRequirement.amo_id == amo_id,
            WorkPackageReadinessRequirement.work_package_id == package_id,
        ).all()
    ]
    latest_assessment = (
        db.query(WorkPackageReadinessAssessment)
        .filter(
            WorkPackageReadinessAssessment.amo_id == amo_id,
            WorkPackageReadinessAssessment.work_package_id == package_id,
        )
        .order_by(WorkPackageReadinessAssessment.version.desc())
        .first()
    )
    orders = []
    for link in package.order_links or []:
        order = link.work_order
        orders.append({
            "id": order.id,
            "wo_number": order.wo_number,
            "status": order.status.value if hasattr(order.status, "value") else str(order.status),
            "tasks": [
                {
                    "id": task.id,
                    "task_code": task.task_code,
                    "title": task.title,
                    "status": task.status.value if hasattr(task.status, "value") else str(task.status),
                    "estimated_manhours": float(task.estimated_manhours or 0),
                    "requires_duplicate_inspection": bool(task.requires_duplicate_inspection),
                }
                for task in order.tasks or []
            ],
        })
    return {
        "package": package_payload,
        "orders": orders,
        "requirements": requirements,
        "assessment": ReadinessAssessmentRead.model_validate(latest_assessment).model_dump(mode="json") if latest_assessment else None,
        "generated_at": _utcnow().isoformat(),
    }


def freeze_package(
    db: Session,
    *,
    amo_id: str,
    package_id: int,
    payload: PackageFreezeCreate,
    actor: User,
) -> WorkPackageFreeze:
    latest_assessment = (
        db.query(WorkPackageReadinessAssessment)
        .filter(
            WorkPackageReadinessAssessment.amo_id == amo_id,
            WorkPackageReadinessAssessment.work_package_id == package_id,
        )
        .order_by(WorkPackageReadinessAssessment.version.desc())
        .first()
    )
    if not latest_assessment or latest_assessment.status != "READY":
        raise HTTPException(status_code=409, detail="A READY package assessment is required before freeze")
    for current in db.query(WorkPackageFreeze).filter(
        WorkPackageFreeze.amo_id == amo_id,
        WorkPackageFreeze.work_package_id == package_id,
        WorkPackageFreeze.status == "ACTIVE",
    ).all():
        current.status = "SUPERSEDED"
        db.add(current)
    version = db.query(WorkPackageFreeze).filter(WorkPackageFreeze.work_package_id == package_id).count() + 1
    manifest = _package_manifest(db, package_id=package_id, amo_id=amo_id)
    freeze = WorkPackageFreeze(
        amo_id=amo_id,
        work_package_id=package_id,
        version=version,
        status="ACTIVE",
        manifest_hash=_hash(manifest),
        manifest_json=manifest,
        reason=payload.reason,
        frozen_by_user_id=actor.id,
        frozen_at=_utcnow(),
    )
    db.add(freeze)
    db.flush()
    _audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor.id,
        entity_type="WorkPackageFreeze",
        entity_id=freeze.id,
        action="freeze",
        after={"package_id": package_id, "version": version, "manifest_hash": freeze.manifest_hash},
    )
    return freeze


def list_assessments(db: Session, *, amo_id: str, package_id: int) -> list[ReadinessAssessmentRead]:
    rows = db.query(WorkPackageReadinessAssessment).filter(
        WorkPackageReadinessAssessment.amo_id == amo_id,
        WorkPackageReadinessAssessment.work_package_id == package_id,
    ).order_by(WorkPackageReadinessAssessment.version.desc()).all()
    return [ReadinessAssessmentRead.model_validate(row) for row in rows]


def list_freezes(db: Session, *, amo_id: str, package_id: int) -> list[PackageFreezeRead]:
    rows = db.query(WorkPackageFreeze).filter(
        WorkPackageFreeze.amo_id == amo_id,
        WorkPackageFreeze.work_package_id == package_id,
    ).order_by(WorkPackageFreeze.version.desc()).all()
    return [PackageFreezeRead.model_validate(row) for row in rows]


def dashboard(db: Session, *, amo_id: str) -> ReadinessDashboardRead:
    latest_assessments: dict[int, WorkPackageReadinessAssessment] = {}
    for row in db.query(WorkPackageReadinessAssessment).filter(
        WorkPackageReadinessAssessment.amo_id == amo_id
    ).order_by(WorkPackageReadinessAssessment.work_package_id.asc(), WorkPackageReadinessAssessment.version.desc()).all():
        latest_assessments.setdefault(row.work_package_id, row)
    return ReadinessDashboardRead(
        scenarios=db.query(PlanningForecastScenario).filter(PlanningForecastScenario.amo_id == amo_id).count(),
        completed_scenarios=db.query(PlanningForecastScenario).filter(
            PlanningForecastScenario.amo_id == amo_id,
            PlanningForecastScenario.status == "COMPLETE",
        ).count(),
        packages_assessed=len(latest_assessments),
        ready_packages=sum(1 for row in latest_assessments.values() if row.status == "READY"),
        blocked_packages=sum(1 for row in latest_assessments.values() if row.status == "BLOCKED"),
        shortages=db.query(WorkPackageReadinessRequirement).filter(
            WorkPackageReadinessRequirement.amo_id == amo_id,
            WorkPackageReadinessRequirement.status.in_(["REQUIRED", "SHORTAGE"]),
        ).count(),
        active_freezes=db.query(WorkPackageFreeze).filter(
            WorkPackageFreeze.amo_id == amo_id,
            WorkPackageFreeze.status == "ACTIVE",
        ).count(),
    )
