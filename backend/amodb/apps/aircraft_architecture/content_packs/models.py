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


class AircraftContentPack(Base):
    __tablename__ = "aircraft_content_packs"
    __table_args__ = (
        UniqueConstraint("code", name="uq_aircraft_content_pack_code"),
        CheckConstraint(
            "status IN ('SOURCE_INTAKE','ACTIVE','INACTIVE')",
            name="ck_aircraft_content_pack_status",
        ),
        Index("ix_aircraft_content_pack_family", "manufacturer", "family", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    code = Column(String(80), nullable=False)
    manufacturer = Column(String(120), nullable=False)
    family = Column(String(120), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="SOURCE_INTAKE")
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    revisions = relationship(
        "AircraftContentPackRevision",
        back_populates="pack",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class AircraftContentPackRevision(Base):
    __tablename__ = "aircraft_content_pack_revisions"
    __table_args__ = (
        UniqueConstraint("pack_id", "revision_code", name="uq_aircraft_content_pack_revision"),
        CheckConstraint(
            "status IN ('DRAFT','PUBLISHED','SUPERSEDED','WITHDRAWN')",
            name="ck_aircraft_content_pack_revision_status",
        ),
        Index("ix_aircraft_content_pack_revision_status", "pack_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    pack_id = Column(String(36), ForeignKey("aircraft_content_packs.id", ondelete="CASCADE"), nullable=False)
    revision_code = Column(String(40), nullable=False)
    status = Column(String(16), nullable=False, default="DRAFT")
    content_hash = Column(String(64), nullable=True)
    change_summary = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    published_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    published_at = Column(DateTime(timezone=True), nullable=True)

    pack = relationship("AircraftContentPack", back_populates="revisions", lazy="joined")
    sources = relationship(
        "AircraftContentPackSource",
        back_populates="revision",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    positions = relationship(
        "AircraftContentPackPosition",
        back_populates="revision",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    components = relationship(
        "AircraftContentPackComponent",
        back_populates="revision",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    tasks = relationship(
        "AircraftContentPackTask",
        back_populates="revision",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class AircraftContentPackSource(Base):
    __tablename__ = "aircraft_content_pack_sources"
    __table_args__ = (
        UniqueConstraint(
            "revision_id",
            "reference",
            "source_revision",
            name="uq_aircraft_content_pack_source",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    revision_id = Column(
        String(36),
        ForeignKey("aircraft_content_pack_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_type = Column(String(40), nullable=False)
    reference = Column(String(255), nullable=False)
    source_revision = Column(String(80), nullable=False)
    effective_date = Column(Date, nullable=True)
    checksum_sha256 = Column(String(64), nullable=False)
    authority = Column(String(80), nullable=False)
    provenance_json = Column(JSON, nullable=False, default=dict)

    revision = relationship("AircraftContentPackRevision", back_populates="sources", lazy="joined")


class AircraftContentPackPosition(Base):
    __tablename__ = "aircraft_content_pack_positions"
    __table_args__ = (
        UniqueConstraint("revision_id", "code", name="uq_aircraft_content_pack_position"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    revision_id = Column(
        String(36),
        ForeignKey("aircraft_content_pack_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    code = Column(String(50), nullable=False)
    label = Column(String(160), nullable=False)
    position_kind = Column(String(40), nullable=False)
    required = Column(Boolean, nullable=False, default=True)
    source_reference = Column(String(255), nullable=False)
    metadata_json = Column(JSON, nullable=False, default=dict)

    revision = relationship("AircraftContentPackRevision", back_populates="positions", lazy="joined")


class AircraftContentPackComponent(Base):
    __tablename__ = "aircraft_content_pack_components"
    __table_args__ = (
        UniqueConstraint(
            "revision_id",
            "definition_code",
            name="uq_aircraft_content_pack_component",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    revision_id = Column(
        String(36),
        ForeignKey("aircraft_content_pack_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    definition_code = Column(String(80), nullable=False)
    position_code = Column(String(50), nullable=False)
    description = Column(String(255), nullable=False)
    component_class = Column(String(50), nullable=False)
    accepted_part_numbers_json = Column(JSON, nullable=False, default=list)
    life_limit_json = Column(JSON, nullable=False, default=dict)
    metadata_json = Column(JSON, nullable=False, default=dict)
    source_reference = Column(String(255), nullable=False)

    revision = relationship("AircraftContentPackRevision", back_populates="components", lazy="joined")


class AircraftContentPackTask(Base):
    __tablename__ = "aircraft_content_pack_tasks"
    __table_args__ = (
        UniqueConstraint("revision_id", "task_code", name="uq_aircraft_content_pack_task"),
        CheckConstraint(
            "source_reference <> '' AND source_revision <> ''",
            name="ck_aircraft_content_pack_task_source",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    revision_id = Column(
        String(36),
        ForeignKey("aircraft_content_pack_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_code = Column(String(100), nullable=False)
    title = Column(String(255), nullable=False)
    ata_chapter = Column(String(12), nullable=True)
    intervals_json = Column(JSON, nullable=False)
    effectivity_expression_json = Column(JSON, nullable=False, default=dict)
    source_reference = Column(String(255), nullable=False)
    source_revision = Column(String(80), nullable=False)
    source_checksum_sha256 = Column(String(64), nullable=False)
    metadata_json = Column(JSON, nullable=False, default=dict)

    revision = relationship("AircraftContentPackRevision", back_populates="tasks", lazy="joined")
