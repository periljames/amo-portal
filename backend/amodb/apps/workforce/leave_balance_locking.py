from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session, lazyload

from . import models


def leave_balance_query(db: Session, *, request: models.LeaveRequest):
    """Build the balance lookup without relationship eager joins.

    EmployeeLeaveBalance relationships use joined loading for read views. A write
    workflow must not inherit those outer joins because PostgreSQL cannot apply an
    unrestricted row lock to the nullable side of an outer join.
    """
    leave_year = request.starts_at.year
    return db.query(models.EmployeeLeaveBalance).options(lazyload("*")).filter(
        models.EmployeeLeaveBalance.amo_id == request.amo_id,
        models.EmployeeLeaveBalance.user_id == request.user_id,
        models.EmployeeLeaveBalance.leave_type_id == request.leave_type_id,
        models.EmployeeLeaveBalance.leave_year == leave_year,
    )


def load_leave_balance_for_update(
    db: Session,
    *,
    request: models.LeaveRequest,
    create: bool = False,
) -> Optional[models.EmployeeLeaveBalance]:
    """Lock only the authoritative balance row used by leave state transitions."""
    leave_year = request.starts_at.year
    row = leave_balance_query(db, request=request).with_for_update(
        of=models.EmployeeLeaveBalance,
    ).first()
    if row is None and create:
        row = models.EmployeeLeaveBalance(
            amo_id=request.amo_id,
            user_id=request.user_id,
            leave_type_id=request.leave_type_id,
            leave_year=leave_year,
        )
        db.add(row)
        db.flush()
    return row
