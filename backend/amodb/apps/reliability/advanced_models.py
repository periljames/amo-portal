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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.utils.identifiers import generate_uuid7


JSON_VALUE = JSON().with_variant(JSONB, "postgresql")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReliabilitySource(Base):
    __tablename__ = "reliability_sources"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_reliability_sources_amo_code"),
        Index("ix_reliability_sources_amo_type", "amo_id", "source_type"),
        Index("ix_reliability_sources_due", "amo_id", "status", "next_poll_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(80), nullable=False)
    name = Column(String(255), nullable=False)
    source_type = Column(String(40), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="ACTIVE", index=True)
    transport = Column(String(24), nullable=False, default="PUSH")
    mapping_version = Column(String(40), nullable=False, default="1")
    configuration_json = Column(JSON_VALUE, nullable=False, default=dict)
    poll_interval_minutes = Column(Integer, nullable=True)
    next_poll_at = Column(DateTime(timezone=True), nullable=True)
    last_received_at = Column(DateTime(timezone=True), nullable=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    last_failure_at = Column(DateTime(timezone=True), nullable=True)
    last_cursor = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class ReliabilityIngestionBatch(Base):
    __tablename__ = "reliability_ingestion_batches"
    __table_args__ = (
        Index("ix_reliability_batches_amo_received", "amo_id", "received_at"),
        Index("ix_reliability_batches_source_status", "source_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id = Column(String(36), ForeignKey("reliability_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="RECEIVED", index=True)
    content_hash = Column(String(64), nullable=False, index=True)
    record_count = Column(Integer, nullable=False, default=0)
    valid_count = Column(Integer, nullable=False, default=0)
    duplicate_count = Column(Integer, nullable=False, default=0)
    invalid_count = Column(Integer, nullable=False, default=0)
    metadata_json = Column(JSON_VALUE, nullable=False, default=dict)
    error_summary = Column(Text, nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    received_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    source = relationship("ReliabilitySource", lazy="joined")
    records = relationship(
        "ReliabilityIngestionRecord",
        back_populates="batch",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class ReliabilityIngestionRecord(Base):
    __tablename__ = "reliability_ingestion_records"
    __table_args__ = (
        UniqueConstraint("amo_id", "source_id", "external_id", name="uq_reliability_ingestion_external"),
        UniqueConstraint("amo_id", "source_id", "payload_hash", name="uq_reliability_ingestion_payload"),
        Index("ix_reliability_ingestion_batch_status", "batch_id", "validation_status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id = Column(String(36), ForeignKey("reliability_sources.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id = Column(String(36), ForeignKey("reliability_ingestion_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    external_id = Column(String(255), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    payload_json = Column(JSON_VALUE, nullable=False)
    validation_status = Column(String(24), nullable=False, default="PENDING", index=True)
    validation_errors = Column(JSON_VALUE, nullable=False, default=list)
    normalized_event_id = Column(Integer, ForeignKey("reliability_events.id", ondelete="SET NULL"), nullable=True, index=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    batch = relationship("ReliabilityIngestionBatch", back_populates="records", lazy="joined")


class ReliabilityDataQualityIssue(Base):
    __tablename__ = "reliability_data_quality_issues"
    __table_args__ = (
        Index("ix_reliability_dq_amo_status", "amo_id", "status"),
        Index("ix_reliability_dq_source", "source_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id = Column(String(36), ForeignKey("reliability_sources.id", ondelete="SET NULL"), nullable=True, index=True)
    batch_id = Column(String(36), ForeignKey("reliability_ingestion_batches.id", ondelete="SET NULL"), nullable=True, index=True)
    record_id = Column(String(36), ForeignKey("reliability_ingestion_records.id", ondelete="SET NULL"), nullable=True, index=True)
    issue_code = Column(String(80), nullable=False, index=True)
    severity = Column(String(16), nullable=False, default="MEDIUM", index=True)
    status = Column(String(24), nullable=False, default="OPEN", index=True)
    message = Column(Text, nullable=False)
    details_json = Column(JSON_VALUE, nullable=False, default=dict)
    resolution = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ReliabilityOperationalInterruption(Base):
    __tablename__ = "reliability_operational_interruptions"
    __table_args__ = (
        UniqueConstraint("amo_id", "reliability_event_id", name="uq_reliability_interruption_event"),
        Index("ix_reliability_interruptions_amo_type", "amo_id", "interruption_type"),
        Index("ix_reliability_interruptions_flight", "amo_id", "flight_number", "scheduled_departure_at"),
        CheckConstraint("delay_minutes IS NULL OR delay_minutes >= 0", name="ck_reliability_delay_nonnegative"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    reliability_event_id = Column(Integer, ForeignKey("reliability_events.id", ondelete="CASCADE"), nullable=False, index=True)
    interruption_type = Column(String(40), nullable=False, index=True)
    flight_number = Column(String(24), nullable=True, index=True)
    origin = Column(String(8), nullable=True)
    destination = Column(String(8), nullable=True)
    scheduled_departure_at = Column(DateTime(timezone=True), nullable=True)
    actual_departure_at = Column(DateTime(timezone=True), nullable=True)
    delay_minutes = Column(Integer, nullable=True)
    cancelled = Column(Boolean, nullable=False, default=False)
    return_to_gate = Column(Boolean, nullable=False, default=False)
    air_turnback = Column(Boolean, nullable=False, default=False)
    diversion = Column(Boolean, nullable=False, default=False)
    engine_shutdown = Column(Boolean, nullable=False, default=False)
    dispatch_impact = Column(String(40), nullable=True)
    mel_reference = Column(String(80), nullable=True, index=True)
    cdl_reference = Column(String(80), nullable=True, index=True)
    deferral_category = Column(String(16), nullable=True)
    deferred_until = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ReliabilityFracasLifecycle(Base):
    __tablename__ = "reliability_fracas_lifecycles"
    __table_args__ = (
        UniqueConstraint("amo_id", "fracas_case_id", name="uq_reliability_fracas_lifecycle_case"),
        Index("ix_reliability_fracas_stage", "amo_id", "stage"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    fracas_case_id = Column(Integer, ForeignKey("fracas_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(String(40), nullable=False, default="DETECTED", index=True)
    triage_disposition = Column(String(40), nullable=True)
    containment_required = Column(Boolean, nullable=False, default=True)
    containment_complete = Column(Boolean, nullable=False, default=False)
    problem_statement = Column(Text, nullable=True)
    root_cause_method = Column(String(80), nullable=True)
    root_cause_json = Column(JSON_VALUE, nullable=False, default=dict)
    risk_assessment_json = Column(JSON_VALUE, nullable=False, default=dict)
    effectiveness_due_date = Column(Date, nullable=True)
    reopened_count = Column(Integer, nullable=False, default=0)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    stage_entered_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    case = relationship("FRACASCase", lazy="joined")
    evidence = relationship("ReliabilityFracasEvidence", back_populates="lifecycle", lazy="selectin")
    stage_events = relationship("ReliabilityFracasStageEvent", back_populates="lifecycle", lazy="selectin")
    effectiveness_reviews = relationship("ReliabilityEffectivenessReview", back_populates="lifecycle", lazy="selectin")


class ReliabilityFracasEvidence(Base):
    __tablename__ = "reliability_fracas_evidence"
    __table_args__ = (Index("ix_reliability_fracas_evidence_lifecycle", "lifecycle_id", "captured_at"),)

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    lifecycle_id = Column(String(36), ForeignKey("reliability_fracas_lifecycles.id", ondelete="CASCADE"), nullable=False, index=True)
    evidence_type = Column(String(40), nullable=False, index=True)
    reference_type = Column(String(60), nullable=True)
    reference_id = Column(String(128), nullable=True)
    reference_url = Column(Text, nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    source_hash = Column(String(64), nullable=False)
    metadata_json = Column(JSON_VALUE, nullable=False, default=dict)
    captured_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    captured_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    lifecycle = relationship("ReliabilityFracasLifecycle", back_populates="evidence", lazy="joined")


class ReliabilityFracasStageEvent(Base):
    __tablename__ = "reliability_fracas_stage_events"
    __table_args__ = (Index("ix_reliability_fracas_stage_event_chain", "lifecycle_id", "created_at"),)

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    lifecycle_id = Column(String(36), ForeignKey("reliability_fracas_lifecycles.id", ondelete="CASCADE"), nullable=False, index=True)
    from_stage = Column(String(40), nullable=True)
    to_stage = Column(String(40), nullable=False)
    decision = Column(String(40), nullable=False)
    rationale = Column(Text, nullable=False)
    payload_json = Column(JSON_VALUE, nullable=False, default=dict)
    previous_hash = Column(String(64), nullable=True)
    event_hash = Column(String(64), nullable=False, unique=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    lifecycle = relationship("ReliabilityFracasLifecycle", back_populates="stage_events", lazy="joined")


class ReliabilityEffectivenessReview(Base):
    __tablename__ = "reliability_effectiveness_reviews"
    __table_args__ = (Index("ix_reliability_effectiveness_lifecycle_date", "lifecycle_id", "review_date"),)

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    lifecycle_id = Column(String(36), ForeignKey("reliability_fracas_lifecycles.id", ondelete="CASCADE"), nullable=False, index=True)
    review_date = Column(Date, nullable=False)
    metric_code = Column(String(80), nullable=True)
    baseline_value = Column(Numeric(20, 8), nullable=True)
    current_value = Column(Numeric(20, 8), nullable=True)
    acceptance_criteria = Column(Text, nullable=False)
    outcome = Column(String(32), nullable=False, index=True)
    evidence_json = Column(JSON_VALUE, nullable=False, default=list)
    notes = Column(Text, nullable=True)
    reviewer_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    lifecycle = relationship("ReliabilityFracasLifecycle", back_populates="effectiveness_reviews", lazy="joined")


class ReliabilityProgramme(Base):
    __tablename__ = "reliability_programmes"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_reliability_programme_amo_code"),
        Index("ix_reliability_programme_status", "amo_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(80), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(24), nullable=False, default="ACTIVE", index=True)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    versions = relationship("ReliabilityProgrammeVersion", back_populates="programme", lazy="selectin")


class ReliabilityProgrammeVersion(Base):
    __tablename__ = "reliability_programme_versions"
    __table_args__ = (
        UniqueConstraint("programme_id", "revision", name="uq_reliability_programme_revision"),
        Index("ix_reliability_programme_version_status", "amo_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    programme_id = Column(String(36), ForeignKey("reliability_programmes.id", ondelete="CASCADE"), nullable=False, index=True)
    revision = Column(String(40), nullable=False)
    status = Column(String(24), nullable=False, default="DRAFT", index=True)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    change_summary = Column(Text, nullable=False)
    regulatory_profiles = Column(JSON_VALUE, nullable=False, default=list)
    scope_json = Column(JSON_VALUE, nullable=False, default=dict)
    data_sources_json = Column(JSON_VALUE, nullable=False, default=list)
    reporting_json = Column(JSON_VALUE, nullable=False, default=dict)
    responsibility_matrix_json = Column(JSON_VALUE, nullable=False, default=dict)
    approval_json = Column(JSON_VALUE, nullable=False, default=dict)
    authority_required = Column(Boolean, nullable=False, default=False)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    programme = relationship("ReliabilityProgramme", back_populates="versions", lazy="joined")
    metrics = relationship("ReliabilityMetricDefinition", back_populates="programme_version", lazy="selectin")


class ReliabilityMetricDefinition(Base):
    __tablename__ = "reliability_metric_definitions"
    __table_args__ = (
        UniqueConstraint("programme_version_id", "code", name="uq_reliability_metric_version_code"),
        Index("ix_reliability_metric_due", "amo_id", "active", "next_run_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    programme_version_id = Column(String(36), ForeignKey("reliability_programme_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(80), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    scope_type = Column(String(24), nullable=False, default="FLEET")
    method = Column(String(32), nullable=False, default="RATE")
    numerator_event_types = Column(JSON_VALUE, nullable=False, default=list)
    denominator_type = Column(String(24), nullable=False, default="FH")
    multiplier = Column(Numeric(20, 8), nullable=False, default=100)
    window_days = Column(Integer, nullable=False, default=30)
    schedule_interval_minutes = Column(Integer, nullable=False, default=1440)
    minimum_exposure = Column(Numeric(20, 8), nullable=False, default=1)
    direction = Column(String(24), nullable=False, default="ABOVE")
    formula_version = Column(String(40), nullable=False, default="1")
    active = Column(Boolean, nullable=False, default=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    programme_version = relationship("ReliabilityProgrammeVersion", back_populates="metrics", lazy="joined")
    thresholds = relationship("ReliabilityThresholdVersion", back_populates="metric", lazy="selectin")


class ReliabilityThresholdVersion(Base):
    __tablename__ = "reliability_threshold_versions"
    __table_args__ = (
        UniqueConstraint("metric_definition_id", "version", name="uq_reliability_threshold_metric_version"),
        Index("ix_reliability_threshold_status", "amo_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    metric_definition_id = Column(String(36), ForeignKey("reliability_metric_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(String(40), nullable=False)
    status = Column(String(24), nullable=False, default="DRAFT", index=True)
    caution_value = Column(Numeric(20, 8), nullable=True)
    alert_value = Column(Numeric(20, 8), nullable=True)
    lower_caution_value = Column(Numeric(20, 8), nullable=True)
    lower_alert_value = Column(Numeric(20, 8), nullable=True)
    minimum_exposure = Column(Numeric(20, 8), nullable=True)
    rationale = Column(Text, nullable=False)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    metric = relationship("ReliabilityMetricDefinition", back_populates="thresholds", lazy="joined")


class ReliabilityCalculationRun(Base):
    __tablename__ = "reliability_calculation_runs"
    __table_args__ = (
        UniqueConstraint(
            "amo_id",
            "metric_definition_id",
            "scope_type",
            "scope_id",
            "period_start",
            "period_end",
            "formula_version",
            name="uq_reliability_calculation_identity",
        ),
        Index("ix_reliability_calculation_metric_period", "metric_definition_id", "period_end"),
        Index("ix_reliability_calculation_scope", "amo_id", "scope_type", "scope_id"),
        CheckConstraint("denominator IS NULL OR denominator >= 0", name="ck_reliability_calculation_denominator_nonnegative"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    metric_definition_id = Column(String(36), ForeignKey("reliability_metric_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    scope_type = Column(String(24), nullable=False)
    scope_id = Column(String(128), nullable=False, default="FLEET")
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    numerator = Column(Numeric(20, 8), nullable=True)
    denominator = Column(Numeric(20, 8), nullable=True)
    value = Column(Numeric(20, 8), nullable=True)
    confidence_lower = Column(Numeric(20, 8), nullable=True)
    confidence_upper = Column(Numeric(20, 8), nullable=True)
    sample_size = Column(Integer, nullable=False, default=0)
    small_fleet = Column(Boolean, nullable=False, default=False)
    status = Column(String(32), nullable=False, default="VALID", index=True)
    formula_version = Column(String(40), nullable=False)
    source_cutoff_at = Column(DateTime(timezone=True), nullable=False)
    source_lineage_json = Column(JSON_VALUE, nullable=False, default=dict)
    result_hash = Column(String(64), nullable=False, unique=True)
    scheduled = Column(Boolean, nullable=False, default=False)
    run_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ReliabilityReviewMeeting(Base):
    __tablename__ = "reliability_review_meetings"
    __table_args__ = (
        Index("ix_reliability_meeting_schedule", "amo_id", "scheduled_at"),
        Index("ix_reliability_meeting_status", "amo_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    programme_version_id = Column(String(36), ForeignKey("reliability_programme_versions.id", ondelete="SET NULL"), nullable=True)
    meeting_type = Column(String(40), nullable=False, default="MONTHLY_RELIABILITY")
    title = Column(String(255), nullable=False)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(24), nullable=False, default="DRAFT", index=True)
    data_cutoff_at = Column(DateTime(timezone=True), nullable=True)
    agenda_json = Column(JSON_VALUE, nullable=False, default=list)
    attendees_json = Column(JSON_VALUE, nullable=False, default=list)
    quorum_json = Column(JSON_VALUE, nullable=False, default=dict)
    minutes = Column(Text, nullable=True)
    chaired_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    decisions = relationship("ReliabilityMeetingDecision", back_populates="meeting", lazy="selectin")


class ReliabilityMeetingDecision(Base):
    __tablename__ = "reliability_meeting_decisions"
    __table_args__ = (Index("ix_reliability_decision_meeting_status", "meeting_id", "status"),)

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    meeting_id = Column(String(36), ForeignKey("reliability_review_meetings.id", ondelete="CASCADE"), nullable=False, index=True)
    decision_type = Column(String(40), nullable=False)
    title = Column(String(255), nullable=False)
    decision = Column(Text, nullable=False)
    rationale = Column(Text, nullable=False)
    dissent = Column(Text, nullable=True)
    linked_entity_type = Column(String(60), nullable=True)
    linked_entity_id = Column(String(128), nullable=True)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_date = Column(Date, nullable=True)
    status = Column(String(24), nullable=False, default="OPEN", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    meeting = relationship("ReliabilityReviewMeeting", back_populates="decisions", lazy="joined")


class ReliabilityChangeProposal(Base):
    __tablename__ = "reliability_change_proposals"
    __table_args__ = (
        Index("ix_reliability_change_status", "amo_id", "status"),
        Index("ix_reliability_change_source", "source_type", "source_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    programme_version_id = Column(String(36), ForeignKey("reliability_programme_versions.id", ondelete="SET NULL"), nullable=True)
    source_type = Column(String(60), nullable=False)
    source_id = Column(String(128), nullable=False)
    proposal_type = Column(String(40), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    problem_statement = Column(Text, nullable=False)
    proposed_change_json = Column(JSON_VALUE, nullable=False)
    impact_assessment_json = Column(JSON_VALUE, nullable=False, default=dict)
    simulation_json = Column(JSON_VALUE, nullable=False, default=dict)
    status = Column(String(32), nullable=False, default="DRAFT", index=True)
    approval_json = Column(JSON_VALUE, nullable=False, default=dict)
    effective_from = Column(Date, nullable=True)
    effectiveness_due_date = Column(Date, nullable=True)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class ReliabilityHandoff(Base):
    __tablename__ = "reliability_handoffs"
    __table_args__ = (
        Index("ix_reliability_handoff_target_status", "amo_id", "target_module", "status"),
        Index("ix_reliability_handoff_source", "amo_id", "source_type", "source_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(String(60), nullable=False)
    source_id = Column(String(128), nullable=False)
    target_module = Column(String(40), nullable=False, index=True)
    target_route = Column(String(255), nullable=True)
    target_record_type = Column(String(80), nullable=True)
    target_record_id = Column(String(128), nullable=True)
    task_id = Column(String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    payload_json = Column(JSON_VALUE, nullable=False)
    status = Column(String(24), nullable=False, default="DRAFT", index=True)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class ReliabilityAuthoritySubmission(Base):
    __tablename__ = "reliability_authority_submissions"
    __table_args__ = (
        Index("ix_reliability_authority_status", "amo_id", "status"),
        UniqueConstraint("amo_id", "authority_profile", "external_reference", name="uq_reliability_authority_reference"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    programme_version_id = Column(String(36), ForeignKey("reliability_programme_versions.id", ondelete="SET NULL"), nullable=True)
    change_proposal_id = Column(String(36), ForeignKey("reliability_change_proposals.id", ondelete="SET NULL"), nullable=True)
    meeting_id = Column(String(36), ForeignKey("reliability_review_meetings.id", ondelete="SET NULL"), nullable=True)
    authority_profile = Column(String(40), nullable=False, index=True)
    submission_type = Column(String(60), nullable=False)
    status = Column(String(24), nullable=False, default="DRAFT", index=True)
    external_reference = Column(String(128), nullable=True)
    package_manifest_json = Column(JSON_VALUE, nullable=False, default=dict)
    response_json = Column(JSON_VALUE, nullable=False, default=dict)
    submitted_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    decision_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class ReliabilityAuditEvent(Base):
    __tablename__ = "reliability_audit_events"
    __table_args__ = (
        Index("ix_reliability_audit_entity", "amo_id", "entity_type", "entity_id", "created_at"),
        UniqueConstraint("amo_id", "event_hash", name="uq_reliability_audit_hash"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type = Column(String(60), nullable=False)
    entity_id = Column(String(128), nullable=False)
    action = Column(String(80), nullable=False)
    payload_json = Column(JSON_VALUE, nullable=False, default=dict)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    previous_hash = Column(String(64), nullable=True)
    event_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ReliabilityAiReview(Base):
    __tablename__ = "reliability_ai_reviews"
    __table_args__ = (
        Index("ix_reliability_ai_entity", "amo_id", "entity_type", "entity_id"),
        Index("ix_reliability_ai_status", "amo_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    review_type = Column(String(60), nullable=False)
    entity_type = Column(String(60), nullable=False)
    entity_id = Column(String(128), nullable=False)
    model_id = Column(String(80), nullable=False)
    model_version = Column(String(80), nullable=False)
    prompt_hash = Column(String(64), nullable=False)
    input_snapshot_json = Column(JSON_VALUE, nullable=False)
    citations_json = Column(JSON_VALUE, nullable=False, default=list)
    output_json = Column(JSON_VALUE, nullable=False)
    confidence = Column(Numeric(7, 6), nullable=True)
    advisory_only = Column(Boolean, nullable=False, default=True)
    status = Column(String(24), nullable=False, default="DRAFT", index=True)
    review_notes = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
