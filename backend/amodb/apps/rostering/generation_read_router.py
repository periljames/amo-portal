from __future__ import annotations

"""Scale-sensitive roster reads used by the monthly planner."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import models, schemas, services

router = APIRouter(prefix="/rostering", tags=["rostering"])


def _amo(user: account_models.User) -> str:
    return services.effective_amo_id(user)


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "detail": "Roster version not found",
            "error_code": "ROSTER_VERSION_NOT_FOUND",
            "field_errors": {},
            "conflicts": [],
            "retryable": False,
        },
    )


@router.get("/versions/{version_id}/assignments", response_model=list[schemas.RosterAssignmentRead])
def list_roster_assignments_scaled(
    version_id: str,
    include_deleted: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not services.can_view_roster(db, user=current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "detail": "Roster access denied",
                "error_code": "ROSTER_ACCESS_DENIED",
                "field_errors": {},
                "conflicts": [],
                "retryable": False,
            },
        )

    amo_id = _amo(current_user)
    # The legacy route called get_version(), whose read model eagerly loads all
    # assignments/findings, and then immediately called list_assignments() to
    # load those assignments a second time. Existence needs one indexed scalar
    # probe; the assignment query remains the single authoritative data load.
    exists = db.query(models.RosterVersion.id).filter(
        models.RosterVersion.amo_id == amo_id,
        models.RosterVersion.id == version_id,
    ).first()
    if not exists:
        raise _not_found()

    return [
        services.serialize_assignment(row)
        for row in services.list_assignments(
            db,
            amo_id=amo_id,
            version_id=version_id,
            include_deleted=include_deleted,
        )
    ]


__all__ = ["router"]
