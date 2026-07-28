from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from .workspace_decision_policy import is_decision_approver
from .workspace_router import get_document_detail as _get_full_document_detail
from .workspace_service import (
    get_manual,
    get_profile,
    is_control_user,
    readable_revision,
    require_manual_access,
    resolve_tenant,
    role_value,
    serialize_manual,
    serialize_revision,
)


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


def _active_tenant_people(db: Session, amo_id: str) -> list[dict]:
    rows = (
        db.query(account_models.User)
        .filter(
            account_models.User.amo_id == amo_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        )
        .order_by(account_models.User.full_name.asc(), account_models.User.email.asc())
        .all()
    )
    return [
        {
            "id": row.id,
            "name": row.full_name,
            "email": row.email,
            "role": role_value(row),
            "department": getattr(getattr(row, "department", None), "code", None),
            "active": True,
        }
        for row in rows
    ]


def _reader_detail(
    db: Session,
    *,
    tenant_slug: str,
    manual_id: str,
    current_user: account_models.User,
) -> dict:
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    profile = get_profile(db, tenant, manual.id)
    require_manual_access(current_user, profile)
    target, target_kind = readable_revision(db, manual, current_user)
    document = serialize_manual(manual, profile, target, target_kind, target)
    profile_payload = document.get("profile")
    if isinstance(profile_payload, dict):
        profile_payload["access_scope"] = {}
        profile_payload["metadata"] = {}
    return {
        "document": document,
        "revisions": [serialize_revision(target)] if target else [],
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
        "active_users": [],
        "capabilities": {"read": True, "control": False, "approve": False},
    }


@router.get("/t/{tenant_slug}/documents/{manual_id}", include_in_schema=False)
def get_role_appropriate_document_detail(
    tenant_slug: str,
    manual_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Return controller governance or a minimal reader-safe document projection."""
    if not is_control_user(current_user):
        return _reader_detail(
            db,
            tenant_slug=tenant_slug,
            manual_id=manual_id,
            current_user=current_user,
        )

    detail = _get_full_document_detail(
        tenant_slug=tenant_slug,
        manual_id=manual_id,
        db=db,
        current_user=current_user,
    )
    tenant = resolve_tenant(db, tenant_slug, current_user)
    detail["history"] = _controller_history(db, tenant.id, detail)
    detail["active_users"] = _active_tenant_people(db, tenant.amo_id)
    capabilities = detail.setdefault("capabilities", {})
    capabilities["read"] = True
    capabilities["control"] = True
    capabilities["approve"] = is_decision_approver(current_user)
    return detail
