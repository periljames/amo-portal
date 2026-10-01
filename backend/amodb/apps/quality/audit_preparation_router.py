from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from amodb.database import get_write_db

from . import models
from .audit_checklist_template_models import QualityAuditChecklistBinding
from .audit_checklist_execution_models import QualityAuditChecklistExecutionGovernance
from .audit_evidence_models import QualityAuditEvidenceArtifact
from .audit_occurrence_completion_models import QualityAuditDocumentRequestMetadata, QualityAuditMeeting
from .audit_preparation_models import QualityAuditPreparationEvent, QualityAuditPreparationRevision, QualityAuditWorkPackage
from .tenant_security import TenantContext, assert_quality_permission, require_quality_permission, set_postgres_tenant_context, write_tenant_context


router = APIRouter(tags=["Quality audit preparation governance"])


class PreparationRevisionCreate(BaseModel):
    reason: str = Field(min_length=8, max_length=4000)
    preparation_scope: str | None = Field(default=None, max_length=8000)


class PreparationIssue(BaseModel):
    reason: str = Field(min_length=8, max_length=4000)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _audit(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> models.QMSAudit:
    row = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == amo_id,
        models.QMSAudit.id == audit_id,
        models.QMSAudit.deleted_at.is_(None),
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit not found.")
    return row


def _capture_sources(db: Session, *, amo_id: str, audit: models.QMSAudit) -> dict[str, Any]:
    checklist = db.query(models.QualityAuditChecklistItem).filter(
        models.QualityAuditChecklistItem.amo_id == amo_id,
        models.QualityAuditChecklistItem.audit_id == audit.id,
    ).order_by(
        models.QualityAuditChecklistItem.section.asc(),
        models.QualityAuditChecklistItem.sort_order.asc(),
        models.QualityAuditChecklistItem.created_at.asc(),
    ).all()
    requests = db.query(models.QualityAuditDocumentRequest).filter(
        models.QualityAuditDocumentRequest.amo_id == amo_id,
        models.QualityAuditDocumentRequest.audit_id == audit.id,
    ).order_by(models.QualityAuditDocumentRequest.created_at.asc()).all()
    bindings = db.query(QualityAuditChecklistBinding).filter(
        QualityAuditChecklistBinding.amo_id == amo_id,
        QualityAuditChecklistBinding.audit_id == audit.id,
    ).order_by(QualityAuditChecklistBinding.applied_at.asc()).all()
    request_metadata = db.query(QualityAuditDocumentRequestMetadata).filter(
        QualityAuditDocumentRequestMetadata.amo_id == amo_id,
        QualityAuditDocumentRequestMetadata.audit_id == audit.id,
    ).all()
    metadata_by_request = {row.request_id: row for row in request_metadata}

    audit_snapshot = {
        "audit_id": str(audit.id),
        "audit_ref": audit.audit_ref,
        "title": audit.title,
        "domain": _enum_value(audit.domain),
        "kind": _enum_value(audit.kind),
        "status": _enum_value(audit.status),
        "scope": audit.scope,
        "criteria": audit.criteria,
        "audit_scope_id": str(audit.audit_scope_id) if audit.audit_scope_id else None,
        "audit_scope_code": audit.audit_scope_code,
        "auditee": audit.auditee,
        "auditee_user_id": audit.auditee_user_id,
        "lead_auditor_user_id": audit.lead_auditor_user_id,
        "observer_auditor_user_id": audit.observer_auditor_user_id,
        "assistant_auditor_user_id": audit.assistant_auditor_user_id,
        "planned_start": audit.planned_start.isoformat() if audit.planned_start else None,
        "planned_end": audit.planned_end.isoformat() if audit.planned_end else None,
    }
    checklist_snapshot = [
        {
            "id": str(item.id),
            "section": item.section,
            "checklist_ref": item.checklist_ref,
            "requirement_ref": item.requirement_ref,
            "prompt": item.prompt,
            "response_status": item.response_status,
            "objective_evidence": item.objective_evidence,
            "finding_id": str(item.finding_id) if item.finding_id else None,
            "assigned_to_user_id": item.assigned_to_user_id,
            "sort_order": item.sort_order,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }
        for item in checklist
    ]
    request_snapshot = []
    for item in requests:
        metadata = metadata_by_request.get(item.id)
        request_snapshot.append({
            "id": str(item.id),
            "title": item.title,
            "description": item.description,
            "due_date": item.due_date.isoformat() if item.due_date else None,
            "status": item.status,
            "file_ref": item.file_ref,
            "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            "request_type": metadata.request_type if metadata else "DOCUMENT",
            "linked_criterion": metadata.linked_criterion if metadata else None,
            "is_required": metadata.is_required if metadata else True,
            "requirement_stage": metadata.requirement_stage if metadata else "REQUIRED_BEFORE_ISSUE",
            "source_mode": metadata.source_mode if metadata else "UPLOAD_OR_CONTROLLED",
            "controlled_source_system": metadata.controlled_source_system if metadata else "QMS_LOCAL",
            "controlled_document_id": str(metadata.controlled_document_id) if metadata and metadata.controlled_document_id else None,
            "controlled_revision_id": str(metadata.controlled_revision_id) if metadata and metadata.controlled_revision_id else None,
            "canonical_document_id": metadata.canonical_document_id if metadata else None,
            "canonical_revision_id": metadata.canonical_revision_id if metadata else None,
        })
    source_references = [
        {"source_type": "QMS_AUDIT", "source_id": str(audit.id), "source_route": f"/quality/audit/{audit.id}/run"},
        *[
            {"source_type": "QUALITY_AUDIT_CHECKLIST_ITEM", "source_id": str(item.id), "source_route": f"/quality/audit/{audit.id}/run"}
            for item in checklist
        ],
        *[
            {"source_type": "QUALITY_AUDIT_DOCUMENT_REQUEST", "source_id": str(item.id), "source_route": f"/quality/audit/{audit.id}/run"}
            for item in requests
        ],
        *[
            {
                "source_type": "QUALITY_AUDIT_CHECKLIST_BINDING",
                "source_id": str(binding.id),
                "template_revision_id": str(binding.template_revision_id),
                "template_code": binding.template_code,
                "revision_no": binding.revision_no,
                "content_sha256": binding.content_sha256,
            }
            for binding in bindings
        ],
        *[
            {
                **source,
                "checklist_binding_id": str(binding.id),
                "source_type": source.get("source_system", "CHECKLIST_SOURCE"),
            }
            for binding in bindings
            for source in list(binding.source_references or [])
            if isinstance(source, dict)
        ],
    ]
    fingerprint_payload = {
        # Execution status and fieldwork answers are outcomes, not preparation
        # inputs. Excluding them prevents a legitimate first fieldwork update
        # from making the issued preparation snapshot appear stale.
        "audit": {key: value for key, value in audit_snapshot.items() if key != "status"},
        "checklist": [
            {
                key: value
                for key, value in item.items()
                if key not in {"response_status", "objective_evidence", "finding_id", "updated_at"}
            }
            for item in checklist_snapshot
        ],
        # Only the governed request definition belongs to the preparation
        # fingerprint. Submission/review state is execution evidence and may
        # legitimately change after issue without invalidating fieldwork.
        "document_requests": [
            {
                key: value
                for key, value in request.items()
                if key not in {"status", "file_ref", "reviewed_at", "updated_at"}
            }
            for request in request_snapshot
        ],
        "checklist_bindings": [
            {
                "id": str(binding.id),
                "template_revision_id": str(binding.template_revision_id),
                "content_sha256": binding.content_sha256,
                "source_references": list(binding.source_references or []),
            }
            for binding in bindings
        ],
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return {
        "audit_snapshot": audit_snapshot,
        "checklist_snapshot": checklist_snapshot,
        "document_request_snapshot": request_snapshot,
        "source_references": source_references,
        "source_fingerprint": fingerprint,
    }


def _preparation_readiness_blockers(
    captured: dict[str, Any],
    *,
    phase: str = "ISSUE",
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if not captured.get("checklist_snapshot"):
        blockers.append({"type": "CHECKLIST", "reason": "At least one governed checklist item must be prepared before issue."})

    blocking_stages = {"REQUIRED_BEFORE_ISSUE"}
    if phase == "FIELDWORK":
        blocking_stages.add("REQUIRED_BEFORE_FIELDWORK")

    unresolved_required = [
        request
        for request in captured.get("document_request_snapshot", [])
        if request.get("is_required", True)
        and request.get("requirement_stage", "REQUIRED_BEFORE_ISSUE") in blocking_stages
        and request.get("status") not in {"ACCEPTED", "WAIVED"}
    ]
    if unresolved_required:
        stage_label = "fieldwork" if phase == "FIELDWORK" else "preparation issue"
        blockers.append({
            "type": "DOCUMENT_REQUEST",
            "count": len(unresolved_required),
            "request_ids": [request.get("id") for request in unresolved_required],
            "reason": f"{len(unresolved_required)} governed document request(s) required before {stage_label} remain unresolved.",
        })
    return blockers


def _work_package_dict(row: QualityAuditWorkPackage) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "audit_id": str(row.audit_id),
        "preparation_revision_id": str(row.preparation_revision_id),
        "revision_no": row.revision_no,
        "package_snapshot": row.package_snapshot or {},
        "content_sha256": row.content_sha256,
        "offline_expires_at": row.offline_expires_at,
        "supersedes_work_package_id": row.supersedes_work_package_id,
        "issued_by_user_id": row.issued_by_user_id,
        "issued_at": row.issued_at,
        "created_at": row.created_at,
    }


def _build_work_package_snapshot(
    db: Session,
    *,
    amo_id: str,
    audit: models.QMSAudit,
    preparation: QualityAuditPreparationRevision,
) -> dict[str, Any]:
    from .audit_preparation_context_router import _audit_dict, _car_dict, _finding_dict, _prior_audits

    prior_audits = _prior_audits(db, current=audit, amo_id=amo_id)
    prior_ids = [item.id for item in prior_audits]
    prior_findings = (
        db.query(models.QMSAuditFinding)
        .filter(
            models.QMSAuditFinding.amo_id == amo_id,
            models.QMSAuditFinding.audit_id.in_(prior_ids),
        )
        .order_by(models.QMSAuditFinding.created_at.desc())
        .limit(150)
        .all()
        if prior_ids
        else []
    )
    prior_finding_ids = [item.id for item in prior_findings]
    prior_cars = (
        db.query(models.CorrectiveActionRequest)
        .filter(models.CorrectiveActionRequest.finding_id.in_(prior_finding_ids))
        .limit(250)
        .all()
        if prior_finding_ids
        else []
    )
    meetings = (
        db.query(QualityAuditMeeting)
        .filter(
            QualityAuditMeeting.amo_id == amo_id,
            QualityAuditMeeting.audit_id == audit.id,
            QualityAuditMeeting.status != "CANCELLED",
        )
        .order_by(QualityAuditMeeting.scheduled_start.asc())
        .all()
    )
    request_definitions = [
        {
            key: value
            for key, value in request.items()
            if key not in {"status", "file_ref", "reviewed_at", "updated_at"}
        }
        for request in list(preparation.document_request_snapshot or [])
    ]
    frozen_bindings = (
        db.query(QualityAuditChecklistBinding)
        .filter(
            QualityAuditChecklistBinding.amo_id == amo_id,
            QualityAuditChecklistBinding.audit_id == audit.id,
        )
        .order_by(QualityAuditChecklistBinding.applied_at.asc())
        .all()
    )
    return {
        "schema": "QMS_AUDIT_WORK_PACKAGE_V1",
        "audit": _audit_dict(audit),
        "preparation": {
            "revision_id": str(preparation.id),
            "revision_no": preparation.revision_no,
            "source_fingerprint": preparation.source_fingerprint,
            "preparation_scope": preparation.preparation_scope,
            "issued_at": preparation.issued_at.isoformat() if preparation.issued_at else None,
        },
        "checklist_snapshot": list(preparation.checklist_snapshot or []),
        "checklist_bindings": [
            {
                "id": str(binding.id),
                "template_id": str(binding.template_id),
                "template_revision_id": str(binding.template_revision_id),
                "template_code": binding.template_code,
                "revision_no": binding.revision_no,
                "content_sha256": binding.content_sha256,
                "item_snapshot": list(binding.item_snapshot or []),
                "source_references": list(binding.source_references or []),
                "instantiated_item_ids": [str(value) for value in list(binding.instantiated_item_ids or [])],
                "application_reason": binding.application_reason,
                "applied_at": binding.applied_at.isoformat() if binding.applied_at else None,
            }
            for binding in frozen_bindings
        ],
        "document_request_definitions": request_definitions,
        "source_references": list(preparation.source_references or []),
        "prior_audits": [_audit_dict(item) for item in prior_audits],
        "prior_findings": [_finding_dict(item) for item in prior_findings],
        "prior_cars": [_car_dict(item) for item in prior_cars],
        "meetings": [
            {
                "id": str(item.id),
                "meeting_type": item.meeting_type,
                "scheduled_start": item.scheduled_start.isoformat() if item.scheduled_start else None,
                "scheduled_end": item.scheduled_end.isoformat() if item.scheduled_end else None,
                "location": item.location,
                "conference_url": item.conference_url,
                "status": item.status,
            }
            for item in meetings
        ],
    }


def _ensure_work_package(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    audit: models.QMSAudit,
    preparation: QualityAuditPreparationRevision,
) -> QualityAuditWorkPackage:
    existing = (
        db.query(QualityAuditWorkPackage)
        .filter(
            QualityAuditWorkPackage.amo_id == amo_id,
            QualityAuditWorkPackage.preparation_revision_id == preparation.id,
        )
        .first()
    )
    if existing is not None:
        return existing

    snapshot = _build_work_package_snapshot(
        db,
        amo_id=amo_id,
        audit=audit,
        preparation=preparation,
    )
    content_sha256 = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    previous = (
        db.query(QualityAuditWorkPackage)
        .filter(
            QualityAuditWorkPackage.amo_id == amo_id,
            QualityAuditWorkPackage.audit_id == audit.id,
        )
        .order_by(QualityAuditWorkPackage.revision_no.desc())
        .first()
    )
    package = QualityAuditWorkPackage(
        amo_id=amo_id,
        audit_id=audit.id,
        preparation_revision_id=preparation.id,
        revision_no=preparation.revision_no,
        package_snapshot=snapshot,
        content_sha256=content_sha256,
        supersedes_work_package_id=str(previous.id) if previous else None,
        issued_by_user_id=user_id,
        issued_at=preparation.issued_at or _utcnow(),
    )
    db.add(package)
    db.flush()
    return package


def _event_dict(row: QualityAuditPreparationEvent) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "event_type": row.event_type,
        "reason": row.reason,
        "actor_user_id": row.actor_user_id,
        "created_at": row.created_at,
    }


def _revision_dict(row: QualityAuditPreparationRevision) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "audit_id": str(row.audit_id),
        "revision_no": row.revision_no,
        "status": row.status,
        "preparation_scope": row.preparation_scope,
        "audit_snapshot": row.audit_snapshot or {},
        "checklist_snapshot": row.checklist_snapshot or [],
        "document_request_snapshot": row.document_request_snapshot or [],
        "source_references": row.source_references or [],
        "source_fingerprint": row.source_fingerprint,
        "change_reason": row.change_reason,
        "supersedes_revision_id": row.supersedes_revision_id,
        "issued_by_user_id": row.issued_by_user_id,
        "issued_at": row.issued_at,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at,
        "events": [_event_dict(item) for item in list(row.events or [])],
    }


@router.get("/audits/{audit_id}/preparation-revisions")
def list_preparation_revisions(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    rows = db.query(QualityAuditPreparationRevision).options(
        selectinload(QualityAuditPreparationRevision.events)
    ).filter(
        QualityAuditPreparationRevision.amo_id == ctx.amo_id,
        QualityAuditPreparationRevision.audit_id == audit_id,
    ).order_by(QualityAuditPreparationRevision.revision_no.desc()).limit(100).all()
    return {"items": [_revision_dict(row) for row in rows]}


@router.post("/audits/{audit_id}/preparation-revisions", status_code=status.HTTP_201_CREATED)
def create_preparation_revision(
    audit_id: uuid.UUID,
    payload: PreparationRevisionCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    latest = db.query(QualityAuditPreparationRevision).filter(
        QualityAuditPreparationRevision.amo_id == ctx.amo_id,
        QualityAuditPreparationRevision.audit_id == audit_id,
    ).order_by(QualityAuditPreparationRevision.revision_no.desc()).with_for_update().first()
    if latest is not None and latest.status == "DRAFT":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A draft preparation revision already exists. Issue it or discard the draft through the governed workflow before creating another revision.",
        )
    captured = _capture_sources(db, amo_id=ctx.amo_id, audit=audit)
    row = QualityAuditPreparationRevision(
        amo_id=ctx.amo_id,
        audit_id=audit.id,
        revision_no=(latest.revision_no + 1) if latest else 1,
        status="DRAFT",
        preparation_scope=payload.preparation_scope,
        **captured,
        change_reason=payload.reason.strip(),
        supersedes_revision_id=str(latest.id) if latest else None,
        created_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.flush()
    db.add(QualityAuditPreparationEvent(
        amo_id=ctx.amo_id,
        audit_id=audit.id,
        revision_id=row.id,
        event_type="CREATED",
        reason=payload.reason.strip(),
        actor_user_id=ctx.user_id,
    ))
    db.commit()
    return _revision_dict(
        db.query(QualityAuditPreparationRevision).options(selectinload(QualityAuditPreparationRevision.events)).filter(
            QualityAuditPreparationRevision.amo_id == ctx.amo_id,
            QualityAuditPreparationRevision.id == row.id,
        ).one()
    )


@router.post("/audits/{audit_id}/preparation-revisions/{revision_id}/issue")
def issue_preparation_revision(
    audit_id: uuid.UUID,
    revision_id: str,
    payload: PreparationIssue,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    row = db.query(QualityAuditPreparationRevision).options(
        selectinload(QualityAuditPreparationRevision.events)
    ).filter(
        QualityAuditPreparationRevision.amo_id == ctx.amo_id,
        QualityAuditPreparationRevision.audit_id == audit_id,
        QualityAuditPreparationRevision.id == revision_id,
    ).with_for_update().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit preparation revision not found.")
    if row.status != "DRAFT":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only a DRAFT preparation revision may be issued.")
    current = _capture_sources(db, amo_id=ctx.amo_id, audit=audit)
    readiness_blockers = _preparation_readiness_blockers(current)
    from .audit_workflow_contract import _audit_setup_ready
    if not _audit_setup_ready(audit, db):
        readiness_blockers.append({
            "type": "SETUP",
            "reason": "Save the audit definition and assign eligible auditors with required independence declarations before issue.",
        })
    if readiness_blockers:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "PREPARATION_NOT_READY",
                "message": "Audit preparation is not ready to issue.",
                "blockers": readiness_blockers,
            },
        )
    # A DRAFT is intentionally mutable. Refresh it from the authoritative audit
    # sources at the moment of issue so an early draft cannot deadlock the audit
    # after a checklist or document request is added. The issued snapshot remains
    # immutable and its fingerprint always matches the exact fieldwork inputs.
    if current["source_fingerprint"] != row.source_fingerprint:
        row.audit_snapshot = current["audit_snapshot"]
        row.checklist_snapshot = current["checklist_snapshot"]
        row.document_request_snapshot = current["document_request_snapshot"]
        row.source_references = current["source_references"]
        row.source_fingerprint = current["source_fingerprint"]
    row.status = "ISSUED"
    row.issued_by_user_id = ctx.user_id
    row.issued_at = _utcnow()
    work_package = _ensure_work_package(
        db,
        amo_id=ctx.amo_id,
        user_id=ctx.user_id,
        audit=audit,
        preparation=row,
    )
    db.add(QualityAuditPreparationEvent(
        amo_id=ctx.amo_id,
        audit_id=audit.id,
        revision_id=row.id,
        event_type="ISSUED",
        reason=payload.reason.strip(),
        actor_user_id=ctx.user_id,
    ))
    db.commit()
    db.refresh(row)
    result = _revision_dict(row)
    result["work_package"] = _work_package_dict(work_package)
    return result



@router.get("/audits/{audit_id}/preparation-readiness")
def get_audit_preparation_readiness(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    captured = _capture_sources(db, amo_id=ctx.amo_id, audit=audit)
    from .audit_workflow_contract import _audit_setup_ready

    issue_blockers = _preparation_readiness_blockers(captured, phase="ISSUE")
    fieldwork_blockers = _preparation_readiness_blockers(captured, phase="FIELDWORK")
    if not _audit_setup_ready(audit, db):
        setup = {
            "type": "SETUP",
            "reason": "Save the audit definition and assign eligible auditors with required independence declarations.",
        }
        issue_blockers.append(setup)
        fieldwork_blockers.append(setup)

    latest = (
        db.query(QualityAuditPreparationRevision)
        .filter(
            QualityAuditPreparationRevision.amo_id == ctx.amo_id,
            QualityAuditPreparationRevision.audit_id == audit_id,
        )
        .order_by(QualityAuditPreparationRevision.revision_no.desc())
        .first()
    )
    issued = latest is not None and latest.status == "ISSUED"
    stale = bool(issued and latest.source_fingerprint != captured["source_fingerprint"])
    if not issued:
        fieldwork_blockers.append({
            "type": "PREPARATION_REVISION",
            "reason": "Issue the current governed preparation revision before fieldwork.",
        })
    elif stale:
        fieldwork_blockers.append({
            "type": "PREPARATION_STALE",
            "reason": "Preparation inputs changed after issue. Create and issue a new controlled preparation revision.",
        })

    checks = [
        {
            "code": "AUDIT_DEFINITION",
            "label": "Audit definition and eligible team",
            "complete": not any(item["type"] == "SETUP" for item in issue_blockers),
        },
        {
            "code": "CHECKLIST",
            "label": "Governed checklist assigned",
            "complete": bool(captured.get("checklist_snapshot")),
        },
        {
            "code": "PRE_ISSUE_REQUESTS",
            "label": "Pre-issue evidence requests resolved",
            "complete": not any(item["type"] == "DOCUMENT_REQUEST" for item in issue_blockers),
        },
        {
            "code": "FIELDWORK_REQUESTS",
            "label": "Pre-fieldwork evidence requests resolved",
            "complete": not any(item["type"] == "DOCUMENT_REQUEST" for item in fieldwork_blockers),
        },
        {
            "code": "CONTROLLED_PREPARATION",
            "label": "Controlled preparation issued and current",
            "complete": issued and not stale,
        },
    ]
    complete_count = sum(1 for item in checks if item["complete"])
    return {
        "issue_ready": len(issue_blockers) == 0,
        "fieldwork_ready": len(fieldwork_blockers) == 0,
        "checks": checks,
        "issue_blockers": issue_blockers,
        "fieldwork_blockers": fieldwork_blockers,
        "complete_count": complete_count,
        "total_count": len(checks),
        "percent": round((complete_count / len(checks)) * 100) if checks else 0,
        "source_fingerprint": captured["source_fingerprint"],
        "issued_preparation_revision_id": str(latest.id) if issued else None,
        "issued_preparation_revision_no": latest.revision_no if issued else None,
    }

@router.get("/audits/{audit_id}/work-package")
def get_audit_work_package(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    row = (
        db.query(QualityAuditWorkPackage)
        .filter(
            QualityAuditWorkPackage.amo_id == ctx.amo_id,
            QualityAuditWorkPackage.audit_id == audit_id,
        )
        .order_by(QualityAuditWorkPackage.revision_no.desc())
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "AUDIT_WORK_PACKAGE_NOT_ISSUED",
                "message": "Issue the governed preparation revision before preparing this audit for offline fieldwork.",
            },
        )
    return _work_package_dict(row)


@router.get("/audits/{audit_id}/offline-pack")
def get_audit_offline_pack(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    package = (
        db.query(QualityAuditWorkPackage)
        .filter(
            QualityAuditWorkPackage.amo_id == ctx.amo_id,
            QualityAuditWorkPackage.audit_id == audit_id,
        )
        .order_by(QualityAuditWorkPackage.revision_no.desc())
        .first()
    )
    if package is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "AUDIT_WORK_PACKAGE_NOT_ISSUED",
                "message": "Issue the governed preparation revision before making this audit available offline.",
            },
        )

    execution = (
        db.query(QualityAuditChecklistExecutionGovernance)
        .filter(
            QualityAuditChecklistExecutionGovernance.amo_id == ctx.amo_id,
            QualityAuditChecklistExecutionGovernance.audit_id == audit_id,
        )
        .order_by(QualityAuditChecklistExecutionGovernance.created_at.asc())
        .all()
    )
    findings = (
        db.query(models.QMSAuditFinding)
        .filter(
            models.QMSAuditFinding.amo_id == ctx.amo_id,
            models.QMSAuditFinding.audit_id == audit_id,
        )
        .order_by(models.QMSAuditFinding.created_at.asc())
        .all()
    )
    evidence = (
        db.query(QualityAuditEvidenceArtifact)
        .filter(
            QualityAuditEvidenceArtifact.amo_id == ctx.amo_id,
            QualityAuditEvidenceArtifact.audit_id == audit_id,
        )
        .order_by(QualityAuditEvidenceArtifact.created_at.asc())
        .all()
    )
    from .audit_checklist_execution_router import _fieldwork_write_blocker
    fieldwork_blocker = _fieldwork_write_blocker(db, amo_id=ctx.amo_id, audit=audit)
    return {
        "schema": "QMS_AUDIT_OFFLINE_PACK_V1",
        "generated_at": _utcnow().isoformat(),
        "audit_id": str(audit.id),
        "fieldwork_state": {
            "authorized": fieldwork_blocker is None,
            "blocker": fieldwork_blocker,
            "audit_status": _enum_value(audit.status),
            "actual_start": audit.actual_start.isoformat() if audit.actual_start else None,
            "actual_end": audit.actual_end.isoformat() if audit.actual_end else None,
            "captured_at": _utcnow().isoformat(),
        },
        "work_package": _work_package_dict(package),
        "execution": [
            {
                "checklist_item_id": str(item.checklist_item_id),
                "canonical_response_status": item.canonical_response_status,
                "response_value": getattr(item, "response_value", None),
                "auditor_notes": item.auditor_notes,
                "evidence_references": item.evidence_references or [],
                "entity_version": item.entity_version,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            }
            for item in execution
        ],
        "findings": [
            {
                "id": str(item.id),
                "finding_ref": item.finding_ref,
                "finding_type": item.finding_type,
                "severity": item.severity,
                "level": item.level,
                "requirement_ref": item.requirement_ref,
                "description": item.description,
                "objective_evidence": item.objective_evidence,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "closed_at": item.closed_at.isoformat() if item.closed_at else None,
            }
            for item in findings
        ],
        "evidence": [
            {
                "id": str(item.id),
                "checklist_item_id": str(item.checklist_item_id) if item.checklist_item_id else None,
                "finding_id": str(item.finding_id) if item.finding_id else None,
                "filename": item.filename,
                "content_type": item.content_type,
                "size_bytes": item.size_bytes,
                "sha256": item.sha256,
                "description": item.description,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in evidence
        ],
        "sync_contract": {
            "server_authoritative": True,
            "conflict_strategy": "BASE_VERSION",
            "idempotency": "CLIENT_MUTATION_ID",
            "binary_evidence_state": "SEPARATE_DURABLE_QUEUE",
        },
    }