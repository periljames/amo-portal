from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.utils.identifiers import generate_uuid7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TenantMaintenanceProgramme(Base):
    __tablename__ = "tenant_maintenance_programmes"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_tenant_maintenance_programme_code"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_tenant_maintenance_programme_status"),
        Index("ix_tenant_maintenance_programme_scope", "amo_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(80), nullable=False)
    title = Column(String(200), nullable=False)
    authority = Column(String(80), nullable=True)
    approval_reference = Column(String(160), nullable=True)
    status = Column(String(16), nullable=False, default="ACTIVE")
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    revisions = relationship(
        "TenantProgrammeRevision",
        back_populates="programme",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
        order_by="TenantProgrammeRevision.created_at.desc()",
    )


class TenantProgrammeRevision(Base):
    __tablename__ = "tenant_maintenance_programme_revisions"
    __table_args__ = (
        UniqueConstraint("programme_id", "revision_code", name="uq_tenant_maintenance_programme_revision"),
        CheckConstraint(
            "status IN ('DRAFT','PUBLISHED','SUPERSEDED','WITHDRAWN')",
            name="ck_tenant_maintenance_programme_revision_status",
        ),
        Index("ix_tenant_maintenance_programme_revision_status", "programme_id", "status"),
        Index("ix_tenant_programme_revision_oem_baseline", "base_content_pack_revision_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    programme_id = Column(String(36), ForeignKey("tenant_maintenance_programmes.id", ondelete="CASCADE"), nullable=False, index=True)
    revision_code = Column(String(40), nullable=False)
    status = Column(String(16), nullable=False, default="DRAFT")
    aircraft_type_revision_id = Column(
        String(36),
        ForeignKey("aircraft_type_template_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    effectivity_rule_version_id = Column(
        String(36),
        ForeignKey("aircraft_effectivity_rule_versions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    base_content_pack_revision_id = Column(
        String(36),
        ForeignKey("aircraft_content_pack_revisions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    source_reference = Column(String(255), nullable=False)
    source_revision = Column(String(80), nullable=False)
    source_checksum_sha256 = Column(String(64), nullable=True)
    source_currentness_at_approval = Column(String(40), nullable=True)
    approval_reference = Column(String(160), nullable=True)
    content_hash = Column(String(64), nullable=True)
    change_summary = Column(Text, nullable=True)
    supersedes_revision_id = Column(
        String(36),
        ForeignKey("tenant_maintenance_programme_revisions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    published_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    published_at = Column(DateTime(timezone=True), nullable=True)

    programme = relationship("TenantMaintenanceProgramme", back_populates="revisions", lazy="joined")
    tasks = relationship(
        "TenantProgrammeTask",
        back_populates="revision",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    validation_runs = relationship(
        "TenantProgrammeValidationRun",
        back_populates="revision",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
        order_by="TenantProgrammeValidationRun.created_at.desc()",
    )


class TenantProgrammeTask(Base):
    __tablename__ = "tenant_maintenance_programme_tasks"
    __table_args__ = (
        UniqueConstraint("revision_id", "task_code", name="uq_tenant_maintenance_programme_task"),
        CheckConstraint(
            "decision IN ('INHERIT','TIGHTEN','ADD','LEGACY')",
            name="ck_tenant_programme_task_decision",
        ),
        Index("ix_tenant_maintenance_programme_task_ata", "revision_id", "ata_chapter"),
        Index("ix_tenant_programme_task_source", "revision_id", "source_content_task_id", "decision"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    revision_id = Column(String(36), ForeignKey("tenant_maintenance_programme_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    source_content_task_id = Column(
        String(36),
        ForeignKey("aircraft_content_pack_tasks.id", ondelete="RESTRICT"),
        nullable=True,
    )
    decision = Column(String(20), nullable=False, default="LEGACY")
    task_code = Column(String(100), nullable=False)
    title = Column(String(255), nullable=False)
    ata_chapter = Column(String(12), nullable=True)
    intervals_json = Column(JSON, nullable=False, default=dict)
    effectivity_expression_json = Column(JSON, nullable=False, default=dict)
    source_reference = Column(String(255), nullable=False)
    justification = Column(Text, nullable=True)
    approval_reference = Column(String(160), nullable=True)
    source_task_hash = Column(String(64), nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)

    revision = relationship("TenantProgrammeRevision", back_populates="tasks", lazy="joined")


class TenantProgrammeValidationRun(Base):
    __tablename__ = "tenant_programme_validation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PASS','WARN','BLOCKED')",
            name="ck_tenant_programme_validation_status",
        ),
        Index("ix_tenant_programme_validation_revision", "revision_id", "created_at"),
        Index("ix_tenant_programme_validation_scope", "amo_id", "status", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    revision_id = Column(
        String(36),
        ForeignKey("tenant_maintenance_programme_revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    baseline_revision_id = Column(
        String(36),
        ForeignKey("aircraft_content_pack_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    programme_content_hash = Column(String(64), nullable=False)
    baseline_content_hash = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False)
    blocking_count = Column(Integer, nullable=False, default=0)
    warning_count = Column(Integer, nullable=False, default=0)
    issues_json = Column(JSON, nullable=False, default=list)
    summary_json = Column(JSON, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    revision = relationship("TenantProgrammeRevision", back_populates="validation_runs", lazy="joined")


class ProgrammeUpgradeProposal(Base):
    __tablename__ = "tenant_programme_upgrade_proposals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','IMPACT_REVIEW','APPROVED','REJECTED','APPLIED')",
            name="ck_tenant_programme_upgrade_proposal_status",
        ),
        Index("ix_tenant_programme_upgrade_proposal_scope", "amo_id", "programme_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    programme_id = Column(String(36), ForeignKey("tenant_maintenance_programmes.id", ondelete="CASCADE"), nullable=False, index=True)
    from_revision_id = Column(String(36), ForeignKey("tenant_maintenance_programme_revisions.id", ondelete="RESTRICT"), nullable=False)
    proposed_type_revision_id = Column(String(36), ForeignKey("aircraft_type_template_revisions.id", ondelete="RESTRICT"), nullable=False)
    proposed_effectivity_version_id = Column(String(36), ForeignKey("aircraft_effectivity_rule_versions.id", ondelete="RESTRICT"), nullable=True)
    status = Column(String(20), nullable=False, default="DRAFT")
    impact_json = Column(JSON, nullable=False, default=dict)
    requested_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    approved_at = Column(DateTime(timezone=True), nullable=True)
