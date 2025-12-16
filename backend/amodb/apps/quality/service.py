# backend/amodb/apps/quality/service.py
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from . import models
from .enums import (
    FindingLevel,
    FINDING_LEVEL_DUE_DAYS,
    QMSChangeRequestStatus,
    QMSAuditStatus,
    QMSDocStatus,
    QMSDomain,
    infer_level_from_severity,
)


def compute_target_close_date(level: FindingLevel, base: Optional[date] = None) -> date:
    base_date = base or date.today()
    return base_date + timedelta(days=FINDING_LEVEL_DUE_DAYS[level])


def normalize_finding_level(severity, level: Optional[FindingLevel]) -> FindingLevel:
    if level is not None:
        return level
    return infer_level_from_severity(severity)


def get_dashboard(db: Session, domain: Optional[QMSDomain] = None) -> dict:
    # Documents
    doc_q = db.query(models.QMSDocument)
    if domain:
        doc_q = doc_q.filter(models.QMSDocument.domain == domain)

    documents_total = doc_q.count()
    documents_active = doc_q.filter(models.QMSDocument.status == QMSDocStatus.ACTIVE).count()
    documents_draft = doc_q.filter(models.QMSDocument.status == QMSDocStatus.DRAFT).count()
    documents_obsolete = doc_q.filter(models.QMSDocument.status == QMSDocStatus.OBSOLETE).count()

    # Pending acknowledgements
    dist_q = db.query(models.QMSDocumentDistribution).filter(
        models.QMSDocumentDistribution.requires_ack.is_(True),
        models.QMSDocumentDistribution.acked_at.is_(None),
    )
    if domain:
        dist_q = dist_q.join(models.QMSDocument).filter(models.QMSDocument.domain == domain)
    distributions_pending_ack = dist_q.count()

    # Change requests
    cr_q = db.query(models.QMSManualChangeRequest)
    if domain:
        cr_q = cr_q.filter(models.QMSManualChangeRequest.domain == domain)
    change_requests_total = cr_q.count()
    change_requests_open = cr_q.filter(
        or_(
            models.QMSManualChangeRequest.status == QMSChangeRequestStatus.SUBMITTED,
            models.QMSManualChangeRequest.status == QMSChangeRequestStatus.UNDER_REVIEW,
        )
    ).count()

    # Audits
    a_q = db.query(models.QMSAudit)
    if domain:
        a_q = a_q.filter(models.QMSAudit.domain == domain)
    audits_total = a_q.count()
    audits_open = a_q.filter(
        or_(
            models.QMSAudit.status == QMSAuditStatus.PLANNED,
            models.QMSAudit.status == QMSAuditStatus.IN_PROGRESS,
            models.QMSAudit.status == QMSAuditStatus.CAP_OPEN,
        )
    ).count()

    # Findings (open = not closed)
    f_q = db.query(models.QMSAuditFinding)
    if domain:
        f_q = f_q.join(models.QMSAudit).filter(models.QMSAudit.domain == domain)

    findings_open = f_q.filter(models.QMSAuditFinding.closed_at.is_(None))
    findings_open_total = findings_open.count()
    findings_open_level_1 = findings_open.filter(models.QMSAuditFinding.level == FindingLevel.LEVEL_1).count()
    findings_open_level_2 = findings_open.filter(models.QMSAuditFinding.level == FindingLevel.LEVEL_2).count()
    findings_open_level_3 = findings_open.filter(models.QMSAuditFinding.level == FindingLevel.LEVEL_3).count()

    # Overdue (target date passed and still open)
    today = date.today()
    overdue_q = findings_open.filter(
        models.QMSAuditFinding.target_close_date.is_not(None),
        models.QMSAuditFinding.target_close_date < today,
    )
    findings_overdue_total = overdue_q.count()

    return {
        "domain": domain,
        "documents_total": documents_total,
        "documents_active": documents_active,
        "documents_draft": documents_draft,
        "documents_obsolete": documents_obsolete,
        "distributions_pending_ack": distributions_pending_ack,
        "change_requests_total": change_requests_total,
        "change_requests_open": change_requests_open,
        "audits_total": audits_total,
        "audits_open": audits_open,
        "findings_open_total": findings_open_total,
        "findings_open_level_1": findings_open_level_1,
        "findings_open_level_2": findings_open_level_2,
        "findings_open_level_3": findings_open_level_3,
        "findings_overdue_total": findings_overdue_total,
    }
