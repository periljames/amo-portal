from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from .workspace_router import get_document_detail as _get_full_document_detail
from .workspace_service import is_control_user


router = APIRouter(prefix="/workspace", tags=["Document Control Record"])


@router.get("/t/{tenant_slug}/documents/{manual_id}", include_in_schema=False)
def get_role_appropriate_document_detail(
    tenant_slug: str,
    manual_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Return the unified record without exposing controller work to readers.

    The full record remains available to Document Control personnel. Ordinary
    readers receive only the document identity and the revision they are allowed
    to open; internal change, approval, authority, distribution, custody,
    integration, access-scope, and audit payloads are removed server-side.
    """
    detail = _get_full_document_detail(
        tenant_slug=tenant_slug,
        manual_id=manual_id,
        db=db,
        current_user=current_user,
    )
    if is_control_user(current_user):
        return detail

    document = dict(detail.get("document") or {})
    profile = document.get("profile")
    if isinstance(profile, dict):
        profile["access_scope"] = {}
        profile["metadata"] = {}
    target_revision_id = (document.get("read_target") or {}).get("revision_id")
    permitted_revisions = [
        revision
        for revision in list(detail.get("revisions") or [])
        if revision.get("id") == target_revision_id
    ]
    return {
        "document": document,
        "revisions": permitted_revisions,
        "changes": [],
        "workflows": [],
        "authority_submissions": [],
        "temporary_revisions": [],
        "distribution_campaigns": [],
        "reviews": [],
        "controlled_copies": [],
        "external_sources": [],
        "applicability": [],
        "integrations": [],
        "history": [],
        "capabilities": {"control": False},
    }
