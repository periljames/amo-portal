"""Lease-safe retained report exports for the Training operating system."""
from __future__ import annotations

import csv
import hashlib
import io
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import models as audit_models
from amodb.apps.audit import services as audit_services
from amodb.apps.training import models as legacy_models
from amodb.apps.training import operating_models as models
from amodb.database import WriteSessionLocal, close_session_safely


UTC = timezone.utc
ROOT = Path(os.getenv("TRAINING_REPORT_STORAGE_DIR", "uploads/training_reports")).resolve()


def _value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime, Decimal)):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, (list, dict)):
        import json
        return json.dumps(value, default=str, sort_keys=True)
    return str(value)


def _row(row: Any, *, fields: list[str] | None = None) -> dict[str, Any]:
    names = fields or [column.name for column in row.__table__.columns]
    return {name: _value(getattr(row, name, None)) for name in names}


def _dataset(db: Session, job: models.TrainingReportJob) -> list[dict[str, Any]]:
    code = job.report_code.upper()
    if job.report_definition_id:
        definition = db.query(models.TrainingReportDefinition).filter(
            models.TrainingReportDefinition.id == job.report_definition_id,
            models.TrainingReportDefinition.amo_id == job.amo_id,
            models.TrainingReportDefinition.active.is_(True),
        ).first()
        if definition is None:
            raise ValueError("The tenant report definition is unavailable or inactive.")
        code = str(definition.dataset).upper()
    filters = job.filters_json or {}
    if code == "PEOPLE_COMPLIANCE":
        query = db.query(account_models.User).filter(account_models.User.amo_id == job.amo_id, account_models.User.is_system_account.is_(False))
        rows = query.order_by(account_models.User.full_name).all()
        return [_row(row, fields=["id", "staff_code", "full_name", "email", "position_title", "department_id", "is_active", "licence_number", "licence_expires_on"]) for row in rows]
    mapping: dict[str, tuple[type, Any]] = {
        "TRAINING_PLAN": (models.TrainingPlanParticipant, models.TrainingPlanParticipant.created_at),
        "ATTENDANCE": (models.TrainingAttendanceEntry, models.TrainingAttendanceEntry.signed_at),
        "ASSESSMENTS": (models.TrainingAssessmentInstance, models.TrainingAssessmentInstance.created_at),
        "AUTHORIZATIONS": (models.TrainingAuthorizationCase, models.TrainingAuthorizationCase.created_at),
        "CERTIFICATES": (legacy_models.TrainingCertificateIssue, legacy_models.TrainingCertificateIssue.issued_at),
        "BUDGET": (models.TrainingBudgetLine, models.TrainingBudgetLine.created_at),
        "AUDIT": (audit_models.AuditEvent, audit_models.AuditEvent.created_at),
    }
    model, order = mapping[code]
    query = db.query(model).filter(model.amo_id == job.amo_id)
    if filters.get("status") and hasattr(model, "status"):
        query = query.filter(model.status == str(filters["status"]).upper())
    rows = query.order_by(order.desc()).all()
    return [_row(row) for row in rows]


def _csv(rows: list[dict[str, Any]]) -> bytes:
    output = io.StringIO(newline="")
    headers = list(rows[0]) if rows else ["result"]
    writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue().encode("utf-8-sig")


def _xlsx(rows: list[dict[str, Any]], title: str) -> bytes:
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Report")
    headers = list(rows[0]) if rows else ["result"]
    sheet.append([title]); sheet.append(headers)
    for row in rows:
        sheet.append([row.get(header) for header in headers])
    output = io.BytesIO(); workbook.save(output)
    return output.getvalue()


def _pdf(rows: list[dict[str, Any]], title: str) -> bytes:
    output = io.BytesIO()
    styles = getSampleStyleSheet()
    story: list[Any] = [Paragraph(title, styles["Title"]), Paragraph(f"Complete server population: {len(rows)} records", styles["BodyText"])]
    headers = (list(rows[0]) if rows else ["result"])[:8]
    data = [headers] + [[str(row.get(header, ""))[:140] for header in headers] for row in rows]
    widths = [max(23 * mm, min(48 * mm, 250 * mm / max(1, len(headers)))) for _ in headers]
    table = Table(data, repeatRows=1, colWidths=widths)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#13233f")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), .25, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(table)
    SimpleDocTemplate(output, pagesize=landscape(A4), leftMargin=8 * mm, rightMargin=8 * mm, topMargin=8 * mm, bottomMargin=8 * mm, title=title).build(story)
    return output.getvalue()


def render_job(db: Session, job: models.TrainingReportJob) -> None:
    job.status = "RUNNING"; job.started_at = datetime.now(UTC); db.flush()
    try:
        rows = _dataset(db, job)
        title = f"Training {job.report_code.replace('_', ' ').title()}"
        if job.output_format == "CSV":
            content, extension = _csv(rows), "csv"
        elif job.output_format == "XLSX":
            content, extension = _xlsx(rows, title), "xlsx"
        else:
            content, extension = _pdf(rows, title), "pdf"
        folder = (ROOT / str(job.amo_id) / str(job.id)).resolve()
        if ROOT not in folder.parents:
            raise ValueError("Training report storage path escaped its tenant root.")
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{job.report_code.lower()}.{extension}"
        path.write_bytes(content)
        checksum = hashlib.sha256(content).hexdigest()
        job.artifact_path = str(path); job.artifact_checksum = checksum; job.status = "COMPLETED"; job.completed_at = datetime.now(UTC)
        job.scope_manifest = {**(job.scope_manifest or {}), "record_count": len(rows), "columns": list(rows[0]) if rows else [], "artifact_checksum": checksum, "completed_at": job.completed_at.isoformat()}
        audit_services.log_event(
            db,
            amo_id=str(job.amo_id),
            actor_user_id=str(job.requested_by_user_id) if job.requested_by_user_id else None,
            entity_type="training.report_job",
            entity_id=str(job.id),
            action="COMPLETED",
            after={"record_count": len(rows), "output_format": job.output_format, "artifact_checksum": checksum},
            metadata={"module": "training", "server_population": True},
            critical=True,
        )
    except Exception as exc:
        job.status = "FAILED"; job.error_text = f"{type(exc).__name__}: {exc}"[:4000]; job.completed_at = datetime.now(UTC)
        audit_services.log_event(
            db,
            amo_id=str(job.amo_id),
            actor_user_id=str(job.requested_by_user_id) if job.requested_by_user_id else None,
            entity_type="training.report_job",
            entity_id=str(job.id),
            action="FAILED",
            after={"error": job.error_text},
            metadata={"module": "training"},
        )
    db.flush()


def run_once(limit: int = 3) -> dict[str, int]:
    db = WriteSessionLocal()
    summary = {"claimed": 0, "completed": 0, "failed": 0}
    try:
        if db.get_bind().dialect.name == "postgresql":
            jobs = db.query(models.TrainingReportJob).filter(models.TrainingReportJob.status == "QUEUED").order_by(models.TrainingReportJob.created_at).with_for_update(skip_locked=True).limit(limit).all()
        else:
            jobs = db.query(models.TrainingReportJob).filter(models.TrainingReportJob.status == "QUEUED").order_by(models.TrainingReportJob.created_at).limit(limit).all()
        for job in jobs:
            summary["claimed"] += 1; render_job(db, job); summary["completed" if job.status == "COMPLETED" else "failed"] += 1
        db.commit(); return summary
    except Exception:
        db.rollback(); summary["failed"] += 1; return summary
    finally:
        close_session_safely(db)


def resolved_artifact_path(job: models.TrainingReportJob) -> Path:
    if not job.artifact_path or not job.artifact_checksum:
        raise FileNotFoundError("Report artifact is not ready.")
    path = Path(job.artifact_path).resolve()
    if ROOT not in path.parents or not path.is_file():
        raise FileNotFoundError("Report artifact is unavailable.")
    if hashlib.sha256(path.read_bytes()).hexdigest() != job.artifact_checksum:
        raise ValueError("Report artifact checksum verification failed.")
    return path
