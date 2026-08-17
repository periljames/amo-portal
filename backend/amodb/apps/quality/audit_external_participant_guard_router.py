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
    """Permit only assurance modes backed by an implemented ceremony.

    Email-link access remains valid for auditees and explicitly configured external
    participants. PASSKEY is available only to external auditors because the
    public bootstrap/assertion flow is purpose-bound to their assigned fieldwork
    identity. MFA remains fail-closed until a real MFA provider is integrated.
    """

    if payload.assurance_level == "MFA":
        raise HTTPException(
            status_code=422,
            detail="MFA external audit access is not enabled because no MFA provider is currently wired to the QMS assurance flow.",
        )
    if payload.assurance_level == "PASSKEY" and payload.participant_type != "EXTERNAL_AUDITOR":
        raise HTTPException(
            status_code=422,
            detail="PASSKEY assurance is currently supported only for assigned external auditors. Auditee guest access remains purpose-bound EMAIL_LINK access.",
        )
    return create_external_participant(audit_id=audit_id, payload=payload, ctx=ctx, db=db)
