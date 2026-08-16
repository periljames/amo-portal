from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from amodb.database import get_write_db

from .audit_external_access_router import ExternalParticipantCreate, create_external_participant
from .tenant_security import TenantContext, require_quality_permission


router = APIRouter(tags=["Quality external audit access guard"])


@router.post("/audits/{audit_id}/external-participants", status_code=status.HTTP_201_CREATED)
def create_external_participant_guarded(
    audit_id: uuid.UUID,
    payload: ExternalParticipantCreate,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    """Fail closed until a real MFA/passkey ceremony is wired to external audit access.

    The underlying external participant model retains the future assurance vocabulary,
    but current invitations are email-link sessions only. This compatibility route is
    registered before the older create route so the API cannot silently label an
    email-link session as MFA or passkey assured.
    """

    if payload.assurance_level != "EMAIL_LINK":
        raise HTTPException(
            status_code=422,
            detail="MFA/passkey external audit access is not enabled yet. Use EMAIL_LINK until the current-main identity assurance provider is integrated.",
        )
    return create_external_participant(audit_id=audit_id, payload=payload, ctx=ctx, db=db)
