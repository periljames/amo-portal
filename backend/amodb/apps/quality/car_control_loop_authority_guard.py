from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_write_db

from .car_control_loop_guard_router import close_control_loop_guarded as _close_control_loop_guarded
from .car_control_loop_router import (
    CloseControlLoop,
    MilestoneUpdate,
    _load_car,
    update_milestone as _update_milestone_base,
)
from .tenant_security import (
    TenantContext,
    assert_quality_permission,
    set_postgres_tenant_context,
    write_tenant_context,
)

router = APIRouter(prefix="/cars/{car_id}/control-loop", tags=["Quality CAR control-loop authority"])


def _require_milestone_review_authority(
    db: Session,
    *,
    ctx: TenantContext,
    car,
    requested_status: str | None,
) -> None:
    if requested_status not in {"ACCEPTED", "REJECTED"}:
        return
    current_user = (
        db.query(account_models.User)
        .filter(
            account_models.User.id == ctx.user_id,
            account_models.User.amo_id == ctx.amo_id,
            account_models.User.is_active.is_(True),
        )
        .first()
    )
    if current_user is None:
        raise HTTPException(status_code=403, detail="The active Quality reviewer could not be resolved.")

    from .router import _require_car_review_access

    _require_car_review_access(db, current_user, car)


@router.patch("/milestones/{milestone_id}")
def update_milestone_with_review_authority(
    car_id: UUID,
    milestone_id: UUID,
    payload: MilestoneUpdate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
):
    assert_quality_permission(db, ctx, "qms.car.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    car = _load_car(db, amo_id=ctx.amo_id, car_id=car_id, lock=True)
    _require_milestone_review_authority(
        db,
        ctx=ctx,
        car=car,
        requested_status=payload.status,
    )
    return _update_milestone_base(str(car_id), str(milestone_id), payload, ctx, db)


@router.post("/close")
def close_control_loop_with_close_authority(
    car_id: UUID,
    payload: CloseControlLoop,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
):
    # Closure is a distinct governed capability in the canonical CAR action map.
    # The delegated guard still requires manage access, so callers must satisfy
    # both general CAR management and the explicit close authority boundary.
    assert_quality_permission(db, ctx, "qms.car.close")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _close_control_loop_guarded(car_id, payload, ctx, db)
