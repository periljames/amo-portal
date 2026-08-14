from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)

from ...database import Base
from ...user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TrainingWorkbookImportJob(Base):
    """Durable, tenant-scoped state for a multi-sheet training migration."""

    __tablename__ = "training_workbook_import_jobs"
    __table_args__ = (
        Index("ix_training_wb_jobs_amo_created", "amo_id", "created_at"),
        Index("ix_training_wb_jobs_amo_status", "amo_id", "status"),
        Index("ix_training_wb_jobs_hash", "amo_id", "file_sha256"),
        UniqueConstraint("amo_id", "idempotency_key", name="uq_training_wb_jobs_amo_idempotency"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    committed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    filename = Column(String(255), nullable=False)
    content_type = Column(String(128), nullable=True)
    size_bytes = Column(Integer, nullable=False, default=0)
    file_sha256 = Column(String(64), nullable=False)
    storage_path = Column(Text, nullable=False)
    idempotency_key = Column(String(160), nullable=False)
    duplicate_of_job_id = Column(String(36), ForeignKey("training_workbook_import_jobs.id", ondelete="SET NULL"), nullable=True)

    status = Column(String(32), nullable=False, default="QUEUED", index=True)
    stage = Column(String(32), nullable=False, default="UPLOAD")
    current_sheet = Column(String(128), nullable=True)
    current_record_label = Column(String(255), nullable=True)
    processed_rows = Column(Integer, nullable=False, default=0)
    total_rows = Column(Integer, nullable=False, default=0)

    created_count = Column(Integer, nullable=False, default=0)
    updated_count = Column(Integer, nullable=False, default=0)
    unchanged_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    review_count = Column(Integer, nullable=False, default=0)

    summary_json = Column(JSON, nullable=False, default=dict)
    error_message = Column(Text, nullable=True)
    cancel_requested = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    started_at = Column(DateTime(timezone=True), nullable=True)
    preview_completed_at = Column(DateTime(timezone=True), nullable=True)
    committed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingWorkbookImportSheet(Base):
    __tablename__ = "training_workbook_import_sheets"
    __table_args__ = (
        UniqueConstraint("job_id", "sheet_name", name="uq_training_wb_sheets_job_name"),
        Index("ix_training_wb_sheets_job_order", "job_id", "display_order"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    job_id = Column(String(36), ForeignKey("training_workbook_import_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    sheet_name = Column(String(128), nullable=False)
    visibility = Column(String(16), nullable=False, default="VISIBLE")
    classification = Column(String(32), nullable=False)
    portal_destination = Column(String(255), nullable=False)
    is_operational = Column(Boolean, nullable=False, default=False)
    display_order = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="PENDING")
    total_rows = Column(Integer, nullable=False, default=0)
    processed_rows = Column(Integer, nullable=False, default=0)
    created_count = Column(Integer, nullable=False, default=0)
    updated_count = Column(Integer, nullable=False, default=0)
    unchanged_count = Column(Integer, nullable=False, default=0)
    skipped_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    review_count = Column(Integer, nullable=False, default=0)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingWorkbookImportRow(Base):
    __tablename__ = "training_workbook_import_rows"
    __table_args__ = (
        UniqueConstraint("job_id", "sheet_name", "source_row", "entity_type", name="uq_training_wb_rows_identity"),
        Index("ix_training_wb_rows_job_status", "job_id", "status"),
        Index("ix_training_wb_rows_job_review", "job_id", "decision_required"),
        Index("ix_training_wb_rows_job_sheet", "job_id", "sheet_name", "source_row"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    job_id = Column(String(36), ForeignKey("training_workbook_import_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    sheet_name = Column(String(128), nullable=False)
    source_row = Column(Integer, nullable=False)
    entity_type = Column(String(48), nullable=False)
    source_key = Column(String(255), nullable=True)
    display_label = Column(String(255), nullable=True)
    proposed_action = Column(String(32), nullable=False, default="UNCHANGED")
    status = Column(String(32), nullable=False, default="READY")
    decision_required = Column(Boolean, nullable=False, default=False)
    decision = Column(String(48), nullable=True)
    decision_options = Column(JSON, nullable=False, default=list)
    payload_json = Column(JSON, nullable=False, default=dict)
    changes_json = Column(JSON, nullable=False, default=list)
    issue_code = Column(String(64), nullable=True)
    issue_message = Column(Text, nullable=True)
    committed_entity_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class PersonnelLicence(Base):
    """Multiple regulatory licences/authorisations sourced from the People register."""

    __tablename__ = "personnel_licences"
    __table_args__ = (
        UniqueConstraint(
            "amo_id",
            "personnel_profile_id",
            "authority",
            "licence_number",
            name="uq_personnel_licences_identity",
        ),
        Index("ix_personnel_licences_amo_profile", "amo_id", "personnel_profile_id"),
        Index("ix_personnel_licences_amo_user", "amo_id", "user_id"),
        Index("ix_personnel_licences_expiry", "amo_id", "expires_on"),
        Index("ix_personnel_licences_expiry_source", "amo_id", "expiry_source_record_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    personnel_profile_id = Column(String(36), ForeignKey("personnel_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    authority = Column(String(64), nullable=False)
    country = Column(String(64), nullable=True)
    licence_number = Column(String(128), nullable=False)
    # A licence can carry a governed list of aircraft/engine category scopes.
    # These are regulatory evidence, not a single short lookup code, so retain
    # the complete source wording instead of truncating it to 255 characters.
    category_code = Column(Text, nullable=True)
    category_source = Column(String(64), nullable=True)
    issued_on = Column(Date, nullable=True)
    expires_on = Column(Date, nullable=True)
    expiry_source_record_id = Column(String(36), ForeignKey("training_records.id", ondelete="SET NULL"), nullable=True)
    expiry_source_course_id = Column(String(36), ForeignKey("training_courses.id", ondelete="SET NULL"), nullable=True)
    expiry_synced_at = Column(DateTime(timezone=True), nullable=True)
    internal_stamp_no = Column(String(255), nullable=True)
    initial_authorization_date = Column(Date, nullable=True)
    status = Column(String(32), nullable=False, default="ACTIVE", index=True)
    is_primary = Column(Boolean, nullable=False, default=False)
    source_job_id = Column(String(36), ForeignKey("training_workbook_import_jobs.id", ondelete="SET NULL"), nullable=True)
    source_row = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingRoleGroup(Base):
    __tablename__ = "training_role_groups"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_training_role_groups_amo_code"),
        Index("ix_training_role_groups_amo_active", "amo_id", "is_active"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    source_job_id = Column(String(36), ForeignKey("training_workbook_import_jobs.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingPersonRole(Base):
    __tablename__ = "training_person_roles"
    __table_args__ = (
        UniqueConstraint("amo_id", "person_id", "role_group_id", name="uq_training_person_roles_identity"),
        Index("ix_training_person_roles_person", "amo_id", "person_id", "is_active"),
        Index("ix_training_person_roles_user", "amo_id", "user_id", "is_active"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    person_id = Column(String(64), nullable=False)
    personnel_profile_id = Column(String(36), ForeignKey("personnel_profiles.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    role_group_id = Column(String(36), ForeignKey("training_role_groups.id", ondelete="CASCADE"), nullable=False)
    department = Column(String(255), nullable=True)
    position = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    source_job_id = Column(String(36), ForeignKey("training_workbook_import_jobs.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingCourseRoleRule(Base):
    __tablename__ = "training_course_role_rules"
    __table_args__ = (
        UniqueConstraint("amo_id", "course_id", "role_group_id", "requirement_type", name="uq_training_course_role_rules_identity"),
        Index("ix_training_course_role_rules_course", "amo_id", "course_id", "is_active"),
        Index("ix_training_course_role_rules_group", "amo_id", "role_group_id", "is_active"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(String(36), ForeignKey("training_courses.id", ondelete="CASCADE"), nullable=False)
    role_group_id = Column(String(36), ForeignKey("training_role_groups.id", ondelete="CASCADE"), nullable=False)
    is_required = Column(Boolean, nullable=False, default=True)
    requirement_type = Column(String(64), nullable=False, default="GENERAL")
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    source_job_id = Column(String(36), ForeignKey("training_workbook_import_jobs.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
