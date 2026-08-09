from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.utils.identifiers import generate_uuid7


JSON_VALUE = JSON().with_variant(JSONB, "postgresql")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RegulatoryProfileStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    WITHDRAWN = "WITHDRAWN"


class RegulatoryRequirementLifecycle(str, Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    WITHDRAWN = "WITHDRAWN"


class RegulatoryObligation(str, Enum):
    MANDATORY = "MANDATORY"
    ADVISORY = "ADVISORY"


class RequirementAssessmentStatus(str, Enum):
    SATISFIED = "SATISFIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    WITHHELD = "WITHHELD"
    GAP = "GAP"
    SUPERSEDED = "SUPERSEDED"


class FormalReportStatus(str, Enum):
    DRAFT = "DRAFT"
    DATA_REVIEW = "DATA_REVIEW"
    TECHNICAL_REVIEW = "TECHNICAL_REVIEW"
    QUALITY_REVIEW = "QUALITY_REVIEW"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    SUPERSEDED = "SUPERSEDED"
    WITHDRAWN = "WITHDRAWN"


class FormalPeriodType(str, Enum):
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    HALF_YEAR = "HALF_YEAR"
    ANNUAL = "ANNUAL"
    YEAR_TO_DATE = "YEAR_TO_DATE"
    ROLLING_3_MONTH = "ROLLING_3_MONTH"
    ROLLING_6_MONTH = "ROLLING_6_MONTH"
    ROLLING_12_MONTH = "ROLLING_12_MONTH"
    CUSTOM = "CUSTOM"


class FormalSectionStatus(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    WITHHELD = "WITHHELD"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FormalDecision(str, Enum):
    SUBMIT = "SUBMIT"
    APPROVE = "APPROVE"
    RETURN = "RETURN"
    REJECT = "REJECT"
    PUBLISH = "PUBLISH"
    SUPERSEDE = "SUPERSEDE"
    WITHDRAW = "WITHDRAW"


class AmpRecommendationStatus(str, Enum):
    IDENTIFIED = "IDENTIFIED"
    ANALYSIS = "ANALYSIS"
    RECOMMENDED = "RECOMMENDED"
    TECHNICAL_REVIEW = "TECHNICAL_REVIEW"
    QUALITY_REVIEW = "QUALITY_REVIEW"
    AUTHORITY_APPROVAL_REQUIRED = "AUTHORITY_APPROVAL_REQUIRED"
    APPROVED = "APPROVED"
    IMPLEMENTED = "IMPLEMENTED"
    EFFECTIVENESS_MONITORING = "EFFECTIVENESS_MONITORING"
    CLOSED = "CLOSED"


class ReportingScheduleStatus(str, Enum):
    PLANNED = "PLANNED"
    DUE = "DUE"
    IN_PREPARATION = "IN_PREPARATION"
    IN_REVIEW = "IN_REVIEW"
    COMPLETE = "COMPLETE"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"


class ReliabilityRegulatoryProfile(Base):
    __tablename__ = "reliability_regulatory_profiles"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", "version", name="uq_rel_reg_profile_version"),
        Index("ix_rel_reg_profile_active", "amo_id", "code", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(32), nullable=False, index=True)
    version = Column(String(40), nullable=False)
    name = Column(String(255), nullable=False)
    authority = Column(String(32), nullable=False, index=True)
    jurisdiction = Column(String(64), nullable=False)
    effective_date = Column(Date, nullable=True)
    revision = Column(String(80), nullable=True)
    status = Column(String(24), nullable=False, default=RegulatoryProfileStatus.DRAFT.value, index=True)
    derived_from_profiles = Column(JSON_VALUE, nullable=False, default=list)
    required_sections = Column(JSON_VALUE, nullable=False, default=list)
    mandatory_kpis = Column(JSON_VALUE, nullable=False, default=list)
    minimum_analysis_periods = Column(JSON_VALUE, nullable=False, default=dict)
    statistical_methods = Column(JSON_VALUE, nullable=False, default=list)
    historical_windows = Column(JSON_VALUE, nullable=False, default=list)
    commentary_rules = Column(JSON_VALUE, nullable=False, default=dict)
    evidence_rules = Column(JSON_VALUE, nullable=False, default=dict)
    approval_workflow = Column(JSON_VALUE, nullable=False, default=dict)
    publication_rules = Column(JSON_VALUE, nullable=False, default=dict)
    source_manifest = Column(JSON_VALUE, nullable=False, default=list)
    is_default = Column(Boolean, nullable=False, default=False)
    supersedes_profile_id = Column(String(36), ForeignKey("reliability_regulatory_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    requirements = relationship("ReliabilityRegulatoryRequirement", back_populates="profile", lazy="selectin")


class ReliabilityRegulatoryRequirement(Base):
    __tablename__ = "reliability_regulatory_requirements"
    __table_args__ = (
        UniqueConstraint("profile_id", "requirement_key", "revision", name="uq_rel_reg_requirement_revision"),
        Index("ix_rel_reg_requirement_profile_status", "profile_id", "lifecycle_status"),
        Index("ix_rel_reg_requirement_authority_ref", "amo_id", "authority", "source_reference"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_id = Column(String(36), ForeignKey("reliability_regulatory_profiles.id", ondelete="RESTRICT"), nullable=False, index=True)
    requirement_key = Column(String(120), nullable=False, index=True)
    authority = Column(String(32), nullable=False, index=True)
    jurisdiction = Column(String(64), nullable=False)
    source_kind = Column(String(32), nullable=False)
    source_reference = Column(String(255), nullable=False)
    paragraph_reference = Column(String(120), nullable=True)
    source_url = Column(Text, nullable=False)
    effective_date = Column(Date, nullable=True)
    revision = Column(String(80), nullable=False)
    controlled_summary = Column(Text, nullable=False)
    applicability_rule = Column(JSON_VALUE, nullable=False, default=dict)
    aircraft_applicability = Column(JSON_VALUE, nullable=False, default=dict)
    operator_applicability = Column(JSON_VALUE, nullable=False, default=dict)
    obligation_status = Column(String(20), nullable=False, default=RegulatoryObligation.ADVISORY.value, index=True)
    report_section_code = Column(String(80), nullable=False, index=True)
    data_source_codes = Column(JSON_VALUE, nullable=False, default=list)
    calculation_code = Column(String(120), nullable=True)
    minimum_analysis_months = Column(Integer, nullable=True)
    historical_comparison_months = Column(Integer, nullable=True)
    evidence_rule = Column(JSON_VALUE, nullable=False, default=dict)
    approval_role = Column(String(64), nullable=True)
    completeness_rule = Column(JSON_VALUE, nullable=False, default=dict)
    reviewer_notes = Column(Text, nullable=True)
    lifecycle_status = Column(String(24), nullable=False, default=RegulatoryRequirementLifecycle.ACTIVE.value, index=True)
    supersedes_requirement_id = Column(String(36), ForeignKey("reliability_regulatory_requirements.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    profile = relationship("ReliabilityRegulatoryProfile", back_populates="requirements", lazy="joined")


class ReliabilityFormalReport(Base):
    __tablename__ = "reliability_formal_reports"
    __table_args__ = (
        UniqueConstraint("amo_id", "report_number", "revision", name="uq_rel_formal_report_revision"),
        Index("ix_rel_formal_report_status_period", "amo_id", "status", "period_start", "period_end"),
        Index("ix_rel_formal_report_profile", "profile_id", "period_end"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    programme_id = Column(String(36), ForeignKey("reliability_programmes.id", ondelete="SET NULL"), nullable=True, index=True)
    profile_id = Column(String(36), ForeignKey("reliability_regulatory_profiles.id", ondelete="RESTRICT"), nullable=False, index=True)
    report_number = Column(String(100), nullable=False, index=True)
    revision = Column(Integer, nullable=False, default=0)
    title = Column(String(255), nullable=False)
    period_type = Column(String(32), nullable=False, index=True)
    period_start = Column(Date, nullable=False, index=True)
    period_end = Column(Date, nullable=False, index=True)
    status = Column(String(32), nullable=False, default=FormalReportStatus.DRAFT.value, index=True)
    profile_code_snapshot = Column(String(32), nullable=False)
    profile_version_snapshot = Column(String(40), nullable=False)
    regulatory_manifest = Column(JSON_VALUE, nullable=False, default=list)
    data_cutoff_at = Column(DateTime(timezone=True), nullable=True, index=True)
    effectivity_json = Column(JSON_VALUE, nullable=False, default=dict)
    effectivity_frozen_at = Column(DateTime(timezone=True), nullable=True)
    source_population_json = Column(JSON_VALUE, nullable=False, default=dict)
    formula_revisions_json = Column(JSON_VALUE, nullable=False, default=list)
    calculation_snapshots_json = Column(JSON_VALUE, nullable=False, default=dict)
    chart_data_json = Column(JSON_VALUE, nullable=False, default=dict)
    narrative_json = Column(JSON_VALUE, nullable=False, default=list)
    data_quality_json = Column(JSON_VALUE, nullable=False, default=dict)
    completeness_json = Column(JSON_VALUE, nullable=False, default=dict)
    rendered_html = Column(Text, nullable=True)
    html_sha256 = Column(String(64), nullable=True, index=True)
    pdf_storage_ref = Column(Text, nullable=True)
    pdf_sha256 = Column(String(64), nullable=True, index=True)
    pdf_size_bytes = Column(Integer, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True, index=True)
    published_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    supersedes_report_id = Column(String(36), ForeignKey("reliability_formal_reports.id", ondelete="SET NULL"), nullable=True, index=True)
    superseded_at = Column(DateTime(timezone=True), nullable=True)
    superseded_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    withdrawn_at = Column(DateTime(timezone=True), nullable=True)
    withdrawn_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    profile = relationship("ReliabilityRegulatoryProfile", lazy="joined")
    sections = relationship("ReliabilityFormalReportSection", back_populates="report", lazy="selectin", cascade="all, delete-orphan", order_by="ReliabilityFormalReportSection.sequence")
    requirement_assessments = relationship("ReliabilityFormalRequirementAssessment", back_populates="report", lazy="selectin", cascade="all, delete-orphan")


class ReliabilityFormalReportSection(Base):
    __tablename__ = "reliability_formal_report_sections"
    __table_args__ = (
        UniqueConstraint("report_id", "section_code", name="uq_rel_formal_report_section"),
        Index("ix_rel_formal_section_order", "report_id", "sequence"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    report_id = Column(String(36), ForeignKey("reliability_formal_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    section_code = Column(String(80), nullable=False)
    sequence = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    required = Column(Boolean, nullable=False, default=True)
    status = Column(String(24), nullable=False, default=FormalSectionStatus.DRAFT.value, index=True)
    computed_data = Column(JSON_VALUE, nullable=False, default=dict)
    commentary = Column(JSON_VALUE, nullable=False, default=list)
    evidence_refs = Column(JSON_VALUE, nullable=False, default=list)
    warnings = Column(JSON_VALUE, nullable=False, default=list)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    report = relationship("ReliabilityFormalReport", back_populates="sections", lazy="joined")


class ReliabilityFormalRequirementAssessment(Base):
    __tablename__ = "reliability_formal_requirement_assessments"
    __table_args__ = (
        UniqueConstraint("report_id", "requirement_id", name="uq_rel_formal_requirement_assessment"),
        Index("ix_rel_formal_requirement_status", "report_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    report_id = Column(String(36), ForeignKey("reliability_formal_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_id = Column(String(36), ForeignKey("reliability_regulatory_requirements.id", ondelete="RESTRICT"), nullable=False, index=True)
    section_code = Column(String(80), nullable=False, index=True)
    applicable = Column(Boolean, nullable=False, default=True)
    status = Column(String(24), nullable=False, default=RequirementAssessmentStatus.GAP.value, index=True)
    requirement_snapshot = Column(JSON_VALUE, nullable=False, default=dict)
    evidence_refs = Column(JSON_VALUE, nullable=False, default=list)
    calculation_refs = Column(JSON_VALUE, nullable=False, default=list)
    source_refs = Column(JSON_VALUE, nullable=False, default=list)
    reviewer_note = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    report = relationship("ReliabilityFormalReport", back_populates="requirement_assessments", lazy="joined")
    requirement = relationship("ReliabilityRegulatoryRequirement", lazy="joined")


class ReliabilityFormalReportSource(Base):
    __tablename__ = "reliability_formal_report_sources"
    __table_args__ = (
        UniqueConstraint("report_id", "source_kind", "source_id", name="uq_rel_formal_report_source"),
        Index("ix_rel_formal_report_source_kind", "report_id", "source_kind"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    report_id = Column(String(36), ForeignKey("reliability_formal_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    source_kind = Column(String(40), nullable=False)
    source_id = Column(String(128), nullable=False)
    source_hash = Column(String(64), nullable=True)
    source_date = Column(Date, nullable=True, index=True)
    dataset_code = Column(String(32), nullable=True, index=True)
    aircraft_serial_number = Column(String(50), nullable=True, index=True)
    reference_code = Column(String(128), nullable=True)
    captured_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ReliabilityFormalApproval(Base):
    __tablename__ = "reliability_formal_approvals"
    __table_args__ = (Index("ix_rel_formal_approval_chain", "report_id", "created_at"),)

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    report_id = Column(String(36), ForeignKey("reliability_formal_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(String(32), nullable=False)
    decision = Column(String(24), nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    role_snapshot = Column(String(64), nullable=False)
    comment = Column(Text, nullable=True)
    report_revision = Column(Integer, nullable=False)
    report_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ReliabilityFormalLifecycleEvent(Base):
    __tablename__ = "reliability_formal_lifecycle_events"
    __table_args__ = (
        Index("ix_rel_formal_lifecycle_chain", "report_id", "created_at"),
        UniqueConstraint("event_hash", name="uq_rel_formal_lifecycle_event_hash"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    report_id = Column(String(36), ForeignKey("reliability_formal_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status = Column(String(32), nullable=True)
    to_status = Column(String(32), nullable=False)
    action = Column(String(32), nullable=False)
    rationale = Column(Text, nullable=True)
    payload_json = Column(JSON_VALUE, nullable=False, default=dict)
    previous_hash = Column(String(64), nullable=True)
    event_hash = Column(String(64), nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    role_snapshot = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ReliabilityFormalCompletenessOverride(Base):
    __tablename__ = "reliability_formal_completeness_overrides"
    __table_args__ = (Index("ix_rel_formal_override_report", "report_id", "created_at"),)

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    report_id = Column(String(36), ForeignKey("reliability_formal_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    check_code = Column(String(120), nullable=False)
    requirement_id = Column(String(36), ForeignKey("reliability_regulatory_requirements.id", ondelete="SET NULL"), nullable=True, index=True)
    justification = Column(Text, nullable=False)
    authority_basis = Column(Text, nullable=False)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)
    approved_role = Column(String(64), nullable=False)
    report_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ReliabilityAmpRecommendation(Base):
    __tablename__ = "reliability_amp_recommendations"
    __table_args__ = (
        Index("ix_rel_amp_rec_status", "amo_id", "status"),
        Index("ix_rel_amp_rec_report", "report_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    report_id = Column(String(36), ForeignKey("reliability_formal_reports.id", ondelete="SET NULL"), nullable=True, index=True)
    programme_id = Column(String(36), ForeignKey("reliability_programmes.id", ondelete="SET NULL"), nullable=True, index=True)
    programme_item_id = Column(Integer, ForeignKey("amp_program_items.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=False)
    change_type = Column(String(48), nullable=False, index=True)
    status = Column(String(40), nullable=False, default=AmpRecommendationStatus.IDENTIFIED.value, index=True)
    source_evidence = Column(JSON_VALUE, nullable=False, default=list)
    current_requirement = Column(JSON_VALUE, nullable=False, default=dict)
    proposed_change = Column(JSON_VALUE, nullable=False, default=dict)
    technical_basis = Column(JSON_VALUE, nullable=False, default=dict)
    authority_approval_required = Column(Boolean, nullable=False, default=False)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    target_date = Column(Date, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    implemented_at = Column(DateTime(timezone=True), nullable=True)
    effectiveness_due_date = Column(Date, nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class ReliabilityReportingSchedule(Base):
    __tablename__ = "reliability_reporting_schedule"
    __table_args__ = (
        UniqueConstraint("amo_id", "obligation_code", "period_start", "period_end", name="uq_rel_reporting_schedule_period"),
        Index("ix_rel_reporting_schedule_due", "amo_id", "status", "due_date"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_id = Column(String(36), ForeignKey("reliability_regulatory_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    programme_id = Column(String(36), ForeignKey("reliability_programmes.id", ondelete="SET NULL"), nullable=True, index=True)
    report_id = Column(String(36), ForeignKey("reliability_formal_reports.id", ondelete="SET NULL"), nullable=True, index=True)
    obligation_code = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    period_type = Column(String(32), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False, index=True)
    cycle_config = Column(JSON_VALUE, nullable=False, default=dict)
    status = Column(String(32), nullable=False, default=ReportingScheduleStatus.PLANNED.value, index=True)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completeness_json = Column(JSON_VALUE, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class ReliabilityFormalDistribution(Base):
    __tablename__ = "reliability_formal_distributions"
    __table_args__ = (Index("ix_rel_formal_distribution_report", "report_id", "distributed_at"),)

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    report_id = Column(String(36), ForeignKey("reliability_formal_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    recipient_role = Column(String(64), nullable=True)
    external_recipient_ref = Column(String(255), nullable=True)
    channel = Column(String(32), nullable=False, default="PORTAL")
    revision_snapshot = Column(Integer, nullable=False)
    report_hash = Column(String(64), nullable=False)
    distributed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    distributed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
