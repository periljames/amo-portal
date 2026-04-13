# backend/amodb/apps/training/router.py

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import threading
import time
import tempfile
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session, load_only, noload
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from ...database import SessionLocal, get_db
from ...entitlements import require_module
from ...security import get_current_active_user
from ..accounts import models as accounts_models
from ..audit import services as audit_services
from ..accounts import services as account_services
from ..tasks import services as task_services
from ..exports import build_evidence_pack
from . import models as training_models
from . import schemas as training_schemas
from . import compliance as training_compliance
from ..workflow import apply_transition, TransitionError
from .courses_import import import_courses_rows, parse_courses_sheet
from .records_import import import_training_records_rows, parse_training_records_sheet

router = APIRouter(
    prefix="/training",
    tags=["training"],
    dependencies=[Depends(require_module("training"))],
)

public_router = APIRouter(prefix="/public", tags=["training-public"])

_MAX_PAGE_SIZE = 1000  # hard ceiling for list endpoints to protect DB

_TRAINING_RECORD_PDF_CACHE_DIR = Path(tempfile.gettempdir()) / "amodb-training-record-pdf-cache"
_TRAINING_RECORD_PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_TRAINING_RECORD_PDF_CACHE_LOCK = threading.Lock()
_TRAINING_RECORD_PDF_WARMING: set[str] = set()

_TRAINING_RECORD_FORM_NO = os.getenv("TRAINING_RECORD_FORM_NO", "QAM/49A")
_TRAINING_RECORD_ISSUE_DATE = os.getenv("TRAINING_RECORD_ISSUE_DATE", "1 Sept 25")
_TRAINING_RECORD_REVISION = os.getenv("TRAINING_RECORD_REVISION", "00")
_TRAINING_RECORD_PUBLIC_BASE_URL = os.getenv("APP_PUBLIC_BASE_URL", "").rstrip("/")
_TRAINING_RECORD_BRAND_PRIMARY = colors.HexColor("#b28f2c")
_TRAINING_RECORD_BRAND_PRIMARY_DARK = colors.HexColor("#8a6f20")
_TRAINING_RECORD_BRAND_PRIMARY_SOFT = colors.HexColor("#f6f0dc")
_TRAINING_RECORD_BRAND_ROW_ALT = colors.HexColor("#fbf7ea")
_TRAINING_RECORD_OK = colors.HexColor("#15803d")
_TRAINING_RECORD_DUE_SOON = colors.HexColor("#b45309")
_TRAINING_RECORD_OVERDUE = colors.HexColor("#b42318")


_TRAINING_SCHEMA_COMPAT_CHECKED = False
_TRAINING_SCHEMA_COMPAT_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# STORAGE CONFIG (FILES)
# ---------------------------------------------------------------------------

# You can override this per environment:
#   TRAINING_UPLOAD_DIR=/var/lib/amodb/uploads/training
_TRAINING_UPLOAD_DIR = Path(os.getenv("TRAINING_UPLOAD_DIR", "uploads/training")).resolve()
_TRAINING_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Optional: max file size guard (bytes). 0/None disables.
_MAX_UPLOAD_BYTES = int(os.getenv("TRAINING_MAX_UPLOAD_BYTES", "0") or "0")


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------


def _next_certificate_number(db: Session, amo_id: str) -> str:
    prefix = f"TC-{amo_id[:6].upper()}"
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    seq = 1
    while True:
        candidate = f"{prefix}-{today}-{seq:04d}"
        exists = (
            db.query(training_models.TrainingRecord.id)
            .filter(
                training_models.TrainingRecord.amo_id == amo_id,
                training_models.TrainingRecord.certificate_reference == candidate,
            )
            .first()
        )
        if not exists:
            return candidate
        seq += 1





def _ensure_training_catalog_schema_compat(db: Session) -> None:
    """
    One-time, best-effort schema compatibility guard.

    Important: avoid issuing ALTER TABLE statements on every request because
    the training page fires many concurrent reads in development, which can
    deadlock against runtime DDL. We inspect first and only mutate once when
    genuinely required.
    """
    global _TRAINING_SCHEMA_COMPAT_CHECKED

    if _TRAINING_SCHEMA_COMPAT_CHECKED:
        return

    with _TRAINING_SCHEMA_COMPAT_LOCK:
        if _TRAINING_SCHEMA_COMPAT_CHECKED:
            return

        bind = db.get_bind()
        if bind is None:
            return

        try:
            existing = {col["name"] for col in inspect(bind).get_columns("training_courses")}
        except Exception:
            return

        statements: list[str] = []
        if "category_raw" not in existing:
            statements.append("ALTER TABLE training_courses ADD COLUMN IF NOT EXISTS category_raw VARCHAR(255)")
        if "status" not in existing:
            statements.append("ALTER TABLE training_courses ADD COLUMN IF NOT EXISTS status VARCHAR(64) DEFAULT 'One_Off'")
        if "scope" not in existing:
            statements.append("ALTER TABLE training_courses ADD COLUMN IF NOT EXISTS scope VARCHAR(255)")

        if statements:
            with bind.begin() as conn:
                for statement in statements:
                    conn.execute(text(statement))

        _TRAINING_SCHEMA_COMPAT_CHECKED = True


def _run_deadlock_retry(db: Session, fn, *, attempts: int = 2):
    last_exc = None
    for attempt in range(attempts):
        try:
            return fn()
        except OperationalError as exc:
            db.rollback()
            last_exc = exc
            if "deadlock detected" not in str(exc).lower() or attempt >= attempts - 1:
                raise
            time.sleep(0.05 * (attempt + 1))
    if last_exc is not None:
        raise last_exc



def _fmt_date(value: Optional[date | datetime | str]) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%d %b %Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d %b %Y")
    raw = str(value).strip()
    return raw or "-"


def _status_counter(items: List[training_schemas.TrainingStatusItem]) -> Dict[str, int]:
    counts = {"OVERDUE": 0, "DUE_SOON": 0, "DEFERRED": 0, "SCHEDULED_ONLY": 0, "NOT_DONE": 0, "OK": 0}
    for item in items:
        key = item.status.value if hasattr(item.status, "value") else str(item.status)
        key = (key or "").upper()
        counts[key] = counts.get(key, 0) + 1
    return counts


def _extract_record_remark_token(remarks: Optional[str], key: str) -> Optional[str]:
    if not remarks:
        return None
    match = re.search(rf"(?:^|\|)\s*{re.escape(key)}\s*=\s*([^|]+?)\s*(?:\||$)", remarks, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip() or None


def _normalize_record_state(value: Optional[str]) -> Optional[str]:
    raw = (value or "").strip().upper().replace(" ", "_")
    if not raw:
        return None
    aliases = {
        "DUE_SOON": "DUE_SOON",
        "DUE": "DUE_SOON",
        "OK": "OK",
        "CURRENT": "OK",
        "COMPLIANT": "OK",
        "RENEWED": "RENEWED",
        "SUPERSEDED": "RENEWED",
        "INACTIVE": "RENEWED",
    }
    return aliases.get(raw, raw)


def _record_source_status(record: training_models.TrainingRecord) -> Optional[str]:
    return _normalize_record_state(_extract_record_remark_token(getattr(record, "remarks", None), "Status"))


def _record_lifecycle_status(record: training_models.TrainingRecord) -> Optional[str]:
    lifecycle = _normalize_record_state(_extract_record_remark_token(getattr(record, "remarks", None), "LifecycleStatus"))
    return lifecycle or _record_source_status(record)


def _is_record_active_for_display(record: training_models.TrainingRecord) -> bool:
    state = _record_lifecycle_status(record)
    return state not in {"RENEWED"}


def _status_label_for_pdf(status: Optional[str]) -> str:
    key = (status or "").upper()
    if key == "OVERDUE":
        return "Overdue"
    if key == "DUE_SOON":
        return "Due soon"
    if key == "DEFERRED":
        return "Deferred"
    if key == "SCHEDULED_ONLY":
        return "Scheduled"
    if key == "NOT_DONE":
        return "Not done"
    return "Current"


def _status_color_for_pdf(status: Optional[str]):
    key = (status or "").upper()
    if key == "OVERDUE":
        return _TRAINING_RECORD_OVERDUE
    if key == "DUE_SOON":
        return _TRAINING_RECORD_DUE_SOON
    if key == "DEFERRED":
        return colors.HexColor("#175cd3")
    if key == "NOT_DONE":
        return _TRAINING_RECORD_OVERDUE
    return _TRAINING_RECORD_OK


class _TrainingRecordNumberedCanvas(canvas.Canvas):
    def __init__(self, *args, training_pdf_meta: Optional[dict] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict] = []
        self._training_pdf_meta = training_pdf_meta or {}

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        self._saved_page_states.append(dict(self.__dict__))
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_header_footer(total_pages)
            super().showPage()
        super().save()

    def _draw_header_footer(self, total_pages: int) -> None:
        meta = self._training_pdf_meta or {}
        page_width, page_height = self._pagesize
        left = 14 * mm
        right = page_width - 14 * mm
        top = page_height - 10 * mm

        logo_path = meta.get("logo_path")
        amo_name = meta.get("amo_name") or "AMO"
        self.saveState()
        if logo_path and Path(str(logo_path)).exists():
            try:
                self.drawImage(ImageReader(str(logo_path)), left, page_height - 24 * mm, width=24 * mm, height=12 * mm, preserveAspectRatio=True, mask='auto')
                title_x = left + 28 * mm
            except Exception:
                title_x = left
        else:
            title_x = left

        self.setFillColor(_TRAINING_RECORD_BRAND_PRIMARY_DARK)
        self.setFont("Helvetica-Bold", 12)
        self.drawString(title_x, top, str(amo_name).upper())
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#475467"))
        self.drawString(title_x, top - 4.8 * mm, "Individual Training Record")

        meta_x = right - 64 * mm
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#111827"))
        self.drawRightString(right, top, f"Form No: {_TRAINING_RECORD_FORM_NO}")
        self.drawRightString(right, top - 4.2 * mm, f"Issue date: {_TRAINING_RECORD_ISSUE_DATE}")
        self.drawRightString(right, top - 8.4 * mm, f"Revision: {_TRAINING_RECORD_REVISION}")
        self.drawRightString(right, top - 12.6 * mm, f"Page {self._pageNumber} of {total_pages}")

        self.setStrokeColor(_TRAINING_RECORD_BRAND_PRIMARY)
        self.setLineWidth(1)
        self.line(left, page_height - 26 * mm, right, page_height - 26 * mm)

        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.HexColor("#667085"))
        printed_at = meta.get("printed_at") or datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
        self.drawString(left, 8 * mm, f"Printed on {printed_at}")
        self.drawRightString(right, 8 * mm, f"Training_Tracker_DB_v1.2    {self._pageNumber} of {total_pages}")
        self.restoreState()


def _training_canvas_maker(meta: dict):
    def _maker(*args, **kwargs):
        return _TrainingRecordNumberedCanvas(*args, training_pdf_meta=meta, **kwargs)
    return _maker


def _build_training_profile_qr_drawing(value: str, size_mm: float = 28) -> Drawing:
    qr_widget = qr.QrCodeWidget(value)
    bounds = qr_widget.getBounds()
    qr_width = max(bounds[2] - bounds[0], 1)
    qr_height = max(bounds[3] - bounds[1], 1)
    size = size_mm * mm
    drawing = Drawing(size, size, transform=[size / qr_width, 0, 0, size / qr_height, 0, 0])
    drawing.add(qr_widget)
    return drawing


def _build_training_user_record_pdf_bytes(
    *,
    user: accounts_models.User,
    amo: Optional[accounts_models.AMO],
    logo_path: Optional[str],
    status_items: List[training_schemas.TrainingStatusItem],
    records: List[training_models.TrainingRecord],
    course_by_id: Dict[str, training_models.TrainingCourse],
    upcoming_events: List[training_models.TrainingEvent],
    deferrals: List[training_models.TrainingDeferralRequest],
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=30 * mm,
        bottomMargin=18 * mm,
        title="Personnel Training Record",
        author="AMO Portal",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TrainingTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=19,
        textColor=colors.HexColor("#17212b"),
        spaceAfter=3,
    )
    subtitle_style = ParagraphStyle(
        "TrainingSubtitle",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#667085"),
        spaceAfter=8,
    )
    section_style = ParagraphStyle(
        "TrainingSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=13,
        textColor=colors.HexColor("#17212b"),
        spaceBefore=6,
        spaceAfter=5,
    )
    body_style = ParagraphStyle(
        "TrainingBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=10.2,
        textColor=colors.HexColor("#111827"),
    )
    compact_style = ParagraphStyle(
        "TrainingCompact",
        parent=body_style,
        fontSize=7.5,
        leading=9.4,
    )
    label_style = ParagraphStyle(
        "TrainingLabel",
        parent=body_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#475467"),
    )

    counts = _status_counter(status_items)
    generated_at = datetime.now(timezone.utc)
    printed_at = generated_at.strftime("%d %b %Y %H:%M UTC")
    next_due = next(
        iter(
            sorted(
                [item for item in status_items if item.extended_due_date or item.valid_until],
                key=lambda item: str(item.extended_due_date or item.valid_until or ""),
            )
        ),
        None,
    )

    public_identifier = getattr(amo, "login_slug", None) or getattr(amo, "amo_code", None) or getattr(amo, "id", None) or getattr(user, "amo_id", None) or "amo"
    profile_path = f"/maintenance/{public_identifier}/quality/qms/training/{user.id}"
    qr_value = f"{_TRAINING_RECORD_PUBLIC_BASE_URL}{profile_path}" if _TRAINING_RECORD_PUBLIC_BASE_URL else f"Training profile {user.id}"

    story: list = [
        Paragraph("Personnel Training Record", title_style),
        Paragraph(
            "Controlled training record generated from the QMS training profile. Only current and due items are shown in the main log; superseded renewed history is excluded from this export.",
            subtitle_style,
        ),
    ]

    details_table = Table(
        [
            [
                Paragraph("<b>Name</b>", label_style),
                Paragraph(user.full_name or "-", body_style),
                Paragraph("<b>Staff code</b>", label_style),
                Paragraph(user.staff_code or "-", body_style),
            ],
            [
                Paragraph("<b>Position</b>", label_style),
                Paragraph(getattr(user, "position_title", None) or "-", body_style),
                Paragraph("<b>Licence No</b>", label_style),
                Paragraph(getattr(user, "licence_number", None) or "NIL", body_style),
            ],
            [
                Paragraph("<b>Profile status</b>", label_style),
                Paragraph("Active" if getattr(user, "is_active", False) else "Inactive", body_style),
                Paragraph("<b>Generated at</b>", label_style),
                Paragraph(printed_at, body_style),
            ],
        ],
        colWidths=[22 * mm, 56 * mm, 22 * mm, 40 * mm],
    )
    details_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#d0d5dd")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#e4e7ec")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    qr_caption = Paragraph(
        "<b>Record QR</b><br/>Scan to open the live training profile used to generate this record.",
        compact_style,
    )
    front_table = Table(
        [[details_table, _build_training_profile_qr_drawing(qr_value, size_mm=28)], ["", qr_caption]],
        colWidths=[140 * mm, 30 * mm],
    )
    front_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.extend([front_table, Spacer(1, 6)])

    summary_table = Table(
        [
            [
                Paragraph("<b>Current</b>", label_style), Paragraph(str(counts.get("OK", 0)), body_style),
                Paragraph("<b>Due soon</b>", label_style), Paragraph(str(counts.get("DUE_SOON", 0)), body_style),
                Paragraph("<b>Overdue</b>", label_style), Paragraph(str(counts.get("OVERDUE", 0)), body_style),
            ],
            [
                Paragraph("<b>Deferred</b>", label_style), Paragraph(str(counts.get("DEFERRED", 0)), body_style),
                Paragraph("<b>Scheduled</b>", label_style), Paragraph(str(counts.get("SCHEDULED_ONLY", 0)), body_style),
                Paragraph("<b>Records shown</b>", label_style), Paragraph(str(len(records)), body_style),
            ],
            [
                Paragraph("<b>Next due</b>", label_style),
                Paragraph(next_due.course_name if next_due else "No due dates available", body_style),
                Paragraph("<b>Due date</b>", label_style),
                Paragraph(_fmt_date(next_due.extended_due_date or next_due.valid_until) if next_due else "-", body_style),
                Paragraph("<b>Status</b>", label_style),
                Paragraph(
                    f'<font color="{_status_color_for_pdf(next_due.status).hexval()[2:]}">{_status_label_for_pdf(next_due.status)}</font>' if next_due else "-",
                    body_style,
                ),
            ],
        ],
        colWidths=[22 * mm, 38 * mm, 22 * mm, 28 * mm, 20 * mm, 24 * mm],
    )
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _TRAINING_RECORD_BRAND_PRIMARY_SOFT),
                ("BOX", (0, 0), (-1, -1), 0.45, _TRAINING_RECORD_BRAND_PRIMARY),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#e4e7ec")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([Paragraph("Compliance summary", section_style), summary_table, Spacer(1, 6)])

    history_header = [
        Paragraph("<b>Course code</b>", compact_style),
        Paragraph("<b>Course title</b>", compact_style),
        Paragraph("<b>Completed</b>", compact_style),
        Paragraph("<b>Next due</b>", compact_style),
        Paragraph("<b>Status</b>", compact_style),
        Paragraph("<b>Hours</b>", compact_style),
        Paragraph("<b>Score</b>", compact_style),
        Paragraph("<b>Certificate</b>", compact_style),
    ]
    history_rows = [history_header]
    active_records = sorted(records, key=lambda r: (r.completion_date or date.min, getattr(r, "created_at", None) or datetime.min), reverse=True)
    for record in active_records:
        course = course_by_id.get(record.course_id)
        source_status = _record_source_status(record)
        item = None
        if course is not None:
            item = next((entry for entry in status_items if entry.course_id == course.course_id and entry.course_name == course.course_name), None)
        display_status = (item.status if item else None) or source_status or "OK"
        history_rows.append(
            [
                Paragraph(getattr(course, "course_id", None) or str(record.course_id), compact_style),
                Paragraph(getattr(course, "course_name", None) or str(record.course_id), compact_style),
                Paragraph(_fmt_date(record.completion_date), compact_style),
                Paragraph(_fmt_date((item.extended_due_date if item else None) or (item.valid_until if item else None) or record.valid_until), compact_style),
                Paragraph(f'<font color="{_status_color_for_pdf(display_status).hexval()[2:]}"><b>{_status_label_for_pdf(display_status)}</b></font>', compact_style),
                Paragraph('-' if record.hours_completed is None else str(record.hours_completed), compact_style),
                Paragraph('-' if record.exam_score is None else str(record.exam_score), compact_style),
                Paragraph(record.certificate_reference or '-', compact_style),
            ]
        )
    if len(history_rows) == 1:
        history_rows.append([
            Paragraph('-', compact_style),
            Paragraph('No active training records were found for this profile.', compact_style),
            Paragraph('-', compact_style),
            Paragraph('-', compact_style),
            Paragraph('-', compact_style),
            Paragraph('-', compact_style),
            Paragraph('-', compact_style),
            Paragraph('-', compact_style),
        ])
    history_table = Table(history_rows, repeatRows=1, colWidths=[20 * mm, 66 * mm, 18 * mm, 18 * mm, 18 * mm, 12 * mm, 12 * mm, 18 * mm])
    history_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _TRAINING_RECORD_BRAND_PRIMARY_DARK),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), 'Helvetica-Bold'),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _TRAINING_RECORD_BRAND_ROW_ALT]),
                ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor('#d0d5dd')),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor('#e4e7ec')),
                ("VALIGN", (0, 0), (-1, -1), 'MIDDLE'),
                ("ALIGN", (2, 1), (7, -1), 'CENTER'),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([Paragraph("Training record log", section_style), history_table, Spacer(1, 6)])

    schedule_header = [Paragraph("<b>Course</b>", compact_style), Paragraph("<b>Event</b>", compact_style), Paragraph("<b>Starts</b>", compact_style), Paragraph("<b>Ends</b>", compact_style), Paragraph("<b>Status</b>", compact_style), Paragraph("<b>Location</b>", compact_style)]
    schedule_rows = [schedule_header]
    for event in sorted(upcoming_events, key=lambda e: (e.starts_on or date.max, e.title or '')):
        course = course_by_id.get(event.course_id)
        schedule_rows.append([
            Paragraph(getattr(course, 'course_name', None) or str(event.course_id), compact_style),
            Paragraph(event.title or '-', compact_style),
            Paragraph(_fmt_date(event.starts_on), compact_style),
            Paragraph(_fmt_date(event.ends_on), compact_style),
            Paragraph(str(event.status).replace('_', ' '), compact_style),
            Paragraph(event.location or '-', compact_style),
        ])
    if len(schedule_rows) == 1:
        schedule_rows.append([Paragraph('-', compact_style), Paragraph('No upcoming scheduled training events linked to this profile.', compact_style), Paragraph('-', compact_style), Paragraph('-', compact_style), Paragraph('-', compact_style), Paragraph('-', compact_style)])
    schedule_table = Table(schedule_rows, repeatRows=1, colWidths=[46 * mm, 50 * mm, 18 * mm, 18 * mm, 18 * mm, 30 * mm])
    schedule_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#344054')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('BOX', (0, 0), (-1, -1), 0.45, colors.HexColor('#d0d5dd')),
        ('INNERGRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#e4e7ec')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.extend([Paragraph("Scheduled training and events", section_style), schedule_table, Spacer(1, 6)])

    deferral_header = [Paragraph("<b>Course</b>", compact_style), Paragraph("<b>Original due</b>", compact_style), Paragraph("<b>Requested due</b>", compact_style), Paragraph("<b>Status</b>", compact_style), Paragraph("<b>Requested at</b>", compact_style), Paragraph("<b>Decision</b>", compact_style)]
    deferral_rows = [deferral_header]
    for item in deferrals:
        course = course_by_id.get(item.course_id)
        deferral_rows.append([
            Paragraph(getattr(course, 'course_name', None) or str(item.course_id), compact_style),
            Paragraph(_fmt_date(item.original_due_date), compact_style),
            Paragraph(_fmt_date(item.requested_new_due_date), compact_style),
            Paragraph(str(item.status), compact_style),
            Paragraph(_fmt_date(item.requested_at), compact_style),
            Paragraph(item.decision_comment or '-', compact_style),
        ])
    if len(deferral_rows) == 1:
        deferral_rows.append([Paragraph('-', compact_style), Paragraph('-', compact_style), Paragraph('-', compact_style), Paragraph('No deferral requests on record.', compact_style), Paragraph('-', compact_style), Paragraph('-', compact_style)])
    deferral_table = Table(deferral_rows, repeatRows=1, colWidths=[46 * mm, 22 * mm, 22 * mm, 22 * mm, 22 * mm, 42 * mm])
    deferral_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#175cd3')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#eff8ff')]),
        ('BOX', (0, 0), (-1, -1), 0.45, colors.HexColor('#d0d5dd')),
        ('INNERGRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#e4e7ec')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.extend([Paragraph("Deferral and extension history", section_style), deferral_table])

    canvas_meta = {
        'logo_path': logo_path,
        'amo_name': getattr(amo, 'name', None) or getattr(amo, 'amo_code', None) or getattr(user, 'amo_id', None),
        'printed_at': printed_at,
    }
    doc.build(story, canvasmaker=_training_canvas_maker(canvas_meta))
    buffer.seek(0)
    return buffer.read()


def _normalize_pagination(limit: int, offset: int) -> Tuple[int, int]:
    if limit <= 0:
        limit = 50
    if limit > _MAX_PAGE_SIZE:
        limit = _MAX_PAGE_SIZE
    if offset < 0:
        offset = 0
    return limit, offset


def _ensure_training_upload_path(path: Path) -> Path:
    resolved = path.resolve()
    if not str(resolved).startswith(str(_TRAINING_UPLOAD_DIR)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid training upload path.",
        )
    return resolved


def _require_training_editor(
    current_user: accounts_models.User = Depends(get_current_active_user),
) -> accounts_models.User:
    """
    Allow edits only for:
    - SUPERUSER
    - AMO_ADMIN
    - QUALITY_MANAGER
    - Any user whose department.code == 'QUALITY'

    Block system / service accounts even if flags are set.
    """
    if getattr(current_user, "is_system_account", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System/service accounts cannot manage training records.",
        )

    if getattr(current_user, "is_superuser", False) or getattr(current_user, "is_amo_admin", False):
        return current_user

    if current_user.role == accounts_models.AccountRole.QUALITY_MANAGER:
        return current_user

    dept = getattr(current_user, "department", None)
    if dept is not None and getattr(dept, "code", "").upper() == "QUALITY":
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only Quality department or AMO Admin may modify training data.",
    )


def _is_training_editor(user: accounts_models.User) -> bool:
    try:
        _require_training_editor(user)  # type: ignore[arg-type]
        return True
    except HTTPException:
        return False


def _get_user_department_code(user: accounts_models.User) -> Optional[str]:
    dept = getattr(user, "department", None)
    code = getattr(dept, "code", None) if dept is not None else None
    return code.upper() if isinstance(code, str) and code.strip() else None


def _get_user_job_role(user: accounts_models.User) -> Optional[str]:
    """
    Best-effort extraction. Adjust these attribute names if your User model differs.
    """
    for attr in ("job_role", "job_title", "position", "title", "designation"):
        v = getattr(user, attr, None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _add_months(base: date, months: int) -> date:
    return training_compliance.add_months(base, months)


def _audit(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: Optional[str],
    action: str,
    entity_type: str,
    entity_id: Optional[str],
    details: Optional[dict] = None,
) -> None:
    """
    Best-effort audit log. Never blocks the main action if logging fails.
    """
    try:
        audit_services.log_event(
            db,
            amo_id=amo_id,
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else "unknown",
            action=action,
            after=details,
            metadata={"module": "training"},
        )
        log = training_models.TrainingAuditLog(
            amo_id=amo_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
        )
        db.add(log)
    except Exception:
        # Intentionally swallow to avoid breaking ops due to logging
        return


def _create_notification(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    title: str,
    body: Optional[str],
    severity: training_models.TrainingNotificationSeverity = training_models.TrainingNotificationSeverity.INFO,
    link_path: Optional[str] = None,
    dedupe_key: Optional[str] = None,
    created_by_user_id: Optional[str] = None,
) -> None:
    """
    Creates an in-app notification. Uses dedupe_key to prevent spamming.
    """
    if dedupe_key:
        existing = (
            db.query(training_models.TrainingNotification)
            .filter(
                training_models.TrainingNotification.amo_id == amo_id,
                training_models.TrainingNotification.user_id == user_id,
                training_models.TrainingNotification.dedupe_key == dedupe_key,
            )
            .first()
        )
        if existing:
            return

    n = training_models.TrainingNotification(
        amo_id=amo_id,
        user_id=user_id,
        title=title,
        body=body,
        severity=severity,
        link_path=link_path,
        dedupe_key=dedupe_key,
        created_by_user_id=created_by_user_id,
    )
    db.add(n)
    account_services.record_usage(
        db,
        amo_id=amo_id,
        meter_key=account_services.METER_KEY_NOTIFICATIONS,
        quantity=1,
        commit=False,
    )


def _maybe_send_email(background_tasks: BackgroundTasks, to_email: Optional[str], subject: str, body: str) -> None:
    """
    Optional email hook (safe-by-default).
    If SMTP env vars are not set, this does nothing.

    Env expected:
      SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM
    """
    if not to_email or not isinstance(to_email, str) or "@" not in to_email:
        return

    host = os.getenv("SMTP_HOST")
    port = os.getenv("SMTP_PORT")
    user = os.getenv("SMTP_USER")
    pwd = os.getenv("SMTP_PASS")
    sender = os.getenv("SMTP_FROM")

    if not (host and port and sender):
        return

    def _send() -> None:
        import smtplib
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)

        with smtplib.SMTP(host, int(port)) as s:
            s.starttls()
            if user and pwd:
                s.login(user, pwd)
            s.send_message(msg)

    background_tasks.add_task(_send)


def _preferred_phone(user: object) -> Optional[str]:
    primary = _preferred_phone(user)
    secondary = getattr(user, "secondary_phone", None)
    return primary or secondary


def _maybe_send_whatsapp(background_tasks: BackgroundTasks, to_phone: Optional[str], message: str) -> None:
    """
    Optional WhatsApp hook (safe-by-default).
    If WHATSAPP_WEBHOOK_URL is not set, this does nothing.

    Env expected:
      WHATSAPP_WEBHOOK_URL
      WHATSAPP_WEBHOOK_BEARER (optional)
    """
    if not to_phone or not isinstance(to_phone, str):
        return

    url = os.getenv("WHATSAPP_WEBHOOK_URL")
    if not url:
        return

    token = os.getenv("WHATSAPP_WEBHOOK_BEARER")

    def _send() -> None:
        payload = json.dumps({"to": to_phone, "message": message}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=10):
            pass

    background_tasks.add_task(_send)


def _build_status_item_from_dates(
    *,
    course: training_models.TrainingCourse,
    last_completion_date: Optional[date],
    due_date: Optional[date],
    deferral_due: Optional[date],
    upcoming_event_id: Optional[str],
    upcoming_event_date: Optional[date],
    today: date,
) -> training_schemas.TrainingStatusItem:
    return training_compliance.build_status_item_from_dates(
        course=course,
        last_completion_date=last_completion_date,
        due_date=due_date,
        deferral_due=deferral_due,
        upcoming_event_id=upcoming_event_id,
        upcoming_event_date=upcoming_event_date,
        today=today,
    )


def _event_to_read(event: training_models.TrainingEvent) -> training_schemas.TrainingEventRead:
    return training_schemas.TrainingEventRead(
        id=event.id,
        amo_id=event.amo_id,
        course_pk=event.course_id,
        title=event.title,
        location=event.location,
        provider=event.provider,
        starts_on=event.starts_on,
        ends_on=event.ends_on,
        status=event.status,
        notes=event.notes,
        created_by_user_id=event.created_by_user_id,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


def _participant_to_read(p: training_models.TrainingEventParticipant) -> training_schemas.TrainingEventParticipantRead:
    return training_schemas.TrainingEventParticipantRead(
        id=p.id,
        amo_id=p.amo_id,
        event_id=p.event_id,
        user_id=p.user_id,
        status=p.status,
        attendance_note=p.attendance_note,
        notes=getattr(p, "notes", None),
        deferral_request_id=p.deferral_request_id,
        attendance_marked_at=getattr(p, "attendance_marked_at", None),
        attendance_marked_by_user_id=getattr(p, "attendance_marked_by_user_id", None),
        attended_at=p.attended_at,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )




def _record_to_read(r: training_models.TrainingRecord) -> training_schemas.TrainingRecordRead:
    return training_schemas.TrainingRecordRead(
        id=r.id,
        amo_id=r.amo_id,
        user_id=r.user_id,
        course_pk=r.course_id,
        event_id=r.event_id,
        completion_date=r.completion_date,
        valid_until=r.valid_until,
        hours_completed=r.hours_completed,
        exam_score=r.exam_score,
        certificate_reference=r.certificate_reference,
        remarks=r.remarks,
        is_manual_entry=r.is_manual_entry,
        created_by_user_id=r.created_by_user_id,
        created_at=r.created_at,
        updated_at=getattr(r, "updated_at", None),
        course_id=r.course_id,
        legacy_record_id=_extract_record_remark_token(getattr(r, "remarks", None), "RecordID"),
        source_status=_record_source_status(r),
        record_status=_record_lifecycle_status(r),
        superseded_by_record_id=getattr(r, "superseded_by_record_id", None),
        superseded_at=getattr(r, "superseded_at", None),
        purge_after=getattr(r, "purge_after", None),
        verification_status=r.verification_status,
        verified_at=r.verified_at,
        verified_by_user_id=r.verified_by_user_id,
        verification_comment=r.verification_comment,
    )


def _deferral_to_read(d: training_models.TrainingDeferralRequest) -> training_schemas.TrainingDeferralRequestRead:
    return training_schemas.TrainingDeferralRequestRead(
        id=d.id,
        amo_id=d.amo_id,
        user_id=d.user_id,
        course_pk=d.course_id,
        original_due_date=d.original_due_date,
        requested_new_due_date=d.requested_new_due_date,
        reason_category=d.reason_category,
        reason_text=d.reason_text,
        status=d.status,
        requested_by_user_id=d.requested_by_user_id,
        requested_at=d.requested_at,
        decided_at=d.decided_at,
        decided_by_user_id=d.decided_by_user_id,
        decision_comment=d.decision_comment,
        updated_at=getattr(d, "updated_at", None),
    )


def _requirement_to_read(r: training_models.TrainingRequirement) -> training_schemas.TrainingRequirementRead:
    return training_schemas.TrainingRequirementRead(
        id=r.id,
        amo_id=r.amo_id,
        course_pk=r.course_id,
        scope=r.scope,
        department_code=r.department_code,
        job_role=r.job_role,
        user_id=r.user_id,
        is_mandatory=r.is_mandatory,
        is_active=r.is_active,
        effective_from=r.effective_from,
        effective_to=r.effective_to,
        created_by_user_id=r.created_by_user_id,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def _notification_to_read(n: training_models.TrainingNotification) -> training_schemas.TrainingNotificationRead:
    return training_schemas.TrainingNotificationRead(
        id=n.id,
        amo_id=n.amo_id,
        user_id=n.user_id,
        title=n.title,
        body=n.body,
        severity=n.severity,
        link_path=n.link_path,
        dedupe_key=n.dedupe_key,
        created_by_user_id=n.created_by_user_id,
        created_at=n.created_at,
        read_at=n.read_at,
    )


def _file_to_read(f: training_models.TrainingFile) -> training_schemas.TrainingFileRead:
    return training_schemas.TrainingFileRead(
        id=f.id,
        amo_id=f.amo_id,
        owner_user_id=f.owner_user_id,
        kind=f.kind,
        course_id=f.course_id,
        event_id=f.event_id,
        record_id=f.record_id,
        deferral_request_id=f.deferral_request_id,
        original_filename=f.original_filename,
        storage_path=f.storage_path,
        content_type=f.content_type,
        size_bytes=f.size_bytes,
        sha256=f.sha256,
        review_status=f.review_status,
        reviewed_at=f.reviewed_at,
        reviewed_by_user_id=f.reviewed_by_user_id,
        review_comment=f.review_comment,
        uploaded_by_user_id=f.uploaded_by_user_id,
        uploaded_at=f.uploaded_at,
    )


# ---------------------------------------------------------------------------
# COURSES
# ---------------------------------------------------------------------------


@router.get(
    "/courses",
    response_model=List[training_schemas.TrainingCourseRead],
    summary="List training courses for the current AMO",
)
def list_courses(
    include_inactive: bool = False,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    limit, offset = _normalize_pagination(limit, offset)
    _ensure_training_catalog_schema_compat(db)

    q = db.query(training_models.TrainingCourse).filter(
        training_models.TrainingCourse.amo_id == current_user.amo_id
    )
    if not include_inactive:
        q = q.filter(training_models.TrainingCourse.is_active.is_(True))

    return q.order_by(training_models.TrainingCourse.course_id.asc()).offset(offset).limit(limit).all()


@router.get(
    "/courses/{course_pk}",
    response_model=training_schemas.TrainingCourseRead,
    summary="Get a single training course by id",
)
def get_course(
    course_pk: str,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    _ensure_training_catalog_schema_compat(db)
    course = (
        db.query(training_models.TrainingCourse)
        .filter(
            training_models.TrainingCourse.id == course_pk,
            training_models.TrainingCourse.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training course not found for your AMO.")
    return course


@router.post(
    "/courses",
    response_model=training_schemas.TrainingCourseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a training course (Quality / AMO admin only)",
)
def create_course(
    payload: training_schemas.TrainingCourseCreate,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    course_id_norm = payload.course_id.strip().upper()

    existing = (
        db.query(training_models.TrainingCourse)
        .filter(
            training_models.TrainingCourse.amo_id == current_user.amo_id,
            training_models.TrainingCourse.course_id == course_id_norm,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A course with this CourseID already exists.")

    course = training_models.TrainingCourse(
        amo_id=current_user.amo_id,
        course_id=course_id_norm,
        course_name=payload.course_name.strip(),
        frequency_months=payload.frequency_months,
        category=payload.category,
        category_raw=(payload.category_raw.strip() if payload.category_raw else None),
        status=payload.status.strip(),
        scope=(payload.scope.strip() if payload.scope else None),
        kind=payload.kind,
        delivery_method=payload.delivery_method,
        regulatory_reference=payload.regulatory_reference,
        default_provider=payload.default_provider,
        default_duration_days=payload.default_duration_days,
        is_mandatory=payload.is_mandatory,
        mandatory_for_all=payload.mandatory_for_all,
        prerequisite_course_id=payload.prerequisite_course_id,
        is_active=True,
        created_by_user_id=current_user.id,
        updated_by_user_id=current_user.id,
    )

    db.add(course)
    _audit(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        action="COURSE_CREATE",
        entity_type="TrainingCourse",
        entity_id=None,
        details={"course_id": course_id_norm, "course_name": payload.course_name},
    )
    db.commit()
    db.refresh(course)
    return course


@router.post(
    "/courses/import",
    response_model=training_schemas.CourseImportSummary,
    summary="Import training courses from Courses worksheet (dry-run by default)",
)
async def import_courses(
    file: UploadFile = File(...),
    dry_run: bool = True,
    sheet_name: str = "Courses",
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    try:
        rows = parse_courses_sheet(content, filename=file.filename or "courses.xlsx", sheet_name=sheet_name)
        summary = import_courses_rows(db, amo_id=current_user.amo_id, rows=rows, dry_run=dry_run)
        return summary
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Courses import database error: {exc}")




@router.post(
    "/records/import",
    response_model=training_schemas.TrainingRecordImportSummary,
    summary="Import training history from Training worksheet (dry-run by default)",
)
async def import_training_records(
    file: UploadFile = File(...),
    dry_run: bool = True,
    sheet_name: str = "Training",
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    try:
        rows = parse_training_records_sheet(content, filename=file.filename or "training.xlsx", sheet_name=sheet_name)
        summary = import_training_records_rows(
            db,
            amo_id=current_user.amo_id,
            rows=rows,
            dry_run=dry_run,
            actor_user_id=current_user.id,
        )
        return summary
    except (ValueError, RuntimeError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Training records import database error: {exc}")


@router.put(
    "/courses/{course_pk}",
    response_model=training_schemas.TrainingCourseRead,
    summary="Update a training course (Quality / AMO admin only)",
)
def update_course(
    course_pk: str,
    payload: training_schemas.TrainingCourseUpdate,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    course = (
        db.query(training_models.TrainingCourse)
        .filter(
            training_models.TrainingCourse.id == course_pk,
            training_models.TrainingCourse.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training course not found for your AMO.")

    update_data = payload.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(course, field, value)

    course.updated_by_user_id = current_user.id

    _audit(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        action="COURSE_UPDATE",
        entity_type="TrainingCourse",
        entity_id=course.id,
        details={"changes": update_data},
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


# ---------------------------------------------------------------------------
# REQUIREMENTS (WHO MUST HAVE WHAT) - IOSA STYLE MATRIX
# ---------------------------------------------------------------------------


@router.get(
    "/requirements",
    response_model=List[training_schemas.TrainingRequirementRead],
    summary="List training requirements (Quality / AMO admin only)",
)
def list_requirements(
    include_inactive: bool = False,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    limit, offset = _normalize_pagination(limit, offset)

    q = db.query(training_models.TrainingRequirement).filter(training_models.TrainingRequirement.amo_id == current_user.amo_id)
    if not include_inactive:
        q = q.filter(training_models.TrainingRequirement.is_active.is_(True))

    reqs = q.order_by(training_models.TrainingRequirement.created_at.desc()).offset(offset).limit(limit).all()
    return [_requirement_to_read(r) for r in reqs]


@router.post(
    "/requirements",
    response_model=training_schemas.TrainingRequirementRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a training requirement rule (Quality / AMO admin only)",
)
def create_requirement(
    payload: training_schemas.TrainingRequirementCreate,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    course = (
        db.query(training_models.TrainingCourse)
        .filter(training_models.TrainingCourse.id == payload.course_pk, training_models.TrainingCourse.amo_id == current_user.amo_id)
        .first()
    )
    if not course:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid course for this AMO.")

    # Basic scope sanity checks
    if payload.scope == training_models.TrainingRequirementScope.DEPARTMENT and not payload.department_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="department_code is required for scope=DEPARTMENT.")
    if payload.scope == training_models.TrainingRequirementScope.JOB_ROLE and not payload.job_role:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="job_role is required for scope=JOB_ROLE.")
    if payload.scope == training_models.TrainingRequirementScope.USER and not payload.user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id is required for scope=USER.")

    req = training_models.TrainingRequirement(
        amo_id=current_user.amo_id,
        course_id=course.id,
        scope=payload.scope,
        department_code=(payload.department_code.strip().upper() if payload.department_code else None),
        job_role=(payload.job_role.strip() if payload.job_role else None),
        user_id=payload.user_id,
        is_mandatory=payload.is_mandatory,
        is_active=payload.is_active,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        created_by_user_id=current_user.id,
    )

    db.add(req)
    _audit(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        action="REQUIREMENT_CREATE",
        entity_type="TrainingRequirement",
        entity_id=None,
        details=payload.model_dump(),
    )
    db.commit()
    db.refresh(req)
    return _requirement_to_read(req)


@router.put(
    "/requirements/{requirement_id}",
    response_model=training_schemas.TrainingRequirementRead,
    summary="Update a training requirement rule (Quality / AMO admin only)",
)
def update_requirement(
    requirement_id: str,
    payload: training_schemas.TrainingRequirementUpdate,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    req = (
        db.query(training_models.TrainingRequirement)
        .filter(training_models.TrainingRequirement.id == requirement_id, training_models.TrainingRequirement.amo_id == current_user.amo_id)
        .first()
    )
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirement rule not found.")

    data = payload.model_dump(exclude_unset=True)

    if "department_code" in data and data["department_code"]:
        data["department_code"] = data["department_code"].strip().upper()
    if "job_role" in data and data["job_role"]:
        data["job_role"] = data["job_role"].strip()

    for k, v in data.items():
        setattr(req, k, v)

    _audit(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        action="REQUIREMENT_UPDATE",
        entity_type="TrainingRequirement",
        entity_id=req.id,
        details={"changes": data},
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return _requirement_to_read(req)


# ---------------------------------------------------------------------------
# EVENTS
# ---------------------------------------------------------------------------


@router.get(
    "/events",
    response_model=List[training_schemas.TrainingEventRead],
    summary="List training events for the current AMO",
)
def list_events(
    course_pk: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    limit, offset = _normalize_pagination(limit, offset)
    _ensure_training_catalog_schema_compat(db)

    q = db.query(training_models.TrainingEvent).filter(training_models.TrainingEvent.amo_id == current_user.amo_id)

    if course_pk:
        q = q.filter(training_models.TrainingEvent.course_id == course_pk)
    if from_date:
        q = q.filter(training_models.TrainingEvent.starts_on >= from_date)
    if to_date:
        q = q.filter(training_models.TrainingEvent.starts_on <= to_date)

    events = q.order_by(training_models.TrainingEvent.starts_on.asc()).offset(offset).limit(limit).all()
    return [_event_to_read(e) for e in events]


@router.get(
    "/events/me/upcoming",
    response_model=List[training_schemas.TrainingEventRead],
    summary="List upcoming training events for the current user",
)
def list_my_upcoming_events(
    from_date: Optional[date] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    limit, offset = _normalize_pagination(limit, offset)
    if from_date is None:
        from_date = date.today()

    q = (
        db.query(training_models.TrainingEvent)
        .join(training_models.TrainingEventParticipant, training_models.TrainingEvent.id == training_models.TrainingEventParticipant.event_id)
        .filter(
            training_models.TrainingEvent.amo_id == current_user.amo_id,
            training_models.TrainingEvent.starts_on >= from_date,
            training_models.TrainingEventParticipant.user_id == current_user.id,
            training_models.TrainingEventParticipant.status.in_(
                [
                    training_models.TrainingParticipantStatus.SCHEDULED,
                    training_models.TrainingParticipantStatus.INVITED,
                    training_models.TrainingParticipantStatus.CONFIRMED,
                ]
            ),
            training_models.TrainingEvent.status.in_(
                [training_models.TrainingEventStatus.PLANNED, training_models.TrainingEventStatus.IN_PROGRESS]
            ),
        )
        .order_by(training_models.TrainingEvent.starts_on.asc())
        .offset(offset)
        .limit(limit)
    )

    events = q.all()
    return [_event_to_read(e) for e in events]


@router.get(
    "/events/{event_id}/participants",
    response_model=List[training_schemas.TrainingEventParticipantRead],
    summary="List participants for a training event",
)
def list_event_participants(
    event_id: str,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    event = (
        db.query(training_models.TrainingEvent)
        .filter(training_models.TrainingEvent.id == event_id, training_models.TrainingEvent.amo_id == current_user.amo_id)
        .first()
    )
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training event not found for your AMO.")

    # Privacy: non-editors can only see participants if they are in the event.
    if not _is_training_editor(current_user):
        is_in_event = (
            db.query(training_models.TrainingEventParticipant)
            .filter(
                training_models.TrainingEventParticipant.event_id == event.id,
                training_models.TrainingEventParticipant.user_id == current_user.id,
            )
            .first()
            is not None
        )
        if not is_in_event:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view event participants.")

    participants = (
        db.query(training_models.TrainingEventParticipant)
        .filter(
            training_models.TrainingEventParticipant.event_id == event.id,
            training_models.TrainingEventParticipant.amo_id == current_user.amo_id,
        )
        .order_by(training_models.TrainingEventParticipant.id.asc())
        .all()
    )
    return [_participant_to_read(p) for p in participants]


@router.post(
    "/events",
    response_model=training_schemas.TrainingEventRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a training event (Quality / AMO admin only)",
)
def create_event(
    payload: training_schemas.TrainingEventCreate,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    course = (
        db.query(training_models.TrainingCourse)
        .filter(training_models.TrainingCourse.id == payload.course_pk, training_models.TrainingCourse.amo_id == current_user.amo_id)
        .first()
    )
    if not course:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid course for this AMO.")

    event = training_models.TrainingEvent(
        amo_id=current_user.amo_id,
        course_id=course.id,
        title=payload.title or course.course_name,
        location=payload.location,
        provider=payload.provider or course.default_provider,
        starts_on=payload.starts_on,
        ends_on=payload.ends_on,
        status=payload.status,
        notes=payload.notes,
        created_by_user_id=current_user.id,
    )

    db.add(event)
    _audit(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        action="EVENT_CREATE",
        entity_type="TrainingEvent",
        entity_id=None,
        details={"course_id": course.id, "starts_on": str(payload.starts_on), "title": payload.title},
    )
    db.commit()
    db.refresh(event)
    return _event_to_read(event)


@router.put(
    "/events/{event_id}",
    response_model=training_schemas.TrainingEventRead,
    summary="Update a training event (Quality / AMO admin only)",
)
def update_event(
    event_id: str,
    payload: training_schemas.TrainingEventUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    event = (
        db.query(training_models.TrainingEvent)
        .filter(training_models.TrainingEvent.id == event_id, training_models.TrainingEvent.amo_id == current_user.amo_id)
        .first()
    )
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training event not found for your AMO.")

    old_starts_on = event.starts_on
    old_status = event.status
    old_title = event.title

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(event, field, value)

    db.add(event)

    _audit(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        action="EVENT_UPDATE",
        entity_type="TrainingEvent",
        entity_id=event.id,
        details={"changes": data},
    )

    if "status" in data and data["status"] != old_status:
        try:
            apply_transition(
                db,
                actor_user_id=current_user.id,
                entity_type="training_event",
                entity_id=event.id,
                from_state=old_status.value,
                to_state=event.status.value,
                before_obj={
                    "status": old_status.value,
                    "amo_id": current_user.amo_id,
                },
                after_obj={
                    "status": event.status.value,
                    "starts_on": str(event.starts_on),
                    "amo_id": current_user.amo_id,
                },
                critical=False,
            )
        except TransitionError as exc:
            return JSONResponse(status_code=400, content={"error": exc.code, "detail": exc.detail})

    # If key scheduling attributes changed, notify participants
    key_changed = False
    if "starts_on" in data and data["starts_on"] != old_starts_on:
        key_changed = True
    if "status" in data and data["status"] != old_status:
        key_changed = True
    if "title" in data and data["title"] != old_title:
        key_changed = True

    if key_changed:
        participants = (
            db.query(training_models.TrainingEventParticipant)
            .filter(
                training_models.TrainingEventParticipant.amo_id == current_user.amo_id,
                training_models.TrainingEventParticipant.event_id == event.id,
            )
            .all()
        )
        for p in participants:
            title = "Training event updated"
            body = f"Your training session '{event.title}' has been updated. Start date: {event.starts_on}."
            severity = training_models.TrainingNotificationSeverity.INFO

            if event.status == training_models.TrainingEventStatus.CANCELLED:
                title = "Training event cancelled"
                body = f"Your training session '{event.title}' scheduled on {event.starts_on} has been cancelled."
                severity = training_models.TrainingNotificationSeverity.WARNING

            dedupe_key = f"event:{event.id}:status:{event.status}:start:{event.starts_on.isoformat()}"
            _create_notification(
                db,
                amo_id=current_user.amo_id,
                user_id=p.user_id,
                title=title,
                body=body,
                severity=severity,
                link_path=f"/training/events/{event.id}",
                dedupe_key=dedupe_key,
                created_by_user_id=current_user.id,
            )

            # Optional email hook
            trainee = db.query(accounts_models.User).filter(accounts_models.User.id == p.user_id).first()
            if trainee:
                _maybe_send_email(background_tasks, getattr(trainee, "email", None), title, body)
                _maybe_send_whatsapp(background_tasks, _preferred_phone(trainee), body)

    db.commit()
    db.refresh(event)
    return _event_to_read(event)


# ---------------------------------------------------------------------------
# EVENT PARTICIPANTS
# ---------------------------------------------------------------------------


@router.post(
    "/event-participants",
    response_model=training_schemas.TrainingEventParticipantRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a participant to a training event (Quality / AMO admin only)",
)
def add_event_participant(
    payload: training_schemas.TrainingEventParticipantCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    event = (
        db.query(training_models.TrainingEvent)
        .filter(training_models.TrainingEvent.id == payload.event_id, training_models.TrainingEvent.amo_id == current_user.amo_id)
        .first()
    )
    if not event:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Event not found for your AMO.")

    trainee = (
        db.query(accounts_models.User)
        .filter(accounts_models.User.id == payload.user_id, accounts_models.User.amo_id == current_user.amo_id)
        .first()
    )
    if not trainee:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target user not found in your AMO.")

    existing = (
        db.query(training_models.TrainingEventParticipant)
        .filter(
            training_models.TrainingEventParticipant.event_id == event.id,
            training_models.TrainingEventParticipant.user_id == trainee.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already assigned to this event.")

    participant = training_models.TrainingEventParticipant(
        amo_id=current_user.amo_id,
        event_id=event.id,
        user_id=trainee.id,
        status=payload.status,
        attendance_note=payload.attendance_note,
        deferral_request_id=payload.deferral_request_id,
    )

    db.add(participant)

    # In-app notification (popup on login)
    notif_title = "Training scheduled"
    notif_body = f"You have been scheduled for '{event.title}' on {event.starts_on}."
    dedupe_key = f"event:{event.id}:user:{trainee.id}:start:{event.starts_on.isoformat()}"
    _create_notification(
        db,
        amo_id=current_user.amo_id,
        user_id=trainee.id,
        title=notif_title,
        body=notif_body,
        severity=training_models.TrainingNotificationSeverity.ACTION_REQUIRED,
        link_path=f"/training/events/{event.id}",
        dedupe_key=dedupe_key,
        created_by_user_id=current_user.id,
    )

    # Optional email hook
    _maybe_send_email(background_tasks, getattr(trainee, "email", None), notif_title, notif_body)
    _maybe_send_whatsapp(background_tasks, _preferred_phone(trainee), notif_body)

    _audit(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        action="EVENT_PARTICIPANT_ADD",
        entity_type="TrainingEventParticipant",
        entity_id=None,
        details={"event_id": event.id, "user_id": trainee.id, "status": str(payload.status)},
    )

    if participant.status in (
        training_models.TrainingParticipantStatus.SCHEDULED,
        training_models.TrainingParticipantStatus.INVITED,
        training_models.TrainingParticipantStatus.CONFIRMED,
    ):
        due_date = event.ends_on or event.starts_on
        due_at = datetime.combine(due_date, datetime.min.time(), tzinfo=timezone.utc)
        task_services.create_task(
            db,
            amo_id=current_user.amo_id,
            title="Complete training",
            description=f"Complete training event '{event.title}'.",
            owner_user_id=participant.user_id,
            supervisor_user_id=None,
            due_at=due_at,
            entity_type="training_event_participant",
            entity_id=participant.id,
            priority=3,
        )

    db.commit()
    db.refresh(participant)
    return _participant_to_read(participant)


@router.put(
    "/event-participants/{participant_id}",
    response_model=training_schemas.TrainingEventParticipantRead,
    summary="Update a participant's status in an event (Quality / AMO admin only)",
)
def update_event_participant(
    participant_id: str,
    payload: training_schemas.TrainingEventParticipantUpdate,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    participant = (
        db.query(training_models.TrainingEventParticipant)
        .join(training_models.TrainingEvent)
        .filter(
            training_models.TrainingEventParticipant.id == participant_id,
            training_models.TrainingEvent.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not participant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training event participant not found.")

    data = payload.model_dump(exclude_unset=True)
    before_status = participant.status

    # Attendance governance: if status is being set to ATTENDED/NO_SHOW, stamp who/when
    if "status" in data and data["status"] in (
        training_models.TrainingParticipantStatus.ATTENDED,
        training_models.TrainingParticipantStatus.NO_SHOW,
    ):
        participant.attendance_marked_at = datetime.utcnow()
        participant.attendance_marked_by_user_id = current_user.id
        if data["status"] == training_models.TrainingParticipantStatus.ATTENDED and participant.attended_at is None:
            participant.attended_at = datetime.utcnow()

    for field, value in data.items():
        setattr(participant, field, value)

    if "status" in data and data["status"] != before_status:
        try:
            apply_transition(
                db,
                actor_user_id=current_user.id,
                entity_type="training_event_participant",
                entity_id=participant.id,
                from_state=before_status.value,
                to_state=participant.status.value,
                before_obj={
                    "status": before_status.value,
                    "amo_id": current_user.amo_id,
                },
                after_obj={
                    "status": participant.status.value,
                    "attendance_marked_at": str(participant.attendance_marked_at) if participant.attendance_marked_at else None,
                    "attendance_marked_by_user_id": participant.attendance_marked_by_user_id,
                    "amo_id": current_user.amo_id,
                },
                critical=False,
            )
        except TransitionError as exc:
            return JSONResponse(status_code=400, content={"error": exc.code, "detail": exc.detail})
        if data["status"] in (
            training_models.TrainingParticipantStatus.ATTENDED,
            training_models.TrainingParticipantStatus.NO_SHOW,
            training_models.TrainingParticipantStatus.CANCELLED,
        ):
            task_services.close_tasks_for_entity(
                db,
                amo_id=current_user.amo_id,
                entity_type="training_event_participant",
                entity_id=participant.id,
                actor_user_id=current_user.id,
            )

    _audit(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        action="EVENT_PARTICIPANT_UPDATE",
        entity_type="TrainingEventParticipant",
        entity_id=participant.id,
        details={"changes": data},
    )

    db.add(participant)
    db.commit()
    db.refresh(participant)
    return _participant_to_read(participant)


# ---------------------------------------------------------------------------
# TRAINING RECORDS
# ---------------------------------------------------------------------------


@router.get(
    "/records",
    response_model=List[training_schemas.TrainingRecordRead],
    summary="List training records (Quality/AMO admin sees AMO-wide; users see their own)",
)
def list_training_records(
    user_id: Optional[str] = None,
    course_pk: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    limit, offset = _normalize_pagination(limit, offset)

    is_editor = _is_training_editor(current_user)

    # Non-editors are restricted to their own records
    if not is_editor:
        user_id = current_user.id

    def _fetch_records():
        q = (
            db.query(training_models.TrainingRecord)
            .options(
                noload("*"),
                load_only(
                    training_models.TrainingRecord.id,
                    training_models.TrainingRecord.amo_id,
                    training_models.TrainingRecord.user_id,
                    training_models.TrainingRecord.course_id,
                    training_models.TrainingRecord.event_id,
                    training_models.TrainingRecord.completion_date,
                    training_models.TrainingRecord.valid_until,
                    training_models.TrainingRecord.hours_completed,
                    training_models.TrainingRecord.exam_score,
                    training_models.TrainingRecord.certificate_reference,
                    training_models.TrainingRecord.remarks,
                    training_models.TrainingRecord.is_manual_entry,
                    training_models.TrainingRecord.created_by_user_id,
                    training_models.TrainingRecord.created_at,
                    training_models.TrainingRecord.verification_status,
                    training_models.TrainingRecord.verified_at,
                    training_models.TrainingRecord.verified_by_user_id,
                    training_models.TrainingRecord.verification_comment,
                ),
            )
            .filter(training_models.TrainingRecord.amo_id == current_user.amo_id)
        )
        if user_id:
            q = q.filter(training_models.TrainingRecord.user_id == user_id)
        if course_pk:
            q = q.filter(training_models.TrainingRecord.course_id == course_pk)
        return (
            q.order_by(
                training_models.TrainingRecord.user_id.asc(),
                training_models.TrainingRecord.completion_date.desc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )

    records = _run_deadlock_retry(db, _fetch_records)
    return [_record_to_read(r) for r in records]


@router.get(
    "/records/me",
    response_model=List[training_schemas.TrainingRecordRead],
    summary="List training records for the current user",
)
def list_my_training_records(
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    limit, offset = _normalize_pagination(limit, offset)
    def _fetch_records():
        return (
            db.query(training_models.TrainingRecord)
            .options(
                noload("*"),
                load_only(
                    training_models.TrainingRecord.id,
                    training_models.TrainingRecord.amo_id,
                    training_models.TrainingRecord.user_id,
                    training_models.TrainingRecord.course_id,
                    training_models.TrainingRecord.event_id,
                    training_models.TrainingRecord.completion_date,
                    training_models.TrainingRecord.valid_until,
                    training_models.TrainingRecord.hours_completed,
                    training_models.TrainingRecord.exam_score,
                    training_models.TrainingRecord.certificate_reference,
                    training_models.TrainingRecord.remarks,
                    training_models.TrainingRecord.is_manual_entry,
                    training_models.TrainingRecord.created_by_user_id,
                    training_models.TrainingRecord.created_at,
                    training_models.TrainingRecord.verification_status,
                    training_models.TrainingRecord.verified_at,
                    training_models.TrainingRecord.verified_by_user_id,
                    training_models.TrainingRecord.verification_comment,
                ),
            )
            .filter(training_models.TrainingRecord.amo_id == current_user.amo_id, training_models.TrainingRecord.user_id == current_user.id)
            .order_by(training_models.TrainingRecord.completion_date.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    records = _run_deadlock_retry(db, _fetch_records)
    return [_record_to_read(r) for r in records]


@router.post(
    "/records",
    response_model=training_schemas.TrainingRecordRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a training completion record (Quality / AMO admin only)",
)
def create_training_record(
    payload: training_schemas.TrainingRecordCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    today = date.today()
    if payload.completion_date > today:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Completion date cannot be in the future.")

    course = (
        db.query(training_models.TrainingCourse)
        .filter(training_models.TrainingCourse.id == payload.course_pk, training_models.TrainingCourse.amo_id == current_user.amo_id)
        .first()
    )
    if not course:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid course for this AMO.")

    trainee = (
        db.query(accounts_models.User)
        .filter(accounts_models.User.id == payload.user_id, accounts_models.User.amo_id == current_user.amo_id)
        .first()
    )
    if not trainee:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target user not found in your AMO.")

    valid_until = _add_months(payload.completion_date, course.frequency_months) if course.frequency_months else None
    hours_completed = course.nominal_hours if course.nominal_hours is not None else None

    linked_file = None
    if payload.attachment_file_id:
        linked_file = (
            db.query(training_models.TrainingFile)
            .filter(
                training_models.TrainingFile.id == payload.attachment_file_id,
                training_models.TrainingFile.amo_id == current_user.amo_id,
            )
            .first()
        )
        if not linked_file:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected attachment could not be found for this AMO.")
        if linked_file.owner_user_id != trainee.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected attachment belongs to a different person.")
        if linked_file.course_id and linked_file.course_id != course.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected attachment is linked to a different course.")

    if payload.certificate_reference and not linked_file:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A certificate attachment is required when a certificate reference is provided.")
    if payload.certificate_reference and linked_file and linked_file.kind != training_models.TrainingFileKind.CERTIFICATE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The linked attachment must be uploaded as a certificate file.")

    record = training_models.TrainingRecord(
        amo_id=current_user.amo_id,
        user_id=trainee.id,
        course_id=course.id,
        event_id=payload.event_id,
        completion_date=payload.completion_date,
        valid_until=valid_until,
        hours_completed=hours_completed,
        exam_score=payload.exam_score,
        certificate_reference=payload.certificate_reference,
        remarks=payload.remarks,
        is_manual_entry=payload.is_manual_entry,
        created_by_user_id=current_user.id,
        # verification_status defaults to PENDING in model (IOSA-friendly)
    )

    db.add(record)
    db.flush()

    if linked_file is not None:
        linked_file.record_id = record.id
        linked_file.course_id = course.id
        db.add(linked_file)

    # Notify user (in-app + optional email)
    notif_title = "Training record updated"
    notif_body = f"A training record for '{course.course_name}' has been added/updated on your profile."
    _create_notification(
        db,
        amo_id=current_user.amo_id,
        user_id=trainee.id,
        title=notif_title,
        body=notif_body,
        severity=training_models.TrainingNotificationSeverity.INFO,
        link_path="/profile/training",
        dedupe_key=f"record:{trainee.id}:{course.id}:{payload.completion_date.isoformat()}",
        created_by_user_id=current_user.id,
    )
    _maybe_send_email(background_tasks, getattr(trainee, "email", None), notif_title, notif_body)
    _maybe_send_whatsapp(background_tasks, _preferred_phone(trainee), notif_body)

    _audit(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        action="RECORD_CREATE",
        entity_type="TrainingRecord",
        entity_id=None,
        details={"user_id": trainee.id, "course_id": course.id, "completion_date": str(payload.completion_date)},
    )

    db.commit()
    db.refresh(record)
    return _record_to_read(record)


@router.put(
    "/records/{record_id}/verify",
    response_model=training_schemas.TrainingRecordRead,
    summary="Verify/reject a training record (Quality / AMO admin only)",
)
def verify_training_record(
    record_id: str,
    payload: training_schemas.TrainingRecordVerify,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    record = (
        db.query(training_models.TrainingRecord)
        .filter(training_models.TrainingRecord.id == record_id, training_models.TrainingRecord.amo_id == current_user.amo_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training record not found.")

    record.verification_status = payload.verification_status
    record.verification_comment = payload.verification_comment
    record.verified_at = datetime.utcnow()
    record.verified_by_user_id = current_user.id

    # Notify user
    trainee = db.query(accounts_models.User).filter(accounts_models.User.id == record.user_id).first()
    if trainee:
        title = "Training record verified" if payload.verification_status == training_models.TrainingRecordVerificationStatus.VERIFIED else "Training record requires attention"
        body = f"Your training record has been set to '{payload.verification_status}'."
        if payload.verification_comment:
            body += f"\n\nComment: {payload.verification_comment}"

        _create_notification(
            db,
            amo_id=current_user.amo_id,
            user_id=trainee.id,
            title=title,
            body=body,
            severity=training_models.TrainingNotificationSeverity.INFO
            if payload.verification_status == training_models.TrainingRecordVerificationStatus.VERIFIED
            else training_models.TrainingNotificationSeverity.ACTION_REQUIRED,
            link_path="/profile/training",
            dedupe_key=f"record-verify:{record.id}:{payload.verification_status}",
            created_by_user_id=current_user.id,
        )
        _maybe_send_email(background_tasks, getattr(trainee, "email", None), title, body)
        _maybe_send_whatsapp(background_tasks, _preferred_phone(trainee), body)

    _audit(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        action="RECORD_VERIFY",
        entity_type="TrainingRecord",
        entity_id=record.id,
        details={"status": str(payload.verification_status), "comment": payload.verification_comment},
    )

    db.add(record)
    db.commit()
    db.refresh(record)
    return _record_to_read(record)


# ---------------------------------------------------------------------------
# DEFERRALS (QWI-026)
# ---------------------------------------------------------------------------


@router.post(
    "/deferrals",
    response_model=training_schemas.TrainingDeferralRequestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Request a training deferral",
)
def create_deferral_request(
    payload: training_schemas.TrainingDeferralRequestCreate,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    course = (
        db.query(training_models.TrainingCourse)
        .filter(training_models.TrainingCourse.id == payload.course_pk, training_models.TrainingCourse.amo_id == current_user.amo_id)
        .first()
    )
    if not course:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid course for this AMO.")

    trainee = (
        db.query(accounts_models.User)
        .filter(accounts_models.User.id == payload.user_id, accounts_models.User.amo_id == current_user.amo_id)
        .first()
    )
    if not trainee:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target user not found in your AMO.")

    is_editor = _is_training_editor(current_user)
    if not is_editor and trainee.id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only request deferrals for yourself.")

    today = date.today()
    if payload.original_due_date < today:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Training is already past due; request before expiry.")

    if (payload.original_due_date - today) < timedelta(days=3):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deferral requests must be sent at least 72 hours before the due date.",
        )

    if payload.requested_new_due_date < payload.original_due_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New due date cannot be earlier than the original due date.")

    deferral = training_models.TrainingDeferralRequest(
        amo_id=current_user.amo_id,
        user_id=trainee.id,
        requested_by_user_id=current_user.id,
        course_id=course.id,
        original_due_date=payload.original_due_date,
        requested_new_due_date=payload.requested_new_due_date,
        reason_category=payload.reason_category,
        reason_text=payload.reason_text,
        status=training_models.DeferralStatus.PENDING,
    )

    db.add(deferral)

    _audit(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        action="DEFERRAL_CREATE",
        entity_type="TrainingDeferralRequest",
        entity_id=None,
        details=payload.model_dump(),
    )

    # Notify Quality team via in-app notifications (best effort)
    # NOTE: this assumes your Quality users have department.code == 'QUALITY'
    quality_users = (
        db.query(accounts_models.User)
        .filter(accounts_models.User.amo_id == current_user.amo_id)
        .all()
    )
    for u in quality_users:
        dept_code = _get_user_department_code(u)
        if dept_code == "QUALITY" or u.role == accounts_models.AccountRole.QUALITY_MANAGER:
            _create_notification(
                db,
                amo_id=current_user.amo_id,
                user_id=u.id,
                title="Training deferral pending",
                body=f"A deferral request is pending for user {trainee.id} on course {course.course_id}.",
                severity=training_models.TrainingNotificationSeverity.ACTION_REQUIRED,
                link_path="/training/deferrals",
                dedupe_key=f"deferral-pending:{deferral.id}",
                created_by_user_id=current_user.id,
            )

    db.commit()
    db.refresh(deferral)
    return _deferral_to_read(deferral)


@router.put(
    "/deferrals/{deferral_id}",
    response_model=training_schemas.TrainingDeferralRequestRead,
    summary="Approve or reject a training deferral (Quality / AMO admin only)",
)
def update_deferral_request(
    deferral_id: str,
    payload: training_schemas.TrainingDeferralRequestUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    deferral = (
        db.query(training_models.TrainingDeferralRequest)
        .filter(training_models.TrainingDeferralRequest.id == deferral_id, training_models.TrainingDeferralRequest.amo_id == current_user.amo_id)
        .first()
    )
    if not deferral:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deferral request not found.")

    data = payload.model_dump(exclude_unset=True)
    status_value = data.get("status")

    if "requested_new_due_date" in data and data["requested_new_due_date"] is not None:
        if data["requested_new_due_date"] < deferral.original_due_date:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New due date cannot be earlier than the original due date.")
        deferral.requested_new_due_date = data["requested_new_due_date"]

    if "decision_comment" in data:
        deferral.decision_comment = data["decision_comment"]

    if status_value is not None:
        deferral.status = status_value
        deferral.decided_at = datetime.utcnow()
        deferral.decided_by_user_id = current_user.id

    db.add(deferral)

    # Notify trainee
    trainee = db.query(accounts_models.User).filter(accounts_models.User.id == deferral.user_id).first()
    if trainee and status_value is not None:
        title = f"Deferral {deferral.status}"
        body = f"Your training deferral request has been {deferral.status}."
        if deferral.decision_comment:
            body += f"\n\nComment: {deferral.decision_comment}"

        _create_notification(
            db,
            amo_id=current_user.amo_id,
            user_id=trainee.id,
            title=title,
            body=body,
            severity=training_models.TrainingNotificationSeverity.INFO
            if deferral.status == training_models.DeferralStatus.APPROVED
            else training_models.TrainingNotificationSeverity.ACTION_REQUIRED,
            link_path="/profile/training",
            dedupe_key=f"deferral:{deferral.id}:status:{deferral.status}",
            created_by_user_id=current_user.id,
        )
        _maybe_send_email(background_tasks, getattr(trainee, "email", None), title, body)
        _maybe_send_whatsapp(background_tasks, _preferred_phone(trainee), body)

    _audit(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        action="DEFERRAL_DECIDE" if status_value is not None else "DEFERRAL_UPDATE",
        entity_type="TrainingDeferralRequest",
        entity_id=deferral.id,
        details={"changes": data},
    )

    db.commit()
    db.refresh(deferral)
    return _deferral_to_read(deferral)


@router.post(
    "/deferrals/{deferral_id}/cancel",
    response_model=training_schemas.TrainingDeferralRequestRead,
    summary="Cancel a pending deferral request (requester or Quality only)",
)
def cancel_deferral_request(
    deferral_id: str,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    deferral = (
        db.query(training_models.TrainingDeferralRequest)
        .filter(training_models.TrainingDeferralRequest.id == deferral_id, training_models.TrainingDeferralRequest.amo_id == current_user.amo_id)
        .first()
    )
    if not deferral:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deferral request not found.")

    is_editor = _is_training_editor(current_user)
    if not is_editor and deferral.requested_by_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to cancel this deferral.")

    if deferral.status != training_models.DeferralStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending deferrals can be cancelled.")

    deferral.status = training_models.DeferralStatus.CANCELLED
    deferral.decided_at = datetime.utcnow()
    deferral.decided_by_user_id = current_user.id
    deferral.decision_comment = (deferral.decision_comment or "") + "\nCancelled by requester."

    _audit(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        action="DEFERRAL_CANCEL",
        entity_type="TrainingDeferralRequest",
        entity_id=deferral.id,
        details={"by": current_user.id},
    )

    db.add(deferral)
    db.commit()
    db.refresh(deferral)
    return _deferral_to_read(deferral)


@router.get(
    "/deferrals",
    response_model=List[training_schemas.TrainingDeferralRequestRead],
    summary="List training deferrals (Quality / AMO admin only)",
)
def list_deferrals(
    user_id: Optional[str] = None,
    course_pk: Optional[str] = None,
    status_filter: Optional[training_models.DeferralStatus] = None,
    only_pending: bool = False,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    limit, offset = _normalize_pagination(limit, offset)

    q = db.query(training_models.TrainingDeferralRequest).filter(training_models.TrainingDeferralRequest.amo_id == current_user.amo_id)

    if user_id:
        q = q.filter(training_models.TrainingDeferralRequest.user_id == user_id)
    if course_pk:
        q = q.filter(training_models.TrainingDeferralRequest.course_id == course_pk)
    if only_pending:
        q = q.filter(training_models.TrainingDeferralRequest.status == training_models.DeferralStatus.PENDING)
    elif status_filter is not None:
        q = q.filter(training_models.TrainingDeferralRequest.status == status_filter)

    deferrals = q.order_by(training_models.TrainingDeferralRequest.requested_at.desc()).offset(offset).limit(limit).all()
    return [_deferral_to_read(d) for d in deferrals]


@router.get(
    "/deferrals/me",
    response_model=List[training_schemas.TrainingDeferralRequestRead],
    summary="List deferrals for the current user",
)
def list_my_deferrals(
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    limit, offset = _normalize_pagination(limit, offset)
    deferrals = (
        db.query(training_models.TrainingDeferralRequest)
        .filter(training_models.TrainingDeferralRequest.amo_id == current_user.amo_id, training_models.TrainingDeferralRequest.user_id == current_user.id)
        .order_by(training_models.TrainingDeferralRequest.requested_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_deferral_to_read(d) for d in deferrals]


# ---------------------------------------------------------------------------
# FILES (UPLOAD / REVIEW / DOWNLOAD)
# ---------------------------------------------------------------------------


@router.post(
    "/files/upload",
    response_model=training_schemas.TrainingFileRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload training evidence (user uploads for self; Quality can upload for anyone)",
)
def upload_training_file(
    background_tasks: BackgroundTasks,
    kind: training_models.TrainingFileKind = Form(training_models.TrainingFileKind.OTHER),
    owner_user_id: Optional[str] = Form(None),
    course_id: Optional[str] = Form(None),
    event_id: Optional[str] = Form(None),
    record_id: Optional[str] = Form(None),
    deferral_request_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    is_editor = _is_training_editor(current_user)

    # Default: user uploads for themselves
    if owner_user_id is None:
        owner_user_id = current_user.id

    # Non-editors can only upload their own evidence
    if not is_editor and owner_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only upload evidence for your own account.")

    owner = (
        db.query(accounts_models.User)
        .filter(accounts_models.User.id == owner_user_id, accounts_models.User.amo_id == current_user.amo_id)
        .first()
    )
    if not owner:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Owner user not found in your AMO.")

    # Basic FK checks (best-effort)
    if course_id:
        ok = db.query(training_models.TrainingCourse).filter(
            training_models.TrainingCourse.id == course_id,
            training_models.TrainingCourse.amo_id == current_user.amo_id,
        ).first()
        if not ok:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid course_id for this AMO.")
    if event_id:
        ok = db.query(training_models.TrainingEvent).filter(
            training_models.TrainingEvent.id == event_id,
            training_models.TrainingEvent.amo_id == current_user.amo_id,
        ).first()
        if not ok:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid event_id for this AMO.")
    if record_id:
        ok = db.query(training_models.TrainingRecord).filter(
            training_models.TrainingRecord.id == record_id,
            training_models.TrainingRecord.amo_id == current_user.amo_id,
        ).first()
        if not ok:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid record_id for this AMO.")
    if deferral_request_id:
        ok = db.query(training_models.TrainingDeferralRequest).filter(
            training_models.TrainingDeferralRequest.id == deferral_request_id,
            training_models.TrainingDeferralRequest.amo_id == current_user.amo_id,
        ).first()
        if not ok:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid deferral_request_id for this AMO.")

    original_name = file.filename or "upload.bin"
    ext = "".join(Path(original_name).suffixes)[-20:]  # guard weird names
    file_id = training_models.generate_user_id()  # stable name + DB id
    amo_folder = _ensure_training_upload_path(_TRAINING_UPLOAD_DIR / current_user.amo_id)
    amo_folder.mkdir(parents=True, exist_ok=True)
    dest_path = _ensure_training_upload_path(amo_folder / f"{file_id}{ext}")

    sha = hashlib.sha256()
    total = 0

    with dest_path.open("wb") as out:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if _MAX_UPLOAD_BYTES and total > _MAX_UPLOAD_BYTES:
                try:
                    out.close()
                    dest_path.unlink(missing_ok=True)
                except Exception:
                    pass
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large.")
            sha.update(chunk)
            out.write(chunk)

    f = training_models.TrainingFile(
        id=file_id,
        amo_id=current_user.amo_id,
        owner_user_id=owner.id,
        kind=kind,
        course_id=course_id,
        event_id=event_id,
        record_id=record_id,
        deferral_request_id=deferral_request_id,
        original_filename=original_name,
        storage_path=str(dest_path),
        content_type=file.content_type,
        size_bytes=total,
        sha256=sha.hexdigest(),
        review_status=training_models.TrainingFileReviewStatus.PENDING,
        uploaded_by_user_id=current_user.id,
    )

    db.add(f)

    account_services.record_usage(
        db,
        amo_id=current_user.amo_id,
        meter_key=account_services.METER_KEY_STORAGE_MB,
        quantity=account_services.megabytes_from_bytes(total),
        commit=False,
    )

    # Notify Quality (and optionally the owner)
    _create_notification(
        db,
        amo_id=current_user.amo_id,
        user_id=owner.id,
        title="Evidence uploaded",
        body=f"Your document '{original_name}' was uploaded and is pending review.",
        severity=training_models.TrainingNotificationSeverity.INFO,
        link_path="/profile/training",
        dedupe_key=f"file:{file_id}:uploaded",
        created_by_user_id=current_user.id,
    )

    _audit(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        action="FILE_UPLOAD",
        entity_type="TrainingFile",
        entity_id=file_id,
        details={"owner_user_id": owner.id, "kind": str(kind), "filename": original_name},
    )

    db.commit()
    db.refresh(f)

    return _file_to_read(f)


@router.get(
    "/files",
    response_model=List[training_schemas.TrainingFileRead],
    summary="List training files (Quality sees AMO-wide; users see their own)",
)
def list_training_files(
    owner_user_id: Optional[str] = None,
    kind: Optional[training_models.TrainingFileKind] = None,
    review_status: Optional[training_models.TrainingFileReviewStatus] = None,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    limit, offset = _normalize_pagination(limit, offset)
    is_editor = _is_training_editor(current_user)

    if not is_editor:
        owner_user_id = current_user.id

    q = db.query(training_models.TrainingFile).filter(training_models.TrainingFile.amo_id == current_user.amo_id)

    if owner_user_id:
        q = q.filter(training_models.TrainingFile.owner_user_id == owner_user_id)
    if kind is not None:
        q = q.filter(training_models.TrainingFile.kind == kind)
    if review_status is not None:
        q = q.filter(training_models.TrainingFile.review_status == review_status)

    files = q.order_by(training_models.TrainingFile.uploaded_at.desc()).offset(offset).limit(limit).all()
    return [_file_to_read(f) for f in files]


@router.put(
    "/files/{file_id}/review",
    response_model=training_schemas.TrainingFileRead,
    summary="Approve/reject a training file (Quality / AMO admin only)",
)
def review_training_file(
    file_id: str,
    payload: training_schemas.TrainingFileReviewUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    f = (
        db.query(training_models.TrainingFile)
        .filter(training_models.TrainingFile.id == file_id, training_models.TrainingFile.amo_id == current_user.amo_id)
        .first()
    )
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training file not found.")

    f.review_status = payload.review_status
    f.review_comment = payload.review_comment
    f.reviewed_at = datetime.utcnow()
    f.reviewed_by_user_id = current_user.id

    # Notify owner
    owner = db.query(accounts_models.User).filter(accounts_models.User.id == f.owner_user_id).first()
    if owner:
        title = "Evidence approved" if payload.review_status == training_models.TrainingFileReviewStatus.APPROVED else "Evidence rejected"
        body = f"Your document '{f.original_filename}' has been {payload.review_status}."
        if payload.review_comment:
            body += f"\n\nComment: {payload.review_comment}"

        _create_notification(
            db,
            amo_id=current_user.amo_id,
            user_id=owner.id,
            title=title,
            body=body,
            severity=training_models.TrainingNotificationSeverity.INFO
            if payload.review_status == training_models.TrainingFileReviewStatus.APPROVED
            else training_models.TrainingNotificationSeverity.ACTION_REQUIRED,
            link_path="/profile/training",
            dedupe_key=f"file:{f.id}:review:{payload.review_status}",
            created_by_user_id=current_user.id,
        )
        _maybe_send_email(background_tasks, getattr(owner, "email", None), title, body)

    _audit(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        action="FILE_REVIEW",
        entity_type="TrainingFile",
        entity_id=f.id,
        details={"status": str(payload.review_status), "comment": payload.review_comment},
    )

    db.add(f)
    db.commit()
    db.refresh(f)
    return _file_to_read(f)


@router.get(
    "/files/{file_id}/download",
    summary="Download a training file (owner or Quality/AMO admin)",
)
def download_training_file(
    file_id: str,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    f = (
        db.query(training_models.TrainingFile)
        .filter(training_models.TrainingFile.id == file_id, training_models.TrainingFile.amo_id == current_user.amo_id)
        .first()
    )
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training file not found.")

    is_editor = _is_training_editor(current_user)
    if not is_editor and f.owner_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to download this file.")

    path = _ensure_training_upload_path(Path(f.storage_path))
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing on server storage.")

    return FileResponse(
        path=str(path),
        media_type=f.content_type or "application/octet-stream",
        filename=f.original_filename,
    )


# ---------------------------------------------------------------------------
# NOTIFICATIONS (POPUPS ON LOGIN)
# ---------------------------------------------------------------------------


@router.get(
    "/notifications/me",
    response_model=List[training_schemas.TrainingNotificationRead],
    summary="List notifications for the current user",
)
def list_my_notifications(
    unread_only: bool = False,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    limit, offset = _normalize_pagination(limit, offset)

    q = db.query(training_models.TrainingNotification).filter(
        training_models.TrainingNotification.amo_id == current_user.amo_id,
        training_models.TrainingNotification.user_id == current_user.id,
    )
    if unread_only:
        q = q.filter(training_models.TrainingNotification.read_at.is_(None))

    notes = q.order_by(training_models.TrainingNotification.created_at.desc()).offset(offset).limit(limit).all()
    return [_notification_to_read(n) for n in notes]


@router.put(
    "/notifications/{notification_id}/read",
    response_model=training_schemas.TrainingNotificationRead,
    summary="Mark a notification as read",
)
def mark_notification_read(
    notification_id: str,
    payload: training_schemas.TrainingNotificationMarkRead,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    n = (
        db.query(training_models.TrainingNotification)
        .filter(
            training_models.TrainingNotification.id == notification_id,
            training_models.TrainingNotification.amo_id == current_user.amo_id,
            training_models.TrainingNotification.user_id == current_user.id,
        )
        .first()
    )
    if not n:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")

    n.read_at = payload.read_at or datetime.utcnow()

    db.add(n)
    db.commit()
    db.refresh(n)
    return _notification_to_read(n)


@router.post(
    "/notifications/me/read-all",
    summary="Mark all notifications as read for the current user",
)
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    (
        db.query(training_models.TrainingNotification)
        .filter(
            training_models.TrainingNotification.amo_id == current_user.amo_id,
            training_models.TrainingNotification.user_id == current_user.id,
            training_models.TrainingNotification.read_at.is_(None),
        )
        .update({"read_at": datetime.utcnow()}, synchronize_session=False)
    )
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# STATUS (YOUR EXISTING LOGIC KEPT) + OPTIONAL REQUIREMENTS-BASED VIEW
# ---------------------------------------------------------------------------


@router.get(
    "/status/me",
    response_model=List[training_schemas.TrainingStatusItem],
    summary="Training status for the current user (OK / DUE_SOON / OVERDUE / DEFERRED / SCHEDULED_ONLY)",
)
def get_my_training_status(
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    return training_compliance.evaluate_user_training_policy(db, current_user, required_only=False).items


@router.get(
    "/status/me/required",
    response_model=List[training_schemas.TrainingStatusItem],
    summary="Training status for the current user, filtered by requirement matrix (IOSA-style)",
)
def get_my_required_training_status(
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    return training_compliance.evaluate_user_training_policy(db, current_user, required_only=True).items


@router.get(
    "/status/users/{user_id}",
    response_model=List[training_schemas.TrainingStatusItem],
    summary="Training status for a specific user (Quality / AMO admin only)",
)
def get_user_training_status(
    user_id: str,
    required_only: bool = True,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    user = (
        db.query(accounts_models.User)
        .filter(accounts_models.User.id == user_id, accounts_models.User.amo_id == current_user.amo_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training user not found for this AMO.")
    return training_compliance.evaluate_user_training_policy(db, user, required_only=required_only).items


@router.post(
    "/status/users/bulk",
    response_model=training_schemas.TrainingStatusBulkResponse,
    summary="Training status for multiple users in one batch (Quality / AMO admin only)",
)
def get_bulk_training_status_for_users(
    payload: training_schemas.TrainingStatusBulkRequest,
    required_only: bool = True,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    user_ids = sorted({(user_id or "").strip() for user_id in payload.user_ids if (user_id or "").strip()})
    if not user_ids:
        return training_schemas.TrainingStatusBulkResponse(users={})
    users = (
        db.query(accounts_models.User)
        .filter(accounts_models.User.amo_id == current_user.amo_id, accounts_models.User.id.in_(user_ids))
        .all()
    )
    result: Dict[str, List[training_schemas.TrainingStatusItem]] = {}
    for user in users:
        result[str(user.id)] = training_compliance.evaluate_user_training_policy(db, user, required_only=required_only).items
    for missing_id in user_ids:
        result.setdefault(missing_id, [])
    return training_schemas.TrainingStatusBulkResponse(users=result)


@router.get(
    "/status/access/me",
    response_model=training_schemas.TrainingAccessState,
    summary="Training access state for the current user",
)
def get_my_training_access_state(
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    return training_compliance.build_user_access_state(db, current_user)


@router.get(
    "/status/access/users/{user_id}",
    response_model=training_schemas.TrainingAccessState,
    summary="Training access state for a specific user (Quality / AMO admin only)",
)
def get_user_training_access_state(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    user = (
        db.query(accounts_models.User)
        .filter(accounts_models.User.id == user_id, accounts_models.User.amo_id == current_user.amo_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training user not found for this AMO.")
    return training_compliance.build_user_access_state(db, user)


@router.post(
    "/compliance/notifications/sweep",
    summary="Dispatch 60/30/15-day and day-1-overdue training notifications (Quality / AMO admin only)",
)
def run_training_notification_sweep(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    users = (
        db.query(accounts_models.User)
        .filter(accounts_models.User.amo_id == current_user.amo_id, accounts_models.User.is_active.is_(True))
        .all()
    )
    sent = 0
    evaluated = 0
    today = date.today()
    for user in users:
        if getattr(user, "is_system_account", False):
            continue
        evaluation = training_compliance.evaluate_user_training_policy(db, user, required_only=True, today=today)
        evaluated += 1
        for item in evaluation.mandatory_items:
            if item.days_until_due is None:
                continue
            if item.days_until_due not in training_compliance.REMINDER_DAY_MARKS:
                continue
            if item.status in {"OK", "DEFERRED"}:
                continue
            if item.days_until_due >= 0:
                title = f"Training due in {item.days_until_due} day(s)"
                body = f"{item.course_name} is due on {item.extended_due_date or item.valid_until}. Please schedule or complete it before your authorization is affected."
                severity = training_models.TrainingNotificationSeverity.ACTION_REQUIRED
                dedupe_key = f"training-reminder:{user.id}:{item.course_id}:{item.days_until_due}"
            else:
                overdue_days = abs(item.days_until_due)
                title = "Training overdue"
                body = f"{item.course_name} became overdue {overdue_days} day(s) ago. Portal and authorization gates may apply unless an approved deferral exists."
                severity = training_models.TrainingNotificationSeverity.WARNING
                dedupe_key = f"training-overdue:{user.id}:{item.course_id}:{overdue_days}"
            _create_notification(
                db,
                amo_id=current_user.amo_id,
                user_id=user.id,
                title=title,
                body=body,
                severity=severity,
                link_path="/maintenance/{amo}/training" if False else "/training",
                dedupe_key=dedupe_key,
                created_by_user_id=current_user.id,
            )
            _maybe_send_email(background_tasks, getattr(user, "email", None), title, body)
            _maybe_send_whatsapp(background_tasks, _preferred_phone(user), body)
            sent += 1
    db.commit()
    return {"ok": True, "evaluated_users": evaluated, "notifications_attempted": sent}


# ---------------------------------------------------------------------------
# EVIDENCE PACK EXPORTS
# ---------------------------------------------------------------------------


def _serialize_for_pdf_signature(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "value"):
        return getattr(value, "value")
    return value


def _build_training_user_pdf_cache_key(*, user, status_items, records, courses, upcoming_events, deferrals) -> str:
    payload = {
        "today": date.today().isoformat(),
        "user": {
            "id": user.id,
            "updated_at": _serialize_for_pdf_signature(getattr(user, "updated_at", None)),
            "full_name": getattr(user, "full_name", None),
            "staff_code": getattr(user, "staff_code", None),
            "role": getattr(user, "role", None),
            "position_title": getattr(user, "position_title", None),
            "is_active": getattr(user, "is_active", None),
        },
        "status_items": [
            {
                "course_id": item.course_id,
                "status": item.status,
                "last_completion_date": _serialize_for_pdf_signature(item.last_completion_date),
                "valid_until": _serialize_for_pdf_signature(item.valid_until),
                "extended_due_date": _serialize_for_pdf_signature(item.extended_due_date),
                "days_until_due": item.days_until_due,
                "upcoming_event_id": item.upcoming_event_id,
                "upcoming_event_date": _serialize_for_pdf_signature(item.upcoming_event_date),
            }
            for item in status_items
        ],
        "records": [
            {
                "id": row.id,
                "completion_date": _serialize_for_pdf_signature(row.completion_date),
                "valid_until": _serialize_for_pdf_signature(row.valid_until),
                "hours_completed": row.hours_completed,
                "exam_score": row.exam_score,
                "certificate_reference": row.certificate_reference,
                "verification_status": _serialize_for_pdf_signature(getattr(row, "verification_status", None)),
                "created_at": _serialize_for_pdf_signature(getattr(row, "created_at", None)),
                "updated_at": _serialize_for_pdf_signature(getattr(row, "updated_at", None)),
            }
            for row in records
        ],
        "courses": [
            {
                "id": row.id,
                "updated_at": _serialize_for_pdf_signature(getattr(row, "updated_at", None)),
                "course_id": row.course_id,
                "course_name": row.course_name,
                "frequency_months": row.frequency_months,
                "nominal_hours": getattr(row, "nominal_hours", None),
            }
            for row in courses
        ],
        "events": [
            {
                "id": row.id,
                "updated_at": _serialize_for_pdf_signature(getattr(row, "updated_at", None)),
                "starts_on": _serialize_for_pdf_signature(getattr(row, "starts_on", None)),
                "title": getattr(row, "title", None),
                "status": _serialize_for_pdf_signature(getattr(row, "status", None)),
            }
            for row in upcoming_events
        ],
        "deferrals": [
            {
                "id": row.id,
                "updated_at": _serialize_for_pdf_signature(getattr(row, "updated_at", None)),
                "requested_at": _serialize_for_pdf_signature(getattr(row, "requested_at", None)),
                "requested_new_due_date": _serialize_for_pdf_signature(getattr(row, "requested_new_due_date", None)),
                "status": _serialize_for_pdf_signature(getattr(row, "status", None)),
            }
            for row in deferrals
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=_serialize_for_pdf_signature).encode("utf-8")).hexdigest()


def _training_user_pdf_cache_path(user_id: str, cache_key: str) -> Path:
    return _TRAINING_RECORD_PDF_CACHE_DIR / f"{user_id}-{cache_key}.pdf"


def _clear_training_user_pdf_cache(user_id: str) -> None:
    for path in _TRAINING_RECORD_PDF_CACHE_DIR.glob(f"{user_id}-*.pdf"):
        try:
            path.unlink()
        except OSError:
            continue


def _get_training_user_record_export_context(db: Session, *, amo_id: str, user_id: str):
    user = (
        db.query(accounts_models.User)
        .filter(accounts_models.User.id == user_id, accounts_models.User.amo_id == amo_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training user not found in your AMO.")

    amo = db.query(accounts_models.AMO).filter(accounts_models.AMO.id == amo_id).first()
    logo_asset = (
        db.query(accounts_models.AMOAsset)
        .filter(
            accounts_models.AMOAsset.amo_id == amo_id,
            accounts_models.AMOAsset.kind == accounts_models.AMOAssetKind.CRS_LOGO,
            accounts_models.AMOAsset.is_active.is_(True),
        )
        .order_by(accounts_models.AMOAsset.created_at.desc())
        .first()
    )
    logo_path = None
    if logo_asset and getattr(logo_asset, "storage_path", None):
        candidate = Path(str(logo_asset.storage_path))
        if candidate.exists():
            logo_path = str(candidate)

    records = (
        db.query(training_models.TrainingRecord)
        .options(
            noload("*"),
            load_only(
                training_models.TrainingRecord.id,
                training_models.TrainingRecord.user_id,
                training_models.TrainingRecord.course_id,
                training_models.TrainingRecord.event_id,
                training_models.TrainingRecord.completion_date,
                training_models.TrainingRecord.valid_until,
                training_models.TrainingRecord.hours_completed,
                training_models.TrainingRecord.exam_score,
                training_models.TrainingRecord.certificate_reference,
                training_models.TrainingRecord.remarks,
                training_models.TrainingRecord.verification_status,
                training_models.TrainingRecord.created_at,
            ),
        )
        .filter(training_models.TrainingRecord.amo_id == amo_id, training_models.TrainingRecord.user_id == user.id)
        .order_by(training_models.TrainingRecord.completion_date.desc(), training_models.TrainingRecord.created_at.desc())
        .all()
    )
    display_records = [record for record in records if _is_record_active_for_display(record)]

    evaluation = training_compliance.evaluate_user_training_policy(db, user, required_only=False)
    course_ids = {record.course_id for record in records}
    course_ids.update({course.id for course in training_compliance.get_courses_for_user(db, user, required_only=False)})
    courses = []
    if course_ids:
        courses = (
            db.query(training_models.TrainingCourse)
            .options(noload("*"))
            .filter(training_models.TrainingCourse.amo_id == amo_id, training_models.TrainingCourse.id.in_(list(course_ids)))
            .all()
        )
    course_by_id = {course.id: course for course in courses}

    upcoming_event_ids = [item.upcoming_event_id for item in evaluation.items if item.upcoming_event_id]
    upcoming_events = []
    if upcoming_event_ids:
        upcoming_events = (
            db.query(training_models.TrainingEvent)
            .options(noload("*"))
            .filter(training_models.TrainingEvent.amo_id == amo_id, training_models.TrainingEvent.id.in_(upcoming_event_ids))
            .all()
        )

    deferrals = (
        db.query(training_models.TrainingDeferralRequest)
        .options(noload("*"))
        .filter(training_models.TrainingDeferralRequest.amo_id == amo_id, training_models.TrainingDeferralRequest.user_id == user.id)
        .order_by(training_models.TrainingDeferralRequest.requested_at.desc())
        .limit(50)
        .all()
    )

    cache_key = _build_training_user_pdf_cache_key(
        user=user,
        status_items=evaluation.items,
        records=display_records,
        courses=courses,
        upcoming_events=upcoming_events,
        deferrals=deferrals,
    )

    return {
        "user": user,
        "amo": amo,
        "logo_path": logo_path,
        "records": display_records,
        "evaluation": evaluation,
        "course_by_id": course_by_id,
        "upcoming_events": upcoming_events,
        "deferrals": deferrals,
        "cache_key": cache_key,
    }


def _write_training_user_pdf_cache(*, user_id: str, cache_key: str, pdf_bytes: bytes) -> Path:
    cache_path = _training_user_pdf_cache_path(user_id, cache_key)
    with _TRAINING_RECORD_PDF_CACHE_LOCK:
        _clear_training_user_pdf_cache(user_id)
        cache_path.write_bytes(pdf_bytes)
    return cache_path


def _build_and_cache_training_user_record_pdf(*, amo_id: str, user_id: str) -> Optional[Path]:
    db = SessionLocal()
    try:
        context = _get_training_user_record_export_context(db, amo_id=amo_id, user_id=user_id)
        cache_path = _training_user_pdf_cache_path(user_id, context["cache_key"])
        if cache_path.exists():
            return cache_path
        pdf_bytes = _build_training_user_record_pdf_bytes(
            user=context["user"],
            amo=context.get("amo"),
            logo_path=context.get("logo_path"),
            status_items=context["evaluation"].items,
            records=context["records"],
            course_by_id=context["course_by_id"],
            upcoming_events=context["upcoming_events"],
            deferrals=context["deferrals"],
        )
        return _write_training_user_pdf_cache(user_id=user_id, cache_key=context["cache_key"], pdf_bytes=pdf_bytes)
    except Exception:
        return None
    finally:
        db.close()
        with _TRAINING_RECORD_PDF_CACHE_LOCK:
            _TRAINING_RECORD_PDF_WARMING.discard(user_id)


def _queue_training_user_pdf_warm(*, amo_id: str, user_id: str) -> bool:
    with _TRAINING_RECORD_PDF_CACHE_LOCK:
        if user_id in _TRAINING_RECORD_PDF_WARMING:
            return False
        _TRAINING_RECORD_PDF_WARMING.add(user_id)
    thread = threading.Thread(target=_build_and_cache_training_user_record_pdf, kwargs={"amo_id": amo_id, "user_id": user_id}, daemon=True)
    thread.start()
    return True


@router.post(
    "/users/{user_id}/record-pdf/warm",
    summary="Warm and cache a personnel training record PDF for a specific user",
)
def warm_training_user_record_pdf(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    if current_user.id != user_id and not _is_training_editor(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient privileges to prepare training records")

    context = _get_training_user_record_export_context(db, amo_id=current_user.amo_id, user_id=user_id)
    cache_path = _training_user_pdf_cache_path(user_id, context["cache_key"])
    if cache_path.exists():
        return {"queued": False, "ready": True}

    queued = _queue_training_user_pdf_warm(amo_id=current_user.amo_id, user_id=user_id)
    return {"queued": queued, "ready": False}


@router.get(
    "/users/{user_id}/record-pdf",
    summary="Download personnel training record PDF for a specific user",
)
def export_training_user_record_pdf(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    if current_user.id != user_id and not _is_training_editor(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient privileges to export training records")

    context = _get_training_user_record_export_context(db, amo_id=current_user.amo_id, user_id=user_id)
    user = context["user"]
    cache_path = _training_user_pdf_cache_path(user_id, context["cache_key"])
    if cache_path.exists():
        pdf_bytes = cache_path.read_bytes()
    else:
        pdf_bytes = _build_training_user_record_pdf_bytes(
            user=user,
            amo=context.get("amo"),
            logo_path=context.get("logo_path"),
            status_items=context["evaluation"].items,
            records=context["records"],
            course_by_id=context["course_by_id"],
            upcoming_events=context["upcoming_events"],
            deferrals=context["deferrals"],
        )
        _write_training_user_pdf_cache(user_id=user_id, cache_key=context["cache_key"], pdf_bytes=pdf_bytes)
    filename = f"{(user.full_name or user.id).replace(' ', '_')}_training_record.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/users/{user_id}/evidence-pack",
    summary="Export a training evidence pack for a specific user",
)
def export_training_user_evidence_pack(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    if current_user.id != user_id and not _is_training_editor(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient privileges to export training packs")
    return build_evidence_pack(
        "training_user",
        user_id,
        db,
        actor_user_id=current_user.id,
        correlation_id=str(uuid.uuid4()),
        amo_id=current_user.amo_id,
    )


# ---------------------------------------------------------------------------
# GLOBAL DASHBOARD SUMMARY (AMO-WIDE) - YOUR EXISTING ENDPOINT KEPT
# ---------------------------------------------------------------------------


@router.get(
    "/dashboard/summary",
    response_model=training_schemas.TrainingDashboardSummary,
    summary="Global training dashboard summary for the current AMO (Quality / AMO admin only)",
)
def get_training_dashboard_summary(
    include_non_mandatory: bool = False,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    today = date.today()

    courses_q = db.query(training_models.TrainingCourse).filter(
        training_models.TrainingCourse.amo_id == current_user.amo_id,
        training_models.TrainingCourse.is_active.is_(True),
    )
    if not include_non_mandatory:
        courses_q = courses_q.filter(training_models.TrainingCourse.is_mandatory.is_(True))

    courses: List[training_models.TrainingCourse] = courses_q.order_by(training_models.TrainingCourse.course_id.asc()).all()

    if not courses:
        return training_schemas.TrainingDashboardSummary(
            total_mandatory_records=0, ok_count=0, due_soon_count=0, overdue_count=0, deferred_count=0
        )

    course_ids = [c.id for c in courses]

    users: List[accounts_models.User] = db.query(accounts_models.User).filter(accounts_models.User.amo_id == current_user.amo_id).all()
    if not users:
        return training_schemas.TrainingDashboardSummary(
            total_mandatory_records=0, ok_count=0, due_soon_count=0, overdue_count=0, deferred_count=0
        )

    records = (
        db.query(training_models.TrainingRecord)
        .filter(training_models.TrainingRecord.amo_id == current_user.amo_id, training_models.TrainingRecord.course_id.in_(course_ids))
        .order_by(
            training_models.TrainingRecord.user_id.asc(),
            training_models.TrainingRecord.course_id.asc(),
            training_models.TrainingRecord.completion_date.desc(),
        )
        .all()
    )
    latest_record: Dict[Tuple[str, str], training_models.TrainingRecord] = {}
    for r in records:
        key = (r.user_id, r.course_id)
        if key not in latest_record:
            latest_record[key] = r

    deferrals = (
        db.query(training_models.TrainingDeferralRequest)
        .filter(
            training_models.TrainingDeferralRequest.amo_id == current_user.amo_id,
            training_models.TrainingDeferralRequest.course_id.in_(course_ids),
            training_models.TrainingDeferralRequest.status == training_models.DeferralStatus.APPROVED,
        )
        .order_by(
            training_models.TrainingDeferralRequest.user_id.asc(),
            training_models.TrainingDeferralRequest.course_id.asc(),
            training_models.TrainingDeferralRequest.requested_new_due_date.desc(),
        )
        .all()
    )
    latest_deferral: Dict[Tuple[str, str], training_models.TrainingDeferralRequest] = {}
    for d in deferrals:
        key = (d.user_id, d.course_id)
        if key not in latest_deferral:
            latest_deferral[key] = d

    total = 0
    ok_count = 0
    due_soon_count = 0
    overdue_count = 0
    deferred_count = 0

    for user in users:
        if getattr(user, "is_system_account", False):
            continue

        for course in courses:
            total += 1
            key = (user.id, course.id)
            record = latest_record.get(key)
            deferral = latest_deferral.get(key)

            last_completion_date: Optional[date] = None
            due_date: Optional[date] = None
            deferral_due: Optional[date] = None

            if record:
                last_completion_date = record.completion_date
                due_date = record.valid_until or (_add_months(record.completion_date, course.frequency_months) if course.frequency_months else None)

            if deferral:
                deferral_due = deferral.requested_new_due_date

            item = _build_status_item_from_dates(
                course=course,
                last_completion_date=last_completion_date,
                due_date=due_date,
                deferral_due=deferral_due,
                upcoming_event_id=None,
                upcoming_event_date=None,
                today=today,
            )

            if item.status == "OK":
                ok_count += 1
            elif item.status == "DUE_SOON":
                due_soon_count += 1
            elif item.status == "OVERDUE":
                overdue_count += 1
            elif item.status == "DEFERRED":
                deferred_count += 1

    return training_schemas.TrainingDashboardSummary(
        total_mandatory_records=total,
        ok_count=ok_count,
        due_soon_count=due_soon_count,
        overdue_count=overdue_count,
        deferred_count=deferred_count,
    )

@router.get(
    "/certificates",
    response_model=List[training_schemas.TrainingRecordRead],
    summary="List issued training certificates (record-backed)",
)
def list_certificates(
    user_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    q = db.query(training_models.TrainingCertificateIssue).filter(
        training_models.TrainingCertificateIssue.amo_id == current_user.amo_id,
    )
    if user_id:
        q = q.join(training_models.TrainingRecord, training_models.TrainingRecord.id == training_models.TrainingCertificateIssue.record_id)
        q = q.filter(training_models.TrainingRecord.user_id == user_id)
    rows = q.order_by(training_models.TrainingCertificateIssue.issued_at.desc()).all()
    record_ids = [r.record_id for r in rows]
    records = db.query(training_models.TrainingRecord).filter(training_models.TrainingRecord.id.in_(record_ids)).all() if record_ids else []
    by_id = {r.id: r for r in records}
    return [_record_to_read(by_id[r.record_id]) for r in rows if r.record_id in by_id]


@router.post(
    "/certificates/issue/{record_id}",
    response_model=training_schemas.TrainingRecordRead,
    summary="Issue immutable certificate number for a training record",
)
def issue_certificate(
    record_id: str,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    record = (
        db.query(training_models.TrainingRecord)
        .filter(
            training_models.TrainingRecord.id == record_id,
            training_models.TrainingRecord.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Training record not found.")
    existing_issue = db.query(training_models.TrainingCertificateIssue).filter(
        training_models.TrainingCertificateIssue.record_id == record.id,
        training_models.TrainingCertificateIssue.amo_id == current_user.amo_id,
    ).first()
    if existing_issue or record.certificate_reference:
        raise HTTPException(status_code=400, detail="Certificate already issued and immutable.")

    cert_no = _next_certificate_number(db, current_user.amo_id)
    qr_value = f"/verify/certificate/{cert_no}"
    artifact_hash = hashlib.sha256(f"{record.id}:{cert_no}:{record.completion_date}".encode("utf-8")).hexdigest()
    issue = training_models.TrainingCertificateIssue(
        amo_id=current_user.amo_id,
        record_id=record.id,
        certificate_number=cert_no,
        issued_by_user_id=current_user.id,
        status="VALID",
        qr_value=qr_value,
        barcode_value=cert_no,
        artifact_hash=artifact_hash,
    )
    db.add(issue)
    db.flush()
    history = training_models.TrainingCertificateStatusHistory(
        amo_id=current_user.amo_id,
        certificate_issue_id=issue.id,
        status="VALID",
        reason="Initial issuance",
        actor_user_id=current_user.id,
    )
    record.certificate_reference = cert_no
    db.add(history)
    db.add(record)
    db.commit()
    db.refresh(record)
    return _record_to_read(record)


@public_router.get(
    "/certificates/verify/{certificate_number}",
    summary="Public certificate authenticity verification",
)
def verify_certificate_public(certificate_number: str, db: Session = Depends(get_db)):
    token = (certificate_number or "").strip()
    if len(token) < 6:
        return JSONResponse(status_code=400, content={"status": "MALFORMED", "certificate_number": token, "message": "Malformed certificate number."}, media_type="application/json")

    try:
        issue = db.execute(
            select(
                training_models.TrainingCertificateIssue.record_id,
                training_models.TrainingCertificateIssue.status,
            ).where(training_models.TrainingCertificateIssue.certificate_number == token)
        ).first()
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "UNAVAILABLE", "certificate_number": token, "message": "Verification service unavailable."}, media_type="application/json")
    if not issue:
        return JSONResponse(status_code=200, content={"status": "NOT_FOUND", "certificate_number": token}, media_type="application/json")

    record = db.execute(
        select(
            training_models.TrainingRecord.user_id,
            training_models.TrainingRecord.course_id,
            training_models.TrainingRecord.completion_date,
            training_models.TrainingRecord.valid_until,
        ).where(training_models.TrainingRecord.id == issue.record_id)
    ).first()
    if not record:
        return JSONResponse(status_code=200, content={"status": "NOT_FOUND", "certificate_number": token}, media_type="application/json")

    user_name = db.execute(select(accounts_models.User.full_name).where(accounts_models.User.id == record.user_id)).scalar_one_or_none()
    course_name = db.execute(select(training_models.TrainingCourse.course_name).where(training_models.TrainingCourse.id == record.course_id)).scalar_one_or_none()

    now = date.today()
    status_value = issue.status or "VALID"
    if status_value == "VALID" and record.valid_until and record.valid_until < now:
        status_value = "EXPIRED"

    return JSONResponse(
        status_code=200,
        content={
            "status": status_value,
            "certificate_number": token,
            "trainee_name": user_name or "Unknown",
            "course_title": course_name or "Unknown",
            "issue_date": str(record.completion_date),
            "valid_until": str(record.valid_until) if record.valid_until else None,
            "issuer": "AMO Portal",
        },
        media_type="application/json",
    )
