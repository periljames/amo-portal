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
    series = Column(String(80), nullable=True)
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
    resources = relationship(
        "AircraftContentPackResource",
        back_populates="revision",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class AircraftOemPublication(Base):
    __tablename__ = "aircraft_oem_publications"
    __table_args__ = (
        UniqueConstraint("code", name="uq_aircraft_oem_publication_code"),
        CheckConstraint(
            "status IN ('ACTIVE','INACTIVE')",
            name="ck_aircraft_oem_publication_status",
        ),
        Index(
            "ix_aircraft_oem_publication_family",
            "manufacturer",
            "family",
            "series",
            "status",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    code = Column(String(100), nullable=False)
    manufacturer = Column(String(120), nullable=False)
    family = Column(String(120), nullable=False)
    series = Column(String(80), nullable=True)
    publication_code = Column(String(120), nullable=False)
    title = Column(String(255), nullable=False)
    publication_kind = Column(String(40), nullable=False)
    status = Column(String(16), nullable=False, default="ACTIVE")
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    revisions = relationship(
        "AircraftOemPublicationRevision",
        back_populates="publication",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="AircraftOemPublicationRevision.publication_id",
        lazy="selectin",
    )
    watches = relationship(
        "AircraftOemSourceWatch",
        back_populates="publication",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class AircraftOemPublicationRevision(Base):
    __tablename__ = "aircraft_oem_publication_revisions"
    __table_args__ = (
        UniqueConstraint(
            "publication_id",
            "revision_code",
            name="uq_aircraft_oem_publication_revision",
        ),
        CheckConstraint(
            "status IN ('CANDIDATE','VERIFIED','CURRENT','SUPERSEDED','WITHDRAWN','REJECTED')",
            name="ck_aircraft_oem_publication_revision_status",
        ),
        Index(
            "ix_aircraft_oem_publication_revision_status",
            "publication_id",
            "status",
            "effective_date",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    publication_id = Column(
        String(36),
        ForeignKey("aircraft_oem_publications.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_code = Column(String(80), nullable=False)
    status = Column(String(16), nullable=False, default="CANDIDATE")
    issue_date = Column(Date, nullable=True)
    effective_date = Column(Date, nullable=True)
    checksum_sha256 = Column(String(64), nullable=False)
    source_filename = Column(String(255), nullable=True)
    storage_locator = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)
    change_summary = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    supersedes_revision_id = Column(
        String(36),
        ForeignKey("aircraft_oem_publication_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    submitted_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_by_amo_id = Column(String(36), ForeignKey("amos.id", ondelete="SET NULL"), nullable=True)
    verified_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    publication = relationship(
        "AircraftOemPublication",
        back_populates="revisions",
        foreign_keys=[publication_id],
        lazy="joined",
    )
    temporary_revisions = relationship(
        "AircraftOemTemporaryRevision",
        back_populates="publication_revision",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="AircraftOemTemporaryRevision.publication_revision_id",
        lazy="selectin",
    )


class AircraftOemTemporaryRevision(Base):
    __tablename__ = "aircraft_oem_temporary_revisions"
    __table_args__ = (
        UniqueConstraint(
            "publication_revision_id",
            "temporary_revision_code",
            name="uq_aircraft_oem_temporary_revision",
        ),
        CheckConstraint(
            "status IN ('ACTIVE','INCORPORATED','SUPERSEDED','WITHDRAWN','REPLACED')",
            name="ck_aircraft_oem_temporary_revision_status",
        ),
        Index(
            "ix_aircraft_oem_temporary_revision_status",
            "publication_revision_id",
            "status",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    publication_revision_id = Column(
        String(36),
        ForeignKey("aircraft_oem_publication_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    temporary_revision_code = Column(String(80), nullable=False)
    status = Column(String(16), nullable=False, default="ACTIVE")
    issue_date = Column(Date, nullable=True)
    effective_date = Column(Date, nullable=True)
    checksum_sha256 = Column(String(64), nullable=False)
    source_filename = Column(String(255), nullable=True)
    storage_locator = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)
    replaces_temporary_revision_code = Column(String(80), nullable=True)
    filing_instructions = Column(Text, nullable=True)
    change_summary = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    submitted_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_by_amo_id = Column(String(36), ForeignKey("amos.id", ondelete="SET NULL"), nullable=True)
    verified_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    publication_revision = relationship(
        "AircraftOemPublicationRevision",
        back_populates="temporary_revisions",
        foreign_keys=[publication_revision_id],
        lazy="joined",
    )


class AircraftOemSourceWatch(Base):
    __tablename__ = "aircraft_oem_source_watches"
    __table_args__ = (
        UniqueConstraint(
            "publication_id",
            "channel_type",
            "reference",
            name="uq_aircraft_oem_source_watch",
        ),
        CheckConstraint(
            "channel_type IN ('MANUAL_UPLOAD','OEM_PORTAL','EMAIL_NOTICE','RSS','API','OTHER')",
            name="ck_aircraft_oem_source_watch_channel",
        ),
        Index("ix_aircraft_oem_source_watch_active", "publication_id", "is_active"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    publication_id = Column(
        String(36),
        ForeignKey("aircraft_oem_publications.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel_type = Column(String(20), nullable=False)
    reference = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    last_seen_marker = Column(String(255), nullable=True)
    last_result = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    publication = relationship("AircraftOemPublication", back_populates="watches", lazy="joined")


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
    publication_revision_id = Column(
        String(36),
        ForeignKey("aircraft_oem_publication_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    temporary_revision_id = Column(
        String(36),
        ForeignKey("aircraft_oem_temporary_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_page_ref = Column(String(120), nullable=True)
    document_locator = Column(Text, nullable=True)

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
        Index("ix_aircraft_content_pack_task_section", "revision_id", "programme_section", "ata_chapter"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    revision_id = Column(
        String(36),
        ForeignKey("aircraft_content_pack_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_code = Column(String(100), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    ata_chapter = Column(String(12), nullable=True)
    programme_section = Column(String(40), nullable=True)
    task_type = Column(String(16), nullable=True)
    intervals_json = Column(JSON, nullable=False)
    raw_interval_text = Column(Text, nullable=True)
    effectivity_expression_json = Column(JSON, nullable=False, default=dict)
    raw_effectivity_text = Column(Text, nullable=True)
    source_requirements_json = Column(JSON, nullable=False, default=list)
    task_card_number = Column(String(120), nullable=True)
    task_card_configuration = Column(String(120), nullable=True)
    amm_reference = Column(String(120), nullable=True)
    zones_json = Column(JSON, nullable=False, default=list)
    panels_json = Column(JSON, nullable=False, default=list)
    general_references_json = Column(JSON, nullable=False, default=list)
    skill_code = Column(String(40), nullable=True)
    labour_hours = Column(String(24), nullable=True)
    number_of_persons = Column(Integer, nullable=True)
    program_notes_json = Column(JSON, nullable=False, default=list)
    packaging_json = Column(JSON, nullable=False, default=dict)
    source_page_ref = Column(String(120), nullable=True)
    source_reference = Column(String(255), nullable=False)
    source_revision = Column(String(80), nullable=False)
    source_checksum_sha256 = Column(String(64), nullable=False)
    metadata_json = Column(JSON, nullable=False, default=dict)

    revision = relationship("AircraftContentPackRevision", back_populates="tasks", lazy="joined")


class AircraftContentPackResource(Base):
    __tablename__ = "aircraft_content_pack_resources"
    __table_args__ = (
        UniqueConstraint(
            "revision_id",
            "resource_kind",
            "resource_code",
            name="uq_aircraft_content_pack_resource",
        ),
        Index("ix_aircraft_content_pack_resource_kind", "revision_id", "resource_kind"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    revision_id = Column(
        String(36),
        ForeignKey("aircraft_content_pack_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    resource_kind = Column(String(50), nullable=False)
    resource_code = Column(String(140), nullable=False)
    title = Column(String(255), nullable=False)
    payload_json = Column(JSON, nullable=False, default=dict)
    source_reference = Column(String(255), nullable=False)
    source_revision = Column(String(80), nullable=False)
    source_checksum_sha256 = Column(String(64), nullable=False)
    source_page_ref = Column(String(120), nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)

    revision = relationship("AircraftContentPackRevision", back_populates="resources", lazy="joined")
