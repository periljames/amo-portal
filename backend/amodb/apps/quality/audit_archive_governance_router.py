from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session, selectinload

from amodb.database import get_read_db, get_write_db

from . import models
from .audit_archive_governance_models import (
    QualityAuditArchiveManifest,
    QualityAuditArchiveManifestItem,
    QualityAuditDispositionEvent,
    QualityAuditLegalHoldEvent,
    QualityAuditRetentionPolicyRevision,
)
from .audit_checklist_execution_models import QualityAuditChecklistExecutionGovernance
from .audit_closing_assurance_models import QualityAuditAssuranceArtifact, QualityAuditSignatureEvidence
from .audit_closure_models import QualityAuditClosureState
from .audit_report_governance_models import QualityAuditReportRevision
from .tenant_security import TenantContext, assert_quality_permission, require_quality_permission, set_postgres_tenant_context, write_tenant_context


router = APIRouter(tags=["Quality audit archive governance"])
RetentionStart = Literal["EXECUTION_CLOSED", "FOLLOW_UP_COMPLETE"]
DispositionMode = Literal["PRESERVE_METADATA_DELETE_PACKAGE", "TRANSFER_PACKAGE", "NO_DISPOSITION"]


class RetentionPolicyCreate(BaseModel):
    retention_class: str = Field(min_length=2, max_length=96)
    retention_start_event: RetentionStart
    duration_days: int | None = Field(default=None, gt=0)
    indefinite: bool = False
    governing_basis: str = Field(min_length=8, max_length=12000)
    review_before_disposition: bool = True
    legal_hold_supported: bool = True
    disposition_mode: DispositionMode
    approving_capability: str = Field(default="qms.audit.manage", min_length=3, max_length=128)

    @model_validator(mode="after")
    def validate_duration(self):
        if self.indefinite and self.duration_days is not None:
            raise ValueError("Indefinite retention must not also define duration_days.")
        if not self.indefinite and self.duration_days is None:
            raise ValueError("Finite retention requires duration_days.")
        if self.indefinite and self.disposition_mode != "NO_DISPOSITION":
            raise ValueError("Indefinite retention must use NO_DISPOSITION.")
        return self


class HoldAction(BaseModel):
    reason: str = Field(min_length=8, max_length=12000)
    governing_basis: str = Field(min_length=8, max_length=12000)
    manifest_id: str | None = Field(default=None, max_length=36)


class DispositionReview(BaseModel):
    approved: bool
    reason: str = Field(min_length=8, max_length=12000)


class DispositionExecute(BaseModel):
    reason: str = Field(min_length=8, max_length=12000)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(jsonable_encoder(value), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _audit(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> models.QMSAudit:
    row = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == amo_id,
        models.QMSAudit.id == audit_id,
        models.QMSAudit.deleted_at.is_(None),
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit not found.")
    return row


def _latest_policy(db: Session, amo_id: str) -> QualityAuditRetentionPolicyRevision | None:
    return db.query(QualityAuditRetentionPolicyRevision).filter(
        QualityAuditRetentionPolicyRevision.amo_id == amo_id,
    ).order_by(QualityAuditRetentionPolicyRevision.revision_no.desc()).first()


def _policy_dict(row: QualityAuditRetentionPolicyRevision | None) -> dict[str, Any]:
    if row is None:
        return {"configured": False, "current": None}
    return {
        "configured": True,
        "current": {
            "id": row.id,
            "revision_no": row.revision_no,
            "retention_class": row.retention_class,
            "record_type": row.record_type,
            "retention_start_event": row.retention_start_event,
            "duration_days": row.duration_days,
            "indefinite": bool(row.indefinite),
            "governing_basis": row.governing_basis,
            "review_before_disposition": bool(row.review_before_disposition),
            "legal_hold_supported": bool(row.legal_hold_supported),
            "disposition_mode": row.disposition_mode,
            "approving_capability": row.approving_capability,
            "created_by_user_id": row.created_by_user_id,
            "created_at": row.created_at,
        },
    }


def _item_dict(row: QualityAuditArchiveManifestItem) -> dict[str, Any]:
    return {
        "id": row.id,
        "item_type": row.item_type,
        "authoritative_record_id": row.authoritative_record_id,
        "revision_ref": row.revision_ref,
        "source_system": row.source_system,
        "content_hash": row.content_hash,
        "retention_role": row.retention_role,
        "metadata": row.metadata_json or {},
    }


def _manifest_dict(row: QualityAuditArchiveManifest) -> dict[str, Any]:
    return {
        "id": row.id,
        "audit_id": str(row.audit_id),
        "manifest_version": row.manifest_version,
        "retention_policy_revision_id": row.retention_policy_revision_id,
        "retention_class": row.retention_class,
        "retention_start_at": row.retention_start_at,
        "retention_due_at": row.retention_due_at,
        "manifest_sha256": row.manifest_sha256,
        "item_count": row.item_count,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at,
        "items": [_item_dict(item) for item in list(row.items or [])],
    }


def _latest_manifest(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> QualityAuditArchiveManifest | None:
    return db.query(QualityAuditArchiveManifest).options(selectinload(QualityAuditArchiveManifest.items)).filter(
        QualityAuditArchiveManifest.amo_id == amo_id,
        QualityAuditArchiveManifest.audit_id == audit_id,
    ).order_by(QualityAuditArchiveManifest.manifest_version.desc()).first()


def _retention_start(closure: QualityAuditClosureState, policy: QualityAuditRetentionPolicyRevision) -> datetime:
    if policy.retention_start_event == "EXECUTION_CLOSED":
        if closure.execution_status != "CLOSED" or closure.execution_closed_at is None:
            raise HTTPException(status_code=409, detail="Retention policy starts at execution closure, but audit execution is not closed.")
        return closure.execution_closed_at
    if closure.follow_up_status != "COMPLETE" or closure.follow_up_completed_at is None:
        raise HTTPException(status_code=409, detail="Retention policy starts at follow-up completion, but assurance follow-up is not complete.")
    return closure.follow_up_completed_at


def _record_item(
    *,
    item_type: str,
    record_id: str,
    source_system: str,
    retention_role: str,
    revision_ref: str | None = None,
    content_hash: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "item_type": item_type,
        "authoritative_record_id": record_id,
        "revision_ref": revision_ref,
        "source_system": source_system,
        "content_hash": content_hash,
        "retention_role": retention_role,
        "metadata": metadata or {},
    }


def _build_inventory(db: Session, *, amo_id: str, audit: models.QMSAudit) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    audit_snapshot = {
        "audit_ref": audit.audit_ref,
        "title": audit.title,
        "scope": audit.scope,
        "criteria": audit.criteria,
        "planned_start": audit.planned_start,
        "planned_end": audit.planned_end,
        "actual_start": audit.actual_start,
        "actual_end": audit.actual_end,
        "status": str(getattr(audit.status, "value", audit.status)),
    }
    items.append(_record_item(
        item_type="AUDIT",
        record_id=str(audit.id),
        source_system="QUALITY",
        retention_role="AUDIT_IDENTITY_SCOPE_CRITERIA",
        content_hash=_canonical_hash(audit_snapshot),
        metadata=audit_snapshot,
    ))

    reports = db.query(QualityAuditReportRevision).filter(
        QualityAuditReportRevision.amo_id == amo_id,
        QualityAuditReportRevision.audit_id == audit.id,
    ).order_by(QualityAuditReportRevision.revision_no.asc()).all()
    for report in reports:
        items.append(_record_item(
            item_type="REPORT_REVISION",
            record_id=report.id,
            revision_ref=str(report.revision_no),
            source_system="QUALITY_REPORT_GOVERNANCE",
            retention_role="AUDIT_REPORT_HISTORY",
            content_hash=report.sha256,
            metadata={"status": report.status, "filename": report.filename},
        ))

    signatures = db.query(QualityAuditSignatureEvidence).filter(
        QualityAuditSignatureEvidence.amo_id == amo_id,
        QualityAuditSignatureEvidence.audit_id == audit.id,
    ).all()
    for signature in signatures:
        items.append(_record_item(
            item_type="SIGNATURE_EVIDENCE",
            record_id=signature.id,
            revision_ref=signature.report_revision_id,
            source_system="QUALITY_CLOSING_ASSURANCE",
            retention_role="REPORT_APPROVAL_EVIDENCE",
            content_hash=signature.signature_digest,
            metadata={"artifact_sha256": signature.artifact_sha256, "method": signature.method, "purpose": signature.purpose},
        ))

    artifacts = db.query(QualityAuditAssuranceArtifact).filter(
        QualityAuditAssuranceArtifact.amo_id == amo_id,
        QualityAuditAssuranceArtifact.audit_id == audit.id,
    ).all()
    for artifact in artifacts:
        items.append(_record_item(
            item_type="ASSURANCE_ARTIFACT",
            record_id=artifact.id,
            revision_ref=artifact.output_policy_revision_id,
            source_system="QUALITY_CLOSING_ASSURANCE",
            retention_role="POLICY_DRIVEN_CLOSING_OUTPUT",
            content_hash=artifact.sha256,
            metadata={"artifact_type": artifact.artifact_type, "filename": artifact.filename},
        ))

    checklist_rows = db.query(QualityAuditChecklistExecutionGovernance).filter(
        QualityAuditChecklistExecutionGovernance.amo_id == amo_id,
        QualityAuditChecklistExecutionGovernance.audit_id == audit.id,
    ).all()
    for row in checklist_rows:
        snapshot = {
            "canonical_response_status": row.canonical_response_status,
            "auditor_notes": row.auditor_notes,
            "evidence_references": row.evidence_references or [],
            "entity_version": row.entity_version,
        }
        items.append(_record_item(
            item_type="CHECKLIST_EXECUTION",
            record_id=str(row.checklist_item_id),
            revision_ref=str(row.entity_version),
            source_system="QUALITY_CHECKLIST_EXECUTION",
            retention_role="FIELDWORK_DECISION",
            content_hash=_canonical_hash(snapshot),
        ))

    findings = db.query(models.QMSAuditFinding).filter(
        models.QMSAuditFinding.amo_id == amo_id,
        models.QMSAuditFinding.audit_id == audit.id,
    ).all()
    for finding in findings:
        items.append(_record_item(
            item_type="FINDING",
            record_id=str(finding.id),
            revision_ref=finding.finding_ref,
            source_system="QUALITY",
            retention_role="AUDIT_FINDING",
            content_hash=_canonical_hash({
                "finding_ref": finding.finding_ref,
                "finding_type": str(getattr(finding.finding_type, "value", finding.finding_type)),
                "severity": str(getattr(finding.severity, "value", finding.severity)),
                "level": str(getattr(finding.level, "value", finding.level)),
                "requirement_ref": finding.requirement_ref,
                "description": finding.description,
                "objective_evidence": finding.objective_evidence,
            }),
        ))

    finding_ids = [finding.id for finding in findings]
    cars = db.query(models.CorrectiveActionRequest).filter(
        models.CorrectiveActionRequest.amo_id == amo_id,
        models.CorrectiveActionRequest.finding_id.in_(finding_ids),
    ).all() if finding_ids else []
    for car in cars:
        items.append(_record_item(
            item_type="CAR",
            record_id=str(car.id),
            revision_ref=car.car_number,
            source_system="QUALITY_CAR",
            retention_role="CORRECTIVE_ACTION_FOLLOW_UP",
            content_hash=_canonical_hash({
                "car_number": car.car_number,
                "status": str(getattr(car.status, "value", car.status)),
                "due_date": car.due_date,
                "root_cause_status": car.root_cause_status,
                "capa_status": car.capa_status,
                "evidence_verified_at": car.evidence_verified_at,
            }),
        ))

    document_requests = db.query(models.QualityAuditDocumentRequest).filter(
        models.QualityAuditDocumentRequest.amo_id == amo_id,
        models.QualityAuditDocumentRequest.audit_id == audit.id,
    ).all()
    for request in document_requests:
        items.append(_record_item(
            item_type="PREPARATION_DOCUMENT_REQUEST",
            record_id=str(request.id),
            source_system="QUALITY_PREPARATION",
            retention_role="PRE_AUDIT_DOCUMENTATION",
            content_hash=_canonical_hash({
                "title": request.title,
                "status": request.status,
                "file_ref": request.file_ref,
                "review_note": request.review_note,
            }),
        ))

    return items


def _hold_state(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> dict[str, QualityAuditLegalHoldEvent]:
    events = db.query(QualityAuditLegalHoldEvent).filter(
        QualityAuditLegalHoldEvent.amo_id == amo_id,
        QualityAuditLegalHoldEvent.audit_id == audit_id,
    ).order_by(QualityAuditLegalHoldEvent.created_at.asc()).all()
    latest: dict[str, QualityAuditLegalHoldEvent] = {}
    for event in events:
        latest[event.hold_key] = event
    return latest


def _active_holds(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> list[QualityAuditLegalHoldEvent]:
    return [event for event in _hold_state(db, amo_id=amo_id, audit_id=audit_id).values() if event.event_type == "PLACED"]


def _inventory_hash(manifest: QualityAuditArchiveManifest) -> str:
    inventory = sorted(
        [
            {
                "item_type": item.item_type,
                "authoritative_record_id": item.authoritative_record_id,
                "revision_ref": item.revision_ref,
                "content_hash": item.content_hash,
            }
            for item in list(manifest.items or [])
        ],
        key=lambda item: (item["item_type"], item["authoritative_record_id"], item["revision_ref"] or ""),
    )
    return _canonical_hash(inventory)


@router.get("/audit-retention-policy")
def get_retention_policy(
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _policy_dict(_latest_policy(db, ctx.amo_id))


@router.post("/audit-retention-policy/revisions", status_code=status.HTTP_201_CREATED)
def create_retention_policy(
    payload: RetentionPolicyCreate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    latest = db.query(QualityAuditRetentionPolicyRevision).filter(
        QualityAuditRetentionPolicyRevision.amo_id == ctx.amo_id,
    ).order_by(QualityAuditRetentionPolicyRevision.revision_no.desc()).with_for_update().first()
    row = QualityAuditRetentionPolicyRevision(
        amo_id=ctx.amo_id,
        revision_no=(latest.revision_no + 1) if latest else 1,
        retention_class=payload.retention_class.strip(),
        record_type="AUDIT_PACKAGE",
        retention_start_event=payload.retention_start_event,
        duration_days=payload.duration_days,
        indefinite=payload.indefinite,
        governing_basis=payload.governing_basis.strip(),
        review_before_disposition=payload.review_before_disposition,
        legal_hold_supported=payload.legal_hold_supported,
        disposition_mode=payload.disposition_mode,
        approving_capability=payload.approving_capability.strip(),
        created_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _policy_dict(row)["current"]


@router.post("/audits/{audit_id}/legal-holds/{hold_key}/place", status_code=status.HTTP_201_CREATED)
def place_legal_hold(
    audit_id: uuid.UUID,
    hold_key: str,
    payload: HoldAction,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    policy = _latest_policy(db, ctx.amo_id)
    if policy is None or not policy.legal_hold_supported:
        raise HTTPException(status_code=409, detail="Current retention policy does not enable legal-hold governance.")
    normalized_key = hold_key.strip()[:128]
    if not normalized_key:
        raise HTTPException(status_code=422, detail="Legal hold key is required.")
    latest = _hold_state(db, amo_id=ctx.amo_id, audit_id=audit_id).get(normalized_key)
    if latest is not None and latest.event_type == "PLACED":
        raise HTTPException(status_code=409, detail="This legal hold is already active.")
    row = QualityAuditLegalHoldEvent(
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        manifest_id=payload.manifest_id,
        hold_key=normalized_key,
        event_type="PLACED",
        reason=payload.reason.strip(),
        governing_basis=payload.governing_basis.strip(),
        actor_user_id=ctx.user_id,
    )
    db.add(row)
    db.commit()
    return {"hold_key": row.hold_key, "event_type": row.event_type, "created_at": row.created_at}


@router.post("/audits/{audit_id}/legal-holds/{hold_key}/release")
def release_legal_hold(
    audit_id: uuid.UUID,
    hold_key: str,
    payload: HoldAction,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    normalized_key = hold_key.strip()[:128]
    latest = _hold_state(db, amo_id=ctx.amo_id, audit_id=audit_id).get(normalized_key)
    if latest is None or latest.event_type != "PLACED":
        raise HTTPException(status_code=409, detail="This legal hold is not active.")
    row = QualityAuditLegalHoldEvent(
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        manifest_id=payload.manifest_id or latest.manifest_id,
        hold_key=normalized_key,
        event_type="RELEASED",
        reason=payload.reason.strip(),
        governing_basis=payload.governing_basis.strip(),
        actor_user_id=ctx.user_id,
    )
    db.add(row)
    db.commit()
    return {"hold_key": row.hold_key, "event_type": row.event_type, "created_at": row.created_at}


@router.post("/audits/{audit_id}/archive-manifests/{manifest_id}/disposition-review")
def review_disposition(
    audit_id: uuid.UUID,
    manifest_id: str,
    payload: DispositionReview,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    policy = _latest_policy(db, ctx.amo_id)
    if policy is None:
        raise HTTPException(status_code=409, detail="Audit retention policy is not configured.")
    assert_quality_permission(db, ctx, policy.approving_capability)
    manifest = db.query(QualityAuditArchiveManifest).options(selectinload(QualityAuditArchiveManifest.items)).filter(
        QualityAuditArchiveManifest.amo_id == ctx.amo_id,
        QualityAuditArchiveManifest.audit_id == audit_id,
        QualityAuditArchiveManifest.id == manifest_id,
    ).first()
    if manifest is None:
        raise HTTPException(status_code=404, detail="Archive manifest not found.")
    row = QualityAuditDispositionEvent(
        amo_id=ctx.amo_id,
        audit_id=audit_id,
        manifest_id=manifest.id,
        event_type="APPROVED" if payload.approved else "REJECTED",
        disposition_mode=policy.disposition_mode,
        inventory_sha256=_inventory_hash(manifest),
        reason=payload.reason.strip(),
        actor_user_id=ctx.user_id,
    )
    db.add(row)
    db.commit()
    return {"event_type": row.event_type, "inventory_sha256": row.inventory_sha256, "created_at": row.created_at}
