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
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import code128, qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session, load_only, noload, selectinload
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from ...database import SessionLocal, get_db, get_read_db
from ...entitlements import require_module
from ...security import get_current_active_user
from ..accounts import models as accounts_models
from ..audit import services as audit_services
from ..accounts import services as account_services
from ..tasks import services as task_services
from ..exports import build_evidence_pack
from ..quality import models as quality_models
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

_MAX_PAGE_SIZE = 200  # hard ceiling for list endpoints; frontend paginates at 50

_TRAINING_RECORD_PDF_CACHE_DIR = Path(tempfile.gettempdir()) / "amodb-training-record-pdf-cache"
_TRAINING_RECORD_PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_TRAINING_RECORD_PDF_CACHE_LOCK = threading.Lock()
_TRAINING_RECORD_PDF_WARMING: set[str] = set()
_TRAINING_RECORD_PDF_BUILD_LOCKS: dict[str, threading.Lock] = {}

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


_TRAINING_EVENT_META_PREFIX = "[AMO-EVENT-META]"


def _build_training_event_notes(notes: Optional[str], metadata: Optional[dict]) -> Optional[str]:
    payload = {k: v for k, v in (metadata or {}).items() if v not in (None, "", [], {})}
    plain_notes = (notes or "").strip()
    if not payload:
        return plain_notes or None
    rendered = f"{_TRAINING_EVENT_META_PREFIX}{json.dumps(payload, separators=(",", ":"))}"
    if plain_notes:
        rendered = f"{rendered}\n\n{plain_notes}"
    return rendered


def _extract_training_event_metadata(notes: Optional[str]) -> tuple[dict, Optional[str]]:
    raw = (notes or "").strip()
    if not raw.startswith(_TRAINING_EVENT_META_PREFIX):
        return {}, raw or None
    first_line, _, remainder = raw.partition("\n")
    payload = first_line[len(_TRAINING_EVENT_META_PREFIX):].strip()
    try:
        meta = json.loads(payload) if payload else {}
    except json.JSONDecodeError:
        return {}, raw
    return meta if isinstance(meta, dict) else {}, remainder.strip() or None


def _course_family_key_from_course(course: training_models.TrainingCourse) -> str:
    values: list[str] = []
    for attr in ("course_id", "course_name", "category_raw", "scope", "regulatory_reference"):
        value = getattr(course, attr, None)
        if isinstance(value, str) and value.strip():
            values.append(value.strip().lower())
    blob = " ".join(values)
    if not blob:
        return ""
    cleaned = re.sub(r"\b(init|initial|induction|refresh|refresher|recurrent|continuation|renewal|ref|one[ _-]?off)\b", " ", blob)
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned).strip()
    return cleaned


def _find_related_refresher_courses(
    db: Session,
    *,
    amo_id: str,
    initial_course: training_models.TrainingCourse,
) -> list[training_models.TrainingCourse]:
    courses = (
        db.query(training_models.TrainingCourse)
        .filter(
            training_models.TrainingCourse.amo_id == amo_id,
            training_models.TrainingCourse.is_active.is_(True),
        )
        .all()
    )
    initial_family = _course_family_key_from_course(initial_course)
    initial_code = (getattr(initial_course, "course_id", "") or "").strip().upper()
    related: list[training_models.TrainingCourse] = []
    for course in courses:
        if course.id == initial_course.id:
            continue
        if not training_compliance.is_refresher_course(course):
            continue
        prerequisite_code = (getattr(course, "prerequisite_course_id", "") or "").strip().upper()
        if prerequisite_code and prerequisite_code == initial_code:
            related.append(course)
            continue
        course_family = _course_family_key_from_course(course)
        if initial_family and course_family and course_family == initial_family:
            related.append(course)
    return related


def _seed_refresher_records_from_initial(
    db: Session,
    *,
    amo_id: str,
    trainee_id: str,
    initial_course: training_models.TrainingCourse,
    completion_date: date,
    event_id: Optional[str],
    remarks: Optional[str],
    is_manual_entry: bool,
    created_by_user_id: Optional[str],
) -> list[training_models.TrainingRecord]:
    seeded: list[training_models.TrainingRecord] = []
    for refresher in _find_related_refresher_courses(db, amo_id=amo_id, initial_course=initial_course):
        existing = (
            db.query(training_models.TrainingRecord)
            .filter(
                training_models.TrainingRecord.amo_id == amo_id,
                training_models.TrainingRecord.user_id == trainee_id,
                training_models.TrainingRecord.course_id == refresher.id,
                training_models.TrainingRecord.completion_date == completion_date,
            )
            .first()
        )
        if existing:
            continue
        valid_until = _add_months(completion_date, refresher.frequency_months) if refresher.frequency_months else None
        note_parts = [part for part in [remarks, f"AUTO-SEEDED FROM INITIAL {initial_course.course_id}"] if part]
        seeded_record = training_models.TrainingRecord(
            amo_id=amo_id,
            user_id=trainee_id,
            course_id=refresher.id,
            event_id=event_id,
            completion_date=completion_date,
            valid_until=valid_until,
            hours_completed=getattr(refresher, "nominal_hours", None),
            exam_score=None,
            certificate_reference=None,
            remarks=" | ".join(note_parts) if note_parts else None,
            is_manual_entry=is_manual_entry,
            created_by_user_id=created_by_user_id,
        )
        db.add(seeded_record)
        seeded.append(seeded_record)
    return seeded


def _get_amo_logo_path(db: Session, amo_id: str) -> Optional[str]:
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
    if logo_asset and getattr(logo_asset, "storage_path", None):
        candidate = Path(str(logo_asset.storage_path))
        if candidate.exists():
            return str(candidate)
    return None


def _issue_certificate_for_record(
    db: Session,
    *,
    record: training_models.TrainingRecord,
    amo_id: str,
    actor_user_id: Optional[str],
) -> training_models.TrainingCertificateIssue:
    existing_issue = db.query(training_models.TrainingCertificateIssue).filter(
        training_models.TrainingCertificateIssue.record_id == record.id,
        training_models.TrainingCertificateIssue.amo_id == amo_id,
    ).first()
    if existing_issue:
        if not record.certificate_reference:
            record.certificate_reference = existing_issue.certificate_number
            db.add(record)
        return existing_issue

    cert_no = record.certificate_reference or _next_certificate_number(db, amo_id)
    qr_value = f"/verify/certificate/{cert_no}"
    artifact_hash = hashlib.sha256(f"{record.id}:{cert_no}:{record.completion_date}".encode("utf-8")).hexdigest()
    issue = training_models.TrainingCertificateIssue(
        amo_id=amo_id,
        record_id=record.id,
        certificate_number=cert_no,
        issued_by_user_id=actor_user_id,
        status="VALID",
        qr_value=qr_value,
        barcode_value=cert_no,
        artifact_hash=artifact_hash,
    )
    db.add(issue)
    db.flush()
    history = training_models.TrainingCertificateStatusHistory(
        amo_id=amo_id,
        certificate_issue_id=issue.id,
        status="VALID",
        reason="Initial issuance",
        actor_user_id=actor_user_id,
    )
    record.certificate_reference = cert_no
    db.add(history)
    db.add(record)
    return issue


def _current_or_next_availability_window(
    rows: List[quality_models.UserAvailability],
    target_dt: datetime,
) -> tuple[str, Optional[date]]:
    """Return scheduling bucket and next available date for a target datetime.

    Buckets:
    - AVAILABLE: user is schedulable on target date
    - AWAY: temporary away / off-duty window overlaps target date
    - ON_LEAVE: planned leave overlaps target date
    """
    active_status = "AVAILABLE"
    next_available: Optional[date] = None

    for row in rows:
        effective_from = row.effective_from or datetime.min.replace(tzinfo=timezone.utc)
        effective_to = row.effective_to
        starts_after_target = effective_from > target_dt
        overlaps_target = effective_from <= target_dt and (effective_to is None or effective_to >= target_dt)

        if overlaps_target:
            status_value = getattr(row.status, "value", row.status)
            if status_value == "ON_LEAVE":
                active_status = "ON_LEAVE"
            elif status_value == "AWAY":
                active_status = "AWAY"
            else:
                active_status = "AVAILABLE"
            if effective_to is not None:
                next_available = (effective_to + timedelta(days=1)).date()
            return active_status, next_available

        if starts_after_target and next_available is None:
            # A future leave/away window does not block this target date.
            break

    return active_status, next_available


def _latest_availability_rows_for_users(
    db: Session,
    *,
    amo_id: str,
    user_ids: List[str],
) -> Dict[str, List[quality_models.UserAvailability]]:
    if not user_ids:
        return {}
    rows = (
        db.query(quality_models.UserAvailability)
        .filter(
            quality_models.UserAvailability.amo_id == amo_id,
            quality_models.UserAvailability.user_id.in_(user_ids),
        )
        .order_by(
            quality_models.UserAvailability.user_id.asc(),
            quality_models.UserAvailability.updated_at.desc(),
            quality_models.UserAvailability.effective_from.desc(),
        )
        .all()
    )
    grouped: Dict[str, List[quality_models.UserAvailability]] = {}
    for row in rows:
        grouped.setdefault(str(row.user_id), []).append(row)
    return grouped


def _default_start_date_for_status_item(
    *,
    item: training_schemas.TrainingStatusItem,
    course: training_models.TrainingCourse,
    base_start_on: date,
) -> date:
    lead_days = int(getattr(course, "planning_lead_days", 45) or 45)
    if lead_days < 0:
        lead_days = 45

    if item.status == "OVERDUE":
        return base_start_on

    if item.days_until_due is None:
        return base_start_on

    if item.days_until_due <= 7:
        return base_start_on
    if item.days_until_due <= 14:
        return base_start_on + timedelta(days=1)
    if item.days_until_due <= 30:
        return base_start_on + timedelta(days=3)
    if item.days_until_due <= lead_days:
        return base_start_on + timedelta(days=7)
    return base_start_on


def _create_scheduled_event_with_participants(
    db: Session,
    *,
    current_user: accounts_models.User,
    background_tasks: BackgroundTasks,
    course: training_models.TrainingCourse,
    user_ids: List[str],
    trainee_by_id: Dict[str, accounts_models.User],
    starts_on: date,
    ends_on: Optional[date],
    payload_notes: Optional[str],
    provider: Optional[str],
    provider_kind: Optional[str],
    delivery_mode: Optional[str],
    venue_mode: Optional[str],
    instructor_name: Optional[str],
    location: Optional[str],
    meeting_link: Optional[str],
    participant_status: training_models.TrainingParticipantStatus,
    allow_self_attendance: bool,
    auto_issue_certificates: bool,
    title_override: Optional[str] = None,
) -> tuple[training_models.TrainingEvent, List[training_models.TrainingEventParticipant]]:
    event_meta = {
        "provider_kind": (provider_kind or "INTERNAL").upper(),
        "delivery_mode": (delivery_mode or "CLASSROOM").upper(),
        "venue_mode": (venue_mode or "OFFLINE").upper(),
        "meeting_link": meeting_link,
        "instructor_name": instructor_name,
        "allow_self_attendance": allow_self_attendance,
        "auto_issue_certificates": auto_issue_certificates,
    }
    event = training_models.TrainingEvent(
        amo_id=current_user.amo_id,
        course_id=course.id,
        title=(title_override or course.course_name).strip(),
        location=(location or meeting_link or None),
        provider=(provider or course.default_provider or ("Internal" if event_meta["provider_kind"] == "INTERNAL" else None)),
        starts_on=starts_on,
        ends_on=ends_on,
        status=training_models.TrainingEventStatus.PLANNED,
        notes=_build_training_event_notes(payload_notes, event_meta),
        created_by_user_id=current_user.id,
    )
    db.add(event)
    db.flush()

    participants: List[training_models.TrainingEventParticipant] = []
    due_date = event.ends_on or event.starts_on
    due_at = datetime.combine(due_date, datetime.min.time(), tzinfo=timezone.utc)
    for user_id in user_ids:
        trainee = trainee_by_id[user_id]
        participant = training_models.TrainingEventParticipant(
            amo_id=current_user.amo_id,
            event_id=event.id,
            user_id=trainee.id,
            status=participant_status,
            attendance_note=None,
            deferral_request_id=None,
            notes=f"Auto-group scheduled via training control by {current_user.full_name or current_user.email or current_user.id}",
        )
        db.add(participant)
        db.flush()
        participants.append(participant)

        notif_title = "Training scheduled"
        notif_body = f"You have been scheduled for '{event.title}' starting {event.starts_on}."
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
        _maybe_send_email(background_tasks, getattr(trainee, "email", None), notif_title, notif_body)
        _maybe_send_whatsapp(background_tasks, _preferred_phone(trainee), notif_body)
        if participant.status in (
            training_models.TrainingParticipantStatus.SCHEDULED,
            training_models.TrainingParticipantStatus.INVITED,
            training_models.TrainingParticipantStatus.CONFIRMED,
        ):
            task_services.create_task(
                db,
                amo_id=current_user.amo_id,
                title="Complete training",
                description=f"Attend scheduled training '{event.title}'.",
                owner_user_id=participant.user_id,
                supervisor_user_id=None,
                due_at=due_at,
                entity_type="training_event_participant",
                entity_id=participant.id,
                priority=3,
            )
    return event, participants


def _ensure_completion_artifacts_for_participant(
    db: Session,
    *,
    participant: training_models.TrainingEventParticipant,
    actor_user_id: Optional[str],
    auto_issue_certificate: bool = True,
) -> Optional[training_models.TrainingRecord]:
    event = (
        db.query(training_models.TrainingEvent)
        .filter(training_models.TrainingEvent.id == participant.event_id, training_models.TrainingEvent.amo_id == participant.amo_id)
        .first()
    )
    if not event:
        return None
    course = (
        db.query(training_models.TrainingCourse)
        .filter(training_models.TrainingCourse.id == event.course_id, training_models.TrainingCourse.amo_id == participant.amo_id)
        .first()
    )
    if not course:
        return None

    record = (
        db.query(training_models.TrainingRecord)
        .filter(
            training_models.TrainingRecord.amo_id == participant.amo_id,
            training_models.TrainingRecord.user_id == participant.user_id,
            training_models.TrainingRecord.course_id == course.id,
            training_models.TrainingRecord.event_id == event.id,
        )
        .order_by(training_models.TrainingRecord.completion_date.desc(), training_models.TrainingRecord.created_at.desc())
        .first()
    )
    if record is None:
        completion_date = event.ends_on or event.starts_on or date.today()
        valid_until = _add_months(completion_date, course.frequency_months) if course.frequency_months else None
        meta, plain_notes = _extract_training_event_metadata(event.notes)
        note_bits = ["Auto-generated from portal attendance"]
        if plain_notes:
            note_bits.append(plain_notes)
        if meta.get("provider_kind"):
            note_bits.append(f"Provider type={meta['provider_kind']}")
        if meta.get("delivery_mode"):
            note_bits.append(f"Delivery={meta['delivery_mode']}")
        record = training_models.TrainingRecord(
            amo_id=participant.amo_id,
            user_id=participant.user_id,
            course_id=course.id,
            event_id=event.id,
            completion_date=completion_date,
            valid_until=valid_until,
            hours_completed=getattr(course, "nominal_hours", None),
            exam_score=None,
            certificate_reference=None,
            remarks=" | ".join(note_bits),
            is_manual_entry=False,
            created_by_user_id=actor_user_id,
            verification_status=training_models.TrainingRecordVerificationStatus.VERIFIED,
            verified_at=datetime.now(timezone.utc),
            verified_by_user_id=actor_user_id,
            verification_comment="Attendance marked through scheduled session workflow.",
        )
        db.add(record)
        db.flush()

    if auto_issue_certificate:
        _issue_certificate_for_record(db, record=record, amo_id=participant.amo_id, actor_user_id=actor_user_id)

    return record





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
                    f'<font color="#{_status_color_for_pdf(next_due.status).hexval()[2:]}">{_status_label_for_pdf(next_due.status)}</font>' if next_due else "-",
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
                Paragraph(f'<font color="#{_status_color_for_pdf(display_status).hexval()[2:]}"><b>{_status_label_for_pdf(display_status)}</b></font>', compact_style),
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


def _record_course_load_options():
    return (
        selectinload(training_models.TrainingRecord.course).load_only(
            training_models.TrainingCourse.id,
            training_models.TrainingCourse.course_id,
            training_models.TrainingCourse.course_name,
        ),
    )


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
    course = getattr(r, "course", None)
    course_pk = getattr(r, "course_id", None)
    course_code = getattr(course, "course_id", None) if course is not None else None
    course_name = getattr(course, "course_name", None) if course is not None else None
    return training_schemas.TrainingRecordRead(
        id=r.id,
        amo_id=r.amo_id,
        user_id=r.user_id,
        course_pk=course_pk,
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
        course_id=course_pk,
        course_code=course_code,
        course_name=course_name,
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
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_read_db),
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
    db: Session = Depends(get_read_db),
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
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_read_db),
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

    course_pk = data.pop("course_pk", None)
    if course_pk:
        course = (
            db.query(training_models.TrainingCourse)
            .filter(training_models.TrainingCourse.id == course_pk, training_models.TrainingCourse.amo_id == current_user.amo_id)
            .first()
        )
        if not course:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid course for this AMO.")
        req.course_id = course.id

    if "department_code" in data and data["department_code"]:
        data["department_code"] = data["department_code"].strip().upper()
    if "job_role" in data and data["job_role"]:
        data["job_role"] = data["job_role"].strip()

    if "scope" in data:
        scope = data["scope"]
        if scope == training_models.TrainingRequirementScope.DEPARTMENT and not (data.get("department_code") or req.department_code):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="department_code is required for scope=DEPARTMENT.")
        if scope == training_models.TrainingRequirementScope.JOB_ROLE and not (data.get("job_role") or req.job_role):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="job_role is required for scope=JOB_ROLE.")
        if scope == training_models.TrainingRequirementScope.USER and not (data.get("user_id") or req.user_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id is required for scope=USER.")

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


@router.delete(
    "/requirements/{requirement_id}",
    response_model=training_schemas.TrainingMutationResult,
    summary="Delete a training requirement rule (Quality / AMO admin only)",
)
def delete_requirement(
    requirement_id: str,
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

    entity_id = req.id
    details = {
        "course_id": req.course_id,
        "scope": req.scope.value if hasattr(req.scope, "value") else str(req.scope),
        "department_code": req.department_code,
        "job_role": req.job_role,
        "user_id": req.user_id,
        "is_mandatory": req.is_mandatory,
        "is_active": req.is_active,
    }
    _audit(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        action="REQUIREMENT_DELETE",
        entity_type="TrainingRequirement",
        entity_id=entity_id,
        details=details,
    )
    db.delete(req)
    db.commit()
    return training_schemas.TrainingMutationResult(
        id=entity_id,
        action="deleted",
        message="Requirement rule deleted.",
        soft_deleted=False,
    )


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
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_read_db),
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
    db: Session = Depends(get_read_db),
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
    db: Session = Depends(get_read_db),
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


@router.post(
    "/events/batch-schedule",
    response_model=training_schemas.TrainingEventBatchScheduleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create one session and batch-enrol personnel (Quality / AMO admin only)",
)
def batch_schedule_event(
    payload: training_schemas.TrainingEventBatchScheduleCreate,
    background_tasks: BackgroundTasks,
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
    if payload.ends_on and payload.ends_on < payload.starts_on:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="End date cannot be earlier than start date.")

    requested_user_ids = [user_id for user_id in dict.fromkeys(payload.user_ids) if user_id]
    if not requested_user_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one user must be selected for scheduling.")

    trainees = (
        db.query(accounts_models.User)
        .filter(accounts_models.User.amo_id == current_user.amo_id, accounts_models.User.id.in_(requested_user_ids))
        .all()
    )
    trainee_by_id = {user.id: user for user in trainees}
    missing = [user_id for user_id in requested_user_ids if user_id not in trainee_by_id]
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Some selected users were not found in your AMO: {', '.join(missing)}")

    event_meta = {
        "provider_kind": (payload.provider_kind or "INTERNAL").upper(),
        "delivery_mode": (payload.delivery_mode or "CLASSROOM").upper(),
        "venue_mode": (payload.venue_mode or "OFFLINE").upper(),
        "meeting_link": payload.meeting_link,
        "instructor_name": payload.instructor_name,
        "allow_self_attendance": payload.allow_self_attendance,
        "auto_issue_certificates": payload.auto_issue_certificates,
    }
    event = training_models.TrainingEvent(
        amo_id=current_user.amo_id,
        course_id=course.id,
        title=(payload.title or course.course_name).strip(),
        location=(payload.location or payload.meeting_link or None),
        provider=(payload.provider or course.default_provider or ("Internal" if event_meta["provider_kind"] == "INTERNAL" else None)),
        starts_on=payload.starts_on,
        ends_on=payload.ends_on,
        status=training_models.TrainingEventStatus.PLANNED,
        notes=_build_training_event_notes(payload.notes, event_meta),
        created_by_user_id=current_user.id,
    )
    db.add(event)
    db.flush()

    participants: list[training_models.TrainingEventParticipant] = []
    due_date = event.ends_on or event.starts_on
    due_at = datetime.combine(due_date, datetime.min.time(), tzinfo=timezone.utc)
    for user_id in requested_user_ids:
        trainee = trainee_by_id[user_id]
        participant = training_models.TrainingEventParticipant(
            amo_id=current_user.amo_id,
            event_id=event.id,
            user_id=trainee.id,
            status=payload.participant_status,
            attendance_note=None,
            deferral_request_id=None,
            notes=f"Batch scheduled via training control by {current_user.full_name or current_user.email or current_user.id}",
        )
        db.add(participant)
        db.flush()
        participants.append(participant)

        notif_title = "Training scheduled"
        notif_body = f"You have been scheduled for '{event.title}' starting {event.starts_on}."
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
        _maybe_send_email(background_tasks, getattr(trainee, "email", None), notif_title, notif_body)
        _maybe_send_whatsapp(background_tasks, _preferred_phone(trainee), notif_body)
        if participant.status in (
            training_models.TrainingParticipantStatus.SCHEDULED,
            training_models.TrainingParticipantStatus.INVITED,
            training_models.TrainingParticipantStatus.CONFIRMED,
        ):
            task_services.create_task(
                db,
                amo_id=current_user.amo_id,
                title="Complete training",
                description=f"Attend scheduled training '{event.title}'.",
                owner_user_id=participant.user_id,
                supervisor_user_id=None,
                due_at=due_at,
                entity_type="training_event_participant",
                entity_id=participant.id,
                priority=3,
            )

    _audit(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        action="EVENT_BATCH_SCHEDULE",
        entity_type="TrainingEvent",
        entity_id=event.id,
        details={
            "course_id": course.id,
            "starts_on": str(payload.starts_on),
            "title": event.title,
            "participant_count": len(participants),
            "provider_kind": event_meta["provider_kind"],
            "delivery_mode": event_meta["delivery_mode"],
        },
    )
    db.commit()
    db.refresh(event)
    for participant in participants:
        db.refresh(participant)
    return training_schemas.TrainingEventBatchScheduleRead(
        event=_event_to_read(event),
        participants=[_participant_to_read(participant) for participant in participants],
        created_count=len(participants),
    )


@router.post(
    "/events/auto-group-schedule",
    response_model=training_schemas.TrainingAutoGroupScheduleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Auto-group selected personnel by due course, availability, and urgency (Quality / AMO admin only)",
)
def auto_group_schedule_events(
    payload: training_schemas.TrainingAutoGroupScheduleCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    if not payload.include_due_soon and not payload.include_overdue:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select at least one status bucket to schedule.")

    requested_user_ids = [user_id for user_id in dict.fromkeys(payload.user_ids) if user_id]
    if not requested_user_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one user must be selected for scheduling.")

    trainees = (
        db.query(accounts_models.User)
        .filter(accounts_models.User.amo_id == current_user.amo_id, accounts_models.User.id.in_(requested_user_ids))
        .all()
    )
    trainee_by_id = {str(user.id): user for user in trainees}
    missing = [user_id for user_id in requested_user_ids if user_id not in trainee_by_id]
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Some selected users were not found in your AMO: {', '.join(missing)}")

    active_courses = (
        db.query(training_models.TrainingCourse)
        .filter(
            training_models.TrainingCourse.amo_id == current_user.amo_id,
            training_models.TrainingCourse.is_active.is_(True),
        )
        .all()
    )
    course_by_code = {course.course_id: course for course in active_courses}
    availability_rows = _latest_availability_rows_for_users(db, amo_id=current_user.amo_id, user_ids=requested_user_ids)
    base_start_on = payload.base_start_on or date.today()

    grouped_assignments: Dict[Tuple[str, date, Optional[date], str], List[str]] = {}
    skipped: List[training_schemas.TrainingAutoGroupSkippedRead] = []
    user_next_free_date: Dict[str, date] = {user_id: base_start_on for user_id in requested_user_ids}

    for user_id in requested_user_ids:
        user = trainee_by_id[user_id]
        if getattr(user, "is_system_account", False):
            skipped.append(training_schemas.TrainingAutoGroupSkippedRead(user_id=user_id, reason="System accounts cannot be scheduled."))
            continue

        evaluation = training_compliance.evaluate_user_training_policy(db, user, required_only=True)
        due_items = [
            item for item in evaluation.items
            if (payload.include_overdue and item.status == "OVERDUE") or (payload.include_due_soon and item.status == "DUE_SOON")
        ]
        due_items.sort(
            key=lambda item: (
                0 if item.status == "OVERDUE" else 1,
                item.days_until_due if item.days_until_due is not None else 999999,
                item.extended_due_date or item.valid_until or date.max,
                item.course_name.lower(),
            )
        )

        if not due_items:
            skipped.append(training_schemas.TrainingAutoGroupSkippedRead(user_id=user_id, reason="No overdue or due-soon mandatory courses require scheduling."))
            continue

        for item in due_items:
            course = course_by_code.get(item.course_id)
            if course is None:
                skipped.append(
                    training_schemas.TrainingAutoGroupSkippedRead(
                        user_id=user_id,
                        course_code=item.course_id,
                        course_name=item.course_name,
                        reason="Course catalogue entry not found for this status item.",
                    )
                )
                continue

            start_on = max(
                user_next_free_date.get(user_id, base_start_on),
                _default_start_date_for_status_item(item=item, course=course, base_start_on=base_start_on),
            )
            duration_days = max(int(getattr(course, "default_duration_days", 1) or 1), 1)
            target_dt = datetime.combine(start_on, datetime.min.time(), tzinfo=timezone.utc)
            availability_bucket, next_available_on = _current_or_next_availability_window(
                availability_rows.get(user_id, []),
                target_dt,
            )
            if availability_bucket in {"AWAY", "ON_LEAVE"}:
                if next_available_on is None:
                    skipped.append(
                        training_schemas.TrainingAutoGroupSkippedRead(
                            user_id=user_id,
                            course_pk=course.id,
                            course_code=course.course_id,
                            course_name=course.course_name,
                            reason="User is unavailable with no return date captured.",
                            availability_status=availability_bucket,
                        )
                    )
                    continue
                start_on = max(start_on, next_available_on)

            end_on = start_on + timedelta(days=duration_days - 1)
            bucket = availability_bucket if availability_bucket in {"AWAY", "ON_LEAVE"} else "ON_DUTY"
            grouped_assignments.setdefault((course.id, start_on, end_on, bucket), []).append(user_id)
            user_next_free_date[user_id] = end_on + timedelta(days=1)

    sessions: List[training_schemas.TrainingAutoGroupedSessionRead] = []
    total_enrolled = 0
    for (course_pk, starts_on, ends_on, bucket), user_ids in sorted(grouped_assignments.items(), key=lambda item: (item[0][1], item[0][0], item[0][3])):
        course = next((row for row in active_courses if row.id == course_pk), None)
        if course is None:
            continue
        bucket_title = "" if bucket == "ON_DUTY" else f" ({bucket.replace('_', ' ').title()} cohort)"
        notes = payload.notes or None
        if bucket != "ON_DUTY":
            notes = (notes + "\n\n" if notes else "") + f"Auto-group scheduler bucket: {bucket.replace('_', ' ').title()}."
        event, participants = _create_scheduled_event_with_participants(
            db,
            current_user=current_user,
            background_tasks=background_tasks,
            course=course,
            user_ids=user_ids,
            trainee_by_id=trainee_by_id,
            starts_on=starts_on,
            ends_on=ends_on,
            payload_notes=notes,
            provider=payload.provider,
            provider_kind=payload.provider_kind,
            delivery_mode=payload.delivery_mode,
            venue_mode=payload.venue_mode,
            instructor_name=payload.instructor_name,
            location=payload.location,
            meeting_link=payload.meeting_link,
            participant_status=payload.participant_status,
            allow_self_attendance=payload.allow_self_attendance,
            auto_issue_certificates=payload.auto_issue_certificates,
            title_override=f"{course.course_name}{bucket_title}",
        )
        sessions.append(
            training_schemas.TrainingAutoGroupedSessionRead(
                course_pk=course.id,
                course_code=course.course_id,
                course_name=course.course_name,
                availability_bucket=bucket,
                start_on=starts_on,
                end_on=ends_on,
                event=_event_to_read(event),
                participants=[_participant_to_read(participant) for participant in participants],
            )
        )
        total_enrolled += len(participants)

    _audit(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        action="EVENT_AUTO_GROUP_SCHEDULE",
        entity_type="TrainingEvent",
        entity_id=None,
        details={
            "selected_user_count": len(requested_user_ids),
            "session_count": len(sessions),
            "total_enrolled": total_enrolled,
            "include_due_soon": payload.include_due_soon,
            "include_overdue": payload.include_overdue,
        },
    )
    db.commit()
    return training_schemas.TrainingAutoGroupScheduleRead(
        sessions=sessions,
        skipped=skipped,
        total_sessions=len(sessions),
        total_enrolled=total_enrolled,
    )


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
        if data["status"] == training_models.TrainingParticipantStatus.ATTENDED:
            event_row = (
                db.query(training_models.TrainingEvent.notes)
                .filter(training_models.TrainingEvent.id == participant.event_id, training_models.TrainingEvent.amo_id == current_user.amo_id)
                .first()
            )
            meta, _ = _extract_training_event_metadata(event_row[0] if event_row else None)
            _ensure_completion_artifacts_for_participant(
                db,
                participant=participant,
                actor_user_id=current_user.id,
                auto_issue_certificate=bool(meta.get("auto_issue_certificates", True)),
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
# DETAIL BUNDLES / PAGED SLICES
# ---------------------------------------------------------------------------


def _training_user_profile_to_read(user: accounts_models.User, *, hire_date: Optional[date] = None) -> training_schemas.TrainingUserProfileLiteRead:
    return training_schemas.TrainingUserProfileLiteRead(
        id=str(user.id),
        amo_id=str(user.amo_id),
        department_id=str(user.department_id) if getattr(user, "department_id", None) else None,
        staff_code=user.staff_code,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        role=(user.role.value if hasattr(user.role, "value") else str(user.role)),
        position_title=user.position_title,
        phone=user.phone,
        secondary_phone=user.secondary_phone,
        regulatory_authority=(user.regulatory_authority.value if getattr(user, "regulatory_authority", None) is not None else None),
        licence_number=user.licence_number,
        licence_state_or_country=user.licence_state_or_country,
        licence_expires_on=user.licence_expires_on,
        is_active=bool(user.is_active),
        is_superuser=bool(user.is_superuser),
        is_amo_admin=bool(user.is_amo_admin),
        must_change_password=bool(user.must_change_password),
        last_login_at=user.last_login_at,
        last_login_ip=user.last_login_ip,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.get(
    "/users/{user_id}/detail-bundle",
    response_model=training_schemas.TrainingUserDetailBundleRead,
    summary="Optimized training detail bundle for a single user",
)
def get_training_user_detail_bundle(
    user_id: str,
    records_limit: int = 50,
    deferrals_limit: int = 50,
    files_limit: int = 50,
    events_limit: int = 20,
    db: Session = Depends(get_read_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    can_edit = _is_training_editor(current_user)
    target_user_id = user_id if can_edit else current_user.id
    user = (
        db.query(accounts_models.User)
        .filter(accounts_models.User.id == target_user_id, accounts_models.User.amo_id == current_user.amo_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training user not found for this AMO.")

    records_limit, _ = _normalize_pagination(records_limit, 0)
    deferrals_limit, _ = _normalize_pagination(deferrals_limit, 0)
    files_limit, _ = _normalize_pagination(files_limit, 0)
    events_limit, _ = _normalize_pagination(events_limit, 0)

    profile_row = (
        db.query(accounts_models.PersonnelProfile)
        .filter(accounts_models.PersonnelProfile.amo_id == current_user.amo_id, accounts_models.PersonnelProfile.user_id == user.id)
        .first()
    )
    hire_date = profile_row.hire_date if profile_row is not None else None

    status_items = training_compliance.evaluate_user_training_policy(db, user, required_only=False).items

    record_query = (
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
            *_record_course_load_options(),
        )
        .filter(training_models.TrainingRecord.amo_id == current_user.amo_id, training_models.TrainingRecord.user_id == user.id)
    )
    records_total = record_query.count()
    records = record_query.order_by(training_models.TrainingRecord.completion_date.desc()).limit(records_limit).all()

    deferral_query = db.query(training_models.TrainingDeferralRequest).filter(
        training_models.TrainingDeferralRequest.amo_id == current_user.amo_id,
        training_models.TrainingDeferralRequest.user_id == user.id,
    )
    deferrals_total = deferral_query.count()
    deferrals = deferral_query.order_by(training_models.TrainingDeferralRequest.requested_at.desc()).limit(deferrals_limit).all()

    file_query = db.query(training_models.TrainingFile).filter(
        training_models.TrainingFile.amo_id == current_user.amo_id,
        training_models.TrainingFile.owner_user_id == user.id,
    )
    files_total = file_query.count()
    files = file_query.order_by(training_models.TrainingFile.uploaded_at.desc()).limit(files_limit).all()

    relevant_course_ids = list({str(r.course_id) for r in records if getattr(r, "course_id", None)})
    event_query = db.query(training_models.TrainingEvent).filter(training_models.TrainingEvent.amo_id == current_user.amo_id)
    if relevant_course_ids:
        event_query = event_query.filter(training_models.TrainingEvent.course_id.in_(relevant_course_ids))
    event_query = event_query.filter(training_models.TrainingEvent.starts_on >= (date.today() - timedelta(days=30)))
    upcoming_events_total = event_query.count()
    upcoming_events = event_query.order_by(training_models.TrainingEvent.starts_on.asc()).limit(events_limit).all()

    return training_schemas.TrainingUserDetailBundleRead(
        user=_training_user_profile_to_read(user, hire_date=hire_date),
        hire_date=hire_date,
        status_items=status_items,
        records=[_record_to_read(r) for r in records],
        records_total=records_total,
        deferrals=[_deferral_to_read(d) for d in deferrals],
        deferrals_total=deferrals_total,
        files=[_file_to_read(f) for f in files],
        files_total=files_total,
        upcoming_events=[_event_to_read(e) for e in upcoming_events],
        upcoming_events_total=upcoming_events_total,
    )


@router.post(
    "/records/by-users",
    response_model=List[training_schemas.TrainingRecordRead],
    summary="List training records for a page of users",
)
def list_training_records_by_users(
    payload: training_schemas.TrainingRecordsByUsersRequest,
    db: Session = Depends(get_read_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    user_ids = [str(user_id).strip() for user_id in payload.user_ids if str(user_id).strip()]
    if not user_ids:
        return []
    if len(user_ids) > 50:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A maximum of 50 users may be requested at once.")
    limit, offset = _normalize_pagination(payload.limit, payload.offset)
    rows = (
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
            *_record_course_load_options(),
        )
        .filter(
            training_models.TrainingRecord.amo_id == current_user.amo_id,
            training_models.TrainingRecord.user_id.in_(user_ids),
        )
        .order_by(training_models.TrainingRecord.user_id.asc(), training_models.TrainingRecord.completion_date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_record_to_read(row) for row in rows]


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
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_read_db),
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
                *_record_course_load_options(),
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
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_read_db),
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
            *_record_course_load_options(),
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
    hours_completed = getattr(course, "nominal_hours", None)

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
        linked_file.review_status = training_models.TrainingFileReviewStatus.APPROVED
        linked_file.reviewed_at = datetime.now(timezone.utc)
        linked_file.reviewed_by_user_id = current_user.id
        linked_file.review_comment = "Linked by authorized training editor during record capture."
        db.add(linked_file)

    record.verification_status = training_models.TrainingRecordVerificationStatus.VERIFIED
    record.verified_at = datetime.now(timezone.utc)
    record.verified_by_user_id = current_user.id
    record.verification_comment = "Captured by authorized training editor."

    seeded_refresher_records: list[training_models.TrainingRecord] = []
    if training_compliance.is_initial_course(course):
        seeded_refresher_records = _seed_refresher_records_from_initial(
            db,
            amo_id=current_user.amo_id,
            trainee_id=trainee.id,
            initial_course=course,
            completion_date=payload.completion_date,
            event_id=payload.event_id,
            remarks=payload.remarks,
            is_manual_entry=payload.is_manual_entry,
            created_by_user_id=current_user.id,
        )

    # Notify user (in-app + optional email)
    notif_title = "Training record updated"
    notif_body = f"A training record for '{course.course_name}' has been added/updated on your profile."
    if seeded_refresher_records:
        notif_body += f" {len(seeded_refresher_records)} linked refresher entr{'y' if len(seeded_refresher_records) == 1 else 'ies'} were auto-seeded from the initial completion."
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
        details={"user_id": trainee.id, "course_id": course.id, "completion_date": str(payload.completion_date), "auto_seeded_refresher_count": len(seeded_refresher_records)},
    )

    db.commit()
    db.refresh(record)
    return _record_to_read(record)


@router.put(
    "/records/{record_id}",
    response_model=training_schemas.TrainingRecordRead,
    summary="Update a training record (Quality / AMO admin only)",
)
def update_training_record(
    record_id: str,
    payload: training_schemas.TrainingRecordUpdate,
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

    course = (
        db.query(training_models.TrainingCourse)
        .filter(training_models.TrainingCourse.id == record.course_id, training_models.TrainingCourse.amo_id == current_user.amo_id)
        .first()
    )
    if not course:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Training course for this record could not be found.")

    if payload.completion_date is not None:
        if payload.completion_date > date.today():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Completion date cannot be in the future.")
        record.completion_date = payload.completion_date
        if payload.valid_until is None:
            record.valid_until = _add_months(payload.completion_date, course.frequency_months) if course.frequency_months else None

    if payload.valid_until is not None:
        record.valid_until = payload.valid_until
    if payload.hours_completed is not None:
        record.hours_completed = payload.hours_completed
    if payload.exam_score is not None:
        record.exam_score = payload.exam_score
    if payload.certificate_reference is not None:
        record.certificate_reference = payload.certificate_reference
    if payload.remarks is not None:
        record.remarks = payload.remarks

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
        if linked_file.owner_user_id != record.user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected attachment belongs to a different person.")

    if payload.certificate_reference and not (payload.attachment_file_id or db.query(training_models.TrainingFile).filter(training_models.TrainingFile.record_id == record.id, training_models.TrainingFile.kind == training_models.TrainingFileKind.CERTIFICATE).first()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A certificate attachment is required when a certificate reference is provided.")

    if payload.clear_attachment:
        existing_files = db.query(training_models.TrainingFile).filter(training_models.TrainingFile.record_id == record.id).all()
        for f in existing_files:
            f.record_id = None
            db.add(f)

    if linked_file is not None:
        linked_file.record_id = record.id
        linked_file.course_id = record.course_id
        linked_file.review_status = training_models.TrainingFileReviewStatus.APPROVED
        linked_file.reviewed_at = datetime.now(timezone.utc)
        linked_file.reviewed_by_user_id = current_user.id
        linked_file.review_comment = "Linked by authorized training editor during record update."
        db.add(linked_file)

    record.verification_status = training_models.TrainingRecordVerificationStatus.VERIFIED
    record.verified_at = datetime.now(timezone.utc)
    record.verified_by_user_id = current_user.id
    record.verification_comment = "Updated by authorized training editor."

    _audit(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        action="RECORD_UPDATE",
        entity_type="TrainingRecord",
        entity_id=record.id,
        details={
            "completion_date": str(record.completion_date) if record.completion_date else None,
            "valid_until": str(record.valid_until) if record.valid_until else None,
            "certificate_reference": record.certificate_reference,
            "attachment_file_id": payload.attachment_file_id,
        },
    )

    db.add(record)
    db.commit()
    db.refresh(record)
    return _record_to_read(record)


@router.delete(
    "/records/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a training record (Quality / AMO admin only)",
)
def delete_training_record(
    record_id: str,
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

    linked_files = db.query(training_models.TrainingFile).filter(training_models.TrainingFile.record_id == record.id).all()
    for f in linked_files:
        f.record_id = None
        db.add(f)

    _audit(
        db,
        amo_id=current_user.amo_id,
        actor_user_id=current_user.id,
        action="RECORD_DELETE",
        entity_type="TrainingRecord",
        entity_id=record.id,
        details={"user_id": record.user_id, "course_id": record.course_id, "completion_date": str(record.completion_date)},
    )

    db.delete(record)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_read_db),
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
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_read_db),
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

    auto_approved = bool(is_editor and owner.id != current_user.id or is_editor)
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
        review_status=training_models.TrainingFileReviewStatus.APPROVED if auto_approved else training_models.TrainingFileReviewStatus.PENDING,
        reviewed_at=datetime.now(timezone.utc) if auto_approved else None,
        reviewed_by_user_id=current_user.id if auto_approved else None,
        review_comment="Uploaded by authorized training editor." if auto_approved else None,
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
        body=(f"Your document '{original_name}' was uploaded and approved." if auto_approved else f"Your document '{original_name}' was uploaded and is pending review."),
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
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_read_db),
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
    db: Session = Depends(get_read_db),
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
    db: Session = Depends(get_read_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    return training_compliance.evaluate_user_training_policy(db, current_user, required_only=False).items


@router.get(
    "/status/me/required",
    response_model=List[training_schemas.TrainingStatusItem],
    summary="Training status for the current user, filtered by requirement matrix (IOSA-style)",
)
def get_my_required_training_status(
    db: Session = Depends(get_read_db),
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
    db: Session = Depends(get_read_db),
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
    db: Session = Depends(get_read_db),
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
    db: Session = Depends(get_read_db),
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


def _training_user_pdf_build_lock(user_id: str) -> threading.Lock:
    with _TRAINING_RECORD_PDF_CACHE_LOCK:
        lock = _TRAINING_RECORD_PDF_BUILD_LOCKS.get(user_id)
        if lock is None:
            lock = threading.Lock()
            _TRAINING_RECORD_PDF_BUILD_LOCKS[user_id] = lock
        return lock


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
            *_record_course_load_options(),
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
    build_lock = _training_user_pdf_build_lock(user_id)
    try:
        context = _get_training_user_record_export_context(db, amo_id=amo_id, user_id=user_id)
        cache_path = _training_user_pdf_cache_path(user_id, context["cache_key"])
        if cache_path.exists():
            return cache_path
        with build_lock:
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
    db: Session = Depends(get_read_db),
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
    db: Session = Depends(get_read_db),
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
        build_lock = _training_user_pdf_build_lock(user_id)
        with build_lock:
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
    db: Session = Depends(get_read_db),
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
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_read_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    limit, offset = _normalize_pagination(limit, offset)
    q = db.query(training_models.TrainingCertificateIssue).filter(
        training_models.TrainingCertificateIssue.amo_id == current_user.amo_id,
    )
    if user_id:
        q = q.join(training_models.TrainingRecord, training_models.TrainingRecord.id == training_models.TrainingCertificateIssue.record_id)
        q = q.filter(training_models.TrainingRecord.user_id == user_id)
    rows = q.order_by(training_models.TrainingCertificateIssue.issued_at.desc()).offset(offset).limit(limit).all()
    record_ids = [r.record_id for r in rows]
    records = (
        db.query(training_models.TrainingRecord)
        .options(*_record_course_load_options())
        .filter(training_models.TrainingRecord.id.in_(record_ids))
        .all()
    ) if record_ids else []
    by_id = {r.id: r for r in records}
    return [_record_to_read(by_id[r.record_id]) for r in rows if r.record_id in by_id]


def _build_training_certificate_pdf_bytes(
    *,
    user: accounts_models.User,
    course: training_models.TrainingCourse,
    record: training_models.TrainingRecord,
    issue: training_models.TrainingCertificateIssue,
    amo: Optional[accounts_models.AMO],
    event: Optional[training_models.TrainingEvent],
    logo_path: Optional[str],
    signatory_name: Optional[str],
    signatory_title: Optional[str],
    approver_name: Optional[str],
    approver_title: Optional[str],
) -> bytes:
    buffer = io.BytesIO()
    page_width, page_height = landscape(A4)
    pdf = canvas.Canvas(buffer, pagesize=(page_width, page_height))
    pdf.setTitle(f"Training Certificate {issue.certificate_number}")
    pdf.setAuthor("AMO Portal")

    primary = _TRAINING_RECORD_BRAND_PRIMARY
    primary_dark = _TRAINING_RECORD_BRAND_PRIMARY_DARK
    soft = _TRAINING_RECORD_BRAND_PRIMARY_SOFT
    pdf.setFillColor(colors.white)
    pdf.rect(0, 0, page_width, page_height, fill=1, stroke=0)
    pdf.setFillColor(soft)
    pdf.rect(12 * mm, 12 * mm, page_width - 24 * mm, page_height - 24 * mm, fill=1, stroke=0)
    pdf.setStrokeColor(primary)
    pdf.setLineWidth(1.6)
    pdf.rect(14 * mm, 14 * mm, page_width - 28 * mm, page_height - 28 * mm, stroke=1, fill=0)
    pdf.setLineWidth(0.6)
    pdf.rect(18 * mm, 18 * mm, page_width - 36 * mm, page_height - 36 * mm, stroke=1, fill=0)

    if logo_path and Path(str(logo_path)).exists():
        try:
            pdf.drawImage(ImageReader(str(logo_path)), 24 * mm, page_height - 34 * mm, width=34 * mm, height=16 * mm, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("CertTitle", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=26, leading=30, textColor=primary_dark, alignment=1)
    subtitle_style = ParagraphStyle("CertSubtitle", parent=styles["BodyText"], fontName="Helvetica", fontSize=11, leading=14, textColor=colors.HexColor("#475467"), alignment=1)
    name_style = ParagraphStyle("CertName", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=colors.HexColor("#17212b"), alignment=1)
    course_style = ParagraphStyle("CertCourse", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=primary_dark, alignment=1)
    small_style = ParagraphStyle("CertSmall", parent=styles["BodyText"], fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor("#344054"), alignment=1)

    Paragraph("CERTIFICATE OF COMPLETION", title_style).wrapOn(pdf, page_width - 80 * mm, 18 * mm)
    Paragraph("CERTIFICATE OF COMPLETION", title_style).drawOn(pdf, 40 * mm, page_height - 58 * mm)
    Paragraph(f"{(amo.name if amo and getattr(amo, 'name', None) else 'Approved Maintenance Organisation')} certifies that", subtitle_style).wrapOn(pdf, page_width - 70 * mm, 16 * mm)
    Paragraph(f"{(amo.name if amo and getattr(amo, 'name', None) else 'Approved Maintenance Organisation')} certifies that", subtitle_style).drawOn(pdf, 35 * mm, page_height - 72 * mm)

    Paragraph(user.full_name or user.email or user.id, name_style).wrapOn(pdf, page_width - 70 * mm, 24 * mm)
    Paragraph(user.full_name or user.email or user.id, name_style).drawOn(pdf, 35 * mm, page_height - 96 * mm)
    Paragraph("has successfully completed", subtitle_style).wrapOn(pdf, page_width - 70 * mm, 14 * mm)
    Paragraph("has successfully completed", subtitle_style).drawOn(pdf, 35 * mm, page_height - 112 * mm)
    Paragraph(course.course_name, course_style).wrapOn(pdf, page_width - 70 * mm, 34 * mm)
    Paragraph(course.course_name, course_style).drawOn(pdf, 35 * mm, page_height - 145 * mm)

    provider_text = (event.provider if event and event.provider else getattr(course, 'default_provider', None) or (amo.name if amo and getattr(amo, 'name', None) else 'AMO Portal'))
    start_date = event.starts_on if event and getattr(event, 'starts_on', None) else record.completion_date
    end_date = event.ends_on if event and getattr(event, 'ends_on', None) else record.completion_date
    duration_text = _fmt_date(start_date)
    if end_date and end_date != start_date:
        duration_text = f"{_fmt_date(start_date)} to {_fmt_date(end_date)}"
    valid_text = _fmt_date(record.valid_until) if record.valid_until else "No expiry recorded"
    info = [
        ["Certificate No", issue.certificate_number, "Provider", provider_text],
        ["Completed", duration_text, "Valid until", valid_text],
        ["Staff code", user.staff_code or "-", "Position", getattr(user, 'position_title', None) or '-'],
    ]
    info_table = Table(info, colWidths=[28 * mm, 62 * mm, 24 * mm, 62 * mm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, primary),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d0d5dd")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111827")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    w, h = info_table.wrap(page_width - 110 * mm, 40 * mm)
    info_table.drawOn(pdf, 34 * mm, page_height - 195 * mm)

    verify_value = f"{_TRAINING_RECORD_PUBLIC_BASE_URL}/verify/certificate/{issue.certificate_number}" if _TRAINING_RECORD_PUBLIC_BASE_URL else f"/verify/certificate/{issue.certificate_number}"
    qr_drawing = _build_training_profile_qr_drawing(verify_value, size_mm=24)
    renderPDF.draw(qr_drawing, pdf, page_width - 62 * mm, page_height - 178 * mm)
    barcode = code128.Code128(issue.certificate_number, barHeight=12 * mm, barWidth=0.32)
    barcode.drawOn(pdf, page_width - 92 * mm, 42 * mm)
    Paragraph("Scan to verify authenticity", small_style).wrapOn(pdf, 42 * mm, 10 * mm)
    Paragraph("Scan to verify authenticity", small_style).drawOn(pdf, page_width - 74 * mm, page_height - 190 * mm)

    sign_y = 56 * mm
    pdf.setStrokeColor(colors.HexColor("#98a2b3"))
    pdf.line(38 * mm, sign_y, 92 * mm, sign_y)
    pdf.line(page_width - 102 * mm, sign_y, page_width - 48 * mm, sign_y)
    Paragraph(signatory_name or "Training Coordinator", small_style).wrapOn(pdf, 60 * mm, 10 * mm)
    Paragraph(signatory_name or "Training Coordinator", small_style).drawOn(pdf, 36 * mm, sign_y - 16 * mm)
    Paragraph(signatory_title or "For the organisation", small_style).wrapOn(pdf, 60 * mm, 10 * mm)
    Paragraph(signatory_title or "For the organisation", small_style).drawOn(pdf, 36 * mm, sign_y - 22 * mm)
    Paragraph(approver_name or "Quality Manager", small_style).wrapOn(pdf, 60 * mm, 10 * mm)
    Paragraph(approver_name or "Quality Manager", small_style).drawOn(pdf, page_width - 104 * mm, sign_y - 16 * mm)
    Paragraph(approver_title or "Authorised signatory", small_style).wrapOn(pdf, 60 * mm, 10 * mm)
    Paragraph(approver_title or "Authorised signatory", small_style).drawOn(pdf, page_width - 104 * mm, sign_y - 22 * mm)

    footer_text = f"Generated by AMO Portal · {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}"
    Paragraph(footer_text, small_style).wrapOn(pdf, page_width - 60 * mm, 10 * mm)
    Paragraph(footer_text, small_style).drawOn(pdf, 30 * mm, 20 * mm)
    pdf.save()
    return buffer.getvalue()


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

    _issue_certificate_for_record(db, record=record, amo_id=current_user.amo_id, actor_user_id=current_user.id)
    db.commit()
    db.refresh(record)
    return _record_to_read(record)


@router.get(
    "/certificates/artifact/{record_id}",
    summary="Download branded certificate PDF for a training record",
)
def download_certificate_artifact(
    record_id: str,
    signatory_name: Optional[str] = None,
    signatory_title: Optional[str] = None,
    approver_name: Optional[str] = None,
    approver_title: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    record = (
        db.query(training_models.TrainingRecord)
        .filter(training_models.TrainingRecord.id == record_id, training_models.TrainingRecord.amo_id == current_user.amo_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Training record not found.")
    if current_user.id != record.user_id and not _is_training_editor(current_user):
        raise HTTPException(status_code=403, detail="Insufficient privileges to download this certificate.")

    issue = db.query(training_models.TrainingCertificateIssue).filter(
        training_models.TrainingCertificateIssue.record_id == record.id,
        training_models.TrainingCertificateIssue.amo_id == current_user.amo_id,
    ).first()
    if not issue:
        if not _is_training_editor(current_user):
            raise HTTPException(status_code=400, detail="Certificate has not yet been issued for this record.")
        issue = _issue_certificate_for_record(db, record=record, amo_id=current_user.amo_id, actor_user_id=current_user.id)
        db.commit()
        db.refresh(record)

    user = db.query(accounts_models.User).filter(accounts_models.User.id == record.user_id, accounts_models.User.amo_id == current_user.amo_id).first()
    course = db.query(training_models.TrainingCourse).filter(training_models.TrainingCourse.id == record.course_id, training_models.TrainingCourse.amo_id == current_user.amo_id).first()
    if not user or not course:
        raise HTTPException(status_code=400, detail="Certificate source data is incomplete.")
    amo = db.query(accounts_models.AMO).filter(accounts_models.AMO.id == current_user.amo_id).first()
    event = None
    if getattr(record, 'event_id', None):
        event = db.query(training_models.TrainingEvent).filter(training_models.TrainingEvent.id == record.event_id, training_models.TrainingEvent.amo_id == current_user.amo_id).first()
    pdf_bytes = _build_training_certificate_pdf_bytes(
        user=user,
        course=course,
        record=record,
        issue=issue,
        amo=amo,
        event=event,
        logo_path=_get_amo_logo_path(db, current_user.amo_id),
        signatory_name=signatory_name,
        signatory_title=signatory_title,
        approver_name=approver_name,
        approver_title=approver_title,
    )
    filename = f"{(user.full_name or user.id).replace(' ', '_')}_{course.course_id}_certificate.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
