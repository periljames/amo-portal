from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from amodb.database import get_read_db, get_write_db

from .audit_report_composition import build_report_snapshot, generate_report_artifact, resolve_report_artifact
from .audit_report_composition_models import QualityAuditReportArtifact
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


router = APIRouter(tags=["Quality audit report composition"])


def _serialize(row: QualityAuditReportArtifact) -> dict[str, object]:
    return {
        "id": row.id,
        "audit_id": str(row.audit_id),
        "source_snapshot_hash": row.source_snapshot_hash,
        "template_version": row.template_version,
        "renderer_version": row.renderer_version,
        "filename": row.filename,
        "content_type": row.content_type,
        "size_bytes": int(row.size_bytes or 0),
        "sha256": row.sha256,
        "generated_by_user_id": row.generated_by_user_id,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/audits/{audit_id}/report-composition")
def get_report_composition(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    snapshot = build_report_snapshot(db, amo_id=ctx.amo_id, audit_id=audit_id)
    artifacts = db.query(QualityAuditReportArtifact).filter(
        QualityAuditReportArtifact.amo_id == ctx.amo_id,
        QualityAuditReportArtifact.audit_id == audit_id,
    ).order_by(QualityAuditReportArtifact.created_at.desc()).limit(20).all()
    counts: dict[str, int] = {}
    for row in snapshot["checklist"]:
        status_value = str(row.get("canonical_response_status") or "NOT_VERIFIED")
        counts[status_value] = counts.get(status_value, 0) + 1
    return {
        "audit": snapshot["audit"],
        "checklist_counts": counts,
        "findings_count": len(snapshot["findings"]),
        "cars_count": len(snapshot["cars"]),
        "preparation_documents_count": len(snapshot["preparation_documents"]),
        "artifacts": [_serialize(row) for row in artifacts],
    }


@router.post("/audits/{audit_id}/report-composition/generate", status_code=status.HTTP_201_CREATED)
def generate_closing_report(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.manage")),
    db: Session = Depends(get_write_db),
):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    generated = generate_report_artifact(db, amo_id=ctx.amo_id, audit_id=audit_id, actor_user_id=ctx.user_id)
    db.commit()
    db.refresh(generated.artifact)
    return _serialize(generated.artifact)


@router.get("/audits/{audit_id}/report-composition/artifacts/{artifact_id}/download")
def download_closing_report_artifact(
    audit_id: uuid.UUID,
    artifact_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityAuditReportArtifact).filter(
        QualityAuditReportArtifact.amo_id == ctx.amo_id,
        QualityAuditReportArtifact.audit_id == audit_id,
        QualityAuditReportArtifact.id == artifact_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Generated audit report artifact not found.")
    path = resolve_report_artifact(row.storage_ref)
    return FileResponse(path, filename=row.filename, media_type=row.content_type)
