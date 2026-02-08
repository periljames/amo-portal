# backend/amodb/apps/training/router.py

from __future__ import annotations

import hashlib
import json
import os
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
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from ...database import get_db
from ...entitlements import require_module
from ...security import get_current_active_user
from ..accounts import models as accounts_models
from ..audit import services as audit_services
from ..accounts import services as account_services
from ..tasks import services as task_services
from ..exports import build_evidence_pack
from . import models as training_models
from . import schemas as training_schemas
from ..workflow import apply_transition, TransitionError

router = APIRouter(
    prefix="/training",
    tags=["training"],
    dependencies=[Depends(require_module("training"))],
)

_MAX_PAGE_SIZE = 1000  # hard ceiling for list endpoints to protect DB


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
    if months <= 0:
        return base

    year = base.year + (base.month - 1 + months) // 12
    month = (base.month - 1 + months) % 12 + 1
    days_in_month = [
        31,
        29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ][month - 1]
    day = min(base.day, days_in_month)
    return date(year, month, day)


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
    extended_due_date: Optional[date] = None

    if due_date:
        extended_due_date = due_date

    if deferral_due:
        if extended_due_date is None or deferral_due > extended_due_date:
            extended_due_date = deferral_due

    status_label = "NOT_DONE"
    days_until_due: Optional[int] = None

    if extended_due_date:
        days_until_due = (extended_due_date - today).days
        if days_until_due < 0:
            status_label = "OVERDUE"
        elif days_until_due <= 60:
            status_label = "DUE_SOON"
        else:
            status_label = "OK"

    if deferral_due and extended_due_date and days_until_due is not None and days_until_due >= 0:
        status_label = "DEFERRED"

    if last_completion_date is None and upcoming_event_date and status_label == "NOT_DONE":
        status_label = "SCHEDULED_ONLY"

    return training_schemas.TrainingStatusItem(
        course_id=course.course_id,
        course_name=course.course_name,
        frequency_months=course.frequency_months,
        last_completion_date=last_completion_date,
        valid_until=due_date,
        extended_due_date=extended_due_date,
        days_until_due=days_until_due,
        status=status_label,
        upcoming_event_id=upcoming_event_id,
        upcoming_event_date=upcoming_event_date,
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
                _maybe_send_whatsapp(background_tasks, getattr(trainee, "phone", None), body)

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
    _maybe_send_whatsapp(background_tasks, getattr(trainee, "phone", None), notif_body)

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

    q = db.query(training_models.TrainingRecord).filter(training_models.TrainingRecord.amo_id == current_user.amo_id)
    if user_id:
        q = q.filter(training_models.TrainingRecord.user_id == user_id)
    if course_pk:
        q = q.filter(training_models.TrainingRecord.course_id == course_pk)

    records = (
        q.order_by(
            training_models.TrainingRecord.user_id.asc(),
            training_models.TrainingRecord.completion_date.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
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
    records = (
        db.query(training_models.TrainingRecord)
        .filter(training_models.TrainingRecord.amo_id == current_user.amo_id, training_models.TrainingRecord.user_id == current_user.id)
        .order_by(training_models.TrainingRecord.completion_date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
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

    valid_until = payload.valid_until
    if valid_until is None and course.frequency_months:
        valid_until = _add_months(payload.completion_date, course.frequency_months)

    record = training_models.TrainingRecord(
        amo_id=current_user.amo_id,
        user_id=trainee.id,
        course_id=course.id,
        event_id=payload.event_id,
        completion_date=payload.completion_date,
        valid_until=valid_until,
        hours_completed=payload.hours_completed,
        exam_score=payload.exam_score,
        certificate_reference=payload.certificate_reference,
        remarks=payload.remarks,
        is_manual_entry=payload.is_manual_entry,
        created_by_user_id=current_user.id,
        # verification_status defaults to PENDING in model (IOSA-friendly)
    )

    db.add(record)

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
    _maybe_send_whatsapp(background_tasks, getattr(trainee, "phone", None), notif_body)

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
        _maybe_send_whatsapp(background_tasks, getattr(trainee, "phone", None), body)

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
        _maybe_send_whatsapp(background_tasks, getattr(trainee, "phone", None), body)

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
    today = date.today()

    courses: List[training_models.TrainingCourse] = (
        db.query(training_models.TrainingCourse)
        .filter(
            training_models.TrainingCourse.amo_id == current_user.amo_id,
            training_models.TrainingCourse.is_active.is_(True),
        )
        .order_by(training_models.TrainingCourse.course_id.asc())
        .all()
    )
    if not courses:
        return []

    course_ids = [c.id for c in courses]

    records = (
        db.query(training_models.TrainingRecord)
        .filter(
            training_models.TrainingRecord.amo_id == current_user.amo_id,
            training_models.TrainingRecord.user_id == current_user.id,
            training_models.TrainingRecord.course_id.in_(course_ids),
        )
        .order_by(
            training_models.TrainingRecord.course_id.asc(),
            training_models.TrainingRecord.completion_date.desc(),
        )
        .all()
    )
    latest_record: Dict[str, training_models.TrainingRecord] = {}
    for r in records:
        if r.course_id not in latest_record:
            latest_record[r.course_id] = r

    deferrals = (
        db.query(training_models.TrainingDeferralRequest)
        .filter(
            training_models.TrainingDeferralRequest.amo_id == current_user.amo_id,
            training_models.TrainingDeferralRequest.user_id == current_user.id,
            training_models.TrainingDeferralRequest.course_id.in_(course_ids),
            training_models.TrainingDeferralRequest.status == training_models.DeferralStatus.APPROVED,
        )
        .order_by(
            training_models.TrainingDeferralRequest.course_id.asc(),
            training_models.TrainingDeferralRequest.requested_new_due_date.desc(),
        )
        .all()
    )
    latest_deferral: Dict[str, training_models.TrainingDeferralRequest] = {}
    for d in deferrals:
        if d.course_id not in latest_deferral:
            latest_deferral[d.course_id] = d

    upcoming_events = (
        db.query(training_models.TrainingEvent, training_models.TrainingEventParticipant)
        .join(
            training_models.TrainingEventParticipant,
            training_models.TrainingEvent.id == training_models.TrainingEventParticipant.event_id,
        )
        .filter(
            training_models.TrainingEvent.amo_id == current_user.amo_id,
            training_models.TrainingEvent.course_id.in_(course_ids),
            training_models.TrainingEvent.starts_on >= today,
            training_models.TrainingEvent.status == training_models.TrainingEventStatus.PLANNED,
            training_models.TrainingEventParticipant.user_id == current_user.id,
            training_models.TrainingEventParticipant.status.in_(
                [
                    training_models.TrainingParticipantStatus.SCHEDULED,
                    training_models.TrainingParticipantStatus.INVITED,
                    training_models.TrainingParticipantStatus.CONFIRMED,
                ]
            ),
        )
        .order_by(
            training_models.TrainingEvent.course_id.asc(),
            training_models.TrainingEvent.starts_on.asc(),
        )
        .all()
    )
    earliest_event: Dict[str, Tuple[str, date]] = {}
    for event, _participant in upcoming_events:
        if event.course_id not in earliest_event:
            earliest_event[event.course_id] = (event.id, event.starts_on)

    items: List[training_schemas.TrainingStatusItem] = []
    for course in courses:
        record = latest_record.get(course.id)
        deferral = latest_deferral.get(course.id)
        event_info = earliest_event.get(course.id)

        last_completion_date: Optional[date] = None
        due_date: Optional[date] = None
        deferral_due: Optional[date] = None
        upcoming_event_id: Optional[str] = None
        upcoming_event_date: Optional[date] = None

        if record:
            last_completion_date = record.completion_date
            if record.valid_until:
                due_date = record.valid_until
            elif course.frequency_months:
                due_date = _add_months(record.completion_date, course.frequency_months)

        if deferral:
            deferral_due = deferral.requested_new_due_date

        if event_info:
            upcoming_event_id, upcoming_event_date = event_info

        items.append(
            _build_status_item_from_dates(
                course=course,
                last_completion_date=last_completion_date,
                due_date=due_date,
                deferral_due=deferral_due,
                upcoming_event_id=upcoming_event_id,
                upcoming_event_date=upcoming_event_date,
                today=today,
            )
        )

    return items


@router.get(
    "/status/me/required",
    response_model=List[training_schemas.TrainingStatusItem],
    summary="Training status for the current user, filtered by requirement matrix (IOSA-style)",
)
def get_my_required_training_status(
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(get_current_active_user),
):
    """
    Uses TrainingRequirement rules to compute which courses apply to this user.
    If no requirements exist, falls back to mandatory_for_all + is_mandatory courses.
    """
    today = date.today()

    dept_code = _get_user_department_code(current_user)
    job_role = _get_user_job_role(current_user)

    reqs = (
        db.query(training_models.TrainingRequirement)
        .filter(
            training_models.TrainingRequirement.amo_id == current_user.amo_id,
            training_models.TrainingRequirement.is_active.is_(True),
        )
        .all()
    )

    required_course_ids: List[str] = []

    if reqs:
        for r in reqs:
            if r.scope == training_models.TrainingRequirementScope.ALL:
                required_course_ids.append(r.course_id)
            elif r.scope == training_models.TrainingRequirementScope.USER and r.user_id == current_user.id:
                required_course_ids.append(r.course_id)
            elif r.scope == training_models.TrainingRequirementScope.DEPARTMENT and dept_code and r.department_code and r.department_code.upper() == dept_code:
                required_course_ids.append(r.course_id)
            elif r.scope == training_models.TrainingRequirementScope.JOB_ROLE and job_role and r.job_role and r.job_role.strip().lower() == job_role.lower():
                required_course_ids.append(r.course_id)

        required_course_ids = sorted(list(set(required_course_ids)))
    else:
        # fallback to course flags
        required_course_ids = [
            c.id
            for c in db.query(training_models.TrainingCourse)
            .filter(
                training_models.TrainingCourse.amo_id == current_user.amo_id,
                training_models.TrainingCourse.is_active.is_(True),
                training_models.TrainingCourse.is_mandatory.is_(True),
            )
            .all()
        ]

    if not required_course_ids:
        return []

    courses = (
        db.query(training_models.TrainingCourse)
        .filter(
            training_models.TrainingCourse.amo_id == current_user.amo_id,
            training_models.TrainingCourse.id.in_(required_course_ids),
            training_models.TrainingCourse.is_active.is_(True),
        )
        .order_by(training_models.TrainingCourse.course_id.asc())
        .all()
    )
    if not courses:
        return []

    course_ids = [c.id for c in courses]

    records = (
        db.query(training_models.TrainingRecord)
        .filter(
            training_models.TrainingRecord.amo_id == current_user.amo_id,
            training_models.TrainingRecord.user_id == current_user.id,
            training_models.TrainingRecord.course_id.in_(course_ids),
        )
        .order_by(training_models.TrainingRecord.course_id.asc(), training_models.TrainingRecord.completion_date.desc())
        .all()
    )
    latest_record: Dict[str, training_models.TrainingRecord] = {}
    for r in records:
        if r.course_id not in latest_record:
            latest_record[r.course_id] = r

    deferrals = (
        db.query(training_models.TrainingDeferralRequest)
        .filter(
            training_models.TrainingDeferralRequest.amo_id == current_user.amo_id,
            training_models.TrainingDeferralRequest.user_id == current_user.id,
            training_models.TrainingDeferralRequest.course_id.in_(course_ids),
            training_models.TrainingDeferralRequest.status == training_models.DeferralStatus.APPROVED,
        )
        .order_by(training_models.TrainingDeferralRequest.course_id.asc(), training_models.TrainingDeferralRequest.requested_new_due_date.desc())
        .all()
    )
    latest_deferral: Dict[str, training_models.TrainingDeferralRequest] = {}
    for d in deferrals:
        if d.course_id not in latest_deferral:
            latest_deferral[d.course_id] = d

    upcoming_events = (
        db.query(training_models.TrainingEvent, training_models.TrainingEventParticipant)
        .join(training_models.TrainingEventParticipant, training_models.TrainingEvent.id == training_models.TrainingEventParticipant.event_id)
        .filter(
            training_models.TrainingEvent.amo_id == current_user.amo_id,
            training_models.TrainingEvent.course_id.in_(course_ids),
            training_models.TrainingEvent.starts_on >= today,
            training_models.TrainingEvent.status == training_models.TrainingEventStatus.PLANNED,
            training_models.TrainingEventParticipant.user_id == current_user.id,
            training_models.TrainingEventParticipant.status.in_(
                [
                    training_models.TrainingParticipantStatus.SCHEDULED,
                    training_models.TrainingParticipantStatus.INVITED,
                    training_models.TrainingParticipantStatus.CONFIRMED,
                ]
            ),
        )
        .order_by(training_models.TrainingEvent.course_id.asc(), training_models.TrainingEvent.starts_on.asc())
        .all()
    )
    earliest_event: Dict[str, Tuple[str, date]] = {}
    for event, _participant in upcoming_events:
        if event.course_id not in earliest_event:
            earliest_event[event.course_id] = (event.id, event.starts_on)

    items: List[training_schemas.TrainingStatusItem] = []
    for course in courses:
        record = latest_record.get(course.id)
        deferral = latest_deferral.get(course.id)
        event_info = earliest_event.get(course.id)

        last_completion_date: Optional[date] = None
        due_date: Optional[date] = None
        deferral_due: Optional[date] = None
        upcoming_event_id: Optional[str] = None
        upcoming_event_date: Optional[date] = None

        if record:
            last_completion_date = record.completion_date
            due_date = record.valid_until or (_add_months(record.completion_date, course.frequency_months) if course.frequency_months else None)

        if deferral:
            deferral_due = deferral.requested_new_due_date

        if event_info:
            upcoming_event_id, upcoming_event_date = event_info

        items.append(
            _build_status_item_from_dates(
                course=course,
                last_completion_date=last_completion_date,
                due_date=due_date,
                deferral_due=deferral_due,
                upcoming_event_id=upcoming_event_id,
                upcoming_event_date=upcoming_event_date,
                today=today,
            )
        )

    return items


# ---------------------------------------------------------------------------
# EVIDENCE PACK EXPORTS
# ---------------------------------------------------------------------------


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
