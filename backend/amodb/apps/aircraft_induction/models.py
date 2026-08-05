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
from ...utils.identifiers import generate_uuid7


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AircraftFamily(Base):
    __tablename__ = "aircraft_families"
    __table_args__ = (
        UniqueConstraint("code", name="uq_aircraft_family_code"),
        Index("ix_aircraft_family_manufacturer", "manufacturer", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    code = Column(String(64), nullable=False, index=True)
    name = Column(String(160), nullable=False)
    manufacturer = Column(String(160), nullable=False, index=True)
    description = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    types = relationship("AircraftType", back_populates="family", cascade="all, delete-orphan", lazy="selectin")


class AircraftType(Base):
    __tablename__ = "aircraft_types"
    __table_args__ = (
        UniqueConstraint("family_id", "type_code", name="uq_aircraft_type_family_code"),
        Index("ix_aircraft_type_tc", "type_certificate_number", "authority"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    family_id = Column(String(36), ForeignKey("aircraft_families.id", ondelete="CASCADE"), nullable=False, index=True)
    type_code = Column(String(64), nullable=False, index=True)
    name = Column(String(160), nullable=False)
    type_certificate_number = Column(String(128), nullable=True)
    authority = Column(String(32), nullable=True)
    description = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    family = relationship("AircraftFamily", back_populates="types", lazy="joined")
    variants = relationship("AircraftVariant", back_populates="aircraft_type", cascade="all, delete-orphan", lazy="selectin")


class AircraftVariant(Base):
    __tablename__ = "aircraft_variants"
    __table_args__ = (
        UniqueConstraint("aircraft_type_id", "variant_code", name="uq_aircraft_variant_type_code"),
        Index("ix_aircraft_variant_model_code", "model_code"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    aircraft_type_id = Column(String(36), ForeignKey("aircraft_types.id", ondelete="CASCADE"), nullable=False, index=True)
    variant_code = Column(String(64), nullable=False, index=True)
    model_code = Column(String(64), nullable=False, index=True)
    marketing_name = Column(String(160), nullable=True)
    description = Column(Text, nullable=True)
    serial_effectivity_json = Column(JSON, nullable=False, default=dict)
    engine_options_json = Column(JSON, nullable=False, default=list)
    propeller_options_json = Column(JSON, nullable=False, default=list)
    apu_options_json = Column(JSON, nullable=False, default=list)
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    aircraft_type = relationship("AircraftType", back_populates="variants", lazy="joined")
    templates = relationship("AircraftTypeTemplate", back_populates="variant", cascade="all, delete-orphan", lazy="selectin")


class AircraftTypeTemplate(Base):
    __tablename__ = "aircraft_type_templates"
    __table_args__ = (
        UniqueConstraint("code", name="uq_aircraft_type_template_code"),
        Index("ix_aircraft_type_template_scope", "visibility", "owner_amo_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    variant_id = Column(String(36), ForeignKey("aircraft_variants.id", ondelete="RESTRICT"), nullable=False, index=True)
    code = Column(String(96), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    visibility = Column(String(16), nullable=False, default="GLOBAL", index=True)
    owner_amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=True, index=True)
    description = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    variant = relationship("AircraftVariant", back_populates="templates", lazy="joined")
    revisions = relationship("AircraftTypeTemplateRevision", back_populates="template", cascade="all, delete-orphan", lazy="selectin")


class AircraftTypeTemplateRevision(Base):
    __tablename__ = "aircraft_type_template_revisions"
    __table_args__ = (
        UniqueConstraint("template_id", "revision_code", name="uq_aircraft_type_template_revision"),
        Index("ix_aircraft_type_revision_status", "template_id", "status", "effective_date"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    template_id = Column(String(36), ForeignKey("aircraft_type_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    revision_code = Column(String(48), nullable=False)
    status = Column(String(20), nullable=False, default="DRAFT", index=True)
    effective_date = Column(Date, nullable=True)
    source_reference = Column(String(255), nullable=True)
    source_hash = Column(String(64), nullable=True)
    content_hash = Column(String(64), nullable=True, index=True)
    release_notes = Column(Text, nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    template = relationship("AircraftTypeTemplate", back_populates="revisions", lazy="joined")
    source_documents = relationship("TemplateSourceDocument", back_populates="revision", cascade="all, delete-orphan", lazy="selectin")
    configuration_nodes = relationship("TemplateConfigurationNode", back_populates="revision", cascade="all, delete-orphan", lazy="selectin")
    requirements = relationship("TemplateRequirement", back_populates="revision", cascade="all, delete-orphan", lazy="selectin")


class TemplateSourceDocument(Base):
    __tablename__ = "aircraft_template_source_documents"
    __table_args__ = (
        UniqueConstraint("revision_id", "document_type", "reference", "revision", name="uq_aircraft_template_source_document"),
        Index("ix_template_source_revision", "revision_id", "document_type"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    revision_id = Column(String(36), ForeignKey("aircraft_type_template_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    document_type = Column(String(32), nullable=False)
    reference = Column(String(160), nullable=False)
    revision = Column(String(64), nullable=True)
    issue_date = Column(Date, nullable=True)
    authority = Column(String(32), nullable=True)
    source_uri = Column(String(512), nullable=True)
    content_hash = Column(String(64), nullable=True)
    notes = Column(Text, nullable=True)

    revision_rel = relationship("AircraftTypeTemplateRevision", back_populates="source_documents", foreign_keys=[revision_id])

    @property
    def revision_parent(self):
        return self.revision_rel


class TemplateConfigurationNode(Base):
    __tablename__ = "aircraft_template_configuration_nodes"
    __table_args__ = (
        UniqueConstraint("revision_id", "node_key", name="uq_aircraft_template_config_node"),
        Index("ix_template_config_revision_parent", "revision_id", "parent_node_key", "sequence_no"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    revision_id = Column(String(36), ForeignKey("aircraft_type_template_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    node_key = Column(String(128), nullable=False)
    parent_node_key = Column(String(128), nullable=True)
    node_type = Column(String(32), nullable=False)
    position_code = Column(String(64), nullable=True)
    title = Column(String(255), nullable=False)
    ata_chapter = Column(String(20), nullable=True)
    minimum_quantity = Column(Integer, nullable=False, default=0)
    maximum_quantity = Column(Integer, nullable=True)
    allowable_parts_json = Column(JSON, nullable=False, default=list)
    counter_rules_json = Column(JSON, nullable=False, default=list)
    effectivity_json = Column(JSON, nullable=False, default=dict)
    sequence_no = Column(Integer, nullable=False, default=1)

    revision = relationship("AircraftTypeTemplateRevision", back_populates="configuration_nodes", lazy="joined")


class TemplateRequirement(Base):
    __tablename__ = "aircraft_template_requirements"
    __table_args__ = (
        UniqueConstraint("revision_id", "requirement_key", name="uq_aircraft_template_requirement"),
        Index("ix_template_requirement_revision_ata", "revision_id", "ata_chapter", "category"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    revision_id = Column(String(36), ForeignKey("aircraft_type_template_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_key = Column(String(128), nullable=False)
    category = Column(String(32), nullable=False, index=True)
    ata_chapter = Column(String(20), nullable=True, index=True)
    task_code = Column(String(96), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    governing_logic = Column(String(32), nullable=False, default="WHICHEVER_FIRST")
    interval_json = Column(JSON, nullable=False, default=dict)
    threshold_json = Column(JSON, nullable=False, default=dict)
    effectivity_json = Column(JSON, nullable=False, default=dict)
    source_reference = Column(String(255), nullable=True)
    source_document_id = Column(String(36), ForeignKey("aircraft_template_source_documents.id", ondelete="SET NULL"), nullable=True)
    mandatory = Column(Boolean, nullable=False, default=True)
    sequence_no = Column(Integer, nullable=False, default=1)

    revision = relationship("AircraftTypeTemplateRevision", back_populates="requirements", lazy="joined")


class ImportMappingProfile(Base):
    __tablename__ = "aircraft_import_mapping_profiles"
    __table_args__ = (
        UniqueConstraint("scope", "amo_id", "name", "version", name="uq_aircraft_import_mapping_profile"),
        Index("ix_import_mapping_fingerprint", "dataset", "fingerprint", "status"),
        Index("ix_import_mapping_source", "source_system", "source_version", "dataset"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=True, index=True)
    scope = Column(String(16), nullable=False, default="TENANT", index=True)
    name = Column(String(160), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    source_system = Column(String(64), nullable=False, index=True)
    source_version = Column(String(64), nullable=True)
    dataset = Column(String(32), nullable=False, index=True)
    fingerprint = Column(String(64), nullable=False, index=True)
    header_signature_json = Column(JSON, nullable=False, default=list)
    mapping_json = Column(JSON, nullable=False, default=dict)
    transformations_json = Column(JSON, nullable=False, default=dict)
    defaults_json = Column(JSON, nullable=False, default=dict)
    validation_json = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class TenantMaintenanceProgram(Base):
    __tablename__ = "tenant_maintenance_programs"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_tenant_maintenance_program_code"),
        Index("ix_tenant_program_variant", "amo_id", "variant_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    variant_id = Column(String(36), ForeignKey("aircraft_variants.id", ondelete="RESTRICT"), nullable=False, index=True)
    code = Column(String(96), nullable=False)
    title = Column(String(255), nullable=False)
    authority = Column(String(32), nullable=True)
    approval_reference = Column(String(160), nullable=True)
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    revisions = relationship("TenantMaintenanceProgramRevision", back_populates="program", cascade="all, delete-orphan", lazy="selectin")


class TenantMaintenanceProgramRevision(Base):
    __tablename__ = "tenant_maintenance_program_revisions"
    __table_args__ = (
        UniqueConstraint("program_id", "revision_code", name="uq_tenant_program_revision"),
        Index("ix_tenant_program_revision_status", "program_id", "status", "effective_date"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    program_id = Column(String(36), ForeignKey("tenant_maintenance_programs.id", ondelete="CASCADE"), nullable=False, index=True)
    base_template_revision_id = Column(String(36), ForeignKey("aircraft_type_template_revisions.id", ondelete="RESTRICT"), nullable=False, index=True)
    revision_code = Column(String(48), nullable=False)
    status = Column(String(20), nullable=False, default="DRAFT", index=True)
    effective_date = Column(Date, nullable=True)
    approval_reference = Column(String(160), nullable=True)
    approval_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    program = relationship("TenantMaintenanceProgram", back_populates="revisions", lazy="joined")
    overrides = relationship("TenantProgramOverride", back_populates="revision", cascade="all, delete-orphan", lazy="selectin")


class TenantProgramOverride(Base):
    __tablename__ = "tenant_program_overrides"
    __table_args__ = (
        UniqueConstraint("program_revision_id", "requirement_key", name="uq_tenant_program_override"),
        Index("ix_tenant_program_override_action", "program_revision_id", "action"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    program_revision_id = Column(String(36), ForeignKey("tenant_maintenance_program_revisions.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_key = Column(String(128), nullable=False)
    action = Column(String(16), nullable=False)
    patch_json = Column(JSON, nullable=False, default=dict)
    effectivity_json = Column(JSON, nullable=False, default=dict)
    justification = Column(Text, nullable=False)
    authority_reference = Column(String(160), nullable=True)

    revision = relationship("TenantMaintenanceProgramRevision", back_populates="overrides", lazy="joined")


class AircraftInduction(Base):
    __tablename__ = "aircraft_inductions"
    __table_args__ = (
        UniqueConstraint("amo_id", "induction_ref", name="uq_aircraft_induction_ref"),
        Index("ix_aircraft_induction_status", "amo_id", "status", "created_at"),
        Index("ix_aircraft_induction_aircraft", "amo_id", "serial_number", "registration"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    induction_ref = Column(String(96), nullable=False)
    serial_number = Column(String(50), nullable=False, index=True)
    registration = Column(String(20), nullable=False, index=True)
    variant_id = Column(String(36), ForeignKey("aircraft_variants.id", ondelete="RESTRICT"), nullable=False)
    template_revision_id = Column(String(36), ForeignKey("aircraft_type_template_revisions.id", ondelete="RESTRICT"), nullable=False)
    program_revision_id = Column(String(36), ForeignKey("tenant_maintenance_program_revisions.id", ondelete="RESTRICT"), nullable=False)
    status = Column(String(24), nullable=False, default="DRAFT", index=True)
    source_system = Column(String(64), nullable=True)
    source_reference = Column(String(255), nullable=True)
    source_hash = Column(String(64), nullable=True)
    current_step = Column(String(32), nullable=False, default="IDENTIFY")
    counts_json = Column(JSON, nullable=False, default=dict)
    validation_json = Column(JSON, nullable=False, default=dict)
    activation_manifest_json = Column(JSON, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    datasets = relationship("AircraftInductionDataset", back_populates="induction", cascade="all, delete-orphan", lazy="selectin")


class AircraftInductionDataset(Base):
    __tablename__ = "aircraft_induction_datasets"
    __table_args__ = (
        UniqueConstraint("induction_id", "dataset", "source_name", name="uq_aircraft_induction_dataset"),
        Index("ix_aircraft_induction_dataset_status", "induction_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    induction_id = Column(String(36), ForeignKey("aircraft_inductions.id", ondelete="CASCADE"), nullable=False, index=True)
    dataset = Column(String(32), nullable=False, index=True)
    source_name = Column(String(255), nullable=False)
    source_sheet = Column(String(160), nullable=True)
    fingerprint = Column(String(64), nullable=False, index=True)
    mapping_profile_id = Column(String(36), ForeignKey("aircraft_import_mapping_profiles.id", ondelete="SET NULL"), nullable=True)
    headers_json = Column(JSON, nullable=False, default=list)
    row_count = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="STAGED", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    induction = relationship("AircraftInduction", back_populates="datasets", lazy="joined")
    rows = relationship("AircraftInductionRow", back_populates="dataset_rel", cascade="all, delete-orphan", lazy="selectin")


class AircraftInductionRow(Base):
    __tablename__ = "aircraft_induction_rows"
    __table_args__ = (
        UniqueConstraint("dataset_id", "row_number", name="uq_aircraft_induction_row"),
        Index("ix_aircraft_induction_row_status", "dataset_id", "status", "row_number"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    dataset_id = Column(String(36), ForeignKey("aircraft_induction_datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    row_number = Column(Integer, nullable=False)
    source_json = Column(JSON, nullable=False)
    normalized_json = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="STAGED", index=True)
    errors_json = Column(JSON, nullable=False, default=list)
    warnings_json = Column(JSON, nullable=False, default=list)
    decision = Column(String(20), nullable=True)
    final_json = Column(JSON, nullable=False, default=dict)
    decided_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)

    dataset_rel = relationship("AircraftInductionDataset", back_populates="rows", lazy="joined")


class AircraftApplicabilitySnapshot(Base):
    __tablename__ = "aircraft_applicability_snapshots"
    __table_args__ = (
        Index("ix_aircraft_applicability_aircraft", "amo_id", "aircraft_serial_number", "created_at"),
        Index("ix_aircraft_applicability_hash", "snapshot_hash"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    induction_id = Column(String(36), ForeignKey("aircraft_inductions.id", ondelete="SET NULL"), nullable=True, index=True)
    aircraft_serial_number = Column(String(50), nullable=False, index=True)
    template_revision_id = Column(String(36), ForeignKey("aircraft_type_template_revisions.id", ondelete="RESTRICT"), nullable=False)
    program_revision_id = Column(String(36), ForeignKey("tenant_maintenance_program_revisions.id", ondelete="RESTRICT"), nullable=False)
    configuration_hash = Column(String(64), nullable=False)
    snapshot_hash = Column(String(64), nullable=False, index=True)
    context_json = Column(JSON, nullable=False)
    applicable_requirements_json = Column(JSON, nullable=False)
    excluded_requirements_json = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class AircraftTemplateBinding(Base):
    __tablename__ = "aircraft_template_bindings"
    __table_args__ = (
        Index("ix_aircraft_template_binding_active", "amo_id", "aircraft_serial_number", "status"),
        UniqueConstraint("amo_id", "aircraft_serial_number", "status", name="uq_aircraft_template_binding_status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_serial_number = Column(String(50), ForeignKey("aircraft.serial_number", ondelete="CASCADE"), nullable=False, index=True)
    variant_id = Column(String(36), ForeignKey("aircraft_variants.id", ondelete="RESTRICT"), nullable=False)
    template_revision_id = Column(String(36), ForeignKey("aircraft_type_template_revisions.id", ondelete="RESTRICT"), nullable=False)
    program_revision_id = Column(String(36), ForeignKey("tenant_maintenance_program_revisions.id", ondelete="RESTRICT"), nullable=False)
    applicability_snapshot_id = Column(String(36), ForeignKey("aircraft_applicability_snapshots.id", ondelete="RESTRICT"), nullable=False)
    status = Column(String(16), nullable=False, default="ACTIVE", index=True)
    activated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    superseded_at = Column(DateTime(timezone=True), nullable=True)


class InductionCounterBaseline(Base):
    __tablename__ = "aircraft_induction_counter_baselines"
    __table_args__ = (
        UniqueConstraint("induction_id", "counter_code", name="uq_induction_counter_baseline"),
        CheckConstraint("value >= 0", name="ck_induction_counter_baseline_nonnegative"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    induction_id = Column(String(36), ForeignKey("aircraft_inductions.id", ondelete="CASCADE"), nullable=False, index=True)
    counter_code = Column(String(48), nullable=False)
    unit = Column(String(16), nullable=False)
    value = Column(Numeric(18, 4), nullable=False)
    effective_date = Column(Date, nullable=True)
    source_reference = Column(String(255), nullable=True)
