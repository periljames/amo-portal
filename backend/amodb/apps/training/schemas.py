# backend/amodb/apps/training/schemas.py

from __future__ import annotations

from datetime import date, datetime
from typing import Optional, List

from pydantic import BaseModel, Field

from .models import (
    TrainingCourseCategory,
    TrainingKind,
    TrainingDeliveryMethod,
    TrainingEventStatus,
    TrainingParticipantStatus,
    DeferralStatus,
    DeferralReasonCategory,
)


# ---------------------------------------------------------------------------
# TRAINING COURSES
# ---------------------------------------------------------------------------


class TrainingCourseBase(BaseModel):
    """
    Base fields for a training course.

    These map directly (and extend) your Excel structure:

    - course_id          -> CourseID (e.g. 'SMS-REF')
    - course_name        -> CourseName
    - frequency_months   -> FrequencyMonths
    """

    course_id: str = Field(
        ...,
        description="Short code like 'SMS-REF', 'HF-INIT', 'DGR-REF'. "
        "Must be unique within an AMO.",
    )
    course_name: str = Field(
        ...,
        description="Full course name / description as used in manuals.",
    )

    frequency_months: Optional[int] = Field(
        None,
        description="Recurrent interval in months. "
        "If omitted/NULL, validity is not auto-calculated.",
    )

    category: TrainingCourseCategory = Field(
        TrainingCourseCategory.OTHER,
        description="Broad bucket (HF, FTS, EWIS, SMS, TYPE, INTERNAL_TECHNICAL, etc.).",
    )
    kind: TrainingKind = Field(
        TrainingKind.OTHER,
        description="INITIAL / RECURRENT / REFRESHER / CONTINUATION / OTHER.",
    )
    delivery_method: TrainingDeliveryMethod = Field(
        TrainingDeliveryMethod.CLASSROOM,
        description="CLASSROOM / ONLINE / OJT / MIXED / OTHER.",
    )

    regulatory_reference: Optional[str] = Field(
        None,
        description="Optional reference (e.g. MPM section, MTM chapter, KCAR, etc.).",
    )
    default_provider: Optional[str] = None
    default_duration_days: Optional[int] = 1

    is_mandatory: bool = Field(
        True,
        description="True if this is a required course for some staff group.",
    )
    mandatory_for_all: bool = Field(
        False,
        description="True if all staff in the AMO must hold this training.",
    )

    prerequisite_course_id: Optional[str] = Field(
        None,
        description="Optional CourseID of prerequisite (e.g. 'SMS-INIT' for 'SMS-REF').",
    )


class TrainingCourseCreate(TrainingCourseBase):
    """
    amo_id and created_by_user_id come from the current user / context in the router.
    """
    pass


class TrainingCourseUpdate(BaseModel):
    course_name: Optional[str] = None
    frequency_months: Optional[int] = None
    category: Optional[TrainingCourseCategory] = None
    kind: Optional[TrainingKind] = None
    delivery_method: Optional[TrainingDeliveryMethod] = None
    regulatory_reference: Optional[str] = None
    default_provider: Optional[str] = None
    default_duration_days: Optional[int] = None
    is_mandatory: Optional[bool] = None
    mandatory_for_all: Optional[bool] = None
    prerequisite_course_id: Optional[str] = None
    is_active: Optional[bool] = None


class TrainingCourseRead(TrainingCourseBase):
    """
    Full course representation returned to clients.
    """

    id: str
    amo_id: str
    is_active: bool
    created_by_user_id: Optional[str] = None
    updated_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# TRAINING EVENTS (CLASSES / SESSIONS)
# ---------------------------------------------------------------------------


class TrainingEventBase(BaseModel):
    """
    Base fields for a scheduled training session.

    NOTE: `course_pk` is the DB id of TrainingCourse (not the CourseID/code).
    The frontend will typically hold both.
    """

    course_pk: str = Field(
        ...,
        description="Database id of TrainingCourse (not the short CourseID).",
    )
    title: str = Field(
        ...,
        description="Title of the class. You can default this from course_name.",
    )
    location: Optional[str] = None
    provider: Optional[str] = None

    starts_on: date = Field(..., description="Planned start date.")
    ends_on: Optional[date] = Field(
        None,
        description="Optional end date. If omitted, assumed 1-day session.",
    )

    status: TrainingEventStatus = Field(
        TrainingEventStatus.PLANNED,
        description="PLANNED / COMPLETED / CANCELLED.",
    )
    notes: Optional[str] = None


class TrainingEventCreate(TrainingEventBase):
    """
    amo_id and created_by_user_id come from current_user in the router.
    """
    pass


class TrainingEventUpdate(BaseModel):
    title: Optional[str] = None
    location: Optional[str] = None
    provider: Optional[str] = None
    starts_on: Optional[date] = None
    ends_on: Optional[date] = None
    status: Optional[TrainingEventStatus] = None
    notes: Optional[str] = None


class TrainingEventRead(TrainingEventBase):
    id: str
    amo_id: str
    created_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# EVENT PARTICIPANTS
# ---------------------------------------------------------------------------


class TrainingEventParticipantBase(BaseModel):
    event_id: str = Field(..., description="TrainingEvent id.")
    user_id: str = Field(..., description="User id (person assigned to this event).")
    status: TrainingParticipantStatus = Field(
        TrainingParticipantStatus.INVITED,
        description="INVITED / CONFIRMED / ATTENDED / NO_SHOW / CANCELLED / DEFERRED.",
    )
    attendance_note: Optional[str] = None


class TrainingEventParticipantCreate(TrainingEventParticipantBase):
    deferral_request_id: Optional[str] = Field(
        None,
        description="Optional link to a deferral request explaining the change in status.",
    )


class TrainingEventParticipantUpdate(BaseModel):
    status: Optional[TrainingParticipantStatus] = None
    attendance_note: Optional[str] = None
    deferral_request_id: Optional[str] = None


class TrainingEventParticipantRead(TrainingEventParticipantBase):
    id: str
    deferral_request_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# TRAINING RECORDS (COMPLETED TRAINING)
# ---------------------------------------------------------------------------


class TrainingRecordBase(BaseModel):
    user_id: str = Field(..., description="User id of person who completed training.")
    course_pk: str = Field(
        ...,
        description="TrainingCourse DB id associated with this completion.",
    )

    event_id: Optional[str] = Field(
        None,
        description="Optional TrainingEvent id if completion is tied to a class.",
    )

    completion_date: date = Field(..., description="Date the training was completed.")
    valid_until: Optional[date] = Field(
        None,
        description="Explicit validity; usually completion_date + frequency_months.",
    )

    hours_completed: Optional[int] = None
    exam_score: Optional[int] = Field(
        None,
        description="Optional exam/assessment score (percentage or marks).",
    )

    certificate_reference: Optional[str] = None
    remarks: Optional[str] = None
    is_manual_entry: bool = Field(
        False,
        description="True if imported from legacy Excel or manually keyed by QA.",
    )


class TrainingRecordCreate(TrainingRecordBase):
    """
    amo_id and created_by_user_id come from current_user in the router.
    """
    pass


class TrainingRecordUpdate(BaseModel):
    completion_date: Optional[date] = None
    valid_until: Optional[date] = None
    hours_completed: Optional[int] = None
    exam_score: Optional[int] = None
    certificate_reference: Optional[str] = None
    remarks: Optional[str] = None


class TrainingRecordRead(TrainingRecordBase):
    id: str
    amo_id: str
    created_by_user_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# DEFERRALS (QWI-026)
# ---------------------------------------------------------------------------


class TrainingDeferralRequestBase(BaseModel):
    user_id: str = Field(..., description="User asking for / affected by deferral.")
    course_pk: str = Field(
        ...,
        description="TrainingCourse DB id for which deferral is requested.",
    )

    original_due_date: date = Field(
        ...,
        description="Due date at time of request.",
    )
    requested_new_due_date: date = Field(
        ...,
        description="Requested new due date (must remain within allowed window).",
    )

    reason_category: DeferralReasonCategory = Field(
        DeferralReasonCategory.OTHER,
        description="ILLNESS / OPERATIONAL_REQUIREMENTS / PERSONAL_EMERGENCY / "
        "PROVIDER_CANCELLATION / SYSTEM_FAILURE / OTHER.",
    )
    reason_text: Optional[str] = Field(
        None,
        description="Free text justification (e.g. medical certificate, disruption ref).",
    )


class TrainingDeferralRequestCreate(TrainingDeferralRequestBase):
    """
    amo_id and requested_by_user_id / decided_by_user_id are managed in the router.
    """
    pass


class TrainingDeferralRequestUpdate(BaseModel):
    status: Optional[DeferralStatus] = None
    decision_comment: Optional[str] = None
    requested_new_due_date: Optional[date] = None


class TrainingDeferralRequestRead(TrainingDeferralRequestBase):
    id: str
    amo_id: str
    status: DeferralStatus
    requested_at: datetime
    decided_at: Optional[datetime] = None
    decided_by_user_id: Optional[str] = None
    decision_comment: Optional[str] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# DASHBOARD / STATUS VIEWS
# ---------------------------------------------------------------------------


class TrainingStatusItem(BaseModel):
    """
    One line in a per-person training dashboard.

    Example:
    - course_id: 'HF-REF'
    - course_name: 'Human Factors in Aviation (Refresher)'
    - status: 'OK' / 'DUE_SOON' / 'OVERDUE' / 'DEFERRED' / 'SCHEDULED_ONLY'
    """

    course_id: str
    course_name: str
    frequency_months: Optional[int]

    last_completion_date: Optional[date] = None
    valid_until: Optional[date] = None
    extended_due_date: Optional[date] = Field(
        None,
        description="If a deferral is approved, this represents the controlling date.",
    )

    days_until_due: Optional[int] = None
    status: str = Field(
        ...,
        description="Computed label: OK / DUE_SOON / OVERDUE / DEFERRED / SCHEDULED_ONLY / NOT_DONE.",
    )

    upcoming_event_id: Optional[str] = None
    upcoming_event_date: Optional[date] = None


class TrainingDashboardSummary(BaseModel):
    """
    High-level summary counts for the Quality / AMO dashboard.
    """

    total_mandatory_records: int
    ok_count: int
    due_soon_count: int
    overdue_count: int
    deferred_count: int
