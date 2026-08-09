from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
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


class AircraftOemSourceIntake(Base):
    """Persisted, reviewable intake of one OEM workbook/source artifact.

    The source binary itself stays in controlled document/object storage.  This
    record freezes the checksum, detected profile, source manifest and the
    normalized row set used to build a candidate content-pack revision.
    """

    __tablename__ = "aircraft_oem_source_intakes"
    __table_args__ = (
        UniqueConstraint(
            "publication_id",
            "checksum_sha256",
            name="uq_aircraft_oem_source_intake_publication_checksum",
        ),
        CheckConstraint(
            "status IN ('STAGED','VALIDATED','APPROVED','MATERIALIZED','REJECTED','FAILED')",
            name="ck_aircraft_oem_source_intake_status",
        ),
        Index(
            "ix_aircraft_oem_source_intake_status",
            "publication_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_aircraft_oem_source_intake_pack",
            "pack_id",
            "status",
            "created_at",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    publication_id = Column(
        String(36),
        ForeignKey("aircraft_oem_publications.id", ondelete="RESTRICT"),
        nullable=False,
    )
    publication_revision_id = Column(
        String(36),
        ForeignKey("aircraft_oem_publication_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    temporary_revision_id = Column(
        String(36),
        ForeignKey("aircraft_oem_temporary_revisions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    pack_id = Column(
        String(36),
        ForeignKey("aircraft_content_packs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    submitted_by_amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_filename = Column(String(255), nullable=False)
    storage_locator = Column(Text, nullable=True)
    checksum_sha256 = Column(String(64), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    detected_profile = Column(String(80), nullable=False)
    profile_confidence = Column(String(16), nullable=False)
    workbook_kind = Column(String(24), nullable=False)
    status = Column(String(20), nullable=False, default="STAGED")
    source_manifest_json = Column(JSON, nullable=False, default=dict)
    warnings_json = Column(JSON, nullable=False, default=list)
    validation_summary_json = Column(JSON, nullable=False, default=dict)
    normalization_hash = Column(String(64), nullable=True)
    created_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    materialized_revision_id = Column(
        String(36),
        ForeignKey("aircraft_content_pack_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    validated_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    materialized_at = Column(DateTime(timezone=True), nullable=True)

    rows = relationship(
        "AircraftOemSourceIntakeRow",
        back_populates="intake",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
        order_by="AircraftOemSourceIntakeRow.sheet_name, AircraftOemSourceIntakeRow.row_number",
    )


class AircraftOemSourceIntakeRow(Base):
    __tablename__ = "aircraft_oem_source_intake_rows"
    __table_args__ = (
        UniqueConstraint(
            "intake_id",
            "sheet_name",
            "row_number",
            name="uq_aircraft_oem_source_intake_row_position",
        ),
        UniqueConstraint(
            "intake_id",
            "row_hash",
            name="uq_aircraft_oem_source_intake_row_hash",
        ),
        CheckConstraint(
            "row_kind IN ('TASK','RESOURCE','UNMAPPED','IGNORED')",
            name="ck_aircraft_oem_source_intake_row_kind",
        ),
        CheckConstraint(
            "status IN ('VALID','REVIEW_REQUIRED','INVALID','IGNORED')",
            name="ck_aircraft_oem_source_intake_row_status",
        ),
        Index(
            "ix_aircraft_oem_source_intake_row_status",
            "intake_id",
            "status",
            "row_kind",
        ),
        Index(
            "ix_aircraft_oem_source_intake_row_identity",
            "intake_id",
            "identity_key",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    intake_id = Column(
        String(36),
        ForeignKey("aircraft_oem_source_intakes.id", ondelete="CASCADE"),
        nullable=False,
    )
    sheet_name = Column(String(120), nullable=False)
    row_number = Column(Integer, nullable=False)
    row_kind = Column(String(16), nullable=False)
    identity_key = Column(String(180), nullable=True)
    row_hash = Column(String(64), nullable=False)
    source_json = Column(JSON, nullable=False, default=dict)
    normalized_json = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False)
    issues_json = Column(JSON, nullable=False, default=list)
    review_json = Column(JSON, nullable=False, default=dict)
    reviewed_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    intake = relationship("AircraftOemSourceIntake", back_populates="rows", lazy="joined")
