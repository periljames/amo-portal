from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.utils.identifiers import generate_uuid7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ImportMappingProfile(Base):
    __tablename__ = "aircraft_import_mapping_profiles"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_aircraft_import_mapping_profile_scope_code"),
        Index("uq_aircraft_import_global_profile", "code", unique=True, postgresql_where=text("scope = 'GLOBAL'")),
        CheckConstraint("scope IN ('GLOBAL','TENANT')", name="ck_aircraft_import_mapping_profile_scope"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_aircraft_import_mapping_profile_status"),
        Index("ix_aircraft_import_mapping_profile_source", "source_system", "dataset_kind"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=True, index=True)
    code = Column(String(80), nullable=False)
    name = Column(String(200), nullable=False)
    scope = Column(String(16), nullable=False, default="TENANT")
    source_system = Column(String(40), nullable=False)
    dataset_kind = Column(String(60), nullable=False)
    status = Column(String(16), nullable=False, default="ACTIVE")
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    versions = relationship("ImportMappingProfileVersion", back_populates="profile", cascade="all, delete-orphan", passive_deletes=True, lazy="selectin", order_by="ImportMappingProfileVersion.created_at.desc()")


class ImportMappingProfileVersion(Base):
    __tablename__ = "aircraft_import_mapping_profile_versions"
    __table_args__ = (
        UniqueConstraint("profile_id", "version_code", name="uq_aircraft_import_mapping_profile_version"),
        CheckConstraint("status IN ('DRAFT','PUBLISHED','SUPERSEDED','WITHDRAWN')", name="ck_aircraft_import_mapping_profile_version_status"),
        Index("ix_aircraft_import_mapping_profile_version_status", "profile_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    profile_id = Column(String(36), ForeignKey("aircraft_import_mapping_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    version_code = Column(String(40), nullable=False)
    status = Column(String(16), nullable=False, default="DRAFT")
    header_fingerprint = Column(String(64), nullable=False)
    mapping_json = Column(JSON, nullable=False, default=dict)
    parser_options_json = Column(JSON, nullable=False, default=dict)
    content_hash = Column(String(64), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    published_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    published_at = Column(DateTime(timezone=True), nullable=True)
    profile = relationship("ImportMappingProfile", back_populates="versions", lazy="joined")


class AircraftImportBatch(Base):
    __tablename__ = "aircraft_import_batches"
    __table_args__ = (
        UniqueConstraint("amo_id", "idempotency_key", name="uq_aircraft_import_batch_idempotency"),
        CheckConstraint("status IN ('STAGED','VALIDATED','RECONCILED','APPROVED','COMMITTED','FAILED','CANCELLED')", name="ck_aircraft_import_batch_status"),
        Index("ix_aircraft_import_batch_scope_status", "amo_id", "status", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    source_system = Column(String(40), nullable=False)
    idempotency_key = Column(String(96), nullable=False)
    manifest_hash = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, default="STAGED")
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    datasets = relationship("AircraftImportDataset", back_populates="batch", cascade="all, delete-orphan", passive_deletes=True, lazy="selectin")
    issues = relationship("AircraftImportIssue", back_populates="batch", cascade="all, delete-orphan", passive_deletes=True, lazy="selectin")


class AircraftImportDataset(Base):
    __tablename__ = "aircraft_import_datasets"
    __table_args__ = (
        UniqueConstraint("batch_id", "content_hash", name="uq_aircraft_import_dataset_content"),
        Index("ix_aircraft_import_dataset_kind", "batch_id", "dataset_kind"),
    )
    id = Column(String(36), primary_key=True, default=generate_uuid7)
    batch_id = Column(String(36), ForeignKey("aircraft_import_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_kind = Column(String(60), nullable=False)
    adapter_code = Column(String(40), nullable=False)
    file_name = Column(String(255), nullable=False)
    content_hash = Column(String(64), nullable=False)
    header_fingerprint = Column(String(64), nullable=False)
    row_count = Column(Integer, nullable=False, default=0)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    batch = relationship("AircraftImportBatch", back_populates="datasets", lazy="joined")
    rows = relationship("AircraftImportStagingRow", back_populates="dataset", cascade="all, delete-orphan", passive_deletes=True, lazy="selectin")


class AircraftImportStagingRow(Base):
    __tablename__ = "aircraft_import_staging_rows"
    __table_args__ = (
        UniqueConstraint("dataset_id", "row_number", name="uq_aircraft_import_staging_row_number"),
        UniqueConstraint("dataset_id", "row_hash", name="uq_aircraft_import_staging_row_hash"),
        CheckConstraint("status IN ('STAGED','VALID','INVALID','RESOLVED')", name="ck_aircraft_import_staging_row_status"),
        Index("ix_aircraft_import_staging_row_identity", "dataset_id", "identity_key"),
    )
    id = Column(String(36), primary_key=True, default=generate_uuid7)
    dataset_id = Column(String(36), ForeignKey("aircraft_import_datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    row_number = Column(Integer, nullable=False)
    identity_key = Column(String(200), nullable=True)
    row_hash = Column(String(64), nullable=False)
    source_json = Column(JSON, nullable=False)
    normalized_json = Column(JSON, nullable=False)
    status = Column(String(16), nullable=False, default="STAGED")
    dataset = relationship("AircraftImportDataset", back_populates="rows", lazy="joined")


class AircraftImportIssue(Base):
    __tablename__ = "aircraft_import_issues"
    __table_args__ = (
        CheckConstraint("severity IN ('INFO','WARNING','ERROR')", name="ck_aircraft_import_issue_severity"),
        CheckConstraint("resolution_status IN ('OPEN','RESOLVED','WAIVED')", name="ck_aircraft_import_issue_resolution"),
        Index("ix_aircraft_import_issue_open", "batch_id", "severity", "resolution_status"),
    )
    id = Column(String(36), primary_key=True, default=generate_uuid7)
    batch_id = Column(String(36), ForeignKey("aircraft_import_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset_id = Column(String(36), ForeignKey("aircraft_import_datasets.id", ondelete="CASCADE"), nullable=True, index=True)
    row_id = Column(String(36), ForeignKey("aircraft_import_staging_rows.id", ondelete="CASCADE"), nullable=True, index=True)
    severity = Column(String(16), nullable=False)
    code = Column(String(80), nullable=False)
    path = Column(String(200), nullable=True)
    message = Column(Text, nullable=False)
    resolution_status = Column(String(16), nullable=False, default="OPEN")
    batch = relationship("AircraftImportBatch", back_populates="issues", lazy="joined")
    decisions = relationship("AircraftImportDecision", back_populates="issue", cascade="all, delete-orphan", passive_deletes=True, lazy="selectin")


class AircraftImportDecision(Base):
    __tablename__ = "aircraft_import_decisions"
    __table_args__ = (CheckConstraint("decision IN ('ACCEPT','REJECT','CORRECT','WAIVE')", name="ck_aircraft_import_decision"),)
    id = Column(String(36), primary_key=True, default=generate_uuid7)
    issue_id = Column(String(36), ForeignKey("aircraft_import_issues.id", ondelete="CASCADE"), nullable=False, index=True)
    decision = Column(String(16), nullable=False)
    rationale = Column(Text, nullable=False)
    correction_json = Column(JSON, nullable=False, default=dict)
    decided_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    issue = relationship("AircraftImportIssue", back_populates="decisions", lazy="joined")
