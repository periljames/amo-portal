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
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from amodb.database import Base
from amodb.utils.identifiers import generate_uuid7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AircraftInduction(Base):
    __tablename__ = "aircraft_inductions"
    __table_args__ = (
        UniqueConstraint("amo_id", "idempotency_key", name="uq_aircraft_induction_idempotency"),
        UniqueConstraint("amo_id", "aircraft_serial_number", name="uq_aircraft_induction_aircraft"),
        CheckConstraint("status IN ('COMPLETED')", name="ck_aircraft_induction_status"),
        Index("ix_aircraft_induction_scope", "amo_id", "registration", "status"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    registration = Column(String(20), nullable=False, index=True)
    type_revision_id = Column(
        String(36),
        ForeignKey("aircraft_type_template_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    programme_revision_id = Column(
        String(36),
        ForeignKey("tenant_maintenance_programme_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    idempotency_key = Column(String(120), nullable=False)
    request_hash = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, default="COMPLETED")
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    configuration_snapshot = relationship(
        "AircraftConfigurationSnapshot",
        back_populates="induction",
        uselist=False,
        lazy="joined",
    )
    applicability_snapshot = relationship(
        "AircraftApplicabilitySnapshot",
        back_populates="induction",
        uselist=False,
        lazy="joined",
    )
    lineage = relationship(
        "AircraftEngineeringLineage",
        back_populates="induction",
        uselist=False,
        lazy="joined",
    )


class AircraftConfigurationSnapshot(Base):
    __tablename__ = "aircraft_configuration_snapshots"
    __table_args__ = (
        UniqueConstraint("induction_id", name="uq_aircraft_configuration_snapshot_induction"),
        Index("ix_aircraft_configuration_snapshot_aircraft", "amo_id", "aircraft_serial_number"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    induction_id = Column(
        String(36),
        ForeignKey("aircraft_inductions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    type_revision_id = Column(
        String(36),
        ForeignKey("aircraft_type_template_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    snapshot_hash = Column(String(64), nullable=False)
    snapshot_json = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    induction = relationship("AircraftInduction", back_populates="configuration_snapshot", lazy="joined")
    items = relationship(
        "AircraftConfigurationSnapshotItem",
        back_populates="snapshot",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class AircraftConfigurationSnapshotItem(Base):
    __tablename__ = "aircraft_configuration_snapshot_items"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "position_code", name="uq_aircraft_configuration_snapshot_position"),
        Index("ix_aircraft_configuration_snapshot_item_definition", "definition_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    snapshot_id = Column(
        String(36),
        ForeignKey("aircraft_configuration_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position_code = Column(String(50), nullable=False)
    definition_id = Column(
        String(36),
        ForeignKey("aircraft_type_component_definitions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    aircraft_component_id = Column(
        Integer,
        ForeignKey("aircraft_components.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    part_number = Column(String(50), nullable=True)
    serial_number = Column(String(50), nullable=True)
    baseline_hours = Column(Numeric(14, 2), nullable=True)
    baseline_cycles = Column(Integer, nullable=True)
    source_json = Column(JSON, nullable=False, default=dict)

    snapshot = relationship("AircraftConfigurationSnapshot", back_populates="items", lazy="joined")


class AircraftApplicabilitySnapshot(Base):
    __tablename__ = "aircraft_applicability_snapshots"
    __table_args__ = (
        UniqueConstraint("induction_id", name="uq_aircraft_applicability_snapshot_induction"),
        Index("ix_aircraft_applicability_snapshot_aircraft", "amo_id", "aircraft_serial_number"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    induction_id = Column(
        String(36),
        ForeignKey("aircraft_inductions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    programme_revision_id = Column(
        String(36),
        ForeignKey("tenant_maintenance_programme_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    snapshot_hash = Column(String(64), nullable=False)
    context_json = Column(JSON, nullable=False)
    task_results_json = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    induction = relationship("AircraftInduction", back_populates="applicability_snapshot", lazy="joined")


class AircraftEngineeringLineage(Base):
    __tablename__ = "aircraft_engineering_lineage"
    __table_args__ = (
        UniqueConstraint("induction_id", name="uq_aircraft_engineering_lineage_induction"),
        UniqueConstraint("aircraft_serial_number", name="uq_aircraft_engineering_lineage_aircraft"),
        Index("ix_aircraft_engineering_lineage_scope", "amo_id", "type_revision_id", "programme_revision_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    induction_id = Column(
        String(36),
        ForeignKey("aircraft_inductions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_serial_number = Column(
        String(50),
        ForeignKey("aircraft.serial_number", ondelete="RESTRICT"),
        nullable=False,
    )
    type_revision_id = Column(
        String(36),
        ForeignKey("aircraft_type_template_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    programme_revision_id = Column(
        String(36),
        ForeignKey("tenant_maintenance_programme_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    configuration_snapshot_id = Column(
        String(36),
        ForeignKey("aircraft_configuration_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    applicability_snapshot_id = Column(
        String(36),
        ForeignKey("aircraft_applicability_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    type_content_hash = Column(String(64), nullable=False)
    programme_content_hash = Column(String(64), nullable=False)
    lineage_hash = Column(String(64), nullable=False)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    induction = relationship("AircraftInduction", back_populates="lineage", lazy="joined")


class AircraftComponentUtilisationRole(Base):
    __tablename__ = "aircraft_component_utilisation_roles"
    __table_args__ = (
        UniqueConstraint("aircraft_component_id", name="uq_aircraft_component_utilisation_role_component"),
        CheckConstraint(
            "role IN ('ENGINE','PROPELLER','APU','OTHER')",
            name="ck_aircraft_component_utilisation_role",
        ),
        CheckConstraint(
            "assignment_source IN ('TYPE_DEFINITION','MANUAL_APPROVED')",
            name="ck_aircraft_component_utilisation_role_source",
        ),
        Index("ix_aircraft_component_utilisation_role_scope", "amo_id", "role"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    aircraft_component_id = Column(
        Integer,
        ForeignKey("aircraft_components.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = Column(String(16), nullable=False)
    assignment_source = Column(String(24), nullable=False)
    source_definition_id = Column(
        String(36),
        ForeignKey("aircraft_type_component_definitions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source_reference = Column(String(255), nullable=False)
    assigned_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
