from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from .workspace_router import get_document_detail as _get_full_document_detail
from .workspace_service import is_control_user, resolve_tenant


router = APIRouter(prefix="/workspace", tags=["Document Control Record"])


def _entity_ids_for_document(detail: dict) -> set[str]:
    identifiers: set[str] = set()
    document = detail.get("document") or {}
    if document.get("id"):
        identifiers.add(str(document["id"]))
    for collection in (
        "revisions",
        "changes",
        "workflows",
        "authority_submissions",
        "temporary_revisions",
        "distribution_campaigns",
        "reviews",
        "controlled_copies",
        "external_sources",
        "applicability",
        "integrations",
    ):
        for row in detail.get(collection) or []:
            if row.get("id"):
                identifiers.add(str(row["id"]))
    return identifiers


def _controller_history(
    db: Session,
    tenant_id: str,
    detail: dict,
) -> list[dict]:
    """Collect all domain events belonging to this unified document record.

    Governance actions use their own immutable entity IDs, so filtering audit rows
    only by the manual and revision IDs omits workflow, authority, distribution,
    TR, copy, review, and integration events. The controller record already loaded
    those tenant-scoped entities; use that exact ID set to build a complete timeline.
    """
    entity_ids = _entity_ids_for_document(detail)
    if not entity_ids:
        return []
    rows = (
        db.query(manual_models.ManualAuditLog)
        .filter(
            manual_models.ManualAuditLog.tenant_id == tenant_id,
            manual_models.ManualAuditLog.entity_id.in_(sorted(entity_ids)),
        )
        .order_by(manual_models.ManualAuditLog.at.desc())
        .limit(250)
        .all()
    )
    return [
        {
            "id": row.id,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "actor_id": row.actor_id,
            "at": row.at.isoformat() if row.at else None,
            "diff": dict(row.diff_json or {}),
        }
        for row in rows
    ]


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
        tenant = resolve_tenant(db, tenant_slug, current_user)
        detail["history"] = _controller_history(db, tenant.id, detail)
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
