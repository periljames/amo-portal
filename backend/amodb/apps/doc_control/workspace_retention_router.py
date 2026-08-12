from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import evidence_models as em
from . import retention_models as rm
from .workspace_decision_policy import require_decision_approver
from .workspace_evidence_router import validate_evidence_references
from .workspace_service import (
    audit,
    get_manual,
    get_revision,
    require_control_user,
    resolve_tenant,
    utcnow,
)


router = APIRouter(prefix="/workspace", tags=["Document Control Retention"])


class RetentionCreate(BaseModel):
    manual_id: str
    source_type: Literal["DOCUMENT", "REVISION", "EVIDENCE_ASSET", "GENERATED_RECORD"] = "DOCUMENT"
    source_id: str | None = None
    retention_class: str = Field(default="STANDARD", min_length=1, max_length=64)
    retention_until: datetime | None = None
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_source_id_for_scoped_sources(self) -> "RetentionCreate":
        if self.source_type != "DOCUMENT" and not str(self.source_id or "").strip():
            raise ValueError(f"{self.source_type} retention requires a governed source record")
        return self


class RetentionHoldUpdate(BaseModel):
    legal_hold: bool
    reason: str | None = Field(default=None, max_length=4000)


class RetentionRequest(BaseModel):
    justification: str = Field(min_length=3, max_length=8000)


class RetentionDecision(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    justification: str = Field(min_length=3, max_length=8000)


class RetentionDispose(BaseModel):
    disposition_method: str = Field(min_length=2, max_length=64)
    certificate_evidence_asset_id: str
    notes: str | None = Field(default=None, max_length=8000)


def _payload(row: rm.DocumentRetentionDisposition) -> dict:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "manual_id": row.manual_id,
        "revision_id": row.revision_id,
        "source_type": row.source_type,
        "source_id": row.source_id,
        "source_label": row.source_label,
        "retention_class": row.retention_class,
        "retention_until": row.retention_until.isoformat() if row.retention_until else None,
        "status": row.status,
        "legal_hold": bool(row.legal_hold),
        "hold_reason": row.hold_reason,
        "justification": row.justification,
        "disposition_method": row.disposition_method,
        "certificate_evidence_asset_id": row.certificate_evidence_asset_id,
        "created_by_user_id": row.created_by_user_id,
        "requested_by_user_id": row.requested_by_user_id,
        "approved_by_user_id": row.approved_by_user_id,
        "disposed_by_user_id": row.disposed_by_user_id,
        "requested_at": row.requested_at.isoformat() if row.requested_at else None,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "disposed_at": row.disposed_at.isoformat() if row.disposed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "metadata": dict(row.metadata_json or {}),
    }


def _row(db: Session, *, tenant_id: str, retention_id: str) -> rm.DocumentRetentionDisposition:
    row = (
        db.query(rm.DocumentRetentionDisposition)
        .filter(
            rm.DocumentRetentionDisposition.tenant_id == tenant_id,
            rm.DocumentRetentionDisposition.id == retention_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Retention record not found")
    return row


def _due_status(retention_until: datetime | None) -> str:
    if not retention_until:
        return "ACTIVE"
    value = retention_until
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return "DUE" if value <= datetime.now(timezone.utc) else "ACTIVE"


def _resolve_source(db: Session, *, tenant, manual, payload: RetentionCreate) -> tuple[str, str, str | None]:
    if payload.source_type == "DOCUMENT":
        return manual.id, f"{manual.code} — {manual.title}", None
    if payload.source_type == "REVISION":
        revision = get_revision(db, manual, str(payload.source_id))
        return revision.id, f"{manual.code} revision {revision.revision_number}", revision.id
    if payload.source_type == "EVIDENCE_ASSET":
        asset = (
            db.query(em.DocumentEvidenceAsset)
            .filter(
                em.DocumentEvidenceAsset.tenant_id == tenant.amo_id,
                em.DocumentEvidenceAsset.manual_id == manual.id,
                em.DocumentEvidenceAsset.id == str(payload.source_id),
            )
            .first()
        )
        if not asset:
            raise HTTPException(status_code=404, detail="Controlled evidence asset not found for this document")
        return asset.id, asset.filename, asset.revision_id

    generated_model = getattr(dm, "DocumentGeneratedRecord", None)
    if generated_model is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "GENERATED_RECORD_RETENTION_SOURCE_UNAVAILABLE",
                "message": "This deployment does not expose the canonical generated-record model to Document Control retention.",
            },
        )
    record = (
        db.query(generated_model)
        .filter(
            generated_model.tenant_id == tenant.amo_id,
            generated_model.manual_id == manual.id,
            generated_model.id == str(payload.source_id),
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Generated controlled record not found for this document")
    label = (
        getattr(record, "title", None)
        or getattr(record, "record_type", None)
        or getattr(record, "reference", None)
        or f"Generated record {record.id}"
    )
    return str(record.id), str(label), getattr(record, "revision_id", None)


@router.get("/t/{tenant_slug}/documents/{manual_id}/retention")
def list_retention(
    tenant_slug: str,
    manual_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    get_manual(db, tenant, manual_id)
    rows = (
        db.query(rm.DocumentRetentionDisposition)
        .filter(
            rm.DocumentRetentionDisposition.tenant_id == tenant.amo_id,
            rm.DocumentRetentionDisposition.manual_id == manual_id,
        )
        .order_by(rm.DocumentRetentionDisposition.created_at.desc(), rm.DocumentRetentionDisposition.id.desc())
        .limit(500)
        .all()
    )
    return {"items": [_payload(row) for row in rows], "total": len(rows), "bounded": True, "limit": 500}


@router.post("/t/{tenant_slug}/retention")
def create_retention(
    tenant_slug: str,
    payload: RetentionCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, payload.manual_id)
    source_id, source_label, revision_id = _resolve_source(db, tenant=tenant, manual=manual, payload=payload)
    existing = (
        db.query(rm.DocumentRetentionDisposition)
        .filter(
            rm.DocumentRetentionDisposition.tenant_id == tenant.amo_id,
            rm.DocumentRetentionDisposition.manual_id == manual.id,
            rm.DocumentRetentionDisposition.source_type == payload.source_type,
            rm.DocumentRetentionDisposition.source_id == source_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RETENTION_SOURCE_ALREADY_GOVERNED",
                "message": "This controlled source already has a retention/disposition record.",
                "retention_id": existing.id,
            },
        )
    row = rm.DocumentRetentionDisposition(
        tenant_id=tenant.amo_id,
        manual_id=manual.id,
        revision_id=revision_id,
        source_type=payload.source_type,
        source_id=source_id,
        source_label=source_label,
        retention_class=payload.retention_class.strip().upper(),
        retention_until=payload.retention_until,
        status=_due_status(payload.retention_until),
        metadata_json=dict(payload.metadata or {}),
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.flush()
    audit(db, tenant, request, "document.retention.created", "document_retention_disposition", row.id, _payload(row))
    db.commit()
    return _payload(row)


@router.patch("/t/{tenant_slug}/retention/{retention_id}/hold")
def update_retention_hold(
    tenant_slug: str,
    retention_id: str,
    payload: RetentionHoldUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_decision_approver(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = _row(db, tenant_id=tenant.amo_id, retention_id=retention_id)
    if row.status == "DISPOSED":
        raise HTTPException(status_code=409, detail="Disposed retention evidence is immutable")
    reason = str(payload.reason or "").strip()
    if payload.legal_hold and not reason:
        raise HTTPException(status_code=422, detail="Legal hold requires a reason")
    before = _payload(row)
    row.legal_hold = payload.legal_hold
    row.hold_reason = reason or None
    if payload.legal_hold:
        row.status = "HOLD"
        row.approved_by_user_id = None
        row.approved_at = None
    elif row.status == "HOLD":
        row.status = _due_status(row.retention_until)
    row.updated_at = utcnow()
    after = _payload(row)
    audit(db, tenant, request, "document.retention.hold_updated", "document_retention_disposition", row.id, {"before": before, "after": after})
    db.commit()
    return after


@router.post("/t/{tenant_slug}/retention/{retention_id}/request-disposition")
def request_disposition(
    tenant_slug: str,
    retention_id: str,
    payload: RetentionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = _row(db, tenant_id=tenant.amo_id, retention_id=retention_id)
    if row.legal_hold or row.status == "HOLD":
        raise HTTPException(status_code=409, detail="Disposition is blocked by legal hold")
    if row.status not in {"ACTIVE", "DUE", "REJECTED"}:
        raise HTTPException(status_code=409, detail=f"Disposition cannot be requested from {row.status}")
    now = utcnow()
    early = False
    if row.retention_until:
        due = row.retention_until
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        early = due > datetime.now(timezone.utc)
    row.status = "DISPOSITION_REQUESTED"
    row.justification = payload.justification.strip()
    row.requested_by_user_id = current_user.id
    row.requested_at = now
    row.approved_by_user_id = None
    row.approved_at = None
    row.metadata_json = {**dict(row.metadata_json or {}), "early_disposition_requested": early}
    row.updated_at = now
    audit(db, tenant, request, "document.retention.disposition_requested", "document_retention_disposition", row.id, _payload(row))
    db.commit()
    return _payload(row)


@router.post("/t/{tenant_slug}/retention/{retention_id}/decision")
def decide_disposition(
    tenant_slug: str,
    retention_id: str,
    payload: RetentionDecision,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_decision_approver(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = _row(db, tenant_id=tenant.amo_id, retention_id=retention_id)
    if row.status != "DISPOSITION_REQUESTED":
        raise HTTPException(status_code=409, detail="Only a requested disposition can be approved or rejected")
    if row.legal_hold:
        raise HTTPException(status_code=409, detail="Disposition approval is blocked by legal hold")
    if row.requested_by_user_id and str(row.requested_by_user_id) == str(current_user.id):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RETENTION_SEPARATION_OF_DUTIES_REQUIRED",
                "message": "The user who requested disposition cannot approve that disposition.",
            },
        )
    now = utcnow()
    row.justification = payload.justification.strip()
    if payload.decision == "APPROVE":
        row.status = "APPROVED"
        row.approved_by_user_id = current_user.id
        row.approved_at = now
    else:
        row.status = "REJECTED"
        row.approved_by_user_id = None
        row.approved_at = None
    row.updated_at = now
    audit(db, tenant, request, f"document.retention.{payload.decision.lower()}", "document_retention_disposition", row.id, _payload(row))
    db.commit()
    return _payload(row)


@router.post("/t/{tenant_slug}/retention/{retention_id}/dispose")
def record_disposition(
    tenant_slug: str,
    retention_id: str,
    payload: RetentionDispose,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = _row(db, tenant_id=tenant.amo_id, retention_id=retention_id)
    if row.status != "APPROVED":
        raise HTTPException(status_code=409, detail="Disposition must be independently approved before it can be recorded")
    if row.legal_hold:
        raise HTTPException(status_code=409, detail="Disposition is blocked by legal hold")
    evidence = validate_evidence_references(
        db,
        tenant_id=tenant.amo_id,
        manual_id=row.manual_id,
        evidence=[{"asset_id": payload.certificate_evidence_asset_id}],
    )
    if not evidence:
        raise HTTPException(status_code=422, detail="Disposition certificate evidence is required")
    now = utcnow()
    row.status = "DISPOSED"
    row.disposition_method = payload.disposition_method.strip().upper().replace(" ", "_")
    row.certificate_evidence_asset_id = evidence[0]["asset_id"]
    row.disposed_by_user_id = current_user.id
    row.disposed_at = now
    row.metadata_json = {**dict(row.metadata_json or {}), "disposition_notes": str(payload.notes or "").strip() or None}
    row.updated_at = now
    audit(
        db,
        tenant,
        request,
        "document.retention.disposed",
        "document_retention_disposition",
        row.id,
        {
            **_payload(row),
            "controlled_history_deleted": False,
            "certificate_evidence": evidence[0],
        },
    )
    db.commit()
    return _payload(row)
