from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from ...database import Base
from ...user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TrainingOperatingSettings(Base):
    __tablename__ = "training_operating_settings"
    __table_args__ = (UniqueConstraint("amo_id", name="uq_training_operating_settings_amo"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    default_planning_lead_days = Column(Integer, nullable=False, default=45)
    default_recurrent_window_days = Column(Integer, nullable=False, default=45)
    attendance_window_minutes = Column(Integer, nullable=False, default=30)
    attendance_qr_lifetime_minutes = Column(Integer, nullable=False, default=10)
    competence_review_frequency_months = Column(Integer, nullable=False, default=24)
    experience_review_frequency_months = Column(Integer, nullable=False, default=3)
    auditor_observer_count = Column(Integer, nullable=False, default=3)
    reporting_currency = Column(String(3), nullable=False, default="USD")
    budget_rounding_places = Column(Integer, nullable=False, default=2)
    plan_form_reference = Column(String(64), nullable=True)
    budget_form_reference = Column(String(64), nullable=True)
    attendance_form_reference = Column(String(64), nullable=True)
    assessment_form_mappings = Column(JSON, nullable=False, default=dict)
    authorization_form_mappings = Column(JSON, nullable=False, default=dict)
    approval_roles = Column(JSON, nullable=False, default=dict)
    timezone = Column(String(64), nullable=False, default="UTC")
    plan_automation_enabled = Column(Boolean, nullable=False, default=True)
    plan_run_day = Column(Integer, nullable=False, default=1)
    plan_run_hour = Column(Integer, nullable=False, default=2)
    notification_policy = Column(JSON, nullable=False, default=dict)
    certificate_number_prefix = Column(String(32), nullable=False, default="TRN")
    certificate_template_reference = Column(String(128), nullable=True)
    certificate_signatories = Column(JSON, nullable=False, default=list)
    certificate_public_privacy_text = Column(Text, nullable=True)
    default_committee_positions = Column(
        JSON,
        nullable=False,
        default=lambda: ["QUALITY_MANAGER", "BASE_MAINTENANCE_MANAGER", "LINE_MAINTENANCE_MANAGER"],
    )
    setup_status = Column(String(24), nullable=False, default="DRAFT")
    configuration_revision_no = Column(Integer, nullable=False, default=0)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingConfigurationRevision(Base):
    __tablename__ = "training_configuration_revisions"
    __table_args__ = (
        UniqueConstraint("amo_id", "revision_no", name="uq_training_configuration_revision"),
        Index("ix_training_configuration_revision_amo_created", "amo_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    revision_no = Column(Integer, nullable=False)
    snapshot = Column(JSON, nullable=False, default=dict)
    change_summary = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingReferenceResource(Base):
    __tablename__ = "training_reference_resources"
    __table_args__ = (
        UniqueConstraint("amo_id", "resource_type", "code", name="uq_training_reference_resource_code"),
        Index("ix_training_reference_resource_active", "amo_id", "resource_type", "active"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_type = Column(String(24), nullable=False)
    code = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    contact_name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(64), nullable=True)
    address = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    active = Column(Boolean, nullable=False, default=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingControlledFormTemplate(Base):
    __tablename__ = "training_controlled_form_templates"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", "revision_no", name="uq_training_controlled_form_revision"),
        Index("ix_training_controlled_form_active", "amo_id", "workflow", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    workflow = Column(String(64), nullable=False)
    revision_no = Column(Integer, nullable=False, default=1)
    status = Column(String(24), nullable=False, default="DRAFT")
    dms_document_id = Column(String(36), nullable=True)
    dms_revision_id = Column(String(36), nullable=True)
    schema_json = Column(JSON, nullable=False, default=dict)
    retention_rule = Column(String(255), nullable=True)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingAutomationRun(Base):
    __tablename__ = "training_automation_runs"
    __table_args__ = (
        UniqueConstraint("amo_id", "idempotency_key", name="uq_training_automation_run_key"),
        Index("ix_training_automation_run_tenant_period", "amo_id", "period_year", "period_month"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    idempotency_key = Column(String(128), nullable=False)
    period_year = Column(Integer, nullable=False)
    period_month = Column(Integer, nullable=False)
    trigger = Column(String(24), nullable=False, default="SCHEDULED")
    status = Column(String(24), nullable=False, default="RUNNING")
    plan_id = Column(String(36), ForeignKey("training_plans.id", ondelete="SET NULL"), nullable=True)
    summary = Column(JSON, nullable=False, default=dict)
    error_text = Column(Text, nullable=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class TrainingPlan(Base):
    __tablename__ = "training_plans"
    __table_args__ = (
        UniqueConstraint("amo_id", "plan_year", "revision_no", name="uq_training_plan_year_revision"),
        Index("ix_training_plan_amo_status", "amo_id", "status"),
        CheckConstraint("plan_year BETWEEN 2000 AND 2200", name="ck_training_plan_year"),
        CheckConstraint("revision_no > 0", name="ck_training_plan_revision_positive"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_year = Column(Integer, nullable=False, index=True)
    revision_no = Column(Integer, nullable=False, default=1)
    title = Column(String(255), nullable=False, default="Annual Training Plan")
    status = Column(String(32), nullable=False, default="DRAFT", index=True)
    form_reference = Column(String(64), nullable=True)
    issue_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    supersedes_plan_id = Column(String(36), ForeignKey("training_plans.id", ondelete="SET NULL"), nullable=True)
    prepared_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    items = relationship(
        "TrainingPlanItem",
        back_populates="plan",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class TrainingPlanItem(Base):
    __tablename__ = "training_plan_items"
    __table_args__ = (
        Index("ix_training_plan_item_plan_month", "plan_id", "planned_month"),
        Index("ix_training_plan_item_amo_course", "amo_id", "course_id"),
        CheckConstraint("planned_month IS NULL OR planned_month BETWEEN 1 AND 12", name="ck_training_plan_month"),
        CheckConstraint("quarter IS NULL OR quarter BETWEEN 1 AND 4", name="ck_training_plan_quarter"),
        CheckConstraint("participant_count >= 0", name="ck_training_plan_participant_count"),
        CheckConstraint("estimated_unit_cost >= 0", name="ck_training_plan_unit_cost"),
        CheckConstraint("estimated_total_cost >= 0", name="ck_training_plan_total_cost"),
        CheckConstraint("planned_end IS NULL OR planned_start IS NULL OR planned_end >= planned_start", name="ck_training_plan_item_dates"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id = Column(String(36), ForeignKey("training_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(String(36), ForeignKey("training_courses.id", ondelete="SET NULL"), nullable=True, index=True)
    scheduled_event_id = Column(String(36), ForeignKey("training_events.id", ondelete="SET NULL"), nullable=True, index=True)
    course_code_snapshot = Column(String(64), nullable=True)
    course_name_snapshot = Column(String(255), nullable=False)
    training_kind = Column(String(32), nullable=False, default="OTHER")
    provider_mode = Column(String(32), nullable=False, default="INTERNAL")
    provider = Column(String(255), nullable=True)
    participant_count = Column(Integer, nullable=False, default=0)
    planned_month = Column(Integer, nullable=True)
    quarter = Column(Integer, nullable=True)
    planned_start = Column(Date, nullable=True)
    planned_end = Column(Date, nullable=True)
    location = Column(String(255), nullable=True)
    instructor_ids = Column(JSON, nullable=False, default=list)
    duration_days = Column(Integer, nullable=True)
    justification = Column(Text, nullable=True)
    source_type = Column(String(64), nullable=False, default="MANUAL")
    manual_reference = Column(String(255), nullable=True)
    authorization_impact = Column(Text, nullable=True)
    priority = Column(String(16), nullable=False, default="NORMAL")
    original_currency = Column(String(3), nullable=False, default="USD")
    estimated_unit_cost = Column(Numeric(18, 6), nullable=False, default=0)
    estimated_total_cost = Column(Numeric(18, 6), nullable=False, default=0)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    plan = relationship("TrainingPlan", back_populates="items", lazy="joined")
    participants = relationship(
        "TrainingPlanParticipant",
        back_populates="plan_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class TrainingPlanParticipant(Base):
    __tablename__ = "training_plan_participants"
    __table_args__ = (
        UniqueConstraint("plan_item_id", "user_id", name="uq_training_plan_participant_user"),
        Index("ix_training_plan_participant_amo_user", "amo_id", "user_id"),
        Index("ix_training_plan_participant_due", "amo_id", "planned_due_date"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_item_id = Column(String(36), ForeignKey("training_plan_items.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    person_name_snapshot = Column(String(255), nullable=False)
    staff_code_snapshot = Column(String(64), nullable=True)
    last_completion_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)
    planned_due_date = Column(Date, nullable=True)
    obligation_status = Column(String(32), nullable=False, default="PLANNED")
    source_type = Column(String(32), nullable=False, default="REQUIREMENT")
    source_record_id = Column(String(36), nullable=True)
    source_reference = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="PLANNED")
    exclusion_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    plan_item = relationship("TrainingPlanItem", back_populates="participants", lazy="joined")


class TrainingBudget(Base):
    __tablename__ = "training_budgets"
    __table_args__ = (
        UniqueConstraint("amo_id", "plan_id", "revision_no", name="uq_training_budget_plan_revision"),
        Index("ix_training_budget_amo_status", "amo_id", "status"),
        CheckConstraint("revision_no > 0", name="ck_training_budget_revision_positive"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id = Column(String(36), ForeignKey("training_plans.id", ondelete="RESTRICT"), nullable=False, index=True)
    revision_no = Column(Integer, nullable=False, default=1)
    status = Column(String(32), nullable=False, default="DRAFT", index=True)
    reporting_currency = Column(String(3), nullable=False, default="USD")
    form_reference = Column(String(64), nullable=True)
    notes = Column(Text, nullable=True)
    supersedes_budget_id = Column(String(36), ForeignKey("training_budgets.id", ondelete="SET NULL"), nullable=True)
    prepared_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    lines = relationship(
        "TrainingBudgetLine",
        back_populates="budget",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class TrainingBudgetLine(Base):
    __tablename__ = "training_budget_lines"
    __table_args__ = (
        Index("ix_training_budget_line_budget_quarter", "budget_id", "quarter"),
        CheckConstraint("quarter BETWEEN 1 AND 4", name="ck_training_budget_line_quarter"),
        CheckConstraint("trainee_count >= 0", name="ck_training_budget_line_trainees"),
        CheckConstraint("unit_cost >= 0 AND planned_amount >= 0", name="ck_training_budget_line_planned_nonnegative"),
        CheckConstraint("approved_amount >= 0 AND committed_amount >= 0 AND actual_amount >= 0", name="ck_training_budget_line_states_nonnegative"),
        CheckConstraint("exchange_rate > 0", name="ck_training_budget_line_exchange_rate"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    budget_id = Column(String(36), ForeignKey("training_budgets.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_item_id = Column(String(36), ForeignKey("training_plan_items.id", ondelete="SET NULL"), nullable=True, index=True)
    course_id = Column(String(36), ForeignKey("training_courses.id", ondelete="SET NULL"), nullable=True, index=True)
    course_code_snapshot = Column(String(64), nullable=True)
    course_name_snapshot = Column(String(255), nullable=False)
    training_kind = Column(String(32), nullable=False, default="OTHER")
    provider = Column(String(255), nullable=True)
    original_currency = Column(String(3), nullable=False)
    reporting_currency = Column(String(3), nullable=False)
    unit_cost = Column(Numeric(18, 6), nullable=False, default=0)
    trainee_count = Column(Integer, nullable=False, default=0)
    planned_amount = Column(Numeric(18, 6), nullable=False, default=0)
    approved_amount = Column(Numeric(18, 6), nullable=False, default=0)
    committed_amount = Column(Numeric(18, 6), nullable=False, default=0)
    actual_amount = Column(Numeric(18, 6), nullable=False, default=0)
    exchange_rate = Column(Numeric(24, 10), nullable=False, default=1)
    rate_date = Column(Date, nullable=False)
    rate_source = Column(String(255), nullable=False)
    converted_planned_amount = Column(Numeric(18, 6), nullable=False, default=0)
    converted_approved_amount = Column(Numeric(18, 6), nullable=False, default=0)
    converted_committed_amount = Column(Numeric(18, 6), nullable=False, default=0)
    converted_actual_amount = Column(Numeric(18, 6), nullable=False, default=0)
    quarter = Column(Integer, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    budget = relationship("TrainingBudget", back_populates="lines", lazy="joined")


class TrainingAttendanceWindow(Base):
    __tablename__ = "training_attendance_windows"
    __table_args__ = (
        Index("ix_training_attendance_window_event_status", "event_id", "status"),
        UniqueConstraint("token_hash", name="uq_training_attendance_window_token"),
        CheckConstraint("expires_at > opened_at", name="ck_training_attendance_window_expiry"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(String(36), ForeignKey("training_events.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="OPEN", index=True)
    token_hash = Column(String(64), nullable=False, index=True)
    opened_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    opened_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    closed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    certified_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    certified_at = Column(DateTime(timezone=True), nullable=True)
    register_revision = Column(Integer, nullable=False, default=1)
    certification_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingAttendanceEntry(Base):
    __tablename__ = "training_attendance_entries"
    __table_args__ = (
        UniqueConstraint("event_id", "user_id", name="uq_training_attendance_event_user"),
        UniqueConstraint("idempotency_key", name="uq_training_attendance_idempotency"),
        Index("ix_training_attendance_amo_event", "amo_id", "event_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    window_id = Column(String(36), ForeignKey("training_attendance_windows.id", ondelete="SET NULL"), nullable=True, index=True)
    event_id = Column(String(36), ForeignKey("training_events.id", ondelete="CASCADE"), nullable=False, index=True)
    participant_id = Column(String(36), ForeignKey("training_event_participants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="PRESENT")
    method = Column(String(24), nullable=False)
    signed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    signed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    attestation = Column(Text, nullable=True)
    idempotency_key = Column(String(128), nullable=False)
    source_metadata = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingAttendanceCorrection(Base):
    __tablename__ = "training_attendance_corrections"
    __table_args__ = (Index("ix_training_attendance_correction_entry", "attendance_entry_id", "created_at"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    attendance_entry_id = Column(String(36), ForeignKey("training_attendance_entries.id", ondelete="CASCADE"), nullable=False, index=True)
    old_status = Column(String(24), nullable=False)
    new_status = Column(String(24), nullable=False)
    reason = Column(Text, nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingAssessmentTemplate(Base):
    __tablename__ = "training_assessment_templates"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", "revision_no", name="uq_training_assessment_template_revision"),
        Index("ix_training_assessment_template_amo_active", "amo_id", "active"),
        CheckConstraint("revision_no > 0", name="ck_training_assessment_template_revision"),
        CheckConstraint("pass_threshold IS NULL OR pass_threshold BETWEEN 0 AND 100", name="ck_training_assessment_pass_threshold"),
        CheckConstraint("effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from", name="ck_training_assessment_template_dates"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    purpose = Column(Text, nullable=True)
    assessment_type = Column(String(32), nullable=False, index=True)
    outcome_scheme = Column(String(32), nullable=False, default="PASS_FAIL")
    revision_no = Column(Integer, nullable=False, default=1)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    pass_threshold = Column(Numeric(7, 4), nullable=True)
    mandatory_criteria = Column(JSON, nullable=False, default=list)
    evidence_requirements = Column(JSON, nullable=False, default=list)
    assessor_capability = Column(String(120), nullable=False, default="training.assessment.perform")
    approval_required = Column(Boolean, nullable=False, default=True)
    manual_reference = Column(String(255), nullable=True)
    active = Column(Boolean, nullable=False, default=True, index=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    questions = relationship(
        "TrainingAssessmentQuestion",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
        order_by="TrainingAssessmentQuestion.sequence_no",
    )


class TrainingAssessmentQuestion(Base):
    __tablename__ = "training_assessment_questions"
    __table_args__ = (
        UniqueConstraint("template_id", "sequence_no", name="uq_training_assessment_question_sequence"),
        CheckConstraint("marks >= 0", name="ck_training_assessment_question_marks"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id = Column(String(36), ForeignKey("training_assessment_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence_no = Column(Integer, nullable=False)
    question_text = Column(Text, nullable=False)
    response_type = Column(String(32), nullable=False, default="TEXT")
    answer_options = Column(JSON, nullable=False, default=list)
    evaluation_rule = Column(JSON, nullable=False, default=dict)
    answer_key = Column(JSON, nullable=True)
    marks = Column(Numeric(9, 4), nullable=False, default=0)
    mandatory = Column(Boolean, nullable=False, default=False)
    manual_reference = Column(String(255), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingAuthorizationCase(Base):
    __tablename__ = "training_authorization_cases"
    __table_args__ = (
        Index("ix_training_authorization_case_amo_status", "amo_id", "status"),
        Index("ix_training_authorization_case_candidate", "amo_id", "candidate_user_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    authorisation_type_id = Column(String(36), ForeignKey("authorisation_types.id", ondelete="RESTRICT"), nullable=False, index=True)
    requested_scope = Column(Text, nullable=True)
    requested_privileges = Column(JSON, nullable=False, default=list)
    requested_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    application_date = Column(Date, nullable=False)
    status = Column(String(40), nullable=False, default="NOT_READY", index=True)
    required_assessment_types = Column(JSON, nullable=False, default=lambda: ["WRITTEN", "PRACTICAL", "ORAL"])
    manual_references = Column(JSON, nullable=False, default=list)
    required_committee_positions = Column(JSON, nullable=False, default=list)
    readiness_snapshot = Column(JSON, nullable=False, default=dict)
    readiness_computed_at = Column(DateTime(timezone=True), nullable=True)
    recommendation = Column(Text, nullable=True)
    decision = Column(String(32), nullable=True)
    restrictions = Column(Text, nullable=True)
    decision_at = Column(DateTime(timezone=True), nullable=True)
    issued_user_authorisation_id = Column(String(36), ForeignKey("user_authorisations.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingAssessmentInstance(Base):
    __tablename__ = "training_assessment_instances"
    __table_args__ = (
        Index("ix_training_assessment_instance_candidate", "amo_id", "candidate_user_id", "status"),
        CheckConstraint("score IS NULL OR score BETWEEN 0 AND 100", name="ck_training_assessment_instance_score"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id = Column(String(36), ForeignKey("training_assessment_templates.id", ondelete="RESTRICT"), nullable=False, index=True)
    candidate_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(String(36), ForeignKey("training_courses.id", ondelete="SET NULL"), nullable=True, index=True)
    event_id = Column(String(36), ForeignKey("training_events.id", ondelete="SET NULL"), nullable=True, index=True)
    authorization_case_id = Column(String(36), ForeignKey("training_authorization_cases.id", ondelete="SET NULL"), nullable=True, index=True)
    assessor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewer_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    planned_at = Column(DateTime(timezone=True), nullable=True)
    performed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(32), nullable=False, default="DRAFT", index=True)
    results = Column(JSON, nullable=False, default=dict)
    score = Column(Numeric(7, 4), nullable=True)
    outcome = Column(String(32), nullable=True)
    comments = Column(Text, nullable=True)
    review_decision = Column(String(32), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    supersedes_assessment_id = Column(String(36), ForeignKey("training_assessment_instances.id", ondelete="SET NULL"), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingExperienceLog(Base):
    __tablename__ = "training_experience_logs"
    __table_args__ = (
        Index("ix_training_experience_candidate_date", "amo_id", "candidate_user_id", "activity_date"),
        CheckConstraint("duration_hours IS NULL OR duration_hours >= 0", name="ck_training_experience_duration"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    log_type = Column(String(32), nullable=False, default="EXPERIENCE")
    aircraft_component_task = Column(String(255), nullable=True)
    activity = Column(Text, nullable=False)
    supervisor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    activity_date = Column(Date, nullable=False)
    duration_hours = Column(Numeric(10, 2), nullable=True)
    reference = Column(String(255), nullable=True)
    training_file_id = Column(String(36), ForeignKey("training_files.id", ondelete="SET NULL"), nullable=True)
    verification_status = Column(String(24), nullable=False, default="PENDING")
    verified_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingExperienceReview(Base):
    __tablename__ = "training_experience_reviews"
    __table_args__ = (
        Index("ix_training_experience_review_candidate", "amo_id", "candidate_user_id", "reviewed_on"),
        CheckConstraint("next_review_due >= reviewed_on", name="ck_training_experience_review_due"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    authorization_case_id = Column(String(36), ForeignKey("training_authorization_cases.id", ondelete="SET NULL"), nullable=True, index=True)
    required_period_months = Column(Integer, nullable=False, default=3)
    review_status = Column(String(24), nullable=False)
    reviewed_on = Column(Date, nullable=False)
    next_review_due = Column(Date, nullable=False, index=True)
    reviewer_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    evidence_summary = Column(Text, nullable=True)
    training_file_id = Column(String(36), ForeignKey("training_files.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingCommitteeDecision(Base):
    __tablename__ = "training_committee_decisions"
    __table_args__ = (
        UniqueConstraint("authorization_case_id", "position_code", name="uq_training_committee_case_position"),
        Index("ix_training_committee_case", "authorization_case_id", "decided_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    authorization_case_id = Column(String(36), ForeignKey("training_authorization_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    member_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    position_code = Column(String(80), nullable=False)
    position_label_snapshot = Column(String(255), nullable=False)
    decision = Column(String(24), nullable=False)
    comments = Column(Text, nullable=True)
    evidence_snapshot = Column(JSON, nullable=False, default=dict)
    decided_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingEffectivenessEvaluation(Base):
    __tablename__ = "training_effectiveness_evaluations"
    __table_args__ = (
        Index("ix_training_effectiveness_course_level", "amo_id", "course_id", "level"),
        CheckConstraint("level BETWEEN 1 AND 4", name="ck_training_effectiveness_level"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(String(36), ForeignKey("training_courses.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(String(36), ForeignKey("training_events.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    level = Column(Integer, nullable=False)
    evaluation_period_start = Column(Date, nullable=True)
    evaluation_period_end = Column(Date, nullable=True)
    evidence = Column(JSON, nullable=False, default=dict)
    rating = Column(Numeric(7, 4), nullable=True)
    conclusion = Column(Text, nullable=True)
    causation_claimed = Column(Boolean, nullable=False, default=False)
    reviewer_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(24), nullable=False, default="DRAFT")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingCompetenceReview(Base):
    __tablename__ = "training_competence_reviews"
    __table_args__ = (Index("ix_training_competence_review_candidate", "amo_id", "candidate_user_id", "period_end"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    review_type = Column(String(40), nullable=False, default="CONTINUED_COMPETENCE")
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    reviewer_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    authorization_case_id = Column(String(36), ForeignKey("training_authorization_cases.id", ondelete="SET NULL"), nullable=True)
    course_id = Column(String(36), ForeignKey("training_courses.id", ondelete="SET NULL"), nullable=True)
    criteria = Column(JSON, nullable=False, default=list)
    evidence = Column(JSON, nullable=False, default=dict)
    outcome = Column(String(32), nullable=False)
    strengths = Column(Text, nullable=True)
    gaps = Column(Text, nullable=True)
    actions = Column(Text, nullable=True)
    reassessment_due = Column(Date, nullable=True)
    status = Column(String(24), nullable=False, default="DRAFT")
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingRemedialAction(Base):
    __tablename__ = "training_remedial_actions"
    __table_args__ = (Index("ix_training_remedial_candidate_status", "amo_id", "candidate_user_id", "status"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_assessment_id = Column(String(36), ForeignKey("training_assessment_instances.id", ondelete="SET NULL"), nullable=True)
    source_competence_review_id = Column(String(36), ForeignKey("training_competence_reviews.id", ondelete="SET NULL"), nullable=True)
    course_id = Column(String(36), ForeignKey("training_courses.id", ondelete="SET NULL"), nullable=True)
    gap = Column(Text, nullable=False)
    required_activity = Column(Text, nullable=False)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_date = Column(Date, nullable=False, index=True)
    supervised_experience_required = Column(Boolean, nullable=False, default=False)
    reassessment_required = Column(Boolean, nullable=False, default=True)
    status = Column(String(24), nullable=False, default="OPEN")
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingEvidenceLink(Base):
    __tablename__ = "training_evidence_links"
    __table_args__ = (
        UniqueConstraint("amo_id", "entity_type", "entity_id", "training_file_id", name="uq_training_evidence_link"),
        Index("ix_training_evidence_entity", "amo_id", "entity_type", "entity_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(String(36), nullable=False)
    training_file_id = Column(String(36), ForeignKey("training_files.id", ondelete="CASCADE"), nullable=False)
    linked_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    linked_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingSetupVersion(Base):
    """Effective-dated tenant configuration bundle promoted through review."""

    __tablename__ = "training_setup_versions"
    __table_args__ = (
        UniqueConstraint("amo_id", "version_no", name="uq_training_setup_version"),
        Index("ix_training_setup_version_status", "amo_id", "status", "effective_from"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    version_no = Column(Integer, nullable=False)
    source_mode = Column(String(24), nullable=False, default="BLANK")
    status = Column(String(24), nullable=False, default="DRAFT")
    title = Column(String(255), nullable=False)
    change_summary = Column(Text, nullable=True)
    snapshot = Column(JSON, nullable=False, default=dict)
    validation_result = Column(JSON, nullable=False, default=dict)
    effective_from = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    activated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    supersedes_version_id = Column(String(36), ForeignKey("training_setup_versions.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingChangeRequest(Base):
    """Preview/diff envelope for material bulk and lifecycle mutations."""

    __tablename__ = "training_change_requests"
    __table_args__ = (Index("ix_training_change_request_queue", "amo_id", "object_type", "status", "created_at"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    object_type = Column(String(48), nullable=False)
    object_id = Column(String(36), nullable=True)
    operation = Column(String(48), nullable=False)
    status = Column(String(24), nullable=False, default="PREVIEW")
    requested_payload = Column(JSON, nullable=False, default=dict)
    impact_summary = Column(JSON, nullable=False, default=dict)
    validation_result = Column(JSON, nullable=False, default=dict)
    source_cutoff_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    requested_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decision_reason = Column(Text, nullable=True)
    applied_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingWorkflowInstance(Base):
    """Generic, versioned runtime for QMS/36, QAM/51, QAM/52, QAM/58 and tenant forms."""

    __tablename__ = "training_workflow_instances"
    __table_args__ = (
        UniqueConstraint("amo_id", "workflow_type", "idempotency_key", name="uq_training_workflow_idempotency"),
        Index("ix_training_workflow_task_queue", "amo_id", "status", "owner_user_id", "due_at"),
        Index("ix_training_workflow_subject", "amo_id", "subject_user_id", "workflow_type"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_type = Column(String(48), nullable=False)
    form_template_id = Column(String(36), ForeignKey("training_controlled_form_templates.id", ondelete="SET NULL"), nullable=True)
    form_revision_no = Column(Integer, nullable=True)
    subject_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reviewer_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_id = Column(String(36), ForeignKey("training_events.id", ondelete="SET NULL"), nullable=True, index=True)
    course_id = Column(String(36), ForeignKey("training_courses.id", ondelete="SET NULL"), nullable=True, index=True)
    authorization_case_id = Column(String(36), ForeignKey("training_authorization_cases.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(24), nullable=False, default="DRAFT")
    title = Column(String(255), nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=True)
    data_json = Column(JSON, nullable=False, default=dict)
    validation_result = Column(JSON, nullable=False, default=dict)
    provenance = Column(JSON, nullable=False, default=dict)
    idempotency_key = Column(String(128), nullable=False)
    revision_no = Column(Integer, nullable=False, default=1)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingWorkflowStep(Base):
    __tablename__ = "training_workflow_steps"
    __table_args__ = (
        UniqueConstraint("workflow_instance_id", "step_key", name="uq_training_workflow_step"),
        Index("ix_training_workflow_step_status", "amo_id", "status", "assigned_user_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_instance_id = Column(String(36), ForeignKey("training_workflow_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    step_key = Column(String(64), nullable=False)
    label = Column(String(255), nullable=False)
    sequence_no = Column(Integer, nullable=False, default=1)
    status = Column(String(24), nullable=False, default="PENDING")
    assigned_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    response_json = Column(JSON, nullable=False, default=dict)
    signature_json = Column(JSON, nullable=False, default=dict)
    completed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingSessionInvitation(Base):
    __tablename__ = "training_session_invitations"
    __table_args__ = (
        UniqueConstraint("amo_id", "event_id", "user_id", "channel", name="uq_training_session_invitation"),
        Index("ix_training_invitation_delivery", "amo_id", "event_id", "delivery_status"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(String(36), ForeignKey("training_events.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    channel = Column(String(24), nullable=False, default="IN_APP")
    delivery_status = Column(String(24), nullable=False, default="QUEUED")
    email_log_id = Column(String(36), ForeignKey("email_logs.id", ondelete="SET NULL"), nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    rsvp_status = Column(String(24), nullable=False, default="PENDING")
    responded_at = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingReportDefinition(Base):
    __tablename__ = "training_report_definitions"
    __table_args__ = (UniqueConstraint("amo_id", "code", name="uq_training_report_definition_code"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    dataset = Column(String(64), nullable=False)
    allowed_formats = Column(JSON, nullable=False, default=lambda: ["PDF", "XLSX"])
    default_filters = Column(JSON, nullable=False, default=dict)
    schedule_json = Column(JSON, nullable=False, default=dict)
    retention_days = Column(Integer, nullable=False, default=365)
    active = Column(Boolean, nullable=False, default=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class TrainingReportJob(Base):
    __tablename__ = "training_report_jobs"
    __table_args__ = (Index("ix_training_report_job_queue", "amo_id", "status", "created_at"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    report_definition_id = Column(String(36), ForeignKey("training_report_definitions.id", ondelete="SET NULL"), nullable=True)
    report_code = Column(String(64), nullable=False)
    output_format = Column(String(12), nullable=False)
    status = Column(String(24), nullable=False, default="QUEUED")
    filters_json = Column(JSON, nullable=False, default=dict)
    scope_manifest = Column(JSON, nullable=False, default=dict)
    artifact_path = Column(Text, nullable=True)
    artifact_checksum = Column(String(64), nullable=True)
    error_text = Column(Text, nullable=True)
    requested_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TrainingSavedView(Base):
    __tablename__ = "training_saved_views"
    __table_args__ = (UniqueConstraint("amo_id", "user_id", "workspace", "name", name="uq_training_saved_view"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace = Column(String(48), nullable=False)
    name = Column(String(100), nullable=False)
    filter_json = Column(JSON, nullable=False, default=dict)
    column_json = Column(JSON, nullable=False, default=dict)
    density = Column(String(16), nullable=False, default="COMPACT")
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
