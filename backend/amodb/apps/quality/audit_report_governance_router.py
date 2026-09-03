from __future__ import annotations

import hashlib
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from amodb.database import get_read_db, get_write_db

from . import models
from .audit_report_governance_models import QualityAuditReportEvent, QualityAuditReportRevision
from .router import AUDIT_REPORT_DIR
from .tenant_security import TenantContext, assert_quality_permission, require_quality_permission, set_postgres_tenant_context, write_tenant_context


router = APIRouter(tags=["Quality audit report governance"])


class ReportAdoptCurrent(BaseModel):
    reason: str = Field(min_length=8, max_length=4000)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _audit(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> models.QMSAudit:
    row = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == amo_id,
        models.QMSAudit.id == audit_id,
        models.QMSAudit.deleted_at.is_(None),
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit not found.")
    return row


def _safe_report_path(file_ref: str | None) -> Path:
    if not file_ref:
        raise HTTPException(status_code=409, detail="Upload the audit report file before creating a governed report revision.")
    root = AUDIT_REPORT_DIR.resolve()
    candidate = Path(file_ref).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="The current audit report file is outside controlled Quality report storage.") from exc
    if not candidate.is_file():
        raise HTTPException(status_code=409, detail="The current audit report file is missing from controlled storage.")
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _audit_snapshot(db: Session, audit: models.QMSAudit) -> dict[str, Any]:
    findings = db.query(models.QMSAuditFinding).filter(
        models.QMSAuditFinding.amo_id == audit.amo_id,
        models.QMSAuditFinding.audit_id == audit.id,
    ).all()
    return {
        "audit_id": str(audit.id),
        "audit_ref": audit.audit_ref,
        "title": audit.title,
        "status": str(getattr(audit.status, "value", audit.status)),
        "scope": audit.scope,
        "criteria": audit.criteria,
        "planned_start": audit.planned_start.isoformat() if audit.planned_start else None,
        "planned_end": audit.planned_end.isoformat() if audit.planned_end else None,
        "actual_start": audit.actual_start.isoformat() if audit.actual_start else None,
        "actual_end": audit.actual_end.isoformat() if audit.actual_end else None,
        "finding_count": len(findings),
        "open_finding_count": sum(1 for item in findings if not item.closed_at),
        "captured_at": _utcnow().isoformat(),
    }


def _event_dict(row: QualityAuditReportEvent) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "event_type": row.event_type,
        "reason": row.reason,
        "before_snapshot": row.before_snapshot,
        "after_snapshot": row.after_snapshot,
        "actor_user_id": row.actor_user_id,
        "created_at": row.created_at,
    }


def _revision_dict(row: QualityAuditReportRevision) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "audit_id": str(row.audit_id),
        "revision_no": row.revision_no,
        "status": row.status,
        "filename": row.filename,
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
        "sha256": row.sha256,
        "report_snapshot": row.report_snapshot or {},
        "change_reason": row.change_reason,
        "supersedes_revision_id": row.supersedes_revision_id,
        "reviewed_by_user_id": row.reviewed_by_user_id,
        "reviewed_at": row.reviewed_at,
        "approved_by_user_id": row.approved_by_user_id,
        "approved_at": row.approved_at,
        "issued_by_user_id": row.issued_by_user_id,
        "issued_at": row.issued_at,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "events": [_event_dict(item) for item in list(row.events or [])],
    }


def _state_snapshot(row: QualityAuditReportRevision) -> dict[str, Any]:
    return {
        "revision_no": row.revision_no,
        "status": row.status,
        "sha256": row.sha256,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "issued_at": row.issued_at.isoformat() if row.issued_at else None,
    }


def _add_event(
    db: Session,
    *,
    ctx: TenantContext,
    row: QualityAuditReportRevision,
    event_type: str,
    reason: str,
    before: dict[str, Any] | None = None,
) -> None:
    db.add(QualityAuditReportEvent(
        amo_id=ctx.amo_id,
        audit_id=row.audit_id,
        revision_id=row.id,
        event_type=event_type,
        reason=reason.strip(),
        before_snapshot=before,
        after_snapshot=_state_snapshot(row),
        actor_user_id=ctx.user_id,
    ))


@router.get("/audits/{audit_id}/report-revisions")
def list_report_revisions(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    rows = db.query(QualityAuditReportRevision).options(selectinload(QualityAuditReportRevision.events)).filter(
        QualityAuditReportRevision.amo_id == ctx.amo_id,
        QualityAuditReportRevision.audit_id == audit_id,
    ).order_by(QualityAuditReportRevision.revision_no.desc()).limit(100).all()
    return {"items": [_revision_dict(row) for row in rows]}


@router.post("/audits/{audit_id}/report-revisions/adopt-current", status_code=status.HTTP_201_CREATED)
def adopt_current_report(
    audit_id: uuid.UUID,
    payload: ReportAdoptCurrent,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    path = _safe_report_path(audit.report_file_ref)
    digest = _sha256(path)

    latest = db.query(QualityAuditReportRevision).filter(
        QualityAuditReportRevision.amo_id == ctx.amo_id,
        QualityAuditReportRevision.audit_id == audit_id,
    ).order_by(QualityAuditReportRevision.revision_no.desc()).with_for_update().first()
    if latest is not None and latest.status in {"DRAFT", "INTERNAL_REVIEW", "APPROVED"}:
        raise HTTPException(status_code=409, detail="A governed report revision is already in progress. Complete or cancel it before adopting another upload.")
    duplicate = db.query(QualityAuditReportRevision.id).filter(
        QualityAuditReportRevision.amo_id == ctx.amo_id,
        QualityAuditReportRevision.audit_id == audit_id,
        QualityAuditReportRevision.sha256 == digest,
    ).first()
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="This exact report file is already retained in the governed report history.")

    prior_issued = db.query(QualityAuditReportRevision).filter(
        QualityAuditReportRevision.amo_id == ctx.amo_id,
        QualityAuditReportRevision.audit_id == audit_id,
        QualityAuditReportRevision.status == "ISSUED",
    ).order_by(QualityAuditReportRevision.revision_no.desc()).first()

    row = QualityAuditReportRevision(
        amo_id=ctx.amo_id,
        audit_id=audit.id,
        revision_no=(latest.revision_no + 1) if latest else 1,
        status="DRAFT",
        file_ref=str(path),
        filename=path.name,
        content_type=mimetypes.guess_type(path.name)[0],
        size_bytes=path.stat().st_size,
        sha256=digest,
        report_snapshot=_audit_snapshot(db, audit),
        change_reason=payload.reason.strip(),
        supersedes_revision_id=str(prior_issued.id) if prior_issued else None,
        created_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.flush()
    _add_event(db, ctx=ctx, row=row, event_type="ADOPTED", reason=payload.reason)

    # Preserve the last formally issued report as the compatibility projection
    # while a new draft/review revision is in progress. On first issue there is
    # no prior issued file, so the existing upload remains visible.
    if prior_issued is not None:
        audit.report_file_ref = prior_issued.file_ref

    db.commit()
    loaded = db.query(QualityAuditReportRevision).options(selectinload(QualityAuditReportRevision.events)).filter(QualityAuditReportRevision.id == row.id).one()
    return _revision_dict(loaded)
