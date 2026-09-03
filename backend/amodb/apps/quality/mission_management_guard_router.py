from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_write_db

from .mission_models import QualityMission, QualityMissionGate
from .mission_router import (
    CAPABILITY_ADDITION_GATE_TEMPLATE,
    GatePatch,
    MissionCreate,
    MissionRisk,
    _load_mission,
    _mission_dict,
    _mission_ref,
    _utcnow,
    mission_readiness,
)
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


router = APIRouter(prefix="/missions", tags=["Quality mission management"])


class MissionPatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None
    scope: dict[str, Any] | None = None
    regulatory_basis: list[dict[str, Any] | str] | None = None
    risk_level: MissionRisk | None = None
    owner_user_id: str | None = Field(default=None, max_length=36)
    sponsor_user_id: str | None = Field(default=None, max_length=36)
    target_date: date | None = None


class MissionGateCreate(BaseModel):
    gate_code: str = Field(min_length=2, max_length=64, pattern=r"^[A-Z0-9_\-]+$")
    title: str = Field(min_length=3, max_length=255)
    category: str = Field(min_length=2, max_length=80)
    description: str | None = None
    gate_type: Literal["HARD", "SOFT"] = "HARD"
    requirement_ref: str | None = Field(default=None, max_length=255)
    source_owner_module: str = Field(min_length=2, max_length=80)
    source_type: str = Field(min_length=2, max_length=48)
    owner_user_id: str | None = Field(default=None, max_length=36)
    due_date: date | None = None
    sort_order: int = Field(default=100, ge=0, le=10000)


def _tenant_user_or_422(db: Session, *, amo_id: str, user_id: str | None, label: str) -> str | None:
    if not user_id:
        return None
    user = (
        db.query(account_models.User.id)
        .filter(
            account_models.User.id == user_id,
            account_models.User.amo_id == amo_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        )
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{label} must reference a user in the current AMO tenant.",
        )
    return str(user_id)


def _assert_mission_mutable(mission: QualityMission) -> None:
    if mission.status not in {"PLANNING", "IN_PROGRESS", "GATE_REVIEW"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Mission scope and readiness gates are immutable after self-evaluation or terminal approval. Create a new Mission for changed scope.",
        )


def _seed_capability_gates(db: Session, *, mission: QualityMission, amo_id: str, now) -> None:
    for item in CAPABILITY_ADDITION_GATE_TEMPLATE:
        db.add(
            QualityMissionGate(
                amo_id=amo_id,
                mission_id=mission.id,
                gate_code=item["gate_code"],
                title=item["title"],
                category=item["category"],
                gate_type="HARD",
                status="PENDING",
                requirement_ref=item["requirement_ref"],
                source_owner_module=item["source_owner_module"],
                source_type=item["source_type"],
                evidence_status="UNLINKED",
                sort_order=item["sort_order"],
                created_at=now,
                updated_at=now,
            )
        )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_governed_mission(
    payload: MissionCreate,
    ctx: TenantContext = Depends(require_quality_permission("qms.change.manage")),
    db: Session = Depends(get_write_db),
):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    owner_user_id = _tenant_user_or_422(
        db,
        amo_id=ctx.amo_id,
        user_id=payload.owner_user_id or ctx.user_id,
        label="Mission owner",
    )
    sponsor_user_id = _tenant_user_or_422(
        db,
        amo_id=ctx.amo_id,
        user_id=payload.sponsor_user_id,
        label="Accountable Executive",
    )

    now = _utcnow()
    mission = QualityMission(
        amo_id=ctx.amo_id,
        mission_ref=_mission_ref(),
        mission_type=payload.mission_type,
        title=payload.title.strip(),
        description=payload.description,
        scope=payload.scope,
        regulatory_basis=payload.regulatory_basis,
        risk_level=payload.risk_level,
        status="PLANNING",
        owner_user_id=owner_user_id,
        requested_by_user_id=ctx.user_id,
        sponsor_user_id=sponsor_user_id,
        requested_at=now,
        target_date=payload.target_date,
        started_at=now,
        created_by_user_id=ctx.user_id,
        updated_by_user_id=ctx.user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(mission)
    db.flush()
    if payload.mission_type == "CAPABILITY_ADDITION":
        _seed_capability_gates(db, mission=mission, amo_id=ctx.amo_id, now=now)

    mission_id = str(mission.id)
    db.commit()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _mission_dict(_load_mission(db, amo_id=ctx.amo_id, mission_id=mission_id), include_detail=True)


@router.patch("/{mission_id}")
def update_mission_metadata(
    mission_id: str,
    payload: MissionPatch,
    ctx: TenantContext = Depends(require_quality_permission("qms.change.manage")),
    db: Session = Depends(get_write_db),
):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    mission = _load_mission(db, amo_id=ctx.amo_id, mission_id=mission_id, for_update=True)
    _assert_mission_mutable(mission)
    updates = payload.model_dump(exclude_unset=True)

    if "owner_user_id" in updates:
        updates["owner_user_id"] = _tenant_user_or_422(
            db,
            amo_id=ctx.amo_id,
            user_id=updates["owner_user_id"],
            label="Mission owner",
        )
    if "sponsor_user_id" in updates:
        updates["sponsor_user_id"] = _tenant_user_or_422(
            db,
            amo_id=ctx.amo_id,
            user_id=updates["sponsor_user_id"],
            label="Accountable Executive",
        )
    if "title" in updates and updates["title"] is not None:
        updates["title"] = str(updates["title"]).strip()

    for field, value in updates.items():
        setattr(mission, field, value)
    mission.updated_by_user_id = ctx.user_id
    mission.updated_at = _utcnow()
    db.commit()

    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _mission_dict(_load_mission(db, amo_id=ctx.amo_id, mission_id=mission_id), include_detail=True)


@router.post("/{mission_id}/gates", status_code=status.HTTP_201_CREATED)
def create_governed_mission_gate(
    mission_id: str,
    payload: MissionGateCreate,
    ctx: TenantContext = Depends(require_quality_permission("qms.change.manage")),
    db: Session = Depends(get_write_db),
):
    """Add a governed readiness gate for Mission types without a fixed template."""

    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    mission = _load_mission(db, amo_id=ctx.amo_id, mission_id=mission_id, for_update=True)
    _assert_mission_mutable(mission)
    gate_code = payload.gate_code.strip().upper()
    duplicate = db.query(QualityMissionGate.id).filter(
        QualityMissionGate.amo_id == ctx.amo_id,
        QualityMissionGate.mission_id == mission.id,
        QualityMissionGate.gate_code == gate_code,
    ).first()
    if duplicate is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Mission gate code already exists.")
    owner_user_id = _tenant_user_or_422(
        db,
        amo_id=ctx.amo_id,
        user_id=payload.owner_user_id,
        label="Gate owner",
    )
    now = _utcnow()
    db.add(QualityMissionGate(
        amo_id=ctx.amo_id,
        mission_id=mission.id,
        gate_code=gate_code,
        title=payload.title.strip(),
        category=payload.category.strip(),
        description=payload.description,
        gate_type=payload.gate_type,
        status="PENDING",
        requirement_ref=payload.requirement_ref,
        source_owner_module=payload.source_owner_module.strip().lower(),
        source_type=payload.source_type.strip().upper(),
        evidence_status="UNLINKED",
        owner_user_id=owner_user_id,
        due_date=payload.due_date,
        sort_order=payload.sort_order,
        created_at=now,
        updated_at=now,
    ))
    mission.status = "IN_PROGRESS"
    mission.updated_by_user_id = ctx.user_id
    mission.updated_at = now
    db.commit()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _mission_dict(_load_mission(db, amo_id=ctx.amo_id, mission_id=mission_id), include_detail=True)


@router.patch("/{mission_id}/gates/{gate_id}")
def update_governed_mission_gate(
    mission_id: str,
    gate_id: str,
    payload: GatePatch,
    ctx: TenantContext = Depends(require_quality_permission("qms.change.manage")),
    db: Session = Depends(get_write_db),
):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    mission = _load_mission(db, amo_id=ctx.amo_id, mission_id=mission_id, for_update=True)
    _assert_mission_mutable(mission)
    gate = (
        db.query(QualityMissionGate)
        .filter(
            QualityMissionGate.amo_id == ctx.amo_id,
            QualityMissionGate.mission_id == mission.id,
            QualityMissionGate.id == gate_id,
        )
        .with_for_update()
        .first()
    )
    if not gate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission gate not found.")

    updates = payload.model_dump(exclude_unset=True)
    if "owner_user_id" in updates:
        updates["owner_user_id"] = _tenant_user_or_422(
            db,
            amo_id=ctx.amo_id,
            user_id=updates["owner_user_id"],
            label="Gate owner",
        )

    candidate_evidence_status = updates.get("evidence_status", gate.evidence_status)
    candidate_source_type = updates.get("source_type", gate.source_type)
    candidate_source_id = updates.get("source_id", gate.source_id)
    candidate_status = updates.get("status", gate.status)
    candidate_blocking_reason = str(updates.get("blocking_reason", gate.blocking_reason) or "").strip()

    if candidate_status == "PASS":
        if candidate_evidence_status != "VERIFIED" or not candidate_source_type or not candidate_source_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A Mission gate may PASS only with a VERIFIED authoritative source reference.",
            )
    if candidate_status in {"FAIL", "BLOCKED"} and not candidate_blocking_reason:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="FAIL or BLOCKED Mission gates require a blocking reason.",
        )

    for field, value in updates.items():
        setattr(gate, field, value)
    gate.updated_at = _utcnow()
    if candidate_status == "PASS":
        gate.passed_at = _utcnow()
        gate.passed_by_user_id = ctx.user_id
        gate.blocking_reason = None
    elif candidate_status != "PASS":
        gate.passed_at = None
        gate.passed_by_user_id = None

    # Include the locked gate's new in-memory state when deriving readiness.
    readiness = mission_readiness(list(mission.gates))
    mission.status = "GATE_REVIEW" if readiness["ready_for_quality_self_evaluation"] else "IN_PROGRESS"
    mission.updated_by_user_id = ctx.user_id
    mission.updated_at = _utcnow()
    db.commit()

    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _mission_dict(_load_mission(db, amo_id=ctx.amo_id, mission_id=mission_id), include_detail=True)
