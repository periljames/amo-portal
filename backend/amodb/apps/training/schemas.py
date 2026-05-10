# backend/amodb/apps/training/schemas.py

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .models import (
    DeferralReasonCategory,
    DeferralStatus,
    TrainingCourseCategory,
    TrainingDeliveryMethod,
    TrainingEventStatus,
    TrainingFileKind,
    TrainingFileReviewStatus,
    TrainingKind,
    TrainingNotificationSeverity,
    TrainingParticipantStatus,
    TrainingRecordVerificationStatus,
    TrainingRequirementScope,
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
        description="Short code like 'SMS-REF', 'HF-INIT', 'DGR-REF'. Must be unique within an AMO.",
    )
    course_name: str = Field(..., description="Full course name / description as used in manuals.")

    frequency_months: Optional[int] = Field(
        None,
        description="Recurrent interval in months. If omitted/NULL, validity is not auto-calculated.",
    )

    category: TrainingCourseCategory = Field(
        TrainingCourseCategory.OTHER,
        description="Broad bucket (HF, FTS, EWIS, SMS, TYPE, INTERNAL_TECHNICAL, etc.).",
    )
    category_raw: Optional[str] = Field(
        None,
        description="Raw spreadsheet category value (free text) when importing external course catalogs.",
    )
    status: str = Field("One_Off", description="Course status from source catalog (Initial/Recurrent/One_Off).")
    scope: Optional[str] = Field(None, description="Optional applicability scope from source catalog.")
    kind: TrainingKind = Field(TrainingKind.OTHER, description="INITIAL / RECURRENT / REFRESHER / CONTINUATION / OTHER.")
    delivery_method: TrainingDeliveryMethod = Field(
        TrainingDeliveryMethod.CLASSROOM,
        description="CLASSROOM / ONLINE / OJT / MIXED / OTHER.",
    )

    regulatory_reference: Optional[str] = Field(
        None,
        description="Optional reference (e.g. MPM section, MTM chapter, KCAR, IOSA chapter, etc.).",
    )
    default_provider: Optional[str] = None
    default_duration_days: Optional[int] = 1
    nominal_hours: Optional[int] = Field(None, description="Nominal classroom/OJT hours for the course.")
    planning_lead_days: Optional[int] = Field(45, description="Default lead window used to schedule before due date.")
    candidate_requirement_text: Optional[str] = Field(None, description="MTM candidate qualification / scope / audience notes.")

    is_mandatory: bool = Field(False, description="True if this is a required course for some staff group.")
    mandatory_for_all: bool = Field(False, description="True if all staff in the AMO must hold this training.")

    prerequisite_course_id: Optional[str] = Field(
        None,
        description="Optional CourseID of prerequisite (e.g. 'SMS-INIT' for 'SMS-REF').",
    )


class TrainingCourseCreate(TrainingCourseBase):
    """
    amo_id and created_by_user_id come from the current user/context in the router.
    """

    pass


class TrainingCourseUpdate(BaseModel):
    course_name: Optional[str] = None
    frequency_months: Optional[int] = None
    category: Optional[TrainingCourseCategory] = None
    category_raw: Optional[str] = None
    status: Optional[str] = None
    scope: Optional[str] = None
    kind: Optional[TrainingKind] = None
    delivery_method: Optional[TrainingDeliveryMethod] = None
    regulatory_reference: Optional[str] = None
    default_provider: Optional[str] = None
    default_duration_days: Optional[int] = None
    nominal_hours: Optional[int] = None
    planning_lead_days: Optional[int] = None
    candidate_requirement_text: Optional[str] = None
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
# TRAINING REQUIREMENTS (WHO MUST HAVE WHAT)
# ---------------------------------------------------------------------------


class TrainingRequirementBase(BaseModel):
    course_pk: str = Field(..., description="TrainingCourse DB id that is required.")
    scope: TrainingRequirementScope = Field(
        TrainingRequirementScope.ALL,
        description="ALL / DEPARTMENT / JOB_ROLE / USER.",
    )

    department_code: Optional[str] = Field(
        None,
        description="Required when scope=DEPARTMENT. Must match your personnel/HR department code.",
    )
    job_role: Optional[str] = Field(
        None,
        description="Required when scope=JOB_ROLE. Use your standardized role titles.",
    )
    user_id: Optional[str] = Field(
        None,
        description="Required when scope=USER. The specific user required to complete this course.",
    )

    is_mandatory: bool = Field(True, description="True if mandatory for the defined scope.")
    is_active: bool = Field(True, description="Set false to retire a requirement without deleting history.")

    effective_from: Optional[date] = Field(None, description="Optional start date for this requirement rule.")
    effective_to: Optional[date] = Field(None, description="Optional end date for this requirement rule.")


class TrainingRequirementCreate(TrainingRequirementBase):
    """
    amo_id and created_by_user_id come from current_user in the router.
    """

    pass


class TrainingRequirementUpdate(BaseModel):
    course_pk: Optional[str] = None
    scope: Optional[TrainingRequirementScope] = None
    department_code: Optional[str] = None
    job_role: Optional[str] = None
    user_id: Optional[str] = None
    is_mandatory: Optional[bool] = None
    is_active: Optional[bool] = None
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


class TrainingRequirementRead(TrainingRequirementBase):
    id: str
    amo_id: str
    created_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TrainingMutationResult(BaseModel):
    id: str
    action: str
    message: str
    soft_deleted: bool = False


# ---------------------------------------------------------------------------
# TRAINING EVENTS (CLASSES / SESSIONS)
# ---------------------------------------------------------------------------


class TrainingEventBase(BaseModel):
    """
    Base fields for a scheduled training session.

    NOTE: course_pk is the DB id of TrainingCourse (not the CourseID/code).
    """

    course_pk: str = Field(..., description="Database id of TrainingCourse (not the short CourseID).")
    title: str = Field(..., description="Title of the class. You can default this from course_name.")
    location: Optional[str] = None
    provider: Optional[str] = None

    starts_on: date = Field(..., description="Planned start date.")
    ends_on: Optional[date] = Field(None, description="Optional end date. If omitted, assumed 1-day session.")

    status: TrainingEventStatus = Field(
        TrainingEventStatus.PLANNED,
        description="PLANNED / IN_PROGRESS / COMPLETED / CANCELLED.",
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


class TrainingEventBatchScheduleCreate(BaseModel):
    course_pk: str = Field(..., description="Database id of TrainingCourse to be delivered in this class/session.")
    user_ids: List[str] = Field(..., min_length=1, description="Users to batch-enrol into the created session.")
    title: Optional[str] = Field(None, description="Session title. Defaults to course name when omitted.")
    provider: Optional[str] = Field(None, description="Trainer / ATO / provider name.")
    provider_kind: Optional[str] = Field("INTERNAL", description="INTERNAL or EXTERNAL provider delivery.")
    delivery_mode: Optional[str] = Field("CLASSROOM", description="CLASSROOM, ONLINE, OJT, MIXED, or other free text.")
    venue_mode: Optional[str] = Field("OFFLINE", description="OFFLINE, ONLINE, or BLENDED presentation mode.")
    instructor_name: Optional[str] = Field(None, description="Internal instructor or external trainer name.")
    location: Optional[str] = Field(None, description="Room / hangar / campus / venue.")
    meeting_link: Optional[str] = Field(None, description="Optional meeting link for online delivery.")
    starts_on: date = Field(..., description="Planned session start date.")
    ends_on: Optional[date] = Field(None, description="Optional end date for multi-day delivery.")
    notes: Optional[str] = Field(None, description="Free-text schedule notes shown in the portal.")
    participant_status: TrainingParticipantStatus = Field(
        TrainingParticipantStatus.SCHEDULED,
        description="Initial participant workflow status applied to all enrolled users.",
    )
    auto_issue_certificates: bool = Field(True, description="Auto-issue certificate numbers when attendance is later marked attended.")
    allow_self_attendance: bool = Field(True, description="Whether attendees may self-mark attendance from the portal.")


class TrainingEventBatchScheduleRead(BaseModel):
    event: TrainingEventRead
    participants: List["TrainingEventParticipantRead"]
    created_count: int


class TrainingAutoGroupScheduleCreate(BaseModel):
    user_ids: List[str] = Field(..., min_length=1, description="Users whose due and overdue courses should be auto-grouped into sessions.")
    include_due_soon: bool = Field(True, description="Include due-soon items in the auto-group scheduler.")
    include_overdue: bool = Field(True, description="Include overdue items in the auto-group scheduler.")
    base_start_on: Optional[date] = Field(None, description="Optional scheduling floor date. Defaults to today.")
    provider: Optional[str] = Field(None, description="Trainer / ATO / provider name applied to created sessions.")
    provider_kind: Optional[str] = Field("INTERNAL", description="INTERNAL or EXTERNAL provider delivery.")
    delivery_mode: Optional[str] = Field("CLASSROOM", description="CLASSROOM, ONLINE, OJT, MIXED, or other free text.")
    venue_mode: Optional[str] = Field("OFFLINE", description="OFFLINE, ONLINE, or BLENDED presentation mode.")
    instructor_name: Optional[str] = Field(None, description="Internal instructor or external trainer name.")
    location: Optional[str] = Field(None, description="Room / hangar / campus / venue.")
    meeting_link: Optional[str] = Field(None, description="Optional meeting link for online delivery.")
    notes: Optional[str] = Field(None, description="Free-text schedule notes shown in the portal.")
    participant_status: TrainingParticipantStatus = Field(
        TrainingParticipantStatus.SCHEDULED,
        description="Initial participant workflow status applied to all enrolled users.",
    )
    auto_issue_certificates: bool = Field(True, description="Auto-issue certificate numbers when attendance is later marked attended.")
    allow_self_attendance: bool = Field(True, description="Whether attendees may self-mark attendance from the portal.")


class TrainingAutoGroupSkippedRead(BaseModel):
    user_id: str
    course_pk: Optional[str] = None
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    reason: str
    availability_status: Optional[str] = None
    next_available_on: Optional[date] = None


class TrainingAutoGroupedSessionRead(BaseModel):
    course_pk: str
    course_code: str
    course_name: str
    availability_bucket: str
    start_on: date
    end_on: Optional[date] = None
    event: TrainingEventRead
    participants: List["TrainingEventParticipantRead"]


class TrainingAutoGroupScheduleRead(BaseModel):
    sessions: List[TrainingAutoGroupedSessionRead] = Field(default_factory=list)
    skipped: List[TrainingAutoGroupSkippedRead] = Field(default_factory=list)
    total_sessions: int = 0
    total_enrolled: int = 0


# ---------------------------------------------------------------------------
# EVENT PARTICIPANTS
# ---------------------------------------------------------------------------


class TrainingEventParticipantBase(BaseModel):
    event_id: str = Field(..., description="TrainingEvent id.")
    user_id: str = Field(..., description="User id (person assigned to this event).")
    status: TrainingParticipantStatus = Field(
        TrainingParticipantStatus.INVITED,
        description="SCHEDULED / INVITED / CONFIRMED / ATTENDED / NO_SHOW / CANCELLED / DEFERRED.",
    )
    attendance_note: Optional[str] = None
    notes: Optional[str] = Field(None, description="General notes about the participant for this event.")


class TrainingEventParticipantCreate(TrainingEventParticipantBase):
    deferral_request_id: Optional[str] = Field(
        None,
        description="Optional link to a deferral request explaining the change in status.",
    )


class TrainingEventParticipantUpdate(BaseModel):
    status: Optional[TrainingParticipantStatus] = None
    attendance_note: Optional[str] = None
    notes: Optional[str] = None
    deferral_request_id: Optional[str] = None

    # These two should normally be set server-side when marking attendance,
    # but included here in case your UI workflow captures it explicitly.
    attendance_marked_at: Optional[datetime] = None
    attendance_marked_by_user_id: Optional[str] = None
    attended_at: Optional[datetime] = None


class TrainingEventParticipantRead(TrainingEventParticipantBase):
    id: str
    amo_id: str
    deferral_request_id: Optional[str] = None

    attendance_marked_at: Optional[datetime] = None
    attendance_marked_by_user_id: Optional[str] = None
    attended_at: Optional[datetime] = None

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# TRAINING RECORDS (COMPLETED TRAINING)
# ---------------------------------------------------------------------------


class TrainingRecordBase(BaseModel):
    user_id: str = Field(..., description="User id of person who completed training.")
    course_pk: str = Field(..., description="TrainingCourse DB id associated with this completion.")

    event_id: Optional[str] = Field(None, description="Optional TrainingEvent id if completion is tied to a class.")

    completion_date: date = Field(..., description="Date the training was completed.")
    valid_until: Optional[date] = Field(
        None,
        description="Explicit validity; usually completion_date + frequency_months.",
    )

    hours_completed: Optional[int] = None
    exam_score: Optional[int] = Field(None, description="Optional exam/assessment score.")

    certificate_reference: Optional[str] = None
    attachment_file_id: Optional[str] = Field(
        None,
        description="Optional uploaded evidence/certificate file id to link to the created training record. Required when certificate_reference is supplied.",
    )
    remarks: Optional[str] = None
    is_manual_entry: bool = Field(False, description="True if imported from legacy Excel or keyed manually by QA.")


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
    attachment_file_id: Optional[str] = None
    clear_attachment: bool = False
    remarks: Optional[str] = None


class TrainingRecordVerify(BaseModel):
    """
    Used by Quality/authorized roles to verify training evidence and the record.
    """

    verification_status: TrainingRecordVerificationStatus = Field(
        ...,
        description="PENDING / VERIFIED / REJECTED.",
    )
    verification_comment: Optional[str] = None


class TrainingRecordRead(TrainingRecordBase):
    id: str
    amo_id: str
    created_by_user_id: Optional[str] = None
    created_at: datetime
    course_id: Optional[str] = None
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    user_staff_code: Optional[str] = None
    user_full_name: Optional[str] = None
    legacy_record_id: Optional[str] = None
    source_status: Optional[str] = None
    record_status: Optional[str] = None
    superseded_by_record_id: Optional[str] = None
    superseded_at: Optional[datetime] = None
    purge_after: Optional[date] = None

    verification_status: TrainingRecordVerificationStatus
    verified_at: Optional[datetime] = None
    verified_by_user_id: Optional[str] = None
    verification_comment: Optional[str] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# DEFERRALS (QWI-026)
# ---------------------------------------------------------------------------


class TrainingDeferralRequestBase(BaseModel):
    user_id: str = Field(..., description="User affected by the deferral (the trainee).")
    course_pk: str = Field(..., description="TrainingCourse DB id for which deferral is requested.")

    original_due_date: date = Field(..., description="Due date at time of request.")
    requested_new_due_date: date = Field(..., description="Requested new due date (must remain within allowed window).")

    reason_category: DeferralReasonCategory = Field(
        DeferralReasonCategory.OTHER,
        description="ILLNESS / OPERATIONAL_REQUIREMENTS / PERSONAL_EMERGENCY / PROVIDER_CANCELLATION / SYSTEM_FAILURE / OTHER.",
    )
    reason_text: Optional[str] = Field(
        None,
        description="Free text justification (e.g. medical certificate, disruption reference).",
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

    requested_by_user_id: Optional[str] = None
    status: DeferralStatus
    requested_at: datetime

    decided_at: Optional[datetime] = None
    decided_by_user_id: Optional[str] = None
    decision_comment: Optional[str] = None

    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# TRAINING FILES (CERTIFICATES / AMEL / EVIDENCE UPLOADS)
# ---------------------------------------------------------------------------


class TrainingFileBase(BaseModel):
    owner_user_id: str = Field(..., description="User id that this file belongs to (usually the trainee).")
    kind: TrainingFileKind = Field(TrainingFileKind.OTHER, description="CERTIFICATE / AMEL / LICENSE / EVIDENCE / OTHER.")

    course_id: Optional[str] = Field(None, description="Optional TrainingCourse id this file relates to.")
    event_id: Optional[str] = Field(None, description="Optional TrainingEvent id this file relates to.")
    record_id: Optional[str] = Field(None, description="Optional TrainingRecord id this file relates to.")
    deferral_request_id: Optional[str] = Field(None, description="Optional TrainingDeferralRequest id this file relates to.")

    original_filename: str = Field(..., description="Original uploaded filename.")
    content_type: Optional[str] = Field(None, description="MIME type, if known.")
    size_bytes: Optional[int] = Field(None, description="File size in bytes, if known.")
    sha256: Optional[str] = Field(None, description="Optional hash for integrity/dedup.")


class TrainingFileCreate(TrainingFileBase):
    """
    Note: actual binary upload will typically use multipart/form-data.
    storage_path/uploaded_by_user_id/uploaded_at are controlled server-side.
    """

    pass


class TrainingFileReviewUpdate(BaseModel):
    review_status: TrainingFileReviewStatus = Field(..., description="PENDING / APPROVED / REJECTED.")
    review_comment: Optional[str] = None


class TrainingFileRead(TrainingFileBase):
    id: str
    amo_id: str

    storage_path: str = Field(..., description="Server-side storage path (relative).")

    review_status: TrainingFileReviewStatus
    reviewed_at: Optional[datetime] = None
    reviewed_by_user_id: Optional[str] = None
    review_comment: Optional[str] = None

    uploaded_by_user_id: Optional[str] = None
    uploaded_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# TRAINING NOTIFICATIONS (IN-APP POPUPS + READ/UNREAD)
# ---------------------------------------------------------------------------


class TrainingNotificationBase(BaseModel):
    title: str
    body: Optional[str] = None
    severity: TrainingNotificationSeverity = Field(
        TrainingNotificationSeverity.INFO,
        description="INFO / ACTION_REQUIRED / WARNING.",
    )
    link_path: Optional[str] = Field(None, description="Frontend route for deep-linking (optional).")
    dedupe_key: Optional[str] = Field(None, description="Optional dedupe key to avoid duplicates/spam.")


class TrainingNotificationCreate(TrainingNotificationBase):
    user_id: str = Field(..., description="Target user id for this notification.")


class TrainingNotificationRead(TrainingNotificationBase):
    id: str
    amo_id: str
    user_id: str
    created_by_user_id: Optional[str] = None
    created_at: datetime
    read_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TrainingNotificationMarkRead(BaseModel):
    read_at: Optional[datetime] = Field(
        None,
        description="If omitted, server sets current timestamp.",
    )


# ---------------------------------------------------------------------------
# TRAINING AUDIT LOG (TRACEABILITY)
# ---------------------------------------------------------------------------


class TrainingAuditLogRead(BaseModel):
    id: str
    amo_id: str
    actor_user_id: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    created_at: datetime

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
    - course_name: 'Human Factors (Refresher)'
    - status: 'OK' / 'DUE_SOON' / 'OVERDUE' / 'DEFERRED' / 'SCHEDULED_ONLY' / 'NOT_DONE'
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


class TrainingStatusBulkRequest(BaseModel):
    user_ids: List[str] = Field(default_factory=list, description="User ids to evaluate in a single batch.")


class TrainingStatusBulkResponse(BaseModel):
    users: Dict[str, List[TrainingStatusItem]] = Field(default_factory=dict)


class TrainingUserProfileLiteRead(BaseModel):
    id: str
    amo_id: str
    department_id: Optional[str] = None
    staff_code: str
    email: str
    first_name: str
    last_name: str
    full_name: str
    role: str
    position_title: Optional[str] = None
    phone: Optional[str] = None
    secondary_phone: Optional[str] = None
    regulatory_authority: Optional[str] = None
    licence_number: Optional[str] = None
    licence_state_or_country: Optional[str] = None
    licence_expires_on: Optional[date] = None
    is_active: bool
    is_superuser: bool
    is_amo_admin: bool
    must_change_password: bool
    last_login_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class TrainingUserDetailBundleRead(BaseModel):
    user: TrainingUserProfileLiteRead
    hire_date: Optional[date] = None
    status_items: List[TrainingStatusItem] = Field(default_factory=list)
    records: List[TrainingRecordRead] = Field(default_factory=list)
    records_total: int = 0
    deferrals: List[TrainingDeferralRequestRead] = Field(default_factory=list)
    deferrals_total: int = 0
    files: List[TrainingFileRead] = Field(default_factory=list)
    files_total: int = 0
    upcoming_events: List[TrainingEventRead] = Field(default_factory=list)
    upcoming_events_total: int = 0


class TrainingRecordsByUsersRequest(BaseModel):
    user_ids: List[str] = Field(default_factory=list, description="Users to fetch training records for.")
    limit: int = Field(500, ge=1, le=2000)
    offset: int = Field(0, ge=0)

class TrainingAccessState(BaseModel):
    user_id: str
    portal_locked: bool
    portal_lock_reason: Optional[str] = None
    crs_blocked: bool
    overdue_mandatory_count: int = 0
    due_soon_mandatory_count: int = 0
    deferred_mandatory_count: int = 0
    not_done_mandatory_count: int = 0
    ok_mandatory_count: int = 0
    upcoming_scheduled_count: int = 0


class TrainingDashboardSummary(BaseModel):
    """
    High-level summary counts for the Quality / AMO dashboard.
    """

    total_mandatory_records: int
    ok_count: int
    due_soon_count: int
    overdue_count: int
    deferred_count: int

    scheduled_count: int = Field(0, description="Count of staff with scheduled events that address due/overdue items.")
    not_done_count: int = Field(0, description="Count of mandatory items with no completion on record.")


class TrainingUserDashboard(BaseModel):
    """
    What a logged-in user can see on their profile/training page.
    """

    user_id: str
    items: List[TrainingStatusItem]
    summary: TrainingDashboardSummary


class TrainingQualityDashboard(BaseModel):
    """
    What Quality can see at a glance.
    """

    summary: TrainingDashboardSummary
    top_overdue: List[TrainingStatusItem] = Field(default_factory=list, description="Optional: most urgent overdue items.")


class CourseImportRowIssue(BaseModel):
    row_number: int
    course_id: Optional[str] = None
    reason: str


class CourseImportSummary(BaseModel):
    dry_run: bool
    total_rows: int
    created_courses: int
    updated_courses: int
    skipped_rows: int
    issues: List[CourseImportRowIssue] = Field(default_factory=list)

class TrainingRecordImportRowIssue(BaseModel):
    row_number: int
    legacy_record_id: Optional[str] = None
    person_id: Optional[str] = None
    course_id: Optional[str] = None
    reason: str


class TrainingRecordImportChange(BaseModel):
    field: str
    label: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None


class TrainingRecordImportRowPreview(BaseModel):
    row_number: int
    legacy_record_id: Optional[str] = None
    person_id: str
    person_name: Optional[str] = None
    course_id: str
    course_name: str
    completion_date: date
    next_due_date: Optional[date] = None
    days_to_due: Optional[int] = None
    source_status: Optional[str] = None
    action: str
    matched_user_id: Optional[str] = None
    matched_user_name: Optional[str] = None
    matched_user_active: Optional[bool] = None
    matched_course_pk: Optional[str] = None
    matched_course_name: Optional[str] = None
    existing_record_id: Optional[str] = None
    changes: List[TrainingRecordImportChange] = Field(default_factory=list)
    reason: Optional[str] = None


class TrainingRecordImportSummary(BaseModel):
    dry_run: bool
    total_rows: int
    created_records: int
    updated_records: int
    unchanged_rows: int
    skipped_rows: int
    matched_inactive_rows: int = 0
    issues: List[TrainingRecordImportRowIssue] = Field(default_factory=list)
    preview_rows: List[TrainingRecordImportRowPreview] = Field(default_factory=list)

