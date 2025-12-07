# backend/amodb/apps/training/models.py

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
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
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TrainingParticipantStatus(str, enum.Enum):
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


# ---------------------------------------------------------------------------
# TRAINING COURSE MASTER
# ---------------------------------------------------------------------------


class TrainingCourse(Base):
    """
    Master list of training courses for an AMO.

    - `course_id`  = your legacy CourseID (e.g. SMS-REF, HF-INIT, DGR-REF)
    - `course_name` = your CourseName string
    - `frequency_months` = FrequencyMonths from your sheet
    """

    __tablename__ = "training_courses"
    __table_args__ = (
        UniqueConstraint("amo_id", "course_id", name="uq_training_courses_amo_courseid"),
        Index("idx_training_courses_amo_active", "amo_id", "is_active"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)

    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # DIRECTLY mapped from your Excel list
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

    # FrequencyMonths from your sheet; used for due/overdue logic
    frequency_months = Column(
        Integer,
        nullable=True,
        doc="Recurrent interval in months; NULL for one-off or manually-controlled courses.",
    )

    # Extra classification to help grouping / dashboards
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

    # Mandatory flags
    is_mandatory = Column(Boolean, nullable=False, default=True)
    mandatory_for_all = Column(Boolean, nullable=False, default=False)

    # Simple prerequisite hook, e.g. "SMS-INIT" before "SMS-REF"
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

    # Relationships
    events = relationship("TrainingEvent", back_populates="course", lazy="selectin")
    records = relationship("TrainingRecord", back_populates="course", lazy="selectin")
    deferral_requests = relationship(
        "TrainingDeferralRequest", back_populates="course", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<TrainingCourse {self.course_id} ({self.amo_id})>"


# ---------------------------------------------------------------------------
# TRAINING EVENTS (CLASSES / SESSIONS)
# ---------------------------------------------------------------------------


class TrainingEvent(Base):
    __tablename__ = "training_events"
    __table_args__ = (
        Index("idx_training_events_amo_course_date", "amo_id", "course_id", "starts_on"),
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

    # Relationships
    course = relationship("TrainingCourse", back_populates="events", lazy="joined")
    participants = relationship(
        "TrainingEventParticipant",
        back_populates="event",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    records = relationship("TrainingRecord", back_populates="event", lazy="selectin")

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
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)

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
    attended_at = Column(DateTime(timezone=True), nullable=True)

    # Link to deferral request if this attendance was deferred
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

    # Optional link back to the training session
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

    course = relationship("TrainingCourse", back_populates="deferral_requests", lazy="joined")

    def __repr__(self) -> str:
        return (
            f"<TrainingDeferralRequest user={self.user_id} "
            f"course={self.course_id} status={self.status}>"
        )
