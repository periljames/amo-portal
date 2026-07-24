from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import services as audit_services
from amodb.database import get_db
from amodb.entitlements import require_module
from amodb.security import get_current_active_user

from .audit_lifecycle_models import QualityAuditEvidenceReview, QualityAuditReportDocument
from .audit_lifecycle_schemas import QualityAuditEvidenceReviewOut, QualityAuditReportMetadataOut
from .audit_lifecycle import _report_metadata
from .router import _audit_metadata, _current_amo_id, _get_audit_for_amo, _require_audit_access, router


_extension_router = APIRouter(
    prefix="/quality",
    tags=["Quality / audit lifecycle"],
    dependencies=[Depends(require_module("quality"))],
)


@_extension_router.get(
    "/audits/{audit_id}/evidence/reviews",
    response_model=list[QualityAuditEvidenceReviewOut],
)
def list_audit_evidence_reviews(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_audit_access(current_user, audit, allow_auditee=True)
    return (
        db.query(QualityAuditEvidenceReview)
        .filter(
            QualityAuditEvidenceReview.audit_id == audit.id,
            QualityAuditEvidenceReview.amo_id == audit.amo_id,
        )
        .order_by(QualityAuditEvidenceReview.updated_at.desc())
        .all()
    )


@_extension_router.post(
    "/audits/{audit_id}/documents/report/distribution",
    response_model=QualityAuditReportMetadataOut,
)
def update_audit_report_distribution(
    audit_id: UUID,
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_audit_access(current_user, audit)
    status = str(payload.get("status") or "").strip().upper()
    if status not in {"NOT_DISTRIBUTED", "PARTIAL", "DISTRIBUTED"}:
        raise HTTPException(status_code=422, detail="Distribution status must be NOT_DISTRIBUTED, PARTIAL or DISTRIBUTED.")
    report_id = payload.get("version_id")
    query = db.query(QualityAuditReportDocument).filter(
        QualityAuditReportDocument.audit_id == audit.id,
        QualityAuditReportDocument.amo_id == audit.amo_id,
        QualityAuditReportDocument.lifecycle_status == "ISSUED",
    )
    if report_id:
        query = query.filter(QualityAuditReportDocument.id == report_id)
    report = query.order_by(QualityAuditReportDocument.issued_at.desc()).first()
    if not report:
        raise HTTPException(status_code=404, detail="Issued report version not found.")
    report.distribution_status = status
    audit_services.log_event(
        db,
        amo_id=audit.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_audit",
        entity_id=str(audit.id),
        action="update_report_distribution",
        after={
            "version_id": str(report.id),
            "distribution_status": status,
            "recipient_groups": payload.get("recipient_groups") or [],
            "shared_count": payload.get("shared_count"),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        },
        correlation_id=str(uuid4()),
        metadata=_audit_metadata(request),
        critical=status == "DISTRIBUTED",
    )
    db.commit()
    return _report_metadata(db, audit, current_user)


router.routes[0:0] = list(_extension_router.routes)
