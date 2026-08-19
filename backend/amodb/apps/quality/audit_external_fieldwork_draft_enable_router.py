from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends
from sqlalchemy.orm import Session

from amodb.database import get_db

from .audit_external_access_router import _GUEST_COOKIE
from .audit_external_fieldwork_router import get_external_auditor_fieldwork
from .router import public_router


router = APIRouter(prefix="/quality/audit-access", tags=["Quality / External Auditor Fieldwork"])


@router.get("/fieldwork", name="get_external_auditor_fieldwork_with_drafts")
def get_external_auditor_fieldwork_with_drafts(
    db: Session = Depends(get_db),
    amo_qms_audit_guest: str | None = Cookie(default=None, alias=_GUEST_COOKIE),
):
    payload = get_external_auditor_fieldwork(db=db, amo_qms_audit_guest=amo_qms_audit_guest)
    # The base projection used a temporary blocker while the immutable draft
    # lifecycle was being built. A non-null blocker here specifically means the
    # participant already has audit:finding_draft in the validated grant.
    if payload.get("finding_draft_blocker"):
        payload["can_draft_findings"] = True
        payload["finding_draft_blocker"] = None
    return payload


# Imported after the base external fieldwork route so this narrower projection
# wins for the same public path without weakening the underlying grant checks.
public_router.routes[0:0] = list(router.routes)
