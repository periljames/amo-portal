from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import workspace_schemas as schemas
from .workspace_decision_policy import require_decision_approver
from .workspace_service import resolve_tenant
from .workspace_tr_router import (
    transition_temporary_revision_with_guards as _transition,
)


router = APIRouter(prefix="/workspace", tags=["Document Control Temporary Revision Terminal Guards"])
_TERMINAL_STATUSES = {"WITHDRAWN", "INCORPORATED"}


@router.post(
    "/t/{tenant_slug}/temporary-revisions/{tr_id}/transition",
    include_in_schema=False,
)
def transition_temporary_revision_with_terminal_immutability(
    tenant_slug: str,
    tr_id: str,
    payload: schemas.TemporaryRevisionTransition,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_decision_approver(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = (
        db.query(dm.DocumentTemporaryRevision)
        .filter(
            dm.DocumentTemporaryRevision.tenant_id == tenant.amo_id,
            dm.DocumentTemporaryRevision.id == tr_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Temporary revision not found")
    if row.status in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TR_TERMINAL_IMMUTABLE",
                "message": (
                    f"A temporary revision in {row.status} state is immutable and "
                    "cannot receive same-state or further transition updates."
                ),
            },
        )

    return _transition(
        tenant_slug=tenant_slug,
        tr_id=tr_id,
        payload=payload,
        request=request,
        db=db,
        current_user=current_user,
    )
