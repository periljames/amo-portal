from __future__ import annotations

"""Batch first-time cycle-position setup for large workforces.

Cycle anchors belong to Workforce work-pattern assignments. This endpoint only
changes that existing governed anchor; it does not create patterns, shifts or
operator defaults. A batch may span multiple pattern records only when their
full rotation signatures are identical.
"""

from datetime import date, timedelta
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from ..audit import services as audit_services
from ..workforce import models as workforce_models
from ..workforce import permissions as workforce_permissions
from ..workforce import services as workforce_services

router = APIRouter(prefix="/workforce", tags=["workforce"])

MAX_CYCLE_START_BATCH = 10_000


class CycleStartBatchItem(BaseModel):
    assignment_id: str = Field(min_length=1, max_length=64)
    target_date: date


class CycleStartBatchRequest(BaseModel):
    items: list[CycleStartBatchItem] = Field(min_length=1, max_length=MAX_CYCLE_START_BATCH)
    cycle_day_index: int = Field(ge=0, le=365)
    reason: str = Field(min_length=3, max_length=500)


class CycleStartBatchResponse(BaseModel):
    batch_id: str
    updated_count: int
    unchanged_count: int
    assignment_ids: list[str]


def _amo(user: account_models.User) -> str:
    return workforce_services.effective_amo_id(user)


def _error(detail: str, *, code: str, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "detail": detail,
            "error_code": code,
            "field_errors": {},
            "conflicts": [],
            "retryable": False,
        },
    )


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _rotation_signature(pattern: workforce_models.WorkPattern) -> tuple[Any, ...]:
    days = sorted(pattern.days or [], key=lambda day: day.cycle_day_index)
    return (
        int(pattern.cycle_length_days),
        str(pattern.timezone_name or "UTC"),
        tuple(
            (
                int(day.cycle_day_index),
                str(day.shift_template_id or ""),
                _enum_value(day.status),
                str(day.start_time_local or ""),
                str(day.end_time_local or ""),
                bool(day.spans_next_day),
                int(day.planned_minutes or 0),
            )
            for day in days
        ),
    )


def _snapshot(row: workforce_models.EmployeeWorkPatternAssignment) -> dict[str, Any]:
    return {
        "work_pattern_id": str(row.work_pattern_id),
        "effective_from": row.effective_from.isoformat(),
        "effective_to": row.effective_to.isoformat() if row.effective_to else None,
        "cycle_anchor_date": row.cycle_anchor_date.isoformat(),
    }


@router.post(
    "/work-pattern-assignments/cycle-starts/batch",
    response_model=CycleStartBatchResponse,
)
def batch_work_pattern_cycle_starts(
    payload: CycleStartBatchRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _amo(current_user)
    assignment_ids = [item.assignment_id for item in payload.items]
    if len(set(assignment_ids)) != len(assignment_ids):
        raise _error(
            "Each work-pattern assignment may appear only once in a cycle-start batch.",
            code="WORK_PATTERN_CYCLE_START_DUPLICATE",
        )

    rows = (
        db.query(workforce_models.EmployeeWorkPatternAssignment)
        .options(
            selectinload(workforce_models.EmployeeWorkPatternAssignment.work_pattern)
            .selectinload(workforce_models.WorkPattern.days),
        )
        .filter(
            workforce_models.EmployeeWorkPatternAssignment.amo_id == amo_id,
            workforce_models.EmployeeWorkPatternAssignment.id.in_(assignment_ids),
        )
        .with_for_update(of=workforce_models.EmployeeWorkPatternAssignment)
        .all()
    )
    by_id = {str(row.id): row for row in rows}
    if len(by_id) != len(assignment_ids):
        db.rollback()
        raise _error(
            "One or more selected work-pattern assignments are unavailable in this tenant.",
            code="WORK_PATTERN_CYCLE_START_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # Match Workforce's canonical active-user/system-account guard without an
    # N+1 query. This stays bounded even when a tenant selects thousands of
    # assignments in first-time setup.
    user_ids = sorted({str(row.user_id) for row in rows})
    active_users = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.id.in_(user_ids),
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).all()
    active_users_by_id = {str(user.id): user for user in active_users}
    if len(active_users_by_id) != len(user_ids):
        db.rollback()
        raise _error(
            "Every selected work-pattern assignment must belong to an active, non-system user in this tenant.",
            code="WORK_PATTERN_CYCLE_START_USER_INACTIVE",
            status_code=status.HTTP_409_CONFLICT,
        )

    # Permission checks are cached by department so a 1,000-person batch does
    # not repeat the same authorization query for every member of one team.
    checked_departments: set[str | None] = set()
    signatures: set[tuple[Any, ...]] = set()
    for row in rows:
        active_user = active_users_by_id[str(row.user_id)]
        department_id = getattr(active_user, "department_id", None)
        if department_id not in checked_departments:
            workforce_permissions.require_permission(
                db,
                user=current_user,
                permission=workforce_permissions.PermissionCode.WORKFORCE_ASSIGN_PATTERNS,
                department_id=department_id,
            )
            checked_departments.add(department_id)
        pattern = row.work_pattern
        if pattern is None or not pattern.is_active:
            db.rollback()
            raise _error(
                "Every selected person must have an active work pattern.",
                code="WORK_PATTERN_CYCLE_START_PATTERN_INACTIVE",
            )

        # Preserve the canonical Workforce pattern-to-user shift-scope check. A
        # person may have moved departments or a shift may have been re-scoped
        # after the original assignment was created; an anchor update must not
        # make that incompatible assignment look newly configured.
        try:
            workforce_services._validate_pattern_user_shift_scope(
                pattern,
                user=active_user,
            )
        except ValueError as exc:
            db.rollback()
            raise _error(
                str(exc),
                code="WORK_PATTERN_CYCLE_START_SCOPE_INVALID",
                status_code=status.HTTP_409_CONFLICT,
            ) from exc

        days = {int(day.cycle_day_index) for day in pattern.days or []}
        if payload.cycle_day_index >= int(pattern.cycle_length_days) or payload.cycle_day_index not in days:
            db.rollback()
            raise _error(
                "The selected starting position does not exist in every selected rotation.",
                code="WORK_PATTERN_CYCLE_START_POSITION_INVALID",
            )
        signatures.add(_rotation_signature(pattern))

    if len(signatures) != 1:
        db.rollback()
        raise _error(
            "Batch starting shifts can only be applied to personnel with an identical shift rotation. Split incompatible patterns into separate groups.",
            code="WORK_PATTERN_CYCLE_START_ROTATION_MISMATCH",
            status_code=status.HTTP_409_CONFLICT,
        )

    item_by_id = {item.assignment_id: item for item in payload.items}
    batch_id = f"cycle-start-{uuid4().hex}"
    updated_count = 0
    unchanged_count = 0

    try:
        for row in rows:
            item = item_by_id[str(row.id)]
            if item.target_date < row.effective_from or (row.effective_to and item.target_date > row.effective_to):
                raise ValueError(
                    "A selected cycle start falls outside that person's effective work-pattern assignment."
                )
            before = _snapshot(row)
            anchor_date = item.target_date - timedelta(days=payload.cycle_day_index)
            if row.cycle_anchor_date == anchor_date:
                unchanged_count += 1
                continue
            row.cycle_anchor_date = anchor_date
            db.add(row)
            updated_count += 1
            audit_services.log_event(
                db,
                amo_id=amo_id,
                actor_user_id=current_user.id,
                entity_type="EmployeeWorkPatternAssignment",
                entity_id=str(row.id),
                action="batch_cycle_start_update",
                correlation_id=batch_id,
                before=before,
                after={**_snapshot(row), "reason": payload.reason},
                metadata={
                    "module": "workforce",
                    "batch_id": batch_id,
                    "cycle_day_index": payload.cycle_day_index,
                },
            )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise _error(
            str(exc),
            code="WORK_PATTERN_CYCLE_START_INVALID",
        ) from exc

    return CycleStartBatchResponse(
        batch_id=batch_id,
        updated_count=updated_count,
        unchanged_count=unchanged_count,
        assignment_ids=assignment_ids,
    )


__all__ = ["router"]
