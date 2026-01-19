# backend/amodb/apps/quality/service.py
from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from . import models
from .enums import (
    CARActionType,
    CARPriority,
    CARProgram,
    CARStatus,
    FindingLevel,
    FINDING_LEVEL_DUE_DAYS,
    QMSChangeRequestStatus,
    QMSAuditStatus,
    QMSDocStatus,
    QMSDomain,
    infer_level_from_severity,
)

# Default reminder window in days based on finding level (quicker for Level 1).
CAR_LEVEL_REMINDER_DAYS: dict[FindingLevel, int] = {
    FindingLevel.LEVEL_1: 2,
    FindingLevel.LEVEL_2: 7,
    FindingLevel.LEVEL_3: 14,
}


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


# -----------------------------
# CAR helpers
# -----------------------------


def _next_car_number(db: Session, program: CARProgram) -> str:
    year = date.today().year
    prefix = "Q" if program == CARProgram.QUALITY else "R"

    pattern = f"{prefix}-{year}-"
    last = (
        db.query(models.CorrectiveActionRequest)
        .filter(
            models.CorrectiveActionRequest.program == program,
            models.CorrectiveActionRequest.car_number.like(f"{pattern}%"),
        )
        .order_by(models.CorrectiveActionRequest.car_number.desc())
        .first()
    )
    if last and last.car_number.startswith(pattern):
        try:
            seq = int(last.car_number.split("-")[-1]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f"{prefix}-{year}-{seq:04d}"


def create_car(
    db: Session,
    program: CARProgram,
    title: str,
    summary: str,
    priority: CARPriority,
    requested_by_user_id: Optional[str],
    assigned_to_user_id: Optional[str],
    due_date: Optional[date],
    target_closure_date: Optional[date],
    finding_id: Optional[str],
) -> models.CorrectiveActionRequest:
    reminder_days = 7
    if finding_id:
        finding = db.query(models.QMSAuditFinding).filter(models.QMSAuditFinding.id == finding_id).first()
        if finding:
            reminder_days = CAR_LEVEL_REMINDER_DAYS.get(finding.level, 7)

    invite_token = uuid.uuid4().hex
    next_reminder_at = datetime.now(timezone.utc) + timedelta(days=reminder_days)
    car = models.CorrectiveActionRequest(
        program=program,
        car_number=_next_car_number(db, program),
        title=title,
        summary=summary,
        priority=priority,
        status=CARStatus.OPEN,
        requested_by_user_id=requested_by_user_id,
        assigned_to_user_id=assigned_to_user_id,
        due_date=due_date,
        target_closure_date=target_closure_date,
        finding_id=finding_id,
        invite_token=invite_token,
        reminder_interval_days=reminder_days,
        next_reminder_at=next_reminder_at,
    )
    db.add(car)
    db.flush()

    log = models.CARActionLog(
        car=car,
        action_type=CARActionType.COMMENT,
        message="CAR created",
        actor_user_id=requested_by_user_id,
    )
    db.add(log)
    return car


def add_car_action(
    db: Session,
    car: models.CorrectiveActionRequest,
    action_type: CARActionType,
    message: str,
    actor_user_id: Optional[str],
) -> models.CARActionLog:
    log = models.CARActionLog(
        car=car,
        action_type=action_type,
        message=message,
        actor_user_id=actor_user_id,
    )
    db.add(log)
    return log


def schedule_next_reminder(car: models.CorrectiveActionRequest, days: Optional[int] = None) -> None:
    interval = days or car.reminder_interval_days or 7
    car.reminder_interval_days = interval
    car.next_reminder_at = datetime.now(timezone.utc) + timedelta(days=interval)


def build_car_invite_link(car: models.CorrectiveActionRequest) -> str:
    base = os.getenv("PORTAL_FRONTEND_BASE_URL", "http://localhost:5173")
    return f"{base}/car-invite?token={car.invite_token}"
