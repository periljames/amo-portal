from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from amodb.database import get_write_db

from .audit_report_composition import resolve_report_artifact
from .audit_report_composition_models import QualityAuditReportArtifact
from .audit_report_governance_models import QualityAuditReportRevision
from .audit_report_governance_router import _add_event, _audit, _audit_snapshot, _revision_dict, _sha256
from .tenant_security import TenantContext, assert_quality_permission, set_postgres_tenant_context, write_tenant_context


router = APIRouter(tags=["Quality audit generated report adoption"])


class GeneratedReportAdopt(BaseModel):
    reason: str = Field(min_length=8, max_length=4000)


@router.post(
    "/audits/{audit_id}/report-revisions/adopt-generated/{artifact_id}",
    status_code=status.HTTP_201_CREATED,
    name="adopt_generated_report_artifact",
)
def adopt_generated_report_artifact(
    audit_id: uuid.UUID,
    artifact_id: str,
    payload: GeneratedReportAdopt,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    """Adopt one deterministic closing-report artifact into report governance.

    The artifact remains the generated source file; the authoritative lifecycle
    continues to be ``QualityAuditReportRevision``. This adapter deliberately
    does not mark the artifact issued or bypass review/approval transitions.
    """

    assert_quality_permission(db, ctx, "qms.audit.manage")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = _audit(db, amo_id=ctx.amo_id, audit_id=audit_id)
    artifact = db.query(QualityAuditReportArtifact).filter(
        QualityAuditReportArtifact.amo_id == ctx.amo_id,
        QualityAuditReportArtifact.audit_id == audit_id,
        QualityAuditReportArtifact.id == artifact_id,
    ).first()
    if artifact is None:
        raise HTTPException(status_code=404, detail="Generated audit report artifact not found.")

    path = resolve_report_artifact(artifact.storage_ref)
    digest = _sha256(path)
    if digest != artifact.sha256:
        raise HTTPException(status_code=409, detail="Generated report artifact no longer matches its governed checksum.")

    latest = db.query(QualityAuditReportRevision).filter(
        QualityAuditReportRevision.amo_id == ctx.amo_id,
        QualityAuditReportRevision.audit_id == audit_id,
    ).order_by(QualityAuditReportRevision.revision_no.desc()).with_for_update().first()
    if latest is not None and latest.status in {"DRAFT", "INTERNAL_REVIEW", "APPROVED"}:
        raise HTTPException(status_code=409, detail="A governed report revision is already in progress. Complete or cancel it before adopting another generated report.")

    duplicate = db.query(QualityAuditReportRevision.id).filter(
        QualityAuditReportRevision.amo_id == ctx.amo_id,
        QualityAuditReportRevision.audit_id == audit_id,
        QualityAuditReportRevision.sha256 == digest,
    ).first()
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="This exact generated report is already retained in the governed report history.")

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
        filename=artifact.filename,
        content_type=artifact.content_type,
        size_bytes=artifact.size_bytes,
        sha256=digest,
        report_snapshot={
            **_audit_snapshot(db, audit),
            "generated_report_artifact_id": artifact.id,
            "source_snapshot_hash": artifact.source_snapshot_hash,
            "template_version": artifact.template_version,
            "renderer_version": artifact.renderer_version,
        },
        change_reason=payload.reason.strip(),
        supersedes_revision_id=str(prior_issued.id) if prior_issued else None,
        created_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.flush()
    _add_event(db, ctx=ctx, row=row, event_type="ADOPTED", reason=payload.reason)

    # A prior issued report remains the compatibility projection until the new
    # revision completes review and is formally issued.
    if prior_issued is not None:
        audit.report_file_ref = prior_issued.file_ref

    db.commit()
    loaded = db.query(QualityAuditReportRevision).options(
        selectinload(QualityAuditReportRevision.events)
    ).filter(QualityAuditReportRevision.id == row.id).one()
    return _revision_dict(loaded)
