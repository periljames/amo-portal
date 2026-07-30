from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import knowledge_models as km
from .knowledge_service import (
    CONTENT_NODE_TYPES,
    NODE_TYPES,
    hierarchy_payload,
    index_revision_background,
    index_revision_references,
    normalize_code,
    reconcile_documentation_hierarchy,
    serialize_execution_profile,
    serialize_index_job,
    update_subtree_paths,
    validate_hierarchy_move,
)
from .workspace_service import is_control_user, require_control_user, resolve_tenant


router = APIRouter(prefix="/workspace", tags=["Document Control Knowledge Graph"])


class NodeUpdate(BaseModel):
    parent_id: str | None = None
    node_type: str
    code: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    order_index: int = Field(default=0, ge=0, le=1_000_000)
    aliases: list[str] = Field(default_factory=list, max_length=100)
    expected_updated_at: datetime | None = None


class ExecutionProfileUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    execution_type: Literal["NONE", "PDF_ACROFORM", "CHECKLIST", "PORTAL_FORM", "DOWNLOADABLE_TEMPLATE", "HYBRID"]
    submission_mode: Literal["DOWNLOAD_ONLY", "FILL_AND_SUBMIT", "DOWNLOAD_AND_UPLOAD", "PORTAL_SUBMISSION"]
    record_series_node_id: str | None = None
    retention_years: int | None = Field(default=None, ge=1, le=100)
    naming_pattern: str = Field(default="{code}-{date}-{sequence}", min_length=3, max_length=255)
    allow_download: bool = True
    allow_save_draft: bool = False
    requires_signature: bool = False
    requires_review: bool = False
    execution_schema: dict[str, Any] = Field(default_factory=dict, alias="schema")
    access_scope: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    expected_version: int | None = Field(default=None, ge=1)


class ReferenceResolution(BaseModel):
    target_manual_id: str
    target_revision_id: str | None = None
    relationship_type: Literal["REFERENCES", "IMPLEMENTS", "USES_FORM", "USES_CHECKLIST", "UPDATES_REGISTER", "CREATES_RECORD"] = "REFERENCES"
    resolution_policy: Literal["CURRENT_EFFECTIVE", "PINNED_REVISION"] = "CURRENT_EFFECTIVE"
    comments: str = Field(min_length=3, max_length=2000)


def _audit(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    user: account_models.User,
    request: Request,
    action: str,
    entity_type: str,
    entity_id: str,
    diff: dict[str, Any],
) -> None:
    db.add(manual_models.ManualAuditLog(
        tenant_id=tenant.id,
        actor_id=user.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_device=f"{request.client.host if request.client else 'unknown'}::{request.headers.get('user-agent', 'n/a')}",
        diff_json=diff,
    ))


@router.get("/t/{tenant_slug}/knowledge/tree")
def get_knowledge_tree(
    tenant_slug: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    payload = hierarchy_payload(db, manual_tenant=tenant, actor_id=current_user.id if is_control_user(current_user) else None)
    db.commit()
    payload["capabilities"] = {"read": True, "control": is_control_user(current_user)}
    return payload


@router.post("/t/{tenant_slug}/knowledge/reconcile")
def reconcile_knowledge_tree(
    tenant_slug: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    rows = reconcile_documentation_hierarchy(db, manual_tenant=tenant, actor_id=current_user.id)
    _audit(
        db,
        tenant=tenant,
        user=current_user,
        request=request,
        action="documentation.hierarchy.reconciled",
        entity_type="documentation_hierarchy",
        entity_id=str(tenant.amo_id),
        diff={"node_count": len(rows)},
    )
    db.commit()
    return hierarchy_payload(db, manual_tenant=tenant, actor_id=current_user.id)


@router.put("/t/{tenant_slug}/knowledge/nodes/{node_id}")
def update_knowledge_node(
    tenant_slug: str,
    node_id: str,
    payload: NodeUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = db.query(km.DocumentationNode).filter(
        km.DocumentationNode.id == node_id,
        km.DocumentationNode.tenant_id == tenant.amo_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Documentation hierarchy node not found")
    if payload.expected_updated_at and row.updated_at and row.updated_at != payload.expected_updated_at:
        raise HTTPException(status_code=409, detail="This hierarchy node changed after it was opened")
    parent = None
    if payload.parent_id:
        parent = db.query(km.DocumentationNode).filter(
            km.DocumentationNode.id == payload.parent_id,
            km.DocumentationNode.tenant_id == tenant.amo_id,
        ).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Hierarchy parent not found")
    previous = {
        "parent_id": row.parent_id,
        "node_type": row.node_type,
        "code": row.code,
        "title": row.title,
        "path": row.path,
    }
    row.node_type = payload.node_type.upper()
    row.code = payload.code.strip()
    row.normalized_code = normalize_code(payload.code)
    row.title = payload.title.strip()
    row.order_index = payload.order_index
    row.metadata_json = {**dict(row.metadata_json or {}), "aliases": list(dict.fromkeys([row.code, *[value.strip() for value in payload.aliases if value.strip()]]))}
    validate_hierarchy_move(db, tenant_id=str(tenant.amo_id), node=row, parent=parent, node_type=row.node_type)
    row.parent_id = parent.id if parent else None
    update_subtree_paths(db, row, parent)
    _audit(
        db,
        tenant=tenant,
        user=current_user,
        request=request,
        action="documentation.hierarchy.node_updated",
        entity_type="documentation_node",
        entity_id=row.id,
        diff={"before": previous, "after": {"parent_id": row.parent_id, "node_type": row.node_type, "code": row.code, "title": row.title, "path": row.path}},
    )
    db.commit()
    return hierarchy_payload(db, manual_tenant=tenant, actor_id=current_user.id)


@router.put("/t/{tenant_slug}/knowledge/documents/{manual_id}/execution-profile")
def upsert_execution_profile(
    tenant_slug: str,
    manual_id: str,
    payload: ExecutionProfileUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = db.query(manual_models.Manual).filter(
        manual_models.Manual.id == manual_id,
        manual_models.Manual.tenant_id == tenant.id,
    ).first()
    if not manual:
        raise HTTPException(status_code=404, detail="Controlled document not found")
    series = None
    if payload.record_series_node_id:
        series = db.query(km.DocumentationNode).filter(
            km.DocumentationNode.id == payload.record_series_node_id,
            km.DocumentationNode.tenant_id == tenant.amo_id,
            km.DocumentationNode.node_type == "RECORD_SERIES",
        ).first()
        if not series:
            raise HTTPException(status_code=422, detail="Select a record-series hierarchy node within this AMO")
    row = db.query(km.DocumentationExecutionProfile).filter(
        km.DocumentationExecutionProfile.tenant_id == tenant.amo_id,
        km.DocumentationExecutionProfile.manual_id == manual.id,
    ).first()
    if not row:
        row = km.DocumentationExecutionProfile(
            tenant_id=tenant.amo_id,
            manual_id=manual.id,
            created_by_user_id=current_user.id,
        )
        db.add(row)
        db.flush()
    elif payload.expected_version and row.version != payload.expected_version:
        raise HTTPException(status_code=409, detail="Execution profile version conflict")
    if payload.submission_mode in {"FILL_AND_SUBMIT", "PORTAL_SUBMISSION", "DOWNLOAD_AND_UPLOAD"} and not series:
        raise HTTPException(status_code=422, detail="Executable templates must output to a controlled record series")
    row.execution_type = payload.execution_type
    row.submission_mode = payload.submission_mode
    row.record_series_node_id = series.id if series else None
    row.retention_years = payload.retention_years
    row.naming_pattern = payload.naming_pattern
    row.allow_download = payload.allow_download
    row.allow_save_draft = payload.allow_save_draft
    row.requires_signature = payload.requires_signature
    row.requires_review = payload.requires_review
    row.schema_json = payload.execution_schema
    row.access_scope_json = payload.access_scope
    row.metadata_json = payload.metadata
    row.version = int(row.version or 0) + 1
    _audit(
        db,
        tenant=tenant,
        user=current_user,
        request=request,
        action="documentation.execution_profile.updated",
        entity_type="documentation_execution_profile",
        entity_id=row.id,
        diff={"manual_id": manual.id, "execution_type": row.execution_type, "submission_mode": row.submission_mode, "record_series_node_id": row.record_series_node_id},
    )
    db.commit()
    db.refresh(row)
    return serialize_execution_profile(row)


@router.post("/t/{tenant_slug}/knowledge/revisions/{revision_id}/reindex")
def reindex_revision(
    tenant_slug: str,
    revision_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    wait: bool = False,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    revision = db.query(manual_models.ManualRevision).join(
        manual_models.Manual, manual_models.Manual.id == manual_models.ManualRevision.manual_id,
    ).filter(
        manual_models.ManualRevision.id == revision_id,
        manual_models.Manual.tenant_id == tenant.id,
    ).first()
    if not revision:
        raise HTTPException(status_code=404, detail="Revision not found")
    if wait:
        result = index_revision_references(db, revision_id=revision.id)
        _audit(db, tenant=tenant, user=current_user, request=request, action="documentation.references.indexed", entity_type="manual_revision", entity_id=revision.id, diff=result)
        db.commit()
        return result
    job = db.query(km.DocumentationIndexJob).filter(km.DocumentationIndexJob.revision_id == revision.id).first()
    if not job:
        job = km.DocumentationIndexJob(tenant_id=tenant.amo_id, manual_id=revision.manual_id, revision_id=revision.id, source_sha256=revision.source_sha256)
        db.add(job)
    job.status = "PENDING"
    job.error_summary = None
    _audit(db, tenant=tenant, user=current_user, request=request, action="documentation.references.index_scheduled", entity_type="manual_revision", entity_id=revision.id, diff={"source_sha256": revision.source_sha256})
    db.commit()
    background_tasks.add_task(index_revision_background, revision.id)
    return serialize_index_job(job)


@router.get("/t/{tenant_slug}/knowledge/reference-monitor")
def reference_monitor(
    tenant_slug: str,
    status: str | None = None,
    limit: int = 250,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = db.query(km.DocumentationReference).filter(km.DocumentationReference.tenant_id == tenant.amo_id)
    if status:
        query = query.filter(km.DocumentationReference.status == status.upper())
    rows = query.order_by(km.DocumentationReference.updated_at.desc()).limit(max(1, min(1000, limit))).all()
    manuals = {row.id: row for row in db.query(manual_models.Manual).filter(manual_models.Manual.tenant_id == tenant.id).all()}
    jobs = db.query(km.DocumentationIndexJob).filter(km.DocumentationIndexJob.tenant_id == tenant.amo_id).order_by(km.DocumentationIndexJob.updated_at.desc()).limit(100).all()
    return {
        "items": [{
            "id": row.id,
            "raw_token": row.raw_token,
            "status": row.status,
            "confidence_percent": row.confidence_percent,
            "relationship_type": row.relationship_type,
            "source_manual": {"id": row.source_manual_id, "code": manuals.get(row.source_manual_id).code if manuals.get(row.source_manual_id) else "—", "title": manuals.get(row.source_manual_id).title if manuals.get(row.source_manual_id) else "Unavailable"},
            "source_revision_id": row.source_revision_id,
            "source_page_number": row.source_page_number,
            "source_context": row.source_context,
            "target_manual": {"id": row.target_manual_id, "code": manuals.get(row.target_manual_id).code if manuals.get(row.target_manual_id) else None, "title": manuals.get(row.target_manual_id).title if manuals.get(row.target_manual_id) else None} if row.target_manual_id else None,
            "candidates": list(row.candidates_json or []),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        } for row in rows],
        "jobs": [serialize_index_job(job) for job in jobs],
    }


@router.post("/t/{tenant_slug}/knowledge/references/{reference_id}/resolve")
def resolve_reference(
    tenant_slug: str,
    reference_id: str,
    payload: ReferenceResolution,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = db.query(km.DocumentationReference).filter(
        km.DocumentationReference.id == reference_id,
        km.DocumentationReference.tenant_id == tenant.amo_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Reference occurrence not found")
    target = db.query(manual_models.Manual).filter(
        manual_models.Manual.id == payload.target_manual_id,
        manual_models.Manual.tenant_id == tenant.id,
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target document not found")
    target_revision_id = payload.target_revision_id
    if payload.resolution_policy == "CURRENT_EFFECTIVE":
        target_revision_id = target.current_published_rev_id
    if not target_revision_id:
        raise HTTPException(status_code=409, detail="The target has no effective revision")
    revision = db.query(manual_models.ManualRevision).filter(
        manual_models.ManualRevision.id == target_revision_id,
        manual_models.ManualRevision.manual_id == target.id,
    ).first()
    if not revision:
        raise HTTPException(status_code=404, detail="Target revision not found")
    row.target_manual_id = target.id
    row.target_revision_id = revision.id
    row.relationship_type = payload.relationship_type
    row.resolution_policy = payload.resolution_policy
    row.status = "VERIFIED"
    row.confidence_percent = 100
    row.verified_by_user_id = current_user.id
    row.verified_at = datetime.utcnow()
    row.last_checked_at = datetime.utcnow()
    row.candidates_json = []
    _audit(
        db,
        tenant=tenant,
        user=current_user,
        request=request,
        action="documentation.reference.verified",
        entity_type="documentation_reference",
        entity_id=row.id,
        diff={"target_manual_id": target.id, "target_revision_id": revision.id, "relationship_type": row.relationship_type, "comments": payload.comments},
    )
    db.commit()
    return {"id": row.id, "status": row.status, "target_manual_id": row.target_manual_id, "target_revision_id": row.target_revision_id}
