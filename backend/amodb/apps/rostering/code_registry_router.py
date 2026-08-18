from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from ..workforce import permissions as workforce_permissions
from . import code_registry, common, models, schemas, services, template_usage_policy
from .code_registry_models import (
    RosterCalendarMode,
    RosterCodeVerificationStatus,
    RosterDutySemantic,
    RosterShiftTemplatePolicy,
)

router = APIRouter(prefix="/rostering", tags=["rostering-code-registry"])


class ShiftPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    unpaid_break_minutes: int = 0
    calendar_mode: RosterCalendarMode = RosterCalendarMode.TIMED
    duty_semantic: RosterDutySemantic = RosterDutySemantic.DUTY
    verification_status: RosterCodeVerificationStatus = RosterCodeVerificationStatus.UNRESOLVED
    requires_personnel_acknowledgement: bool = False
    requires_supervisor_approval: bool = False
    fatigue_weight: float = 1.0
    pay_classification: Optional[str] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    source_reference: Optional[str] = None


class ShiftPolicyUpdate(BaseModel):
    unpaid_break_minutes: Optional[int] = Field(default=None, ge=0, le=24 * 60)
    calendar_mode: Optional[RosterCalendarMode] = None
    duty_semantic: Optional[RosterDutySemantic] = None
    verification_status: Optional[RosterCodeVerificationStatus] = None
    requires_personnel_acknowledgement: Optional[bool] = None
    requires_supervisor_approval: Optional[bool] = None
    fatigue_weight: Optional[float] = Field(default=None, ge=0, le=100)
    pay_classification: Optional[str] = Field(default=None, max_length=64)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    source_reference: Optional[str] = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        return self


class RosterCodeRegistryEntry(BaseModel):
    id: str
    code: str
    label: str
    kind: str
    default_start_time: Optional[str] = None
    default_end_time: Optional[str] = None
    duration_minutes: Optional[int] = None
    counts_as_duty: bool
    is_active: bool
    description: Optional[str] = None
    department_ids: list[str] = Field(default_factory=list)
    policy: ShiftPolicyRead
    usage_count: int
    can_delete: bool


class StarterPackResult(BaseModel):
    created_codes: list[str]
    skipped_existing_codes: list[str]
    recommended_codes: list[str]


class ShiftTemplateMergeRequest(BaseModel):
    target_template_id: str = Field(min_length=1)
    target_code: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9]{1,2}$")
    reason: str = Field(min_length=5, max_length=1000)
    policy_resolution: str = Field(default="REQUIRE_MATCH", pattern=r"^(REQUIRE_MATCH|KEEP_TARGET|KEEP_SOURCE)$")


class ShiftTemplateMergeResult(BaseModel):
    target_template: schemas.ShiftTemplateRead
    moved_counts: dict[str, int]


def _amo(user: account_models.User) -> str:
    return common.effective_amo_id(user)


def _require_manage(db: Session, user: account_models.User) -> None:
    workforce_permissions.require_permission(
        db,
        user=user,
        permission=workforce_permissions.PermissionCode.ROSTER_MANAGE_SHIFT_TEMPLATES,
    )


def _require_semantics(db: Session, user: account_models.User) -> None:
    workforce_permissions.require_permission(
        db,
        user=user,
        permission=workforce_permissions.PermissionCode.ROSTER_MANAGE_SHIFT_SEMANTICS,
    )


def _template_or_404(db: Session, *, amo_id: str, template_id: str) -> models.ShiftTemplate:
    row = (
        db.query(models.ShiftTemplate)
        .filter(models.ShiftTemplate.amo_id == amo_id, models.ShiftTemplate.id == template_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Shift template not found")
    return row


def _default_semantic(row: models.ShiftTemplate) -> RosterDutySemantic:
    if row.kind == models.ShiftTemplateKind.STANDBY:
        return RosterDutySemantic.STANDBY
    if row.kind == models.ShiftTemplateKind.TRAINING:
        return RosterDutySemantic.TRAINING
    if row.kind == models.ShiftTemplateKind.OFF:
        return RosterDutySemantic.OFF
    if row.kind == models.ShiftTemplateKind.LEAVE:
        return RosterDutySemantic.LEAVE
    return RosterDutySemantic.DUTY


def _default_policy(row: models.ShiftTemplate) -> ShiftPolicyRead:
    mode = RosterCalendarMode.ALL_DAY if row.kind in {models.ShiftTemplateKind.OFF, models.ShiftTemplateKind.LEAVE} else RosterCalendarMode.TIMED
    return ShiftPolicyRead(
        unpaid_break_minutes=0,
        calendar_mode=mode,
        duty_semantic=_default_semantic(row),
        verification_status=RosterCodeVerificationStatus.UNRESOLVED,
        requires_personnel_acknowledgement=False,
        requires_supervisor_approval=False,
        fatigue_weight=1.0,
    )


@router.get("/shift-templates/code-registry", response_model=list[RosterCodeRegistryEntry])
def roster_code_registry(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not services.can_view_roster(db, user=current_user):
        raise HTTPException(status_code=403, detail="Roster access denied")
    amo_id = _amo(current_user)
    templates = (
        db.query(models.ShiftTemplate)
        .filter(models.ShiftTemplate.amo_id == amo_id)
        .order_by(models.ShiftTemplate.display_order.asc(), models.ShiftTemplate.code.asc())
        .all()
    )
    policies = {
        row.shift_template_id: row
        for row in db.query(RosterShiftTemplatePolicy)
        .filter(RosterShiftTemplatePolicy.amo_id == amo_id)
        .all()
    }
    result: list[RosterCodeRegistryEntry] = []
    for row in templates:
        usage = code_registry.template_usage_count(db, amo_id=amo_id, template_id=row.id)
        policy = policies.get(row.id)
        result.append(
            RosterCodeRegistryEntry(
                id=row.id,
                code=row.code,
                label=row.label,
                kind=str(getattr(row.kind, "value", row.kind)),
                default_start_time=row.default_start_time,
                default_end_time=row.default_end_time,
                duration_minutes=row.duration_minutes,
                counts_as_duty=row.counts_as_duty,
                is_active=row.is_active,
                description=row.description,
                department_ids=row.department_ids,
                policy=ShiftPolicyRead.model_validate(policy) if policy else _default_policy(row),
                usage_count=usage,
                can_delete=usage == 0,
            )
        )
    return result


@router.post(
    "/shift-templates/starter-pack",
    response_model=StarterPackResult,
    status_code=status.HTTP_201_CREATED,
)
def install_roster_starter_pack(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_manage(db, current_user)
    try:
        created, skipped = code_registry.install_starter_pack(
            db,
            amo_id=_amo(current_user),
            actor_user_id=current_user.id,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return StarterPackResult(
        created_codes=[row.code for row in created],
        skipped_existing_codes=skipped,
        recommended_codes=list(code_registry.STARTER_CODES),
    )


@router.patch("/shift-templates/{template_id}/policy", response_model=ShiftPolicyRead)
def update_shift_policy(
    template_id: str,
    payload: ShiftPolicyUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    # This legacy policy endpoint changes duty/rest semantics, verification,
    # acknowledgement and fatigue controls. It must use the same governed
    # permission as the newer operational-policy endpoint; ordinary planners
    # may still manage names/times/templates but cannot redefine compliance.
    _require_semantics(db, current_user)
    amo_id = _amo(current_user)
    template = _template_or_404(db, amo_id=amo_id, template_id=template_id)
    row = code_registry.policy_for_template(db, amo_id=amo_id, template_id=template_id)
    before = None
    if row is None:
        row = RosterShiftTemplatePolicy(
            amo_id=amo_id,
            shift_template_id=template_id,
            calendar_mode=RosterCalendarMode.ALL_DAY if template.kind in {models.ShiftTemplateKind.OFF, models.ShiftTemplateKind.LEAVE} else RosterCalendarMode.TIMED,
            duty_semantic=_default_semantic(template),
            verification_status=RosterCodeVerificationStatus.UNRESOLVED,
            created_by_user_id=current_user.id,
            updated_by_user_id=current_user.id,
        )
        db.add(row)
    else:
        before = {
            "unpaid_break_minutes": row.unpaid_break_minutes,
            "calendar_mode": str(getattr(row.calendar_mode, "value", row.calendar_mode)),
            "duty_semantic": str(getattr(row.duty_semantic, "value", row.duty_semantic)),
            "verification_status": str(getattr(row.verification_status, "value", row.verification_status)),
            "requires_personnel_acknowledgement": row.requires_personnel_acknowledgement,
            "requires_supervisor_approval": row.requires_supervisor_approval,
            "fatigue_weight": row.fatigue_weight,
            "pay_classification": row.pay_classification,
            "effective_from": row.effective_from.isoformat() if row.effective_from else None,
            "effective_to": row.effective_to.isoformat() if row.effective_to else None,
            "source_reference": row.source_reference,
        }
    fields = payload.model_fields_set
    for field in fields:
        setattr(row, field, getattr(payload, field))
    if row.effective_from and row.effective_to and row.effective_to < row.effective_from:
        raise HTTPException(status_code=400, detail="effective_to must be on or after effective_from")
    row.updated_by_user_id = current_user.id
    db.add(row)
    db.flush()
    common.audit(
        db,
        amo_id=amo_id,
        actor_user_id=current_user.id,
        entity_type="RosterShiftTemplatePolicy",
        entity_id=row.id,
        action="update" if before else "create",
        before=before,
        after={
            "shift_template_id": template_id,
            "unpaid_break_minutes": row.unpaid_break_minutes,
            "calendar_mode": str(getattr(row.calendar_mode, "value", row.calendar_mode)),
            "duty_semantic": str(getattr(row.duty_semantic, "value", row.duty_semantic)),
            "verification_status": str(getattr(row.verification_status, "value", row.verification_status)),
            "requires_personnel_acknowledgement": row.requires_personnel_acknowledgement,
            "requires_supervisor_approval": row.requires_supervisor_approval,
            "fatigue_weight": row.fatigue_weight,
            "pay_classification": row.pay_classification,
            "effective_from": row.effective_from.isoformat() if row.effective_from else None,
            "effective_to": row.effective_to.isoformat() if row.effective_to else None,
            "source_reference": row.source_reference,
        },
    )
    db.commit()
    db.refresh(row)
    return row


@router.post(
    "/shift-templates/{template_id}/merge",
    response_model=ShiftTemplateMergeResult,
)
def merge_duplicate_roster_code(
    template_id: str,
    payload: ShiftTemplateMergeRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_manage(db, current_user)
    try:
        target, moved_counts = template_usage_policy.merge_duplicate_template(
            db,
            amo_id=_amo(current_user),
            source_template_id=template_id,
            target_template_id=payload.target_template_id,
            actor_user_id=current_user.id,
            reason=payload.reason,
            target_code=payload.target_code,
            policy_resolution=payload.policy_resolution,
        )
        db.commit()
        db.refresh(target)
        return ShiftTemplateMergeResult(
            target_template=schemas.ShiftTemplateRead.model_validate(target),
            moved_counts=moved_counts,
        )
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/shift-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_unused_roster_code(
    template_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_manage(db, current_user)
    try:
        code_registry.delete_unused_template(
            db,
            amo_id=_amo(current_user),
            template_id=template_id,
            actor_user_id=current_user.id,
        )
        db.commit()
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
