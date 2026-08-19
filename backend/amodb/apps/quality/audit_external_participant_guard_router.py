from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from amodb.database import get_write_db

from .audit_external_access_models import QualityExternalIdentity
from .audit_external_access_router import ExternalParticipantCreate, _normalise_email, create_external_participant
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


router = APIRouter(tags=["Quality external audit access guard"])


def _assert_identity_assurance_stable(existing_assurance: str | None, requested_assurance: str) -> None:
    if existing_assurance and existing_assurance != requested_assurance:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This external identity already has a different assurance level. "
                "Revoke or deliberately migrate its existing audit access before changing assurance; "
                "participant creation cannot implicitly upgrade or downgrade active invitations."
            ),
        )


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

    Assurance is identity-level, not grant-level. Reusing the same external
    identity with a different assurance mode would retroactively change the
    ceremony required by every active invitation for that identity. Reject that
    implicit change so an existing PASSKEY assignment can never be silently
    downgraded to EMAIL_LINK (or an EMAIL_LINK assignment unexpectedly upgraded)
    by creating another audit role.
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

    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    email = _normalise_email(payload.email)
    existing_identity = db.query(QualityExternalIdentity).filter(
        QualityExternalIdentity.amo_id == ctx.amo_id,
        QualityExternalIdentity.email == email,
    ).first()
    _assert_identity_assurance_stable(
        existing_identity.assurance_level if existing_identity is not None else None,
        payload.assurance_level,
    )

    return create_external_participant(audit_id=audit_id, payload=payload, ctx=ctx, db=db)
