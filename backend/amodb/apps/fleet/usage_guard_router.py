from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from amodb.apps.accounts.models import User

from ...entitlements import require_module
from ...security import get_current_active_user

router = APIRouter(
    prefix="/aircraft",
    tags=["aircraft_usage_control"],
    dependencies=[Depends(require_module("fleet"))],
)


def _correction_required() -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "message": "Accepted utilisation entries are immutable.",
            "code": "USAGE_CORRECTION_REQUIRED",
            "action": "Submit a correction request through /records/utilisation/{usage_id}/corrections.",
        },
    )


@router.put("/usage/{usage_id}")
def block_direct_usage_update(
    usage_id: int,
    current_user: User = Depends(get_current_active_user),
):
    del usage_id, current_user
    _correction_required()


@router.delete("/usage/{usage_id}")
def block_direct_usage_delete(
    usage_id: int,
    current_user: User = Depends(get_current_active_user),
):
    del usage_id, current_user
    _correction_required()
