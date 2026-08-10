from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.apps.manuals.router_legacy import MANUAL_UPLOAD_DIR
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import knowledge_models as km
from .knowledge_service import (
    _default_group_code,
    _node_path,
    normalize_code,
    reconcile_documentation_hierarchy,
)
from .workspace_service import (
    audit,
    get_manual,
    get_profile,
    require_control_user,
    resolve_tenant,
    status_value,
)


router = APIRouter(prefix="/workspace", tags=["Document Control Document Lifecycle"])

DocumentType = Literal[
    "MANUAL",
    "POLICY",
    "PROCEDURE",
    "WORK_INSTRUCTION",
    "FORM",
    "CHECKLIST",
    "REGISTER",
    "EXTERNAL_DOCUMENT",
]

DOCUMENT_TYPES = {
    "MANUAL",
    "POLICY",
    "PROCEDURE",
    "WORK_INSTRUCTION",
    "FORM",
    "CHECKLIST",
    "REGISTER",
    "EXTERNAL_DOCUMENT",
}

# The existing hierarchy reconciler derives structural DMS type from Manual.manual_type.
# Store a human-readable structural token there so explicit user choices remain stable
# after indexing/backfill, while retaining the upload-detected publication family in
# profile metadata for reporting and future classification work.
TYPE_STORAGE_VALUE = {
    "MANUAL": "MANUAL",
    "POLICY": "POLICY",
    "PROCEDURE": "PROCEDURE",
    "WORK_INSTRUCTION": "WORK INSTRUCTION",
    "FORM": "FORM",
    "CHECKLIST": "CHECKLIST",
    "REGISTER": "REGISTER",
    "EXTERNAL_DOCUMENT": "EXTERNAL DOCUMENT",
}
STRUCTURAL_STORAGE_VALUES = set(TYPE_STORAGE_VALUE.values())


class DocumentTypeUpdate(BaseModel):
    document_type: DocumentType


def _document_node(
    db: Session,
    *,
    tenant_id: str,
    manual_id: str,
) -> km.DocumentationNode | None:
    return (
        db.query(km.DocumentationNode)
        .filter(
            km.DocumentationNode.tenant_id == tenant_id,
            km.DocumentationNode.manual_id == manual_id,
        )
        .first()
    )


def _ensure_profile(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    manual: manual_models.Manual,
) -> dm.DocumentControlProfile:
    profile = get_profile(db, tenant, manual.id)
    if profile:
        return profile
    profile = dm.DocumentControlProfile(
        tenant_id=tenant.amo_id,
        manual_id=manual.id,
        owner_department=manual.owner_role or "DOCUMENT_CONTROL",
    )
    db.add(profile)
    db.flush()
    return profile


def _current_document_type(
    db: Session,
    *,
    tenant_id: str,
    manual: manual_models.Manual,
    profile: dm.DocumentControlProfile | None,
) -> tuple[str, str]:
    metadata = dict(profile.metadata_json or {}) if profile else {}
    override = str(metadata.get("document_type_override") or "").strip().upper()
    if override in DOCUMENT_TYPES:
        return override, "OVERRIDE"
    node = _document_node(db, tenant_id=tenant_id, manual_id=manual.id)
    if node and node.node_type in DOCUMENT_TYPES:
        return node.node_type, "HIERARCHY"

    source = " ".join(filter(None, [manual.manual_type, manual.code, manual.title])).upper()
    if profile and profile.document_class == "EXTERNAL":
        return "EXTERNAL_DOCUMENT", "DETECTED"
    if "CHECKLIST" in source or "CHK" in source:
        return "CHECKLIST", "DETECTED"
    if "FORM" in source or "FRM" in source:
        return "FORM", "DETECTED"
    if "REGISTER" in source:
        return "REGISTER", "DETECTED"
    if "WORK INSTRUCTION" in source or " QWI " in f" {source} " or " WI " in f" {source} ":
        return "WORK_INSTRUCTION", "DETECTED"
    if "PROCEDURE" in source or " PROC " in f" {source} " or " SOP " in f" {source} ":
        return "PROCEDURE", "DETECTED"
    if "POLICY" in source:
        return "POLICY", "DETECTED"
    return "MANUAL", "DEFAULT"


def _move_node_to_type_group(
    db: Session,
    *,
    tenant_id: str,
    manual: manual_models.Manual,
    profile: dm.DocumentControlProfile,
    document_type: str,
) -> None:
    node = _document_node(db, tenant_id=tenant_id, manual_id=manual.id)
    if not node:
        return

    node.node_type = document_type
    node.title = manual.title
    node.code = manual.code
    node.normalized_code = normalize_code(manual.code)
    metadata = dict(node.metadata_json or {})
    metadata["document_type_override"] = document_type
    node.metadata_json = metadata

    group_code = _default_group_code(document_type, manual, profile)
    parent = (
        db.query(km.DocumentationNode)
        .filter(
            km.DocumentationNode.tenant_id == tenant_id,
            km.DocumentationNode.normalized_code == normalize_code(group_code),
            km.DocumentationNode.status == "ACTIVE",
        )
        .first()
    )
    if parent and parent.id != node.parent_id:
        node.parent_id = parent.id
        node.path, node.depth = _node_path(parent, node.id, node.code)


def _purge_local_sources(paths: list[str]) -> dict[str, int]:
    root = MANUAL_UPLOAD_DIR.resolve()
    deleted = 0
    skipped = 0
    failed = 0
    for raw in dict.fromkeys(path for path in paths if path):
        try:
            candidate = Path(raw).resolve()
            candidate.relative_to(root)
        except (OSError, ValueError):
            skipped += 1
            continue
        try:
            if candidate.is_file():
                candidate.unlink()
                deleted += 1
        except OSError:
            failed += 1
    return {"deleted": deleted, "skipped": skipped, "failed": failed}


@router.get("/t/{tenant_slug}/documents/{manual_id}/document-type")
def get_document_type(
    tenant_slug: str,
    manual_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    profile = get_profile(db, tenant, manual.id)
    document_type, source = _current_document_type(
        db,
        tenant_id=tenant.amo_id,
        manual=manual,
        profile=profile,
    )
    metadata = dict(profile.metadata_json or {}) if profile else {}
    return {
        "manual_id": manual.id,
        "document_type": document_type,
        "source": source,
        "publication_family": metadata.get("publication_family"),
        "allowed_types": sorted(DOCUMENT_TYPES),
    }


@router.patch("/t/{tenant_slug}/documents/{manual_id}/document-type")
def update_document_type(
    tenant_slug: str,
    manual_id: str,
    payload: DocumentTypeUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    profile = _ensure_profile(db, tenant=tenant, manual=manual)
    previous_type, previous_source = _current_document_type(
        db,
        tenant_id=tenant.amo_id,
        manual=manual,
        profile=profile,
    )
    previous_manual_type = manual.manual_type
    previous_class = profile.document_class

    document_type = str(payload.document_type).upper()
    metadata = dict(profile.metadata_json or {})
    if not metadata.get("publication_family") and previous_manual_type not in STRUCTURAL_STORAGE_VALUES:
        metadata["publication_family"] = previous_manual_type
    metadata["document_type_override"] = document_type

    managed_external = bool(metadata.get("document_type_managed_external_class"))
    if document_type == "EXTERNAL_DOCUMENT":
        profile.document_class = "EXTERNAL"
        metadata["document_type_managed_external_class"] = True
    elif managed_external and profile.document_class == "EXTERNAL":
        profile.document_class = "INTERNAL"
        metadata["document_type_managed_external_class"] = False

    profile.metadata_json = metadata
    profile.version = int(profile.version or 0) + 1
    manual.manual_type = TYPE_STORAGE_VALUE[document_type]

    # A controller's classification decision must be visible in the library in the
    # same transaction. Draft uploads do not always have an indexed hierarchy node
    # yet, so reconcile synchronously before moving/stamping the document node.
    reconcile_documentation_hierarchy(
        db,
        manual_tenant=tenant,
        actor_id=str(current_user.id),
    )
    _move_node_to_type_group(
        db,
        tenant_id=tenant.amo_id,
        manual=manual,
        profile=profile,
        document_type=document_type,
    )

    after = {
        "document_type": document_type,
        "manual_type": manual.manual_type,
        "document_class": profile.document_class,
        "publication_family": metadata.get("publication_family"),
    }
    audit(
        db,
        tenant,
        request,
        "document.type.updated",
        "manual",
        manual.id,
        {
            "before": {
                "document_type": previous_type,
                "source": previous_source,
                "manual_type": previous_manual_type,
                "document_class": previous_class,
            },
            "after": after,
        },
    )
    db.commit()
    return {"manual_id": manual.id, **after, "source": "OVERRIDE"}


@router.delete("/t/{tenant_slug}/documents/{manual_id}")
def delete_document(
    tenant_slug: str,
    manual_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Permanently delete a never-published document and its draft revisions.

    Published, superseded, or archived controlled information is deliberately not
    hard-deletable. Its audit/history obligations must be handled through the
    controlled archive/withdrawal workflow instead.
    """
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    revisions = (
        db.query(manual_models.ManualRevision)
        .filter(manual_models.ManualRevision.manual_id == manual.id)
        .all()
    )
    protected_statuses = {"PUBLISHED", "SUPERSEDED", "ARCHIVED"}
    has_controlled_history = bool(
        manual.current_published_rev_id
        or any(
            status_value(revision) in protected_statuses
            or bool(revision.published_at)
            or bool(revision.immutable_locked)
            for revision in revisions
        )
    )
    if has_controlled_history:
        raise HTTPException(
            status_code=409,
            detail="Published controlled documents cannot be permanently deleted. Archive or withdraw the controlled document instead so revision and audit history are retained.",
        )

    record_count = (
        db.query(km.DocumentationRecord)
        .filter(km.DocumentationRecord.template_manual_id == manual.id)
        .count()
    )
    if record_count:
        raise HTTPException(
            status_code=409,
            detail="This document has retained records and cannot be permanently deleted.",
        )

    node = _document_node(db, tenant_id=tenant.amo_id, manual_id=manual.id)
    if node:
        child_count = (
            db.query(km.DocumentationNode)
            .filter(km.DocumentationNode.parent_id == node.id, km.DocumentationNode.status == "ACTIVE")
            .count()
        )
        if child_count:
            raise HTTPException(
                status_code=409,
                detail="This document contains child nodes in the controlled hierarchy. Move those items before deleting the draft document.",
            )

    source_paths = [str(revision.source_storage_path or "") for revision in revisions if revision.source_storage_path]
    before = {
        "id": manual.id,
        "code": manual.code,
        "title": manual.title,
        "manual_type": manual.manual_type,
        "status": manual.status,
        "revision_ids": [revision.id for revision in revisions],
        "revision_count": len(revisions),
    }
    audit(db, tenant, request, "document.deleted", "manual", manual.id, {"before": before, "after": None})
    if node:
        db.delete(node)
    db.delete(manual)
    db.commit()

    storage = _purge_local_sources(source_paths)
    return {
        "status": "deleted",
        "manual_id": manual_id,
        "code": before["code"],
        "deleted_revisions": len(revisions),
        "storage_cleanup": storage,
    }
