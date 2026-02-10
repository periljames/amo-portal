# backend/amodb/apps/quality/service.py
from __future__ import annotations

import importlib.util
import os
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import models
from ..finance import models as finance_models
from ..training import models as training_models
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

COCKPIT_ACTION_QUEUE_LIMIT = 25

BASE_DIR = Path(__file__).resolve().parents[2]
CAR_FORM_OUTPUT_DIR = BASE_DIR / "generated" / "quality" / "cars"
CAR_FORM_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

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






def _safe_count(query) -> int:
    try:
        return query.count()
    except SQLAlchemyError:
        return 0


def _build_audit_closure_trend(db: Session, window_days: int = 90, bucket_days: int = 7) -> list[dict]:
    today = date.today()
    start = today - timedelta(days=window_days - 1)
    try:
        audits = (
            db.query(models.QMSAudit.id, models.QMSAudit.actual_end)
            .filter(models.QMSAudit.status == QMSAuditStatus.CLOSED, models.QMSAudit.actual_end.is_not(None))
            .all()
        )
    except SQLAlchemyError:
        return []

    buckets: dict[date, list[str]] = defaultdict(list)
    for audit_id, actual_end in audits:
        if not actual_end:
            continue
        closed_day = actual_end
        if closed_day < start or closed_day > today:
            continue
        offset = (closed_day - start).days
        bucket_start = start + timedelta(days=(offset // bucket_days) * bucket_days)
        buckets[bucket_start].append(str(audit_id))

    trend: list[dict] = []
    cursor = start
    while cursor <= today:
        bucket_end = min(cursor + timedelta(days=bucket_days - 1), today)
        ids = sorted(buckets.get(cursor, []))
        trend.append({
            "period_start": cursor,
            "period_end": bucket_end,
            "closed_count": len(ids),
            "audit_ids": ids,
        })
        cursor = cursor + timedelta(days=bucket_days)
    return trend


def get_cockpit_snapshot(db: Session, domain: Optional[QMSDomain] = None) -> dict:
    dashboard = get_dashboard(db, domain=domain)
    open_statuses = [CARStatus.OPEN, CARStatus.IN_PROGRESS, CARStatus.PENDING_VERIFICATION]
    cars_q = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.status.in_(open_statuses))
    action_rows = (
        cars_q.order_by(
            models.CorrectiveActionRequest.due_date.asc().nulls_last(),
            models.CorrectiveActionRequest.updated_at.desc(),
        )
        .limit(COCKPIT_ACTION_QUEUE_LIMIT)
        .all()
    )

    today = date.today()
    cars_open_total = _safe_count(cars_q)
    cars_overdue = _safe_count(cars_q.filter(
        models.CorrectiveActionRequest.due_date.is_not(None),
        models.CorrectiveActionRequest.due_date < today,
    ))

    training_expiring_30d = _safe_count(db.query(training_models.TrainingRecord).filter(
        training_models.TrainingRecord.valid_until.is_not(None),
        training_models.TrainingRecord.valid_until >= today,
        training_models.TrainingRecord.valid_until <= today + timedelta(days=30),
    ))
    training_expired = _safe_count(db.query(training_models.TrainingRecord).filter(
        training_models.TrainingRecord.valid_until.is_not(None),
        training_models.TrainingRecord.valid_until < today,
    ))
    training_unverified = _safe_count(db.query(training_models.TrainingRecord).filter(
        training_models.TrainingRecord.verification_status == training_models.TrainingRecordVerificationStatus.PENDING,
    ))
    training_deferrals_pending = _safe_count(db.query(training_models.TrainingDeferralRequest).filter(
        training_models.TrainingDeferralRequest.status == training_models.DeferralStatus.PENDING,
    ))

    suppliers_active = _safe_count(db.query(finance_models.Vendor).filter(finance_models.Vendor.is_active.is_(True)))
    suppliers_inactive = _safe_count(db.query(finance_models.Vendor).filter(finance_models.Vendor.is_active.is_(False)))

    return {
        "generated_at": datetime.now(timezone.utc),
        "pending_acknowledgements": dashboard["distributions_pending_ack"],
        "audits_open": dashboard["audits_open"],
        "audits_total": dashboard["audits_total"],
        "findings_overdue": dashboard["findings_overdue_total"],
        "findings_open_total": dashboard["findings_open_total"],
        "documents_active": dashboard["documents_active"],
        "documents_draft": dashboard["documents_draft"],
        "documents_obsolete": dashboard["documents_obsolete"],
        "change_requests_open": dashboard["change_requests_open"],
        "cars_open_total": cars_open_total,
        "cars_overdue": cars_overdue,
        "training_records_expiring_30d": training_expiring_30d,
        "training_records_expired": training_expired,
        "training_records_unverified": training_unverified,
        "training_deferrals_pending": training_deferrals_pending,
        "suppliers_active": suppliers_active,
        "suppliers_inactive": suppliers_inactive,
        "audit_closure_trend": _build_audit_closure_trend(db),
        "action_queue": [
            {
                "id": str(row.id),
                "kind": "CAR",
                "title": f"{row.car_number} · {row.title}",
                "status": row.status.value,
                "priority": row.priority.value,
                "due_date": row.due_date,
                "assignee_user_id": row.assigned_to_user_id,
            }
            for row in action_rows
        ],
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


def generate_car_form_pdf(
    car: models.CorrectiveActionRequest,
    invite_url: str,
    requested_by_name: Optional[str] = None,
    assigned_to_name: Optional[str] = None,
) -> Path:
    if importlib.util.find_spec("reportlab") is None:
        raise RuntimeError(
            "Missing dependency 'reportlab'. Install it with 'pip install reportlab'."
        )

    from reportlab.graphics import renderPDF  # type: ignore[import-not-found]
    from reportlab.graphics.barcode import qr  # type: ignore[import-not-found]
    from reportlab.graphics.shapes import Drawing  # type: ignore[import-not-found]
    from reportlab.lib.pagesizes import letter  # type: ignore[import-not-found]
    from reportlab.lib.units import inch  # type: ignore[import-not-found]
    from reportlab.lib.utils import simpleSplit  # type: ignore[import-not-found]
    from reportlab.pdfgen import canvas  # type: ignore[import-not-found]

    output_path = CAR_FORM_OUTPUT_DIR / f"car_form_{car.id}.pdf"
    page_width, page_height = letter
    pdf = canvas.Canvas(str(output_path), pagesize=letter)

    margin = 0.75 * inch
    cursor_y = page_height - margin

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(margin, cursor_y, "Corrective Action Request (CAR)")
    cursor_y -= 0.35 * inch

    pdf.setFont("Helvetica", 11)
    entries = [
        ("CAR Number", car.car_number),
        ("Title", car.title),
        ("Summary", car.summary),
        ("Requested By", requested_by_name or car.requested_by_user_id or "N/A"),
        ("Assigned To", assigned_to_name or car.assigned_to_user_id or "N/A"),
        ("Priority", car.priority.value),
        ("Status", car.status.value),
        ("Due Date", car.due_date.isoformat() if car.due_date else "N/A"),
        (
            "Target Closure Date",
            car.target_closure_date.isoformat() if car.target_closure_date else "N/A",
        ),
        ("Root Cause", car.root_cause or "N/A"),
        ("Corrective Action Plan (CAP)", car.corrective_action or "N/A"),
        ("Preventive Action Plan (PAP)", car.preventive_action or "N/A"),
        ("Evidence Reference", car.evidence_ref or "N/A"),
    ]

    label_width = 170
    max_text_width = page_width - (margin * 2) - label_width

    for label, value in entries:
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(margin, cursor_y, f"{label}:")
        pdf.setFont("Helvetica", 11)
        lines = simpleSplit(str(value), "Helvetica", 11, max_text_width)
        if not lines:
            lines = [""]
        for line in lines:
            pdf.drawString(margin + label_width, cursor_y, line)
            cursor_y -= 0.22 * inch
        cursor_y -= 0.1 * inch
        if cursor_y < margin + (1.5 * inch):
            pdf.showPage()
            cursor_y = page_height - margin

    qr_widget = qr.QrCodeWidget(invite_url)
    bounds = qr_widget.getBounds()
    qr_width = bounds[2] - bounds[0]
    qr_height = bounds[3] - bounds[1]
    qr_size = 1.4 * inch
    drawing = Drawing(
        qr_size,
        qr_size,
        transform=[qr_size / qr_width, 0, 0, qr_size / qr_height, 0, 0],
    )
    drawing.add(qr_widget)
    qr_x = page_width - margin - qr_size
    qr_y = margin
    renderPDF.draw(drawing, pdf, qr_x, qr_y)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(qr_x, qr_y - 0.2 * inch, "Scan to access CAR online")

    pdf.showPage()
    pdf.save()
    return output_path
