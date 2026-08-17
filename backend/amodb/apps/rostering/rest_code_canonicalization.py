from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from ..workforce import models as workforce_models
from ..workforce import permissions as workforce_permissions
from . import common, models
from .code_registry_models import (
    RosterCalendarMode,
    RosterCodeVerificationStatus,
    RosterDutySemantic,
    RosterShiftTemplatePolicy,
)
from .roster_control_models import RosterShiftAlias

router = APIRouter(prefix="/rostering", tags=["rostering-code-registry"])

_REST_ALIASES = ("O", "OF", "RR")


class RestCanonicalizationResult(BaseModel):
    canonical_template_id: str
    canonical_code: str = "RD"
    removed_codes: list[str]
    moved_counts: dict[str, int]


def _amo(user: account_models.User) -> str:
    return common.effective_amo_id(user)


def _normalize_target(
    db: Session,
    *,
    target: models.ShiftTemplate,
    actor_user_id: str,
) -> None:
    target.code = "RD"
    target.label = "Rest Day"
    target.kind = models.ShiftTemplateKind.OFF
    target.default_start_time = None
    target.default_end_time = None
    target.duration_minutes = 0
    target.counts_as_duty = False
    target.is_active = True
    target.updated_by_user_id = actor_user_id
    db.add(target)

    policy = db.query(RosterShiftTemplatePolicy).filter(
        RosterShiftTemplatePolicy.amo_id == target.amo_id,
        RosterShiftTemplatePolicy.shift_template_id == target.id,
    ).first()
    if policy is None:
        policy = RosterShiftTemplatePolicy(
            amo_id=target.amo_id,
            shift_template_id=target.id,
            created_by_user_id=actor_user_id,
        )
    policy.unpaid_break_minutes = 0
    policy.calendar_mode = RosterCalendarMode.ALL_DAY
    policy.duty_semantic = RosterDutySemantic.REST
    policy.verification_status = RosterCodeVerificationStatus.CONFIRMED
    policy.source_reference = "Canonical protected-rest code after O/OF/RR destructive consolidation."
    policy.updated_by_user_id = actor_user_id
    db.add(policy)


def canonicalize_rest_codes(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
) -> RestCanonicalizationResult:
    rows = db.query(models.ShiftTemplate).filter(
        models.ShiftTemplate.amo_id == amo_id,
        func.upper(models.ShiftTemplate.code).in_(("RD",) + _REST_ALIASES),
    ).with_for_update().all()
    by_code = {str(row.code or "").upper(): row for row in rows}
    target = by_code.get("RD")

    if target is None:
        source = next((by_code.get(code) for code in _REST_ALIASES if by_code.get(code) is not None), None)
        if source is None:
            raise LookupError("No RD, O, OF or RR rest template exists to canonicalize")
        target = source
        by_code.pop(str(source.code).upper(), None)

    _normalize_target(db, target=target, actor_user_id=actor_user_id)
    db.flush()

    moved_counts = {
        "roster_assignments": 0,
        "validation_rules": 0,
        "work_pattern_days": 0,
        "aliases": 0,
        "policies": 0,
    }
    removed_codes: list[str] = []

    for code in _REST_ALIASES:
        source = by_code.get(code)
        if source is None or source.id == target.id:
            continue
        moved_counts["roster_assignments"] += int(
            db.query(models.RosterAssignment).filter(
                models.RosterAssignment.amo_id == amo_id,
                models.RosterAssignment.shift_template_id == source.id,
            ).update(
                {
                    models.RosterAssignment.shift_template_id: target.id,
                    models.RosterAssignment.status: models.RosterAssignmentStatus.OFF,
                },
                synchronize_session=False,
            ) or 0
        )
        moved_counts["validation_rules"] += int(
            db.query(models.RosterRule).filter(
                models.RosterRule.amo_id == amo_id,
                models.RosterRule.shift_template_id == source.id,
            ).update({models.RosterRule.shift_template_id: target.id}, synchronize_session=False) or 0
        )
        moved_counts["work_pattern_days"] += int(
            db.query(workforce_models.WorkPatternDay).filter(
                workforce_models.WorkPatternDay.amo_id == amo_id,
                workforce_models.WorkPatternDay.shift_template_id == source.id,
            ).update(
                {
                    workforce_models.WorkPatternDay.shift_template_id: target.id,
                    workforce_models.WorkPatternDay.status: workforce_models.PatternDayStatus.OFF,
                    workforce_models.WorkPatternDay.start_time_local: None,
                    workforce_models.WorkPatternDay.end_time_local: None,
                    workforce_models.WorkPatternDay.spans_next_day: False,
                    workforce_models.WorkPatternDay.planned_minutes: 0,
                },
                synchronize_session=False,
            ) or 0
        )
        moved_counts["aliases"] += int(
            db.query(RosterShiftAlias).filter(
                RosterShiftAlias.amo_id == amo_id,
                RosterShiftAlias.shift_template_id == source.id,
            ).update({RosterShiftAlias.shift_template_id: target.id}, synchronize_session=False) or 0
        )

        source_policy = db.query(RosterShiftTemplatePolicy).filter(
            RosterShiftTemplatePolicy.amo_id == amo_id,
            RosterShiftTemplatePolicy.shift_template_id == source.id,
        ).first()
        if source_policy is not None:
            db.delete(source_policy)
            moved_counts["policies"] += 1

        removed_codes.append(code)
        db.delete(source)

    _normalize_target(db, target=target, actor_user_id=actor_user_id)
    db.flush()
    common.audit(
        db,
        amo_id=amo_id,
        actor_user_id=actor_user_id,
        entity_type="ShiftTemplate",
        entity_id=target.id,
        action="canonicalize_rest_codes",
        before={"equivalent_codes": ["RD", *_REST_ALIASES]},
        after={
            "canonical_code": "RD",
            "removed_codes": removed_codes,
            "moved_counts": moved_counts,
        },
        critical=True,
    )
    return RestCanonicalizationResult(
        canonical_template_id=str(target.id),
        removed_codes=removed_codes,
        moved_counts=moved_counts,
    )


@router.post("/shift-templates/canonicalize-rest", response_model=RestCanonicalizationResult)
def canonicalize_rest_templates(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    workforce_permissions.require_permission(
        db,
        user=current_user,
        permission=workforce_permissions.PermissionCode.ROSTER_MANAGE_SHIFT_TEMPLATES,
    )
    try:
        result = canonicalize_rest_codes(
            db,
            amo_id=_amo(current_user),
            actor_user_id=current_user.id,
        )
        db.commit()
        return result
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


__all__ = ["canonicalize_rest_codes", "router"]
