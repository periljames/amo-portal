from __future__ import annotations

from datetime import datetime
from sqlalchemy import Boolean, Column, Date, DateTime, Integer, JSON, String, Text, UniqueConstraint

from amodb.database import Base
from amodb.user_id import generate_user_id


class TrainingCourse(Base):
    __tablename__ = "quality_training_courses"
    __table_args__ = (UniqueConstraint("tenant_id", "course_id", name="uq_quality_training_course_tenant_course_id"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), nullable=False, index=True)
    course_id = Column(String(64), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(128), nullable=True)
    owner_department = Column(String(128), nullable=True)
    delivery_mode = Column(String(32), nullable=False, default="Class")
    is_recurrent = Column(Boolean, nullable=False, default=False)
    recurrence_interval_months = Column(Integer, nullable=True)
    grace_window_days = Column(Integer, nullable=True)
    prerequisites_text = Column(Text, nullable=True)
    minimum_outcome_type = Column(String(32), nullable=False, default="PassFail")
    minimum_score_optional = Column(Integer, nullable=True)
    active_flag = Column(Boolean, nullable=False, default=True)
    current_syllabus_asset_id = Column(String(128), nullable=True)
    certificate_template_asset_id = Column(String(128), nullable=True)
    evidence_requirements_json = Column(JSON, nullable=False, default=lambda: {"certificate_required": False, "attendance_required": True, "other_required_text": ""})
    purpose = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class TrainingSession(Base):
    __tablename__ = "quality_training_sessions"

    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), nullable=False, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    course_id = Column(String(64), nullable=False, index=True)
    start_datetime = Column(DateTime(timezone=True), nullable=False)
    end_datetime = Column(DateTime(timezone=True), nullable=False)
    location_text = Column(String(255), nullable=True)
    instructor_user_id = Column(String(36), nullable=True)
    status = Column(String(32), nullable=False, default="Planned")
    capacity_optional = Column(Integer, nullable=True)
    notes_text = Column(Text, nullable=True)


class SessionAttendee(Base):
    __tablename__ = "quality_training_session_attendees"

    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), nullable=False, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    staff_id = Column(String(36), nullable=False, index=True)
    attendance_status = Column(String(32), nullable=False, default="Unknown")
    attendance_marked_at = Column(DateTime(timezone=True), nullable=True)
    result_outcome = Column(String(32), nullable=True)
    score_optional = Column(Integer, nullable=True)
    remarks_text = Column(Text, nullable=True)
    evidence_asset_ids = Column(JSON, nullable=True)


class CompletionRecord(Base):
    __tablename__ = "quality_training_completion_records"

    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), nullable=False, index=True)
    completion_id = Column(String(64), nullable=False, index=True)
    staff_id = Column(String(36), nullable=False, index=True)
    course_id = Column(String(64), nullable=False, index=True)
    completion_date = Column(Date, nullable=False)
    outcome = Column(String(32), nullable=False)
    score_optional = Column(Integer, nullable=True)
    source_session_id = Column(String(64), nullable=True)
    next_due_date = Column(Date, nullable=True)
    evidence_asset_ids = Column(JSON, nullable=True)


class RoleTrainingRequirement(Base):
    __tablename__ = "quality_training_role_requirements"

    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), nullable=False, index=True)
    role_id = Column(String(64), nullable=False, index=True)
    course_id = Column(String(64), nullable=False, index=True)
    required_flag = Column(Boolean, nullable=False, default=True)
    interval_override_months = Column(Integer, nullable=True)
    initial_only_flag = Column(Boolean, nullable=False, default=False)
    notes_text = Column(Text, nullable=True)


class StaffTrainingOverride(Base):
    __tablename__ = "quality_training_staff_overrides"

    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), nullable=False, index=True)
    staff_id = Column(String(36), nullable=False, index=True)
    course_id = Column(String(64), nullable=False, index=True)
    override_type = Column(String(32), nullable=False)
    interval_override_months = Column(Integer, nullable=True)
    reason_text = Column(Text, nullable=False)
    approved_by_user_id = Column(String(36), nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=False)


class TrainingAuthorisation(Base):
    __tablename__ = "quality_training_authorisations"

    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), nullable=False, index=True)
    auth_id = Column(String(64), nullable=False, index=True)
    staff_id = Column(String(36), nullable=False, index=True)
    auth_type = Column(String(128), nullable=False)
    granted_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    granted_by_user_id = Column(String(36), nullable=True)
    evidence_asset_id = Column(String(128), nullable=True)
    status = Column(String(32), nullable=False, default="Current")


class TrainingAuditEvent(Base):
    __tablename__ = "quality_training_audit_events"

    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), nullable=False, index=True)
    object_type = Column(String(64), nullable=False)
    object_id = Column(String(64), nullable=False)
    action = Column(String(32), nullable=False)
    actor_user_id = Column(String(36), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    diff_json = Column(JSON, nullable=False, default=dict)


class TrainingTenantSettings(Base):
    __tablename__ = "quality_training_settings"

    id = Column(String(36), primary_key=True, default=generate_user_id)
    tenant_id = Column(String(36), nullable=False, unique=True, index=True)
    default_recurrence_interval_months = Column(Integer, nullable=False, default=12)
    default_grace_window_days = Column(Integer, nullable=False, default=30)
    certificate_mandatory_default = Column(Boolean, nullable=False, default=False)
    attendance_sheet_mandatory_default = Column(Boolean, nullable=False, default=True)
