from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from amodb.apps.accounts import models as account_models
from amodb.apps.ai.contracts import AIRequestContext
from amodb.apps.ai.errors import AIServiceError
from amodb.apps.ai.service import AIService, get_effective_settings
from amodb.apps.doc_control import domain_models as doc_control_models
from amodb.apps.doc_control import knowledge_models as document_knowledge_models
from amodb.apps.doc_control.workspace_service import can_read_manual
from amodb.apps.manuals import core_router as manual_core
from amodb.apps.manuals import models as manual_models
from amodb.database import get_read_db, get_write_db

from . import models
from .audit_checklist_template_models import (
    QualityAuditChecklistBinding,
    QualityAuditChecklistMemory,
    QualityAuditChecklistTemplate,
    QualityAuditChecklistTemplateRevision,
)
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


class CurrentDocumentChecklistBindingCreate(BaseModel):
    reason: str = Field(min_length=8, max_length=4000)
    allow_existing_items: bool = False


class RealtimeAuditChecklistCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str | None = Field(default=None, max_length=8000)
    reason: str = Field(min_length=8, max_length=4000)
    items: list[ChecklistTemplateItem] = Field(min_length=1, max_length=1000)
    canonical_document_id: str | None = Field(default=None, max_length=36)
    canonical_revision_id: str | None = Field(default=None, max_length=36)
    allow_existing_items: bool = False


class ChecklistAIDraftRequest(BaseModel):
    source_document_ids: list[str] = Field(min_length=1, max_length=8)
    title: str = Field(min_length=3, max_length=255)
    audit_kind: str = Field(default="INTERNAL", pattern=r"^(INTERNAL|EXTERNAL|SUPPLIER|REGULATORY|PROCESS|PRODUCT)$")
    focus: str | None = Field(default=None, max_length=2000)
    max_items: int = Field(default=20, ge=5, le=60)


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
        "canonical_document_id": row.canonical_document_id,
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


def _assert_checklist_can_change(audit: models.QMSAudit) -> None:
    if str(getattr(audit.status, "value", audit.status)).upper() == "CLOSED":
        raise HTTPException(status_code=409, detail="A closed audit cannot receive a new checklist binding.")
    if audit.actual_end is not None:
        raise HTTPException(status_code=409, detail="Fieldwork is complete. Reopen the governed audit lifecycle before changing its checklist.")


def _normalise_context_value(value: Any, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9]+", "-", str(value or "").strip().upper()).strip("-")
    return cleaned[:96] or fallback


def _audit_context(audit: models.QMSAudit) -> tuple[str, str, str, str]:
    audit_kind = _normalise_context_value(getattr(audit.kind, "value", audit.kind), "INTERNAL")
    scope_code = _normalise_context_value(audit.audit_scope_code or audit.unit_code, "GENERAL")
    auditee_key = _normalise_context_value(audit.auditee, "ANY")
    return f"{audit_kind}|{scope_code}|{auditee_key}", audit_kind, scope_code, auditee_key


def _remember_checklist(
    db: Session,
    *,
    ctx: TenantContext,
    audit: models.QMSAudit,
    template: QualityAuditChecklistTemplate,
) -> None:
    context_key, audit_kind, scope_code, auditee_key = _audit_context(audit)
    canonical_document_id = str(template.canonical_document_id) if template.canonical_document_id else None
    selection_key = f"DOCUMENT:{canonical_document_id}" if canonical_document_id else f"TEMPLATE:{template.id}"
    row = db.query(QualityAuditChecklistMemory).filter(
        QualityAuditChecklistMemory.amo_id == ctx.amo_id,
        QualityAuditChecklistMemory.context_key == context_key,
        QualityAuditChecklistMemory.selection_key == selection_key,
    ).with_for_update().first()
    if row is None:
        row = QualityAuditChecklistMemory(
            amo_id=ctx.amo_id,
            context_key=context_key,
            selection_key=selection_key,
            audit_scope_code=scope_code,
            audit_kind=audit_kind,
            auditee_key=auditee_key,
            template_id=template.id,
            canonical_document_id=canonical_document_id,
            last_audit_id=audit.id,
            usage_count=1,
        )
        db.add(row)
    else:
        row.template_id = template.id
        row.canonical_document_id = canonical_document_id
        row.last_audit_id = audit.id
        row.usage_count = int(row.usage_count or 0) + 1
        row.last_used_at = _utcnow()


def _manual_tenant(db: Session, amo_id: str) -> manual_models.Tenant | None:
    return db.query(manual_models.Tenant).filter(manual_models.Tenant.amo_id == amo_id).first()


def _active_user(db: Session, ctx: TenantContext) -> account_models.User:
    user = db.query(account_models.User).filter(
        account_models.User.id == ctx.user_id,
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.is_active.is_(True),
    ).first()
    if user is None:
        raise HTTPException(status_code=403, detail="The active AMO user could not be established.")
    return user


def _document_type(node: document_knowledge_models.DocumentationNode | None, document: manual_models.Manual) -> str:
    if node:
        return str(node.node_type or "").upper()
    return str(document.manual_type or "").strip().upper().replace(" ", "_")


def _current_effective_revision(
    db: Session,
    document: manual_models.Manual,
) -> manual_models.ManualRevision | None:
    if not document.current_published_rev_id:
        return None
    return db.query(manual_models.ManualRevision).filter(
        manual_models.ManualRevision.id == document.current_published_rev_id,
        manual_models.ManualRevision.manual_id == document.id,
        manual_models.ManualRevision.status_enum == manual_models.ManualRevisionStatus.PUBLISHED,
        manual_models.ManualRevision.immutable_locked.is_(True),
    ).first()


def _checklist_items_from_revision(
    db: Session,
    *,
    document: manual_models.Manual,
    revision: manual_models.ManualRevision,
) -> list[dict[str, Any]]:
    sections = db.query(manual_models.ManualSection).filter(
        manual_models.ManualSection.revision_id == revision.id,
    ).order_by(manual_models.ManualSection.order_index.asc(), manual_models.ManualSection.id.asc()).all()
    section_ids = [row.id for row in sections]
    blocks = db.query(manual_models.ManualBlock).filter(
        manual_models.ManualBlock.section_id.in_(section_ids or ["-"]),
    ).order_by(manual_models.ManualBlock.section_id.asc(), manual_models.ManualBlock.order_index.asc()).all()
    section_by_id = {row.id: row for row in sections}
    candidates: list[tuple[str, str]] = []
    for block in blocks:
        section = section_by_id.get(block.section_id)
        for raw in str(block.text_plain or "").splitlines():
            prompt = re.sub(r"\s+", " ", raw).strip(" \t\r\n•☐□")
            if len(prompt) < 6 or len(prompt) > 4000:
                continue
            upper = prompt.upper()
            if upper.startswith(("ISSUE NO", "REVISION NO", "PAGE ", "THIS PAGE IS INTENTIONALLY")):
                continue
            candidates.append((str(section.heading if section else "Checklist"), prompt))
    # Preserve order but remove repeated page headers and duplicate questions.
    unique: list[tuple[str, str]] = []
    seen: set[str] = set()
    for section, prompt in candidates:
        key = re.sub(r"[^A-Z0-9]+", "", prompt.upper())
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append((section, prompt))
    if not unique:
        unique = [("Checklist", f"Complete and retain the attached {document.code} · {document.title} checklist as objective audit evidence.")]
    return [
        ChecklistTemplateItem(
            section=section[:128],
            checklist_ref=document.code[:128],
            requirement_ref=document.code[:255],
            manual_source_ref=f"{document.code} Rev {revision.rev_number}",
            prompt=prompt,
            expected_evidence="Record the response and objective evidence against this checklist item.",
            sort_order=index,
        ).model_dump()
        for index, (section, prompt) in enumerate(unique[:500], start=1)
    ]


def _source_reference(document: manual_models.Manual, revision: manual_models.ManualRevision, source_system: str = "DOCUMENT_CONTROL") -> dict[str, Any]:
    return {
        "source_system": source_system,
        "document_id": str(document.id),
        "revision_id": str(revision.id),
        "document_code": document.code,
        "document_title": document.title,
        "manual_type": document.manual_type,
        "issue_number": revision.issue_number,
        "revision_number": revision.rev_number,
        "revision_status": str(getattr(revision.status_enum, "value", revision.status_enum)),
        "effective_date": revision.effective_date.isoformat() if revision.effective_date else None,
        "source_sha256": revision.source_sha256,
    }


def _criteria_document_text(
    db: Session,
    *,
    document: manual_models.Manual,
    revision: manual_models.ManualRevision,
    remaining_characters: int,
) -> str:
    sections = db.query(manual_models.ManualSection).filter(
        manual_models.ManualSection.revision_id == revision.id,
    ).order_by(manual_models.ManualSection.order_index.asc(), manual_models.ManualSection.id.asc()).all()
    if not sections or remaining_characters <= 0:
        return ""
    section_ids = [row.id for row in sections]
    headings = {str(row.id): row.heading for row in sections}
    blocks = db.query(manual_models.ManualBlock).filter(
        manual_models.ManualBlock.section_id.in_(section_ids),
    ).order_by(manual_models.ManualBlock.section_id.asc(), manual_models.ManualBlock.order_index.asc()).all()
    parts = [f"DOCUMENT: {document.code} - {document.title} (current revision {revision.rev_number})"]
    last_heading = ""
    for block in blocks:
        text = re.sub(r"\s+", " ", str(block.text_plain or "")).strip()
        if not text:
            continue
        heading = str(headings.get(str(block.section_id)) or "Criteria")
        prefix = f"\nSECTION: {heading}\n" if heading != last_heading else "\n"
        candidate = f"{prefix}{text}"
        used = sum(len(value) for value in parts)
        if used + len(candidate) > remaining_characters:
            available = remaining_characters - used
            if available > 200:
                parts.append(candidate[:available])
            break
        parts.append(candidate)
        last_heading = heading
    return "".join(parts).strip()


_AI_CHECKLIST_RESPONSE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "name": "audit_checklist_draft",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "description", "category", "items"],
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "category": {"type": "string"},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "section", "category", "checklist_ref", "requirement_ref",
                        "regulatory_source_ref", "manual_source_ref", "prompt",
                        "expected_evidence", "response_type", "applicability",
                        "mandatory", "finding_trigger",
                    ],
                    "properties": {
                        "section": {"type": "string"},
                        "category": {"type": "string"},
                        "checklist_ref": {"type": "string"},
                        "requirement_ref": {"type": "string"},
                        "regulatory_source_ref": {"type": "string"},
                        "manual_source_ref": {"type": "string"},
                        "prompt": {"type": "string"},
                        "expected_evidence": {"type": "string"},
                        "response_type": {
                            "type": "string",
                            "enum": [
                                "COMPLIANT_NONCOMPLIANT_OBSERVATION_NA_NOT_VERIFIED",
                                "COMPLIANT_NONCOMPLIANT_NA", "YES_NO_NA", "TEXT",
                            ],
                        },
                        "applicability": {"type": "string", "enum": ["ALL", "APPLICABLE", "CONDITIONAL"]},
                        "mandatory": {"type": "boolean"},
                        "finding_trigger": {
                            "type": "string",
                            "enum": ["NONE", "NONCOMPLIANT", "OBSERVATION", "ADVERSE_RESPONSE"],
                        },
                    },
                },
            },
        },
    },
}


def _issued_template_for_document(
    db: Session,
    *,
    ctx: TenantContext,
    audit: models.QMSAudit,
    document: manual_models.Manual,
    revision: manual_models.ManualRevision,
    source_system: str = "DOCUMENT_CONTROL",
    items_override: list[dict[str, Any]] | None = None,
) -> tuple[QualityAuditChecklistTemplate, QualityAuditChecklistTemplateRevision]:
    template = db.query(QualityAuditChecklistTemplate).filter(
        QualityAuditChecklistTemplate.amo_id == ctx.amo_id,
        QualityAuditChecklistTemplate.canonical_document_id == document.id,
        QualityAuditChecklistTemplate.status == "ACTIVE",
    ).first()
    if template is None:
        template_code = document.code[:64]
        code_in_use = db.query(QualityAuditChecklistTemplate.id).filter(
            QualityAuditChecklistTemplate.amo_id == ctx.amo_id,
            QualityAuditChecklistTemplate.template_code == template_code,
        ).first()
        if code_in_use:
            template_code = f"DMS-{document.code[:48]}-{str(document.id)[:6]}"[:64]
        template = QualityAuditChecklistTemplate(
            amo_id=ctx.amo_id,
            template_code=template_code,
            title=document.title,
            description=f"Current controlled checklist sourced from DMS document {document.code}.",
            category="DMS_CHECKLIST",
            audit_kind=str(getattr(audit.kind, "value", audit.kind) or "").upper() or None,
            canonical_document_id=document.id,
            status="ACTIVE",
            created_by_user_id=ctx.user_id,
            updated_by_user_id=ctx.user_id,
        )
        db.add(template)
        db.flush()
    latest = db.query(QualityAuditChecklistTemplateRevision).filter(
        QualityAuditChecklistTemplateRevision.amo_id == ctx.amo_id,
        QualityAuditChecklistTemplateRevision.template_id == template.id,
    ).order_by(QualityAuditChecklistTemplateRevision.revision_no.desc()).first()
    if latest and latest.status == "ISSUED" and any(
        isinstance(item, dict) and str(item.get("revision_id")) == str(revision.id)
        for item in list(latest.source_references or [])
    ):
        return template, latest
    items = items_override or _checklist_items_from_revision(db, document=document, revision=revision)
    sources = [_source_reference(document, revision, source_system)]
    issued = QualityAuditChecklistTemplateRevision(
        amo_id=ctx.amo_id,
        template_id=template.id,
        revision_no=(int(latest.revision_no) + 1) if latest else 1,
        status="ISSUED",
        items=items,
        source_references=sources,
        content_sha256=_hash_content(items, sources),
        change_reason="Issued automatically from the current DMS revision selected during audit preparation.",
        supersedes_revision_id=str(latest.id) if latest else None,
        issued_by_user_id=ctx.user_id,
        issued_at=_utcnow(),
        created_by_user_id=ctx.user_id,
    )
    db.add(issued)
    db.flush()
    return template, issued


def _instantiate_binding(
    db: Session,
    *,
    ctx: TenantContext,
    audit: models.QMSAudit,
    template: QualityAuditChecklistTemplate,
    revision: QualityAuditChecklistTemplateRevision,
    reason: str,
    allow_existing_items: bool,
) -> QualityAuditChecklistBinding:
    existing_items = db.query(models.QualityAuditChecklistItem).filter(
        models.QualityAuditChecklistItem.amo_id == ctx.amo_id,
        models.QualityAuditChecklistItem.audit_id == audit.id,
    ).count()
    if existing_items and not allow_existing_items:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "The audit already contains live checklist rows.",
                "existing_items": existing_items,
                "required_action": "Review the existing checklist and explicitly allow additive application if this checklist is intended to supplement it.",
            },
        )

    item_ids: list[str] = []
    for item in list(revision.items or []):
        prompt = str(item.get("prompt") or "").strip()
        if not prompt:
            raise HTTPException(status_code=409, detail="Issued checklist template contains an empty prompt and cannot be instantiated.")
        live = models.QualityAuditChecklistItem(
            amo_id=ctx.amo_id,
            audit_id=audit.id,
            section=item.get("section") or item.get("category"),
            checklist_ref=item.get("checklist_ref") or template.template_code,
            requirement_ref=item.get("requirement_ref") or item.get("regulatory_source_ref") or item.get("manual_source_ref"),
            prompt=prompt,
            response_status="PENDING",
            objective_evidence=None,
            sort_order=int(item.get("sort_order") or 0),
            created_by_user_id=ctx.user_id,
        )
        db.add(live)
        db.flush()
        item_ids.append(str(live.id))

    binding = QualityAuditChecklistBinding(
        amo_id=ctx.amo_id,
        audit_id=audit.id,
        template_id=template.id,
        template_revision_id=revision.id,
        template_code=template.template_code,
        revision_no=revision.revision_no,
        content_sha256=revision.content_sha256,
        item_snapshot=list(revision.items or []),
        source_references=list(revision.source_references or []),
        instantiated_item_ids=item_ids,
        application_reason=reason.strip(),
        applied_by_user_id=ctx.user_id,
    )
    db.add(binding)
    _remember_checklist(db, ctx=ctx, audit=audit, template=template)
    return binding


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


@router.post("/audit-checklist-templates/ai-draft")
def draft_checklist_with_ai(
    payload: ChecklistAIDraftRequest,
    request: Request,
    response: Response,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    """Draft editable checklist rows from current, readable DMS criteria revisions."""
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    request_id = str(request.headers.get("X-Request-ID") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,96}", request_id):
        request_id = str(uuid.uuid4())
    response.headers["X-Request-ID"] = request_id

    try:
        settings = get_effective_settings(db, tenant_id=ctx.amo_id)
    except (AIServiceError, ValueError) as exc:
        error = exc if isinstance(exc, AIServiceError) else AIServiceError(
            "AI_CONFIGURATION_INVALID",
            "AI configuration is invalid.",
            status_code=503,
        )
        raise HTTPException(status_code=error.status_code, detail=error.detail(request_id=request_id)) from exc
    if not settings.allow_external_document_context:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Document-assisted AI is disabled for this tenant. An AI administrator must enable controlled document context.",
                "error_code": "AI_DOCUMENT_CONTEXT_DISABLED",
                "request_id": request_id,
            },
        )

    tenant = _manual_tenant(db, ctx.amo_id)
    if tenant is None:
        raise HTTPException(status_code=409, detail="Document Control is not configured for this AMO.")
    user = _active_user(db, ctx)
    document_ids = list(dict.fromkeys(str(value).strip() for value in payload.source_document_ids if str(value).strip()))
    documents = db.query(manual_models.Manual).filter(
        manual_models.Manual.tenant_id == tenant.id,
        manual_models.Manual.id.in_(document_ids),
        manual_models.Manual.status == "ACTIVE",
    ).all()
    by_id = {str(row.id): row for row in documents}
    if len(by_id) != len(document_ids):
        raise HTTPException(status_code=404, detail="One or more selected DMS criteria documents were not found.")
    profiles = {
        str(row.manual_id): row
        for row in db.query(doc_control_models.DocumentControlProfile).filter(
            doc_control_models.DocumentControlProfile.tenant_id == ctx.amo_id,
            doc_control_models.DocumentControlProfile.manual_id.in_(document_ids),
        ).all()
    }
    nodes = {
        str(row.manual_id): row
        for row in db.query(document_knowledge_models.DocumentationNode).filter(
            document_knowledge_models.DocumentationNode.tenant_id == ctx.amo_id,
            document_knowledge_models.DocumentationNode.manual_id.in_(document_ids),
        ).all()
    }
    allowed_sources = {
        "MANUAL", "REGULATION", "POLICY", "PROCEDURE", "WORK_INSTRUCTION", "FORM",
        "CHECKLIST", "EXTERNAL_DOCUMENT",
    }
    source_references: list[dict[str, Any]] = []
    criteria_parts: list[str] = []
    remaining = 75_000
    per_document_limit = max(4_000, remaining // len(document_ids))
    for document_id in document_ids:
        document = by_id[document_id]
        if not can_read_manual(user, profiles.get(document_id)):
            raise HTTPException(status_code=403, detail="A selected DMS criteria document is restricted.")
        resolved_type = _document_type(nodes.get(document_id), document)
        if resolved_type not in allowed_sources:
            raise HTTPException(status_code=422, detail=f"{document.code} is not an approved checklist criteria document type.")
        revision = _current_effective_revision(db, document)
        if revision is None:
            raise HTTPException(
                status_code=409,
                detail=f"{document.code} has no current effective revision. Complete Document Control approval first.",
            )
        document_text = _criteria_document_text(
            db,
            document=document,
            revision=revision,
            remaining_characters=min(remaining, per_document_limit),
        )
        if not document_text:
            raise HTTPException(
                status_code=409,
                detail=f"{document.code} has not been indexed by Document Control yet. Complete indexing and retry.",
            )
        criteria_parts.append(document_text)
        remaining -= len(document_text)
        source_references.append(_source_reference(document, revision, "AI_CHECKLIST_CRITERIA"))

    instructions = (
        "You are an aviation quality auditor. Build an evidence-led audit checklist only from the supplied "
        "controlled criteria. Every item must be concise, verifiable, cite the most specific source reference "
        "available, and state objective evidence. Do not invent requirements. Observations require auditor "
        "judgment; use NONCOMPLIANT as the finding trigger only for a clear failed requirement. Return the "
        "requested JSON schema and no commentary."
    )
    focus = str(payload.focus or "").strip()
    input_text = (
        f"CHECKLIST TITLE: {payload.title.strip()}\n"
        f"AUDIT KIND: {payload.audit_kind}\n"
        f"MAXIMUM ITEMS: {payload.max_items}\n"
        f"FOCUS: {focus or 'Cover the applicable controlled criteria proportionately.'}\n\n"
        + "\n\n".join(criteria_parts)
    )
    try:
        result = AIService().complete(
            db,
            context=AIRequestContext(
                tenant_id=ctx.amo_id,
                user_id=ctx.user_id,
                document_context={
                    "document_id": document_ids[0],
                    "revision_id": str(source_references[0]["revision_id"]),
                    "source_count": len(source_references),
                },
                workflow_context={"workflow_type": "CHECKLIST_DRAFTING", "workflow_id": request_id},
            ),
            request_id=request_id,
            feature="CHECKLIST_DRAFTING",
            instructions=instructions,
            input_text=input_text,
            max_output_tokens=min(12_000, 700 + (payload.max_items * 230)),
            response_format=_AI_CHECKLIST_RESPONSE_FORMAT,
        )
    except AIServiceError as exc:
        db.commit()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail(request_id=request_id)) from exc

    try:
        generated = json.loads(result.text)
        raw_items = list(generated.get("items") or [])[: payload.max_items]
        if not raw_items:
            raise ValueError("empty checklist")
        items = [
            ChecklistTemplateItem.model_validate({**item, "sort_order": (index + 1) * 10}).model_dump()
            for index, item in enumerate(raw_items)
        ]
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        db.commit()
        raise HTTPException(
            status_code=502,
            detail={
                "message": "The AI provider returned an unusable checklist draft. Retry with fewer or more specific criteria.",
                "error_code": "AI_CHECKLIST_INVALID_RESPONSE",
                "request_id": request_id,
            },
        ) from exc

    db.commit()
    return {
        "draft": {
            "title": str(generated.get("title") or payload.title).strip()[:255],
            "description": str(generated.get("description") or "").strip()[:8000],
            "category": _normalise_context_value(generated.get("category"), "COMPLIANCE")[:64],
            "audit_kind": payload.audit_kind,
            "items": items,
            "source_references": source_references,
        },
        "provider": result.provider,
        "model": result.model,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "request_id": request_id,
    }


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


@router.get("/audits/{audit_id}/checklist-library")
def list_current_dms_checklists(
    audit_id: uuid.UUID,
    q: str | None = Query(default=None, max_length=255),
    document_type: str | None = Query(default=None, pattern=r"^(CHECKLIST|FORM)$"),
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    """List only current effective DMS forms/checklists; clients never choose revisions."""
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    tenant = _manual_tenant(db, ctx.amo_id)
    if tenant is None:
        return {"items": [], "recommendation": None}
    user = _active_user(db, ctx)
    documents = db.query(manual_models.Manual).filter(
        manual_models.Manual.tenant_id == tenant.id,
        manual_models.Manual.current_published_rev_id.is_not(None),
    ).order_by(manual_models.Manual.code.asc()).limit(500).all()
    document_ids = [row.id for row in documents]
    nodes = {
        row.manual_id: row
        for row in db.query(document_knowledge_models.DocumentationNode).filter(
            document_knowledge_models.DocumentationNode.tenant_id == ctx.amo_id,
            document_knowledge_models.DocumentationNode.manual_id.in_(document_ids or ["-"]),
        ).all()
    }
    profiles = {
        row.manual_id: row
        for row in db.query(doc_control_models.DocumentControlProfile).filter(
            doc_control_models.DocumentControlProfile.tenant_id == ctx.amo_id,
            doc_control_models.DocumentControlProfile.manual_id.in_(document_ids or ["-"]),
        ).all()
    }
    needle = str(q or "").strip().lower()
    requested_type = str(document_type or "").upper()
    items: list[dict[str, Any]] = []
    for document in documents:
        profile = profiles.get(document.id)
        if not can_read_manual(user, profile):
            continue
        node = nodes.get(document.id)
        resolved_type = _document_type(node, document)
        if resolved_type not in {"CHECKLIST", "FORM"} or (requested_type and resolved_type != requested_type):
            continue
        if needle and needle not in " ".join(filter(None, [document.code, document.title, document.manual_type, node.path if node else None])).lower():
            continue
        revision = _current_effective_revision(db, document)
        if revision is None:
            continue
        items.append({
            "document_id": document.id,
            "code": document.code,
            "title": document.title,
            "document_type": resolved_type,
            "hierarchy_path": node.path if node else None,
            "owner_department": profile.owner_department if profile else document.owner_role,
            "current_revision": {
                "id": revision.id,
                "issue_number": revision.issue_number,
                "revision_number": revision.rev_number,
                "effective_date": revision.effective_date.isoformat() if revision.effective_date else None,
                "source_filename": revision.source_filename,
                "source_sha256": revision.source_sha256,
            },
        })
    context_key, _, _, _ = _audit_context(audit)
    remembered = db.query(QualityAuditChecklistMemory).filter(
        QualityAuditChecklistMemory.amo_id == ctx.amo_id,
        QualityAuditChecklistMemory.context_key == context_key,
        QualityAuditChecklistMemory.canonical_document_id.is_not(None),
    ).order_by(QualityAuditChecklistMemory.usage_count.desc(), QualityAuditChecklistMemory.last_used_at.desc()).first()
    if remembered is None:
        # A department/scope match is still useful when the named auditee changes
        # between otherwise similar audits.
        _, audit_kind, scope_code, _ = _audit_context(audit)
        remembered = db.query(QualityAuditChecklistMemory).filter(
            QualityAuditChecklistMemory.amo_id == ctx.amo_id,
            QualityAuditChecklistMemory.audit_kind == audit_kind,
            QualityAuditChecklistMemory.audit_scope_code == scope_code,
            QualityAuditChecklistMemory.canonical_document_id.is_not(None),
        ).order_by(QualityAuditChecklistMemory.usage_count.desc(), QualityAuditChecklistMemory.last_used_at.desc()).first()
    recommended_id = str(remembered.canonical_document_id) if remembered else None
    recommendation = next((item for item in items if str(item["document_id"]) == recommended_id), None)
    if recommendation and remembered:
        recommendation = {
            **recommendation,
            "reason": f"Used for {remembered.usage_count} similar audit{'s' if remembered.usage_count != 1 else ''} in this scope.",
            "usage_count": remembered.usage_count,
        }
    return {"items": items[:200], "recommendation": recommendation}


@router.post("/audits/{audit_id}/checklist-library/{document_id}/bind-current", status_code=status.HTTP_201_CREATED)
def bind_current_dms_checklist(
    audit_id: uuid.UUID,
    document_id: str,
    payload: CurrentDocumentChecklistBindingCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    _assert_checklist_can_change(audit)
    tenant = _manual_tenant(db, ctx.amo_id)
    if tenant is None:
        raise HTTPException(status_code=409, detail="Document Control is not configured for this AMO.")
    user = _active_user(db, ctx)
    document = db.query(manual_models.Manual).filter(
        manual_models.Manual.id == document_id,
        manual_models.Manual.tenant_id == tenant.id,
    ).first()
    if document is None:
        raise HTTPException(status_code=404, detail="DMS checklist not found.")
    profile = db.query(doc_control_models.DocumentControlProfile).filter(
        doc_control_models.DocumentControlProfile.tenant_id == ctx.amo_id,
        doc_control_models.DocumentControlProfile.manual_id == document.id,
    ).first()
    if not can_read_manual(user, profile):
        raise HTTPException(status_code=403, detail="The selected DMS checklist is restricted.")
    node = db.query(document_knowledge_models.DocumentationNode).filter(
        document_knowledge_models.DocumentationNode.tenant_id == ctx.amo_id,
        document_knowledge_models.DocumentationNode.manual_id == document.id,
    ).first()
    if _document_type(node, document) not in {"CHECKLIST", "FORM"}:
        raise HTTPException(status_code=422, detail="Only a DMS checklist or form can be bound as the fieldwork checklist.")
    revision = _current_effective_revision(db, document)
    if revision is None:
        raise HTTPException(status_code=409, detail="This DMS document has no current effective revision. Complete Document Control approval first.")
    template, issued = _issued_template_for_document(
        db,
        ctx=ctx,
        audit=audit,
        document=document,
        revision=revision,
    )
    existing = db.query(QualityAuditChecklistBinding).filter(
        QualityAuditChecklistBinding.amo_id == ctx.amo_id,
        QualityAuditChecklistBinding.audit_id == audit.id,
        QualityAuditChecklistBinding.template_revision_id == issued.id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="The current revision of this DMS checklist is already bound to the audit.")
    binding = _instantiate_binding(
        db,
        ctx=ctx,
        audit=audit,
        template=template,
        revision=issued,
        reason=payload.reason,
        allow_existing_items=payload.allow_existing_items,
    )
    db.commit()
    db.refresh(binding)
    return _binding_dict(binding)


@router.post("/audits/{audit_id}/checklist-library/upload", status_code=status.HTTP_201_CREATED)
async def upload_dms_checklist_from_audit(
    audit_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    code: str = Form(..., min_length=2, max_length=64),
    title: str = Form(..., min_length=3, max_length=255),
    revision_number: str = Form(..., min_length=1, max_length=32),
    issue_number: str = Form("00", max_length=32),
    effective_date: str | None = Form(None),
    owner_department: str = Form("QUALITY", max_length=128),
    reason: str = Form(..., min_length=8, max_length=4000),
    control_metadata_json: str = Form(...),
    items_json: str | None = Form(None),
    file: UploadFile = File(...),
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    """Register a checklist in canonical DMS; only an approved current revision may later be bound."""
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    _assert_checklist_can_change(audit)
    tenant = _manual_tenant(db, ctx.amo_id)
    if tenant is None:
        raise HTTPException(status_code=409, detail="Document Control is not configured for this AMO.")
    user = _active_user(db, ctx)
    manual_core._require_manual_control_user(user)
    try:
        metadata = json.loads(control_metadata_json)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Checklist metadata must be valid JSON.") from exc
    if not isinstance(metadata, dict):
        raise HTTPException(status_code=422, detail="Checklist metadata must be a JSON object.")
    document_type = str(metadata.get("document_type") or "CHECKLIST").strip().upper()
    if document_type not in {"CHECKLIST", "FORM"}:
        raise HTTPException(status_code=422, detail="Audit preparation can upload only a Checklist or Form.")
    metadata = {
        **metadata,
        "document_type": document_type,
        "owner_department": owner_department,
        "intake_source": "QMS_AUDIT_PREPARATION",
        "source_audit_id": str(audit.id),
        "source_audit_ref": audit.audit_ref,
    }
    if items_json:
        try:
            raw_items = json.loads(items_json)
            if not isinstance(raw_items, list):
                raise ValueError("not a list")
            for item in raw_items:
                ChecklistTemplateItem.model_validate(item)
        except (TypeError, ValueError) as exc:
            # Validate before the canonical DMS upload commits so a malformed
            # QMS payload cannot leave an unintended partial document intake.
            raise HTTPException(status_code=422, detail="Checklist items must be a valid JSON array.") from exc
    filename = str(file.filename or "").lower()
    common = {
        "tenant_slug": tenant.slug,
        "request": request,
        "code": code.strip(),
        "title": title.strip(),
        "rev_number": revision_number.strip(),
        "manual_type": document_type,
        "owner_role": owner_department.strip() or "QUALITY",
        "issue_number": issue_number.strip(),
        "effective_date": effective_date,
        "change_log": reason.strip(),
        "control_metadata_json": json.dumps(metadata),
        "file": file,
        "db": db,
        "current_user": user,
    }
    if filename.endswith(".pdf"):
        upload = await manual_core.upload_pdf_revision(**common)
        from amodb.apps.manuals.pdf_reader_precompute import precompute_pdf_reader_assets

        background_tasks.add_task(precompute_pdf_reader_assets, upload["revision_id"])
    elif filename.endswith(".docx"):
        upload = await manual_core.upload_docx_revision(**common)
    else:
        raise HTTPException(status_code=422, detail="Upload a PDF or DOCX checklist.")
    from amodb.apps.doc_control.knowledge_indexer import index_revision_background

    background_tasks.add_task(index_revision_background, upload["revision_id"])
    # The manuals intake commits its canonical record; restore the transaction-local
    # tenant context before returning the tenant-scoped DMS identity.
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    document = db.query(manual_models.Manual).filter(
        manual_models.Manual.id == upload["manual_id"],
        manual_models.Manual.tenant_id == tenant.id,
    ).one()
    revision = db.query(manual_models.ManualRevision).filter(
        manual_models.ManualRevision.id == upload["revision_id"],
        manual_models.ManualRevision.manual_id == document.id,
    ).one()
    return {
        "document": {
            "id": document.id,
            "code": document.code,
            "title": document.title,
            "document_type": document_type,
            "revision_id": revision.id,
            "revision_status": str(getattr(revision.status_enum, "value", revision.status_enum)),
            "workflow_required": True,
        },
        "binding": None,
    }


@router.get("/audits/{audit_id}/checklist-recommendations")
def get_checklist_recommendations(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    context_key, audit_kind, scope_code, auditee_key = _audit_context(audit)
    rows = db.query(QualityAuditChecklistMemory).filter(
        QualityAuditChecklistMemory.amo_id == ctx.amo_id,
        QualityAuditChecklistMemory.context_key == context_key,
    ).order_by(QualityAuditChecklistMemory.usage_count.desc(), QualityAuditChecklistMemory.last_used_at.desc()).limit(10).all()
    return {
        "context": {
            "key": context_key,
            "audit_kind": audit_kind,
            "audit_scope_code": scope_code,
            "auditee_key": auditee_key,
        },
        "items": [{
            "template_id": row.template_id,
            "canonical_document_id": row.canonical_document_id,
            "usage_count": row.usage_count,
            "last_audit_id": str(row.last_audit_id) if row.last_audit_id else None,
            "last_used_at": row.last_used_at,
        } for row in rows],
    }


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
    _assert_checklist_can_change(audit)
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
    binding = _instantiate_binding(
        db,
        ctx=ctx,
        audit=audit,
        template=revision.template,
        revision=revision,
        reason=payload.reason,
        allow_existing_items=payload.allow_existing_items,
    )
    db.commit()
    db.refresh(binding)
    return _binding_dict(binding)


@router.post("/audits/{audit_id}/checklists/realtime", status_code=status.HTTP_201_CREATED)
def create_realtime_audit_checklist(
    audit_id: uuid.UUID,
    payload: RealtimeAuditChecklistCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    """Create, issue, and bind an audit-scoped checklist as one transaction."""
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    _assert_checklist_can_change(audit)

    source_references: list[dict[str, Any] | str] = [{
        "source_system": "REALTIME_AUDIT_PREPARATION",
        "audit_id": str(audit.id),
        "audit_ref": audit.audit_ref,
    }]
    document = None
    revision = None
    if payload.canonical_document_id or payload.canonical_revision_id:
        from .audit_occurrence_completion_router import _enum_value, _validate_canonical_controlled_source
        if payload.canonical_document_id and not payload.canonical_revision_id:
            tenant = _manual_tenant(db, ctx.amo_id)
            user = _active_user(db, ctx)
            document = db.query(manual_models.Manual).filter(
                manual_models.Manual.id == payload.canonical_document_id,
                manual_models.Manual.tenant_id == (tenant.id if tenant else "-"),
            ).first()
            profile = db.query(doc_control_models.DocumentControlProfile).filter(
                doc_control_models.DocumentControlProfile.tenant_id == ctx.amo_id,
                doc_control_models.DocumentControlProfile.manual_id == payload.canonical_document_id,
            ).first()
            if document is None or not can_read_manual(user, profile):
                raise HTTPException(status_code=404, detail="The selected DMS document is not available.")
            revision = _current_effective_revision(db, document)
        else:
            document, revision = _validate_canonical_controlled_source(
                db,
                amo_id=ctx.amo_id,
                document_id=payload.canonical_document_id,
                revision_id=payload.canonical_revision_id,
                user_id=ctx.user_id,
                require_revision=True,
            )
        if document is None or revision is None:
            raise HTTPException(status_code=422, detail="The selected DMS document has no current effective revision.")
        source_references.append({
            "source_system": "DOCUMENT_CONTROL",
            "document_id": str(document.id),
            "revision_id": str(revision.id),
            "document_code": document.code,
            "document_title": document.title,
            "manual_type": document.manual_type,
            "issue_number": revision.issue_number,
            "revision_number": revision.rev_number,
            "revision_status": _enum_value(revision.status_enum),
            "effective_date": revision.effective_date.isoformat() if revision.effective_date else None,
            "source_sha256": revision.source_sha256,
        })

    items = [item.model_dump() for item in payload.items]
    now = _utcnow()
    template = QualityAuditChecklistTemplate(
        amo_id=ctx.amo_id,
        template_code=f"AUD-{uuid.uuid4().hex[:12].upper()}",
        title=payload.title.strip(),
        description=(payload.description or "").strip() or None,
        category="AUDIT_SPECIFIC",
        audit_kind=str(getattr(audit.kind, "value", audit.kind) or "").upper() or None,
        canonical_document_id=document.id if document else None,
        status="ACTIVE",
        created_by_user_id=ctx.user_id,
        updated_by_user_id=ctx.user_id,
    )
    db.add(template)
    db.flush()
    revision = QualityAuditChecklistTemplateRevision(
        amo_id=ctx.amo_id,
        template_id=template.id,
        revision_no=1,
        status="ISSUED",
        items=items,
        source_references=source_references,
        content_sha256=_hash_content(items, source_references),
        change_reason=f"{payload.reason.strip()}\nISSUE: Created and issued during audit preparation.",
        issued_by_user_id=ctx.user_id,
        issued_at=now,
        created_by_user_id=ctx.user_id,
    )
    db.add(revision)
    db.flush()
    binding = _instantiate_binding(
        db,
        ctx=ctx,
        audit=audit,
        template=template,
        revision=revision,
        reason=payload.reason,
        allow_existing_items=payload.allow_existing_items,
    )
    db.commit()
    db.refresh(binding)
    return _binding_dict(binding)
