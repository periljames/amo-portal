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
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.utils.identifiers import generate_uuid7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AircraftFamily(Base):
    __tablename__ = "aircraft_type_families"
    __table_args__ = (
        UniqueConstraint("code", name="uq_aircraft_type_family_code"),
        Index("ix_aircraft_type_family_manufacturer", "manufacturer", "status"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_aircraft_type_family_status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    code = Column(String(40), nullable=False)
    manufacturer = Column(String(120), nullable=False)
    name = Column(String(160), nullable=False)
    category = Column(String(40), nullable=False)
    status = Column(String(16), nullable=False, default="ACTIVE")
    description = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    templates = relationship("AircraftTypeTemplate", back_populates="family", lazy="selectin")


class AircraftTypeTemplate(Base):
    __tablename__ = "aircraft_type_templates"
    __table_args__ = (
        UniqueConstraint("code", name="uq_aircraft_type_template_code"),
        Index("ix_aircraft_type_template_family_status", "family_id", "status"),
        Index("ix_aircraft_type_template_family_series", "family_id", "series", "status"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_aircraft_type_template_status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    family_id = Column(String(36), ForeignKey("aircraft_type_families.id", ondelete="RESTRICT"), nullable=False)
    code = Column(String(50), nullable=False)
    manufacturer = Column(String(120), nullable=False)
    model = Column(String(80), nullable=False)
    variant = Column(String(80), nullable=True)
    series = Column(String(80), nullable=True)
    type_certificate = Column(String(80), nullable=True)
    icao_type_designator = Column(String(8), nullable=True)
    category = Column(String(40), nullable=False)
    status = Column(String(16), nullable=False, default="ACTIVE")
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    family = relationship("AircraftFamily", back_populates="templates", lazy="joined")
    revisions = relationship(
        "AircraftTypeTemplateRevision",
        back_populates="template",
        order_by="AircraftTypeTemplateRevision.created_at.desc()",
        lazy="selectin",
    )


class AircraftTypeTemplateRevision(Base):
    __tablename__ = "aircraft_type_template_revisions"
    __table_args__ = (
        UniqueConstraint("template_id", "revision_code", name="uq_aircraft_type_template_revision"),
        Index("ix_aircraft_type_revision_template_status", "template_id", "status"),
        CheckConstraint(
            "status IN ('DRAFT','PUBLISHED','SUPERSEDED','WITHDRAWN')",
            name="ck_aircraft_type_revision_status",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    template_id = Column(String(36), ForeignKey("aircraft_type_templates.id", ondelete="RESTRICT"), nullable=False)
    revision_code = Column(String(40), nullable=False)
    title = Column(String(200), nullable=False)
    status = Column(String(16), nullable=False, default="DRAFT")
    effective_date = Column(Date, nullable=True)
    supersedes_revision_id = Column(
        String(36),
        ForeignKey("aircraft_type_template_revisions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    configuration_schema_json = Column(JSON, nullable=False, default=dict)
    applicability_defaults_json = Column(JSON, nullable=False, default=dict)
    content_hash = Column(String(64), nullable=True)
    change_summary = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    published_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    published_at = Column(DateTime(timezone=True), nullable=True)

    template = relationship("AircraftTypeTemplate", back_populates="revisions", lazy="joined")
    positions = relationship(
        "AircraftTypePosition",
        back_populates="revision",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    component_definitions = relationship(
        "AircraftTypeComponentDefinition",
        back_populates="revision",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    sources = relationship(
        "AircraftTypeSource",
        back_populates="revision",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class AircraftTypePosition(Base):
    __tablename__ = "aircraft_type_positions"
    __table_args__ = (
        UniqueConstraint("revision_id", "code", name="uq_aircraft_type_position_code"),
        Index("ix_aircraft_type_position_revision_kind", "revision_id", "position_kind"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    revision_id = Column(
        String(36),
        ForeignKey("aircraft_type_template_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    code = Column(String(50), nullable=False)
    label = Column(String(160), nullable=False)
    position_kind = Column(String(40), nullable=False)
    parent_code = Column(String(50), nullable=True)
    sequence_no = Column(String(20), nullable=True)
    required = Column(Boolean, nullable=False, default=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    effectivity_json = Column(JSON, nullable=False, default=dict)

    revision = relationship("AircraftTypeTemplateRevision", back_populates="positions", lazy="joined")


class AircraftTypeComponentDefinition(Base):
    __tablename__ = "aircraft_type_component_definitions"
    __table_args__ = (
        UniqueConstraint("revision_id", "definition_code", name="uq_aircraft_type_component_definition"),
        Index("ix_aircraft_type_component_revision_position", "revision_id", "position_code"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    revision_id = Column(
        String(36),
        ForeignKey("aircraft_type_template_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    definition_code = Column(String(80), nullable=False)
    position_code = Column(String(50), nullable=False)
    description = Column(String(255), nullable=False)
    component_class = Column(String(50), nullable=False)
    accepted_part_numbers_json = Column(JSON, nullable=False, default=list)
    life_limit_json = Column(JSON, nullable=False, default=dict)
    effectivity_json = Column(JSON, nullable=False, default=dict)
    metadata_json = Column(JSON, nullable=False, default=dict)

    revision = relationship("AircraftTypeTemplateRevision", back_populates="component_definitions", lazy="joined")


class AircraftTypeSource(Base):
    __tablename__ = "aircraft_type_sources"
    __table_args__ = (
        UniqueConstraint("revision_id", "source_type", "reference", "source_revision", name="uq_aircraft_type_source"),
        Index("ix_aircraft_type_source_revision_type", "revision_id", "source_type"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    revision_id = Column(
        String(36),
        ForeignKey("aircraft_type_template_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_type = Column(String(40), nullable=False)
    reference = Column(String(200), nullable=False)
    source_revision = Column(String(80), nullable=False)
    effective_date = Column(Date, nullable=True)
    checksum_sha256 = Column(String(64), nullable=True)
    authority = Column(String(80), nullable=True)
    provenance_json = Column(JSON, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    revision = relationship("AircraftTypeTemplateRevision", back_populates="sources", lazy="joined")
