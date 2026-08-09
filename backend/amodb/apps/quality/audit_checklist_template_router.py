from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from amodb.database import get_read_db, get_write_db

from . import models
from .audit_checklist_template_models import QualityAuditChecklistBinding, QualityAuditChecklistTemplate, QualityAuditChecklistTemplateRevision
from .tenant_security import TenantContext, assert_quality_permission, require_quality_permission, set_postgres_tenant_context, write_tenant_context


router = APIRouter(tags=["Quality audit checklist template governance"])


class ChecklistTemplateCreate(BaseModel):
    template_code: str = Field(min_length=2, max_length=64)
    title: str = Field(min_length=3, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    category: str | None = Field(default=None, max_length=64)
    audit_kind: str | None = Field(default=None, max_length=32)


class ChecklistTemplateItem(BaseModel):
    section: str | None = Field(default=None, max_length=128)
    category: str | None = Field(default=None, max_length=128)
    checklist_ref: str | None = Field(default=None, max_length=128)
    requirement_ref: str | None = Field(default=None, max_length=255)
    regulatory_source_ref: str | None = Field(default=None, max_length=500)
    manual_source_ref: str | None = Field(default=None, max_length=500)
    prompt: str = Field(min_length=1, max_length=8000)
    expected_evidence: str | None = Field(default=None, max_length=4000)
    response_type: str = Field(default="COMPLIANCE", max_length=64)
    applicability: str = Field(default="APPLICABLE", max_length=64)
    mandatory: bool = True
    finding_trigger: str = Field(
        default="NONE",
        pattern=r"^(NONE|NONCOMPLIANT|OBSERVATION|ADVERSE_RESPONSE)$",
        description="Governed trigger policy only; a triggered response still requires auditor judgment before a finding is finalized.",
    )
    sort_order: int = Field(default=0, ge=0, le=100000)


class ChecklistRevisionCreate(BaseModel):
    reason: str = Field(min_length=8, max_length=4000)
    items: list[ChecklistTemplateItem] = Field(min_length=1, max_length=1000)
    source_references: list[dict[str, Any] | str] = Field(default_factory=list, max_length=1000)


class ChecklistRevisionIssue(BaseModel):
    reason: str = Field(min_length=8, max_length=4000)


class ChecklistBindingCreate(BaseModel):
    template_revision_id: str = Field(min_length=1, max_length=36)
    reason: str = Field(min_length=8, max_length=4000)
    allow_existing_items: bool = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_content(items: list[dict[str, Any]], source_references: list[Any]) -> str:
    payload = {"items": items, "source_references": source_references}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _template_dict(row: QualityAuditChecklistTemplate, *, include_revisions: bool = False) -> dict[str, Any]:
    result = {
        "id": str(row.id),
        "template_code": row.template_code,
        "title": row.title,
        "description": row.description,
        "category": row.category,
        "audit_kind": row.audit_kind,
        "status": row.status,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    if include_revisions:
        result["revisions"] = [_revision_dict(item) for item in sorted(list(row.revisions or []), key=lambda item: item.revision_no, reverse=True)]
    return result


def _revision_dict(row: QualityAuditChecklistTemplateRevision) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "template_id": str(row.template_id),
        "revision_no": row.revision_no,
        "status": row.status,
        "items": row.items or [],
        "source_references": row.source_references or [],
        "content_sha256": row.content_sha256,
        "change_reason": row.change_reason,
        "supersedes_revision_id": row.supersedes_revision_id,
        "issued_by_user_id": row.issued_by_user_id,
        "issued_at": row.issued_at,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at,
    }


def _binding_dict(row: QualityAuditChecklistBinding) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "audit_id": str(row.audit_id),
        "template_id": row.template_id,
        "template_revision_id": row.template_revision_id,
        "template_code": row.template_code,
        "revision_no": row.revision_no,
        "content_sha256": row.content_sha256,
        "item_snapshot": row.item_snapshot or [],
        "source_references": row.source_references or [],
        "instantiated_item_ids": row.instantiated_item_ids or [],
        "application_reason": row.application_reason,
        "applied_by_user_id": row.applied_by_user_id,
        "applied_at": row.applied_at,
    }


def _audit(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> models.QMSAudit:
    row = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == amo_id,
        models.QMSAudit.id == audit_id,
        models.QMSAudit.deleted_at.is_(None),
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit not found.")
    return row


@router.get("/audit-checklist-templates")
def list_checklist_templates(
    active_only: bool = Query(default=True),
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    query = db.query(QualityAuditChecklistTemplate).filter(QualityAuditChecklistTemplate.amo_id == ctx.amo_id)
    if active_only:
        query = query.filter(QualityAuditChecklistTemplate.status == "ACTIVE")
    rows = query.order_by(QualityAuditChecklistTemplate.template_code.asc()).limit(200).all()
    return {"items": [_template_dict(row) for row in rows]}


@router.post("/audit-checklist-templates", status_code=status.HTTP_201_CREATED)
def create_checklist_template(
    payload: ChecklistTemplateCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = QualityAuditChecklistTemplate(
        amo_id=ctx.amo_id,
        template_code=payload.template_code.strip().upper(),
        title=payload.title.strip(),
        description=payload.description,
        category=payload.category,
        audit_kind=payload.audit_kind.strip().upper() if payload.audit_kind else None,
        status="ACTIVE",
        created_by_user_id=ctx.user_id,
        updated_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _template_dict(row)


@router.get("/audit-checklist-templates/{template_id}")
def get_checklist_template(
    template_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityAuditChecklistTemplate).options(selectinload(QualityAuditChecklistTemplate.revisions)).filter(
        QualityAuditChecklistTemplate.amo_id == ctx.amo_id,
        QualityAuditChecklistTemplate.id == template_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit checklist template not found.")
    return _template_dict(row, include_revisions=True)


@router.post("/audit-checklist-templates/{template_id}/revisions", status_code=status.HTTP_201_CREATED)
def create_checklist_revision(
    template_id: str,
    payload: ChecklistRevisionCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    template = db.query(QualityAuditChecklistTemplate).filter(
        QualityAuditChecklistTemplate.amo_id == ctx.amo_id,
        QualityAuditChecklistTemplate.id == template_id,
        QualityAuditChecklistTemplate.status == "ACTIVE",
    ).first()
    if template is None:
        raise HTTPException(status_code=404, detail="Active audit checklist template not found.")
    latest = db.query(QualityAuditChecklistTemplateRevision).filter(
        QualityAuditChecklistTemplateRevision.amo_id == ctx.amo_id,
        QualityAuditChecklistTemplateRevision.template_id == template_id,
    ).order_by(QualityAuditChecklistTemplateRevision.revision_no.desc()).with_for_update().first()
    if latest is not None and latest.status == "DRAFT":
        raise HTTPException(status_code=409, detail="A DRAFT checklist revision already exists for this template.")
    items = [item.model_dump() for item in payload.items]
    sources = list(payload.source_references)
    row = QualityAuditChecklistTemplateRevision(
        amo_id=ctx.amo_id,
        template_id=template.id,
        revision_no=(latest.revision_no + 1) if latest else 1,
        status="DRAFT",
        items=items,
        source_references=sources,
        content_sha256=_hash_content(items, sources),
        change_reason=payload.reason.strip(),
        supersedes_revision_id=str(latest.id) if latest else None,
        created_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _revision_dict(row)


@router.post("/audit-checklist-templates/{template_id}/revisions/{revision_id}/issue")
def issue_checklist_revision(
    template_id: str,
    revision_id: str,
    payload: ChecklistRevisionIssue,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityAuditChecklistTemplateRevision).filter(
        QualityAuditChecklistTemplateRevision.amo_id == ctx.amo_id,
        QualityAuditChecklistTemplateRevision.template_id == template_id,
        QualityAuditChecklistTemplateRevision.id == revision_id,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit checklist template revision not found.")
    if row.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only a DRAFT checklist template revision may be issued.")
    if not row.items:
        raise HTTPException(status_code=409, detail="Checklist revision must contain at least one item before issue.")
    row.status = "ISSUED"
    row.issued_by_user_id = ctx.user_id
    row.issued_at = _utcnow()
    row.change_reason = f"{row.change_reason}\nISSUE: {payload.reason.strip()}"
    db.commit()
    db.refresh(row)
    return _revision_dict(row)


@router.get("/audits/{audit_id}/checklist-bindings")
def list_checklist_bindings(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    rows = db.query(QualityAuditChecklistBinding).filter(
        QualityAuditChecklistBinding.amo_id == ctx.amo_id,
        QualityAuditChecklistBinding.audit_id == audit_id,
    ).order_by(QualityAuditChecklistBinding.applied_at.asc()).limit(100).all()
    return {"items": [_binding_dict(row) for row in rows]}


@router.post("/audits/{audit_id}/checklist-bindings", status_code=status.HTTP_201_CREATED)
def apply_checklist_revision(
    audit_id: uuid.UUID,
    payload: ChecklistBindingCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    if str(getattr(audit.status, "value", audit.status)) == "CLOSED":
        raise HTTPException(status_code=409, detail="A closed audit cannot receive a new checklist template binding.")
    revision = db.query(QualityAuditChecklistTemplateRevision).options(selectinload(QualityAuditChecklistTemplateRevision.template)).filter(
        QualityAuditChecklistTemplateRevision.amo_id == ctx.amo_id,
        QualityAuditChecklistTemplateRevision.id == payload.template_revision_id,
        QualityAuditChecklistTemplateRevision.status == "ISSUED",
    ).first()
    if revision is None:
        raise HTTPException(status_code=404, detail="Issued audit checklist template revision not found.")
    existing_binding = db.query(QualityAuditChecklistBinding).filter(
        QualityAuditChecklistBinding.amo_id == ctx.amo_id,
        QualityAuditChecklistBinding.audit_id == audit_id,
        QualityAuditChecklistBinding.template_revision_id == revision.id,
    ).first()
    if existing_binding is not None:
        raise HTTPException(status_code=409, detail="This checklist template revision is already bound to the audit.")
    existing_items = db.query(models.QualityAuditChecklistItem).filter(
        models.QualityAuditChecklistItem.amo_id == ctx.amo_id,
        models.QualityAuditChecklistItem.audit_id == audit_id,
    ).count()
    if existing_items and not payload.allow_existing_items:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "The audit already contains live checklist rows.",
                "existing_items": existing_items,
                "required_action": "Review the existing checklist and explicitly allow additive template application if the new revision is intended to supplement it.",
            },
        )

    item_ids: list[str] = []
    for item in list(revision.items or []):
        live = models.QualityAuditChecklistItem(
            amo_id=ctx.amo_id,
            audit_id=audit.id,
            section=item.get("section") or item.get("category"),
            checklist_ref=item.get("checklist_ref") or revision.template.template_code,
            requirement_ref=item.get("requirement_ref") or item.get("regulatory_source_ref") or item.get("manual_source_ref"),
            prompt=str(item.get("prompt") or "").strip(),
            response_status="PENDING",
            objective_evidence=None,
            sort_order=int(item.get("sort_order") or 0),
            created_by_user_id=ctx.user_id,
        )
        if not live.prompt:
            raise HTTPException(status_code=409, detail="Issued checklist template contains an empty prompt and cannot be instantiated.")
        db.add(live)
        db.flush()
        item_ids.append(str(live.id))

    binding = QualityAuditChecklistBinding(
        amo_id=ctx.amo_id,
        audit_id=audit.id,
        template_id=revision.template_id,
        template_revision_id=revision.id,
        template_code=revision.template.template_code,
        revision_no=revision.revision_no,
        content_sha256=revision.content_sha256,
        item_snapshot=list(revision.items or []),
        source_references=list(revision.source_references or []),
        instantiated_item_ids=item_ids,
        application_reason=payload.reason.strip(),
        applied_by_user_id=ctx.user_id,
    )
    db.add(binding)
    db.commit()
    db.refresh(binding)
    return _binding_dict(binding)