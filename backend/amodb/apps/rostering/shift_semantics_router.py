from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from ..workforce import permissions as workforce_permissions
from . import common, models
from .code_registry_models import (
    RosterCalendarMode,
    RosterCodeVerificationStatus,
    RosterDutySemantic,
    RosterShiftTemplatePolicy,
)

router = APIRouter(prefix="/rostering", tags=["rostering-shift-semantics"])


class ShiftOperationalPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    shift_template_id: str
    code: str
    label: str
    kind: str
    default_start_time: Optional[str] = None
    default_end_time: Optional[str] = None
    spans_midnight: bool
    counts_as_duty: bool
    counts_as_rest: bool
    on_site_availability: bool
    scheduling_eligible: bool
    effective_scheduling_eligible: bool
    calendar_mode: RosterCalendarMode
    duty_semantic: RosterDutySemantic
    verification_status: RosterCodeVerificationStatus
    unpaid_break_minutes: int
    requires_personnel_acknowledgement: bool
    requires_supervisor_approval: bool
    fatigue_weight: float
    pay_classification: Optional[str] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    source_reference: Optional[str] = None


class ShiftOperationalPolicyUpdate(BaseModel):
    counts_as_duty: Optional[bool] = None
    counts_as_rest: Optional[bool] = None
    on_site_availability: Optional[bool] = None
    scheduling_eligible: Optional[bool] = None
    calendar_mode: Optional[RosterCalendarMode] = None
    duty_semantic: Optional[RosterDutySemantic] = None
    verification_status: Optional[RosterCodeVerificationStatus] = None
    unpaid_break_minutes: Optional[int] = Field(default=None, ge=0, le=24 * 60)
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


def _amo(user: account_models.User) -> str:
    return common.effective_amo_id(user)


def _require_view(db: Session, user: account_models.User) -> None:
    if not common.can_view_roster(db, user=user):
        raise HTTPException(status_code=403, detail={"code": "ROSTER_ACCESS_DENIED"})


def _require_manage(db: Session, user: account_models.User) -> None:
    workforce_permissions.require_permission(
        db,
        user=user,
        permission=workforce_permissions.PermissionCode.ROSTER_MANAGE_SHIFT_TEMPLATES,
    )


def _default_semantic(row: models.ShiftTemplate) -> RosterDutySemantic:
    if row.kind == models.ShiftTemplateKind.STANDBY:
        return RosterDutySemantic.STANDBY
    if row.kind == models.ShiftTemplateKind.TRAINING:
        return RosterDutySemantic.TRAINING
    if row.kind == models.ShiftTemplateKind.OFF:
        return RosterDutySemantic.REST
    if row.kind == models.ShiftTemplateKind.LEAVE:
        return RosterDutySemantic.LEAVE
    return RosterDutySemantic.DUTY


def _spans_midnight(row: models.ShiftTemplate) -> bool:
    start = (row.default_start_time or "").strip()
    end = (row.default_end_time or "").strip()
    return bool(start and end and end <= start)


def _serialize(row: models.ShiftTemplate, policy: RosterShiftTemplatePolicy | None) -> ShiftOperationalPolicyRead:
    semantic = policy.duty_semantic if policy else _default_semantic(row)
    counts_as_rest = bool(policy.counts_as_rest) if policy else bool(
        not row.counts_as_duty and semantic in {RosterDutySemantic.REST, RosterDutySemantic.OFF}
    )
    on_site = bool(policy.on_site_availability) if policy else bool(
        row.counts_as_duty and semantic == RosterDutySemantic.STANDBY
    )
    scheduling_eligible = bool(policy.scheduling_eligible) if policy else True
    return ShiftOperationalPolicyRead(
        shift_template_id=row.id,
        code=row.code,
        label=row.label,
        kind=common.enum_value(row.kind),
        default_start_time=row.default_start_time,
        default_end_time=row.default_end_time,
        spans_midnight=_spans_midnight(row),
        counts_as_duty=bool(row.counts_as_duty),
        counts_as_rest=counts_as_rest,
        on_site_availability=on_site,
        scheduling_eligible=scheduling_eligible,
        effective_scheduling_eligible=bool(row.is_active and scheduling_eligible),
        calendar_mode=policy.calendar_mode if policy else (
            RosterCalendarMode.ALL_DAY
            if row.kind in {models.ShiftTemplateKind.OFF, models.ShiftTemplateKind.LEAVE}
            else RosterCalendarMode.TIMED
        ),
        duty_semantic=semantic,
        verification_status=policy.verification_status if policy else RosterCodeVerificationStatus.UNRESOLVED,
        unpaid_break_minutes=int(policy.unpaid_break_minutes or 0) if policy else 0,
        requires_personnel_acknowledgement=bool(policy.requires_personnel_acknowledgement) if policy else False,
        requires_supervisor_approval=bool(policy.requires_supervisor_approval) if policy else False,
        fatigue_weight=float(policy.fatigue_weight or 0.0) if policy else 1.0,
        pay_classification=policy.pay_classification if policy else None,
        effective_from=policy.effective_from if policy else None,
        effective_to=policy.effective_to if policy else None,
        source_reference=policy.source_reference if policy else None,
    )


def _policy_or_create(
    db: Session,
    *,
    amo_id: str,
    row: models.ShiftTemplate,
    actor_user_id: str,
) -> RosterShiftTemplatePolicy:
    policy = db.query(RosterShiftTemplatePolicy).filter(
        RosterShiftTemplatePolicy.amo_id == amo_id,
        RosterShiftTemplatePolicy.shift_template_id == row.id,
    ).with_for_update().first()
    if policy:
        return policy
    semantic = _default_semantic(row)
    policy = RosterShiftTemplatePolicy(
        amo_id=amo_id,
        shift_template_id=row.id,
        unpaid_break_minutes=0,
        calendar_mode=(
            RosterCalendarMode.ALL_DAY
            if row.kind in {models.ShiftTemplateKind.OFF, models.ShiftTemplateKind.LEAVE}
            else RosterCalendarMode.TIMED
        ),
        duty_semantic=semantic,
        verification_status=RosterCodeVerificationStatus.UNRESOLVED,
        counts_as_rest=bool(not row.counts_as_duty and semantic in {RosterDutySemantic.REST, RosterDutySemantic.OFF}),
        on_site_availability=bool(row.counts_as_duty and semantic == RosterDutySemantic.STANDBY),
        scheduling_eligible=True,
        requires_personnel_acknowledgement=False,
        requires_supervisor_approval=False,
        fatigue_weight=1.0,
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    db.add(policy)
    db.flush()
    return policy


def _validate_semantics(
    *,
    counts_as_duty: bool,
    counts_as_rest: bool,
    on_site_availability: bool,
    duty_semantic: RosterDutySemantic,
) -> None:
    if counts_as_duty and counts_as_rest:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ROSTER_SHIFT_SEMANTICS_CONFLICT",
                "message": "A shift cannot simultaneously count as duty and as a roster rest designation.",
            },
        )
    if on_site_availability and not counts_as_duty:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ROSTER_ONSITE_STANDBY_MUST_COUNT_AS_DUTY",
                "message": "On-site availability/standby must count as duty because personnel are not relieved from all duties.",
            },
        )
    if duty_semantic in {RosterDutySemantic.REST, RosterDutySemantic.OFF} and counts_as_duty:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ROSTER_REST_SEMANTIC_COUNTS_AS_DUTY",
                "message": "REST/OFF semantics cannot be configured to count as duty. Use a duty or standby semantic instead.",
            },
        )


@router.get("/shift-operational-policies", response_model=list[ShiftOperationalPolicyRead])
def list_shift_operational_policies(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_view(db, current_user)
    amo_id = _amo(current_user)
    templates = db.query(models.ShiftTemplate).filter(
        models.ShiftTemplate.amo_id == amo_id,
    ).order_by(models.ShiftTemplate.display_order.asc(), models.ShiftTemplate.code.asc()).all()
    policies = {
        row.shift_template_id: row
        for row in db.query(RosterShiftTemplatePolicy).filter(
            RosterShiftTemplatePolicy.amo_id == amo_id,
        ).all()
    }
    return [_serialize(row, policies.get(row.id)) for row in templates]


@router.patch(
    "/shift-templates/{template_id}/operational-policy",
    response_model=ShiftOperationalPolicyRead,
)
def update_shift_operational_policy(
    template_id: str,
    payload: ShiftOperationalPolicyUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_manage(db, current_user)
    amo_id = _amo(current_user)
    template = db.query(models.ShiftTemplate).filter(
        models.ShiftTemplate.amo_id == amo_id,
        models.ShiftTemplate.id == template_id,
    ).with_for_update().first()
    if template is None:
        raise HTTPException(status_code=404, detail={"code": "ROSTER_SHIFT_TEMPLATE_NOT_FOUND"})
    policy = _policy_or_create(
        db,
        amo_id=amo_id,
        row=template,
        actor_user_id=current_user.id,
    )
    before = _serialize(template, policy).model_dump(mode="json")
    fields = payload.model_fields_set
    counts_as_duty = payload.counts_as_duty if "counts_as_duty" in fields else bool(template.counts_as_duty)
    counts_as_rest = payload.counts_as_rest if "counts_as_rest" in fields else bool(policy.counts_as_rest)
    on_site = payload.on_site_availability if "on_site_availability" in fields else bool(policy.on_site_availability)
    semantic = payload.duty_semantic if "duty_semantic" in fields else policy.duty_semantic
    _validate_semantics(
        counts_as_duty=bool(counts_as_duty),
        counts_as_rest=bool(counts_as_rest),
        on_site_availability=bool(on_site),
        duty_semantic=semantic,
    )

    if "counts_as_duty" in fields:
        template.counts_as_duty = bool(payload.counts_as_duty)
        template.updated_by_user_id = current_user.id
        db.add(template)
    for field in (
        "counts_as_rest",
        "on_site_availability",
        "scheduling_eligible",
        "calendar_mode",
        "duty_semantic",
        "verification_status",
        "unpaid_break_minutes",
        "requires_personnel_acknowledgement",
        "requires_supervisor_approval",
        "fatigue_weight",
        "pay_classification",
        "effective_from",
        "effective_to",
        "source_reference",
    ):
        if field in fields:
            setattr(policy, field, getattr(payload, field))
    if policy.effective_from and policy.effective_to and policy.effective_to < policy.effective_from:
        raise HTTPException(
            status_code=409,
            detail={"code": "ROSTER_SHIFT_POLICY_DATE_INVALID", "message": "Policy effective_to precedes effective_from."},
        )
    policy.updated_by_user_id = current_user.id
    db.add(policy)
    db.flush()
    after = _serialize(template, policy)
    common.audit(
        db,
        amo_id=amo_id,
        actor_user_id=current_user.id,
        entity_type="RosterShiftTemplatePolicy",
        entity_id=policy.id,
        action="operational_policy_update",
        before=before,
        after=after.model_dump(mode="json"),
        critical=True,
    )
    db.commit()
    db.refresh(template)
    db.refresh(policy)
    return _serialize(template, policy)
