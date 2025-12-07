from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as accounts_models
from . import models as training_models
from . import schemas as training_schemas

router = APIRouter(prefix="/training", tags=["training"])

_MAX_PAGE_SIZE = 1000  # hard ceiling for list endpoints to protect DB


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------


def _normalize_pagination(limit: int, offset: int) -> Tuple[int, int]:
    """
    Clamp pagination parameters to safe bounds.
    """
    if limit <= 0:
        limit = 50
    if limit > _MAX_PAGE_SIZE:
        limit = _MAX_PAGE_SIZE
    if offset < 0:
        offset = 0
    return limit, offset


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

    if getattr(current_user, "is_superuser", False) or getattr(
        current_user, "is_amo_admin", False
    ):
        return current_user

    # Explicit role allowance (aligned with router_admin authorisation logic)
    if current_user.role == accounts_models.AccountRole.QUALITY_MANAGER:
        return current_user

    # Department-based allowance for broader Quality team
    dept = getattr(current_user, "department", None)
    if dept is not None and getattr(dept, "code", "").upper() == "QUALITY":
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only Quality department or AMO Admin may modify training data.",
    )


def _add_months(base: date, months: int) -> date:
    """
    Add a number of calendar months to a date.
    This intentionally avoids external dependencies.
    """
    if months <= 0:
        return base

    year = base.year + (base.month - 1 + months) // 12
    month = (base.month - 1 + months) % 12 + 1
    # Clamp day to last valid day of target month
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
    """
    Pure status computation used by per-user views and global dashboards.
    """
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

    # If there is an approved deferral and the controlling due date is not in the past,
    # mark as DEFERRED (it overrides OK / DUE_SOON for reporting purposes).
    if deferral_due and extended_due_date and days_until_due is not None and days_until_due >= 0:
        status_label = "DEFERRED"

    # If there is no completion but an upcoming event, surface SCHEDULED_ONLY
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

    return (
        q.order_by(training_models.TrainingCourse.course_id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )


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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Training course not found for your AMO.",
        )
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
    # Normalise CourseID (trim + upper-case)
    course_id_norm = payload.course_id.strip().upper()

    # Enforce uniqueness of CourseID per AMO
    existing = (
        db.query(training_models.TrainingCourse)
        .filter(
            training_models.TrainingCourse.amo_id == current_user.amo_id,
            training_models.TrainingCourse.course_id == course_id_norm,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A course with this CourseID already exists in this AMO.",
        )

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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Training course not found for your AMO.",
        )

    update_data = payload.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(course, field, value)

    course.updated_by_user_id = current_user.id

    db.add(course)
    db.commit()
    db.refresh(course)
    return course


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

    q = db.query(training_models.TrainingEvent).filter(
        training_models.TrainingEvent.amo_id == current_user.amo_id
    )

    if course_pk:
        q = q.filter(training_models.TrainingEvent.course_id == course_pk)
    if from_date:
        q = q.filter(training_models.TrainingEvent.starts_on >= from_date)
    if to_date:
        q = q.filter(training_models.TrainingEvent.starts_on <= to_date)

    return (
        q.order_by(training_models.TrainingEvent.starts_on.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )


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
    """
    View-only: who is planned/assigned for a specific event.
    """
    # First confirm event belongs to this AMO
    event = (
        db.query(training_models.TrainingEvent)
        .filter(
            training_models.TrainingEvent.id == event_id,
            training_models.TrainingEvent.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Training event not found for your AMO.",
        )

    participants = (
        db.query(training_models.TrainingEventParticipant)
        .filter(training_models.TrainingEventParticipant.event_id == event.id)
        .order_by(training_models.TrainingEventParticipant.id.asc())
        .all()
    )
    return participants


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
        .filter(
            training_models.TrainingCourse.id == payload.course_pk,
            training_models.TrainingCourse.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not course:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid course for this AMO.",
        )

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
    db.commit()
    db.refresh(event)
    return event


@router.put(
    "/events/{event_id}",
    response_model=training_schemas.TrainingEventRead,
    summary="Update a training event (Quality / AMO admin only)",
)
def update_event(
    event_id: str,
    payload: training_schemas.TrainingEventUpdate,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    event = (
        db.query(training_models.TrainingEvent)
        .filter(
            training_models.TrainingEvent.id == event_id,
            training_models.TrainingEvent.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Training event not found for your AMO.",
        )

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(event, field, value)

    db.add(event)
    db.commit()
    db.refresh(event)
    return event


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
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    event = (
        db.query(training_models.TrainingEvent)
        .filter(
            training_models.TrainingEvent.id == payload.event_id,
            training_models.TrainingEvent.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not event:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Event not found for your AMO.",
        )

    trainee = (
        db.query(accounts_models.User)
        .filter(
            accounts_models.User.id == payload.user_id,
            accounts_models.User.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not trainee:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target user not found in your AMO.",
        )

    existing = (
        db.query(training_models.TrainingEventParticipant)
        .filter(
            training_models.TrainingEventParticipant.event_id == event.id,
            training_models.TrainingEventParticipant.user_id == trainee.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already assigned to this event.",
        )

    participant = training_models.TrainingEventParticipant(
        event_id=event.id,
        user_id=trainee.id,
        status=payload.status,
        attendance_note=payload.attendance_note,
        deferral_request_id=payload.deferral_request_id,
    )

    db.add(participant)
    db.commit()
    db.refresh(participant)
    return participant


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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Training event participant not found.",
        )

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(participant, field, value)

    db.add(participant)
    db.commit()
    db.refresh(participant)
    return participant


# ---------------------------------------------------------------------------
# TRAINING RECORDS
# ---------------------------------------------------------------------------


@router.get(
    "/records",
    response_model=List[training_schemas.TrainingRecordRead],
    summary="List training records for the current AMO",
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

    q = db.query(training_models.TrainingRecord).filter(
        training_models.TrainingRecord.amo_id == current_user.amo_id
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


@router.post(
    "/records",
    response_model=training_schemas.TrainingRecordRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a training completion record (Quality / AMO admin only)",
)
def create_training_record(
    payload: training_schemas.TrainingRecordCreate,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    today = date.today()
    if payload.completion_date > today:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Completion date cannot be in the future.",
        )

    course = (
        db.query(training_models.TrainingCourse)
        .filter(
            training_models.TrainingCourse.id == payload.course_pk,
            training_models.TrainingCourse.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not course:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid course for this AMO.",
        )

    trainee = (
        db.query(accounts_models.User)
        .filter(
            accounts_models.User.id == payload.user_id,
            accounts_models.User.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not trainee:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target user not found in your AMO.",
        )

    # Compute valid_until if not explicitly provided
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
    )

    db.add(record)
    db.commit()
    db.refresh(record)
    return record


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
    """
    Any active user may request a deferral for themselves.
    Quality / AMO Admin may raise deferrals on behalf of others.
    """
    # Validate course / user
    course = (
        db.query(training_models.TrainingCourse)
        .filter(
            training_models.TrainingCourse.id == payload.course_pk,
            training_models.TrainingCourse.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not course:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid course for this AMO.",
        )

    trainee = (
        db.query(accounts_models.User)
        .filter(
            accounts_models.User.id == payload.user_id,
            accounts_models.User.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not trainee:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target user not found in your AMO.",
        )

    # If not training editor, user can only request for themselves
    try:
        _require_training_editor(current_user)  # type: ignore[arg-type]
        is_editor = True
    except HTTPException:
        is_editor = False

    if not is_editor and trainee.id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only request training deferrals for yourself.",
        )

    today = date.today()
    if payload.original_due_date < today:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Training is already past due; deferral requests must be made before expiry.",
        )

    # QWI-026: at least 72 hours before due date
    if (payload.original_due_date - today) < timedelta(days=3):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deferral requests must be sent at least 72 hours before the due date.",
        )

    # Sanity: new due date must not be earlier than the original due date
    if payload.requested_new_due_date < payload.original_due_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New due date cannot be earlier than the original due date.",
        )

    deferral = training_models.TrainingDeferralRequest(
        amo_id=current_user.amo_id,
        user_id=trainee.id,
        course_id=course.id,
        original_due_date=payload.original_due_date,
        requested_new_due_date=payload.requested_new_due_date,
        reason_category=payload.reason_category,
        reason_text=payload.reason_text,
        status=training_models.DeferralStatus.PENDING,
    )

    db.add(deferral)
    db.commit()
    db.refresh(deferral)
    return deferral


@router.put(
    "/deferrals/{deferral_id}",
    response_model=training_schemas.TrainingDeferralRequestRead,
    summary="Approve or reject a training deferral (Quality / AMO admin only)",
)
def update_deferral_request(
    deferral_id: str,
    payload: training_schemas.TrainingDeferralRequestUpdate,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    deferral = (
        db.query(training_models.TrainingDeferralRequest)
        .filter(
            training_models.TrainingDeferralRequest.id == deferral_id,
            training_models.TrainingDeferralRequest.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not deferral:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deferral request not found.",
        )

    data = payload.model_dump(exclude_unset=True)
    status_value = data.get("status")
    if status_value is not None:
        # Changing status implies a decision
        deferral.status = status_value
        deferral.decided_at = datetime.utcnow()
        deferral.decided_by_user_id = current_user.id

    if "decision_comment" in data:
        deferral.decision_comment = data["decision_comment"]
    if "requested_new_due_date" in data and data["requested_new_due_date"] is not None:
        if data["requested_new_due_date"] < deferral.original_due_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New due date cannot be earlier than the original due date.",
            )
        deferral.requested_new_due_date = data["requested_new_due_date"]

    db.add(deferral)
    db.commit()
    db.refresh(deferral)
    return deferral


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
    """
    Quality view over deferrals, with filters and pagination.
    """
    limit, offset = _normalize_pagination(limit, offset)

    q = db.query(training_models.TrainingDeferralRequest).filter(
        training_models.TrainingDeferralRequest.amo_id == current_user.amo_id
    )

    if user_id:
        q = q.filter(training_models.TrainingDeferralRequest.user_id == user_id)
    if course_pk:
        q = q.filter(training_models.TrainingDeferralRequest.course_id == course_pk)
    if only_pending:
        q = q.filter(
            training_models.TrainingDeferralRequest.status
            == training_models.DeferralStatus.PENDING
        )
    elif status_filter is not None:
        q = q.filter(training_models.TrainingDeferralRequest.status == status_filter)

    return (
        q.order_by(training_models.TrainingDeferralRequest.requested_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------------------------
# PER-PERSON TRAINING STATUS (DUE SOON / OVERDUE / SCHEDULED)
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
    """
    Returns one line per active course in the AMO, with:
    - last completion
    - due / extended due
    - computed status (OK / DUE_SOON / OVERDUE / DEFERRED / SCHEDULED_ONLY / NOT_DONE)

    Optimised to use constant number of queries regardless of course count.
    """
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

    # Latest completion record per course for this user
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

    # Latest approved deferral per course for this user
    deferrals = (
        db.query(training_models.TrainingDeferralRequest)
        .filter(
            training_models.TrainingDeferralRequest.amo_id == current_user.amo_id,
            training_models.TrainingDeferralRequest.user_id == current_user.id,
            training_models.TrainingDeferralRequest.course_id.in_(course_ids),
            training_models.TrainingDeferralRequest.status
            == training_models.DeferralStatus.APPROVED,
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

    # Earliest upcoming planned event per course for this user
    upcoming_events = (
        db.query(training_models.TrainingEvent, training_models.TrainingEventParticipant)
        .join(
            training_models.TrainingEventParticipant,
            training_models.TrainingEvent.id
            == training_models.TrainingEventParticipant.event_id,
        )
        .filter(
            training_models.TrainingEvent.amo_id == current_user.amo_id,
            training_models.TrainingEvent.course_id.in_(course_ids),
            training_models.TrainingEvent.starts_on >= today,
            training_models.TrainingEvent.status
            == training_models.TrainingEventStatus.PLANNED,
            training_models.TrainingEventParticipant.user_id == current_user.id,
            training_models.TrainingEventParticipant.status.in_(
                [
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
    for event, participant in upcoming_events:
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

        item = _build_status_item_from_dates(
            course=course,
            last_completion_date=last_completion_date,
            due_date=due_date,
            deferral_due=deferral_due,
            upcoming_event_id=upcoming_event_id,
            upcoming_event_date=upcoming_event_date,
            today=today,
        )
        items.append(item)

    return items


@router.get(
    "/status/users/{user_id}",
    response_model=List[training_schemas.TrainingStatusItem],
    summary="Training status for a specific user (Quality / AMO admin only)",
)
def get_user_training_status(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: accounts_models.User = Depends(_require_training_editor),
):
    """
    Quality / AMO Admin view of any user's training status within the same AMO.
    """
    today = date.today()

    trainee = (
        db.query(accounts_models.User)
        .filter(
            accounts_models.User.id == user_id,
            accounts_models.User.amo_id == current_user.amo_id,
        )
        .first()
    )
    if not trainee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in your AMO.",
        )

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

    # Latest completion record per course for this user
    records = (
        db.query(training_models.TrainingRecord)
        .filter(
            training_models.TrainingRecord.amo_id == current_user.amo_id,
            training_models.TrainingRecord.user_id == trainee.id,
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

    # Latest approved deferral per course for this user
    deferrals = (
        db.query(training_models.TrainingDeferralRequest)
        .filter(
            training_models.TrainingDeferralRequest.amo_id == current_user.amo_id,
            training_models.TrainingDeferralRequest.user_id == trainee.id,
            training_models.TrainingDeferralRequest.course_id.in_(course_ids),
            training_models.TrainingDeferralRequest.status
            == training_models.DeferralStatus.APPROVED,
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

    # Earliest upcoming planned event per course for this user
    upcoming_events = (
        db.query(training_models.TrainingEvent, training_models.TrainingEventParticipant)
        .join(
            training_models.TrainingEventParticipant,
            training_models.TrainingEvent.id
            == training_models.TrainingEventParticipant.event_id,
        )
        .filter(
            training_models.TrainingEvent.amo_id == current_user.amo_id,
            training_models.TrainingEvent.course_id.in_(course_ids),
            training_models.TrainingEvent.starts_on >= today,
            training_models.TrainingEvent.status
            == training_models.TrainingEventStatus.PLANNED,
            training_models.TrainingEventParticipant.user_id == trainee.id,
            training_models.TrainingEventParticipant.status.in_(
                [
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
    for event, participant in upcoming_events:
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

        item = _build_status_item_from_dates(
            course=course,
            last_completion_date=last_completion_date,
            due_date=due_date,
            deferral_due=deferral_due,
            upcoming_event_id=upcoming_event_id,
            upcoming_event_date=upcoming_event_date,
            today=today,
        )
        items.append(item)

    return items


# ---------------------------------------------------------------------------
# GLOBAL DASHBOARD SUMMARY (AMO-WIDE)
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
    """
    Returns aggregate counts across the AMO:

    - total_mandatory_records: number of (user, course) combinations considered
    - ok_count: status == 'OK'
    - due_soon_count: status == 'DUE_SOON'
    - overdue_count: status == 'OVERDUE'
    - deferred_count: status == 'DEFERRED'

    For performance, uses only a handful of queries regardless of user/course count.
    """
    today = date.today()

    # Active courses in this AMO
    courses_q = db.query(training_models.TrainingCourse).filter(
        training_models.TrainingCourse.amo_id == current_user.amo_id,
        training_models.TrainingCourse.is_active.is_(True),
    )
    if not include_non_mandatory:
        courses_q = courses_q.filter(
            training_models.TrainingCourse.is_mandatory.is_(True)
        )
    courses: List[training_models.TrainingCourse] = (
        courses_q.order_by(training_models.TrainingCourse.course_id.asc()).all()
    )

    if not courses:
        return training_schemas.TrainingDashboardSummary(
            total_mandatory_records=0,
            ok_count=0,
            due_soon_count=0,
            overdue_count=0,
            deferred_count=0,
        )

    course_ids = [c.id for c in courses]

    # All users in this AMO (we'll skip system accounts in Python loop)
    users: List[accounts_models.User] = (
        db.query(accounts_models.User)
        .filter(accounts_models.User.amo_id == current_user.amo_id)
        .all()
    )
    if not users:
        return training_schemas.TrainingDashboardSummary(
            total_mandatory_records=0,
            ok_count=0,
            due_soon_count=0,
            overdue_count=0,
            deferred_count=0,
        )

    # Latest completion record per (user, course)
    records = (
        db.query(training_models.TrainingRecord)
        .filter(
            training_models.TrainingRecord.amo_id == current_user.amo_id,
            training_models.TrainingRecord.course_id.in_(course_ids),
        )
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

    # Latest approved deferral per (user, course)
    deferrals = (
        db.query(training_models.TrainingDeferralRequest)
        .filter(
            training_models.TrainingDeferralRequest.amo_id == current_user.amo_id,
            training_models.TrainingDeferralRequest.course_id.in_(course_ids),
            training_models.TrainingDeferralRequest.status
            == training_models.DeferralStatus.APPROVED,
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

    # Python loop over (user, course) grid, using preloaded maps.
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
                if record.valid_until:
                    due_date = record.valid_until
                elif course.frequency_months:
                    due_date = _add_months(
                        record.completion_date, course.frequency_months
                    )

            if deferral:
                deferral_due = deferral.requested_new_due_date

            # We don't care about upcoming events for summary counts
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
