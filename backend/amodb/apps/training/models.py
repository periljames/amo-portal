# backend/amodb/apps/training/models.py

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from ...database import Base
from ...user_id import generate_user_id


# ---------------------------------------------------------------------------
# ENUMS
# ---------------------------------------------------------------------------


class TrainingCourseCategory(str, enum.Enum):
    HF = "HF"
    FTS = "FTS"
    EWIS = "EWIS"
    SMS = "SMS"
    TYPE = "TYPE"
    INTERNAL_TECHNICAL = "INTERNAL_TECHNICAL"
    QUALITY_SYSTEMS = "QUALITY_SYSTEMS"
    REGULATORY = "REGULATORY"
    OTHER = "OTHER"


class TrainingKind(str, enum.Enum):
    INITIAL = "INITIAL"
    CONTINUATION = "CONTINUATION"
    RECURRENT = "RECURRENT"
    REFRESHER = "REFRESHER"
    OTHER = "OTHER"


class TrainingDeliveryMethod(str, enum.Enum):
    CLASSROOM = "CLASSROOM"
    ONLINE = "ONLINE"
    OJT = "OJT"
    MIXED = "MIXED"
    OTHER = "OTHER"


class TrainingEventStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TrainingParticipantStatus(str, enum.Enum):
    # Keep legacy values for compatibility; add SCHEDULED for clearer UI wording.
    SCHEDULED = "SCHEDULED"
    INVITED = "INVITED"
    CONFIRMED = "CONFIRMED"
    ATTENDED = "ATTENDED"
    NO_SHOW = "NO_SHOW"
    CANCELLED = "CANCELLED"
    DEFERRED = "DEFERRED"


class DeferralStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class DeferralReasonCategory(str, enum.Enum):
    ILLNESS = "ILLNESS"
    OPERATIONAL_REQUIREMENTS = "OPERATIONAL_REQUIREMENTS"
    PERSONAL_EMERGENCY = "PERSONAL_EMERGENCY"
    PROVIDER_CANCELLATION = "PROVIDER_CANCELLATION"
    SYSTEM_FAILURE = "SYSTEM_FAILURE"
    OTHER = "OTHER"


class TrainingRequirementScope(str, enum.Enum):
    """
    How a requirement is applied.
    - ALL: everyone in the AMO
    - DEPARTMENT: by department code
    - JOB_ROLE: by job role string
    - USER: a specific user
    """

    ALL = "ALL"
    DEPARTMENT = "DEPARTMENT"
    JOB_ROLE = "JOB_ROLE"
    USER = "USER"


class TrainingNotificationSeverity(str, enum.Enum):
    INFO = "INFO"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    WARNING = "WARNING"


class TrainingFileKind(str, enum.Enum):
    CERTIFICATE = "CERTIFICATE"
    AMEL = "AMEL"
    LICENSE = "LICENSE"
    EVIDENCE = "EVIDENCE"
    OTHER = "OTHER"


class TrainingFileReviewStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class TrainingRecordVerificationStatus(str, enum.Enum):
    """
    Optional second-layer control for IOSA-style evidence governance:
    - PENDING: uploaded/created but not verified by Quality
    - VERIFIED: verified by Quality (or authorized role)
    - REJECTED: evidence/record rejected (needs correction)
    """

    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


# ---------------------------------------------------------------------------
# TRAINING COURSE MASTER
# ---------------------------------------------------------------------------


class TrainingCourse(Base):
    """
    Master list of training courses for an AMO.

    - course_id  = your legacy CourseID (e.g. SMS-REF, HF-INIT, DGR-REF)
    - course_name = your CourseName string
    - frequency_months = FrequencyMonths from your sheet
    """

    __tablename__ = "training_courses"
    __table_args__ = (
        UniqueConstraint("amo_id", "course_id", name="uq_training_courses_amo_courseid"),
        Index("idx_training_courses_amo_active", "amo_id", "is_active"),
        Index("idx_training_courses_amo_category", "amo_id", "category"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)

    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    course_id = Column(
        String(64),
        nullable=False,
        doc="Short code like 'SMS-REF', 'HF-INIT', 'DGR-REF'.",
    )
    course_name = Column(
        String(255),
        nullable=False,
        doc="Full course name / description as used in manuals.",
    )

    frequency_months = Column(
        Integer,
        nullable=True,
        doc="Recurrent interval in months; NULL for one-off or manually-controlled courses.",
    )

    category = Column(
        Enum(TrainingCourseCategory, name="training_course_category_enum"),
        nullable=False,
        default=TrainingCourseCategory.OTHER,
        index=True,
    )

    kind = Column(
        Enum(TrainingKind, name="training_kind_enum"),
        nullable=False,
        default=TrainingKind.OTHER,
        index=True,
    )

    delivery_method = Column(
        Enum(TrainingDeliveryMethod, name="training_delivery_method_enum"),
        nullable=False,
        default=TrainingDeliveryMethod.CLASSROOM,
    )

    regulatory_reference = Column(String(255), nullable=True)
    default_provider = Column(String(255), nullable=True)
    default_duration_days = Column(Integer, nullable=True, default=1)

    is_mandatory = Column(Boolean, nullable=False, default=True)
    mandatory_for_all = Column(Boolean, nullable=False, default=False)

    prerequisite_course_id = Column(
        String(64),
        nullable=True,
        doc="Optional CourseID of prerequisite (e.g. 'SMS-INIT' before 'SMS-REF').",
    )

    is_active = Column(Boolean, nullable=False, default=True, index=True)

    created_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    events = relationship("TrainingEvent", back_populates="course", lazy="selectin")
    records = relationship("TrainingRecord", back_populates="course", lazy="selectin")
    deferral_requests = relationship(
        "TrainingDeferralRequest", back_populates="course", lazy="selectin"
    )

    # New (scalable compliance + evidence)
    requirements = relationship("TrainingRequirement", back_populates="course", lazy="selectin")
    files = relationship("TrainingFile", back_populates="course", lazy="selectin")

    def __repr__(self) -> str:
        return f"<TrainingCourse {self.course_id} ({self.amo_id})>"


# ---------------------------------------------------------------------------
# TRAINING REQUIREMENTS (WHO MUST HAVE WHAT)
# ---------------------------------------------------------------------------


class TrainingRequirement(Base):
    """
    IOSA-style requirements matrix to define who must complete which courses.
    This supports global scaling + dashboards.

    scope rules:
    - ALL: required for everyone in the AMO
    - DEPARTMENT: required for a department_code
    - JOB_ROLE: required for a job_role
    - USER: required for a specific user_id
    """

    __tablename__ = "training_requirements"
    __table_args__ = (
        Index("idx_training_requirements_amo_active", "amo_id", "is_active"),
        Index("idx_training_requirements_amo_scope", "amo_id", "scope"),
        Index("idx_training_requirements_user", "amo_id", "user_id"),
        Index("idx_training_requirements_dept", "amo_id", "department_code"),
        Index("idx_training_requirements_role", "amo_id", "job_role"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)

    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    course_id = Column(
        String(36),
        ForeignKey("training_courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    scope = Column(
        Enum(TrainingRequirementScope, name="training_requirement_scope_enum"),
        nullable=False,
        default=TrainingRequirementScope.ALL,
        index=True,
    )

    department_code = Column(String(64), nullable=True, index=True)
    job_role = Column(String(128), nullable=True, index=True)

    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        doc="Only required when scope=USER",
    )

    is_mandatory = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)

    created_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    course = relationship("TrainingCourse", back_populates="requirements", lazy="joined")

    def __repr__(self) -> str:
        return f"<TrainingRequirement {self.id} course={self.course_id} scope={self.scope}>"


# ---------------------------------------------------------------------------
# TRAINING EVENTS (CLASSES / SESSIONS)
# ---------------------------------------------------------------------------


class TrainingEvent(Base):
    __tablename__ = "training_events"
    __table_args__ = (
        Index("idx_training_events_amo_course_date", "amo_id", "course_id", "starts_on"),
        Index("idx_training_events_amo_status", "amo_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)

    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    course_id = Column(
        String(36),
        ForeignKey("training_courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title = Column(
        String(255),
        nullable=False,
        doc="Optional title override; you can default this from course_name.",
    )

    location = Column(String(255), nullable=True)
    provider = Column(String(255), nullable=True)

    starts_on = Column(Date, nullable=False)
    ends_on = Column(Date, nullable=True)

    status = Column(
        Enum(TrainingEventStatus, name="training_event_status_enum"),
        nullable=False,
        default=TrainingEventStatus.PLANNED,
        index=True,
    )

    notes = Column(Text, nullable=True)

    created_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    course = relationship("TrainingCourse", back_populates="events", lazy="joined")
    participants = relationship(
        "TrainingEventParticipant",
        back_populates="event",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    records = relationship("TrainingRecord", back_populates="event", lazy="selectin")

    # New (evidence tied to a session)
    files = relationship("TrainingFile", back_populates="event", lazy="selectin")

    def __repr__(self) -> str:
        return f"<TrainingEvent {self.id} course={self.course_id} status={self.status}>"


class TrainingEventParticipant(Base):
    __tablename__ = "training_event_participants"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "user_id",
            name="uq_training_event_participants_event_user",
        ),
        Index("idx_training_participants_user", "user_id"),
        Index("idx_training_participants_event", "event_id"),
        Index("idx_training_participants_amo_user", "amo_id", "user_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)

    # Multi-tenant guard (helps filtering and avoids expensive joins in some queries)
    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    event_id = Column(
        String(36),
        ForeignKey("training_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status = Column(
        Enum(TrainingParticipantStatus, name="training_participant_status_enum"),
        nullable=False,
        default=TrainingParticipantStatus.INVITED,
        index=True,
    )

    attendance_note = Column(Text, nullable=True)

    # Governance for attendance marking (who marked + when)
    attendance_marked_at = Column(DateTime(timezone=True), nullable=True)
    attendance_marked_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    attended_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    deferral_request_id = Column(
        String(36),
        ForeignKey("training_deferral_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    event = relationship("TrainingEvent", back_populates="participants", lazy="joined")
    deferral_request = relationship("TrainingDeferralRequest", lazy="joined")

    def __repr__(self) -> str:
        return f"<TrainingEventParticipant event={self.event_id} user={self.user_id} status={self.status}>"


# ---------------------------------------------------------------------------
# TRAINING RECORDS (COMPLETED TRAINING)
# ---------------------------------------------------------------------------


class TrainingRecord(Base):
    __tablename__ = "training_records"
    __table_args__ = (
        Index("idx_training_records_user_course", "user_id", "course_id"),
        Index("idx_training_records_validity", "valid_until"),
        Index("idx_training_records_amo_user", "amo_id", "user_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)

    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    course_id = Column(
        String(36),
        ForeignKey("training_courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    event_id = Column(
        String(36),
        ForeignKey("training_events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    completion_date = Column(Date, nullable=False)
    valid_until = Column(
        Date,
        nullable=True,
        doc="Normally completion_date + frequency_months; stored explicitly for audit.",
    )

    hours_completed = Column(Integer, nullable=True)
    exam_score = Column(Integer, nullable=True)

    certificate_reference = Column(String(255), nullable=True)
    remarks = Column(Text, nullable=True)

    # Verification governance (recommended)
    verification_status = Column(
        Enum(
            TrainingRecordVerificationStatus,
            name="training_record_verification_status_enum",
        ),
        nullable=False,
        default=TrainingRecordVerificationStatus.PENDING,
        index=True,
    )
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    verification_comment = Column(Text, nullable=True)

    is_manual_entry = Column(
        Boolean,
        nullable=False,
        default=False,
        doc="True if created from legacy Excel/import instead of via event.",
    )

    created_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    course = relationship("TrainingCourse", back_populates="records", lazy="joined")
    event = relationship("TrainingEvent", back_populates="records", lazy="joined")

    # New (evidence tied to the record)
    files = relationship("TrainingFile", back_populates="record", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<TrainingRecord user={self.user_id} course={self.course_id} "
            f"completion={self.completion_date}>"
        )


# ---------------------------------------------------------------------------
# TRAINING DEFERRALS (QWI-026)
# ---------------------------------------------------------------------------


class TrainingDeferralRequest(Base):
    __tablename__ = "training_deferral_requests"
    __table_args__ = (
        Index(
            "idx_training_deferrals_user_course_status",
            "user_id",
            "course_id",
            "status",
        ),
        Index("idx_training_deferrals_amo_status", "amo_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)

    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # NEW: who raised the deferral (user, manager, Quality, etc.)
    requested_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    course_id = Column(
        String(36),
        ForeignKey("training_courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    original_due_date = Column(
        Date,
        nullable=False,
        doc="Due date at time of request.",
    )
    requested_new_due_date = Column(
        Date,
        nullable=False,
        doc="Requested new date within allowed validity window.",
    )

    reason_category = Column(
        Enum(DeferralReasonCategory, name="training_deferral_reason_enum"),
        nullable=False,
        default=DeferralReasonCategory.OTHER,
    )

    reason_text = Column(Text, nullable=True)

    status = Column(
        Enum(DeferralStatus, name="training_deferral_status_enum"),
        nullable=False,
        default=DeferralStatus.PENDING,
        index=True,
    )

    decided_at = Column(DateTime(timezone=True), nullable=True)

    decided_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Quality / AMO Admin who approved or rejected the deferral.",
    )

    decision_comment = Column(Text, nullable=True)

    requested_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    course = relationship("TrainingCourse", back_populates="deferral_requests", lazy="joined")

    # New (deferral evidence like letters, medical notes, etc.)
    files = relationship("TrainingFile", back_populates="deferral_request", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<TrainingDeferralRequest user={self.user_id} "
            f"course={self.course_id} status={self.status}>"
        )


# ---------------------------------------------------------------------------
# TRAINING FILES (CERTIFICATES / AMEL / EVIDENCE UPLOADS)
# ---------------------------------------------------------------------------


class TrainingFile(Base):
    """
    Stores uploaded training evidence, certificates, licenses (e.g. AMEL) and supporting documents.

    Design notes:
    - storage_path is a server-side relative path (never the raw client path)
    - sha256 supports integrity checks and de-dup
    - review fields support Quality governance
    """

    __tablename__ = "training_files"
    __table_args__ = (
        Index("idx_training_files_amo_owner", "amo_id", "owner_user_id"),
        Index("idx_training_files_course", "amo_id", "course_id"),
        Index("idx_training_files_event", "amo_id", "event_id"),
        Index("idx_training_files_record", "amo_id", "record_id"),
        Index("idx_training_files_deferral", "amo_id", "deferral_request_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)

    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    owner_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="The user this file belongs to (usually the trainee).",
    )

    kind = Column(
        Enum(TrainingFileKind, name="training_file_kind_enum"),
        nullable=False,
        default=TrainingFileKind.OTHER,
        index=True,
    )

    course_id = Column(
        String(36),
        ForeignKey("training_courses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_id = Column(
        String(36),
        ForeignKey("training_events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    record_id = Column(
        String(36),
        ForeignKey("training_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    deferral_request_id = Column(
        String(36),
        ForeignKey("training_deferral_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    original_filename = Column(String(255), nullable=False)
    storage_path = Column(String(512), nullable=False)
    content_type = Column(String(128), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    sha256 = Column(String(64), nullable=True, index=True)

    review_status = Column(
        Enum(TrainingFileReviewStatus, name="training_file_review_status_enum"),
        nullable=False,
        default=TrainingFileReviewStatus.PENDING,
        index=True,
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    review_comment = Column(Text, nullable=True)

    uploaded_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    uploaded_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    course = relationship("TrainingCourse", back_populates="files", lazy="joined")
    event = relationship("TrainingEvent", back_populates="files", lazy="joined")
    record = relationship("TrainingRecord", back_populates="files", lazy="joined")
    deferral_request = relationship("TrainingDeferralRequest", back_populates="files", lazy="joined")

    def __repr__(self) -> str:
        return f"<TrainingFile {self.id} kind={self.kind} owner={self.owner_user_id}>"


# ---------------------------------------------------------------------------
# TRAINING NOTIFICATIONS (IN-APP POPUPS + TRACKING)
# ---------------------------------------------------------------------------


class TrainingNotification(Base):
    """
    In-app notifications for trainees and staff.
    Used for login popups, scheduled/rescheduled/cancelled training, deferral decisions, file reviews, etc.
    """

    __tablename__ = "training_notifications"
    __table_args__ = (
        Index("idx_training_notifications_amo_user_created", "amo_id", "user_id", "created_at"),
        Index("idx_training_notifications_amo_user_unread", "amo_id", "user_id", "read_at"),
        UniqueConstraint("amo_id", "user_id", "dedupe_key", name="uq_training_notifications_dedupe"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)

    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=True)

    severity = Column(
        Enum(TrainingNotificationSeverity, name="training_notification_severity_enum"),
        nullable=False,
        default=TrainingNotificationSeverity.INFO,
        index=True,
    )

    link_path = Column(String(255), nullable=True, doc="Frontend route for deep-linking (optional).")

    # Optional dedupe key to avoid spamming (e.g., event:123:scheduled)
    dedupe_key = Column(String(255), nullable=True)

    created_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    read_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<TrainingNotification {self.id} user={self.user_id} severity={self.severity}>"


# ---------------------------------------------------------------------------
# TRAINING AUDIT LOG (TRACEABILITY)
# ---------------------------------------------------------------------------


class TrainingAuditLog(Base):
    """
    Audit trail for training actions. Keeps the who-did-what trail.
    Store details as JSON (Postgres will map to JSONB where supported).
    """

    __tablename__ = "training_audit_logs"
    __table_args__ = (
        Index("idx_training_audit_amo_created", "amo_id", "created_at"),
        Index("idx_training_audit_entity", "amo_id", "entity_type", "entity_id"),
        Index("idx_training_audit_actor", "amo_id", "actor_user_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)

    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    actor_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="User who performed the action (if known).",
    )

    action = Column(String(64), nullable=False, index=True)

    entity_type = Column(String(64), nullable=False, index=True)
    entity_id = Column(String(36), nullable=True, index=True)

    details = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<TrainingAuditLog {self.id} action={self.action} entity={self.entity_type}:{self.entity_id}>"
