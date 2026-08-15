"""Governed Workforce organisation, position and placement records."""
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
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from ...database import Base
from ...user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkforceOrgUnit(Base):
    __tablename__ = "workforce_org_units"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_workforce_org_unit_code"),
        Index("ix_workforce_org_unit_parent", "amo_id", "parent_id", "is_active"),
        Index("ix_workforce_org_unit_type", "amo_id", "unit_type", "is_active"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_workforce_org_unit_not_self"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = Column(
        String(36),
        ForeignKey("workforce_org_units.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    legacy_department_id = Column(
        String(36),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    code = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    unit_type = Column(String(32), nullable=False, default="TEAM")
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    sort_order = Column(Integer, nullable=False, default=100)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    parent = relationship("WorkforceOrgUnit", remote_side=[id], lazy="joined")
    legacy_department = relationship("Department", lazy="joined")


class WorkforceJobFamily(Base):
    __tablename__ = "workforce_job_families"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_workforce_job_family_code"),
        Index("ix_workforce_job_family_active", "amo_id", "is_active", "name"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class WorkforceGrade(Base):
    __tablename__ = "workforce_grades"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_workforce_grade_code"),
        Index("ix_workforce_grade_active", "amo_id", "is_active", "rank_order"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    rank_order = Column(Integer, nullable=False, default=100)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class WorkforcePosition(Base):
    __tablename__ = "workforce_positions"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_workforce_position_code"),
        UniqueConstraint("amo_id", "role_key", name="uq_workforce_position_role_key"),
        Index("ix_workforce_position_family_grade", "amo_id", "job_family_id", "grade_id"),
        Index("ix_workforce_position_active_title", "amo_id", "is_active", "canonical_title"),
        Index(
            "ix_workforce_position_hierarchy",
            "amo_id",
            "role_source",
            "management_level",
            "is_active",
        ),
        CheckConstraint(
            "role_source IN ('TENANT', 'KCAR_2025')",
            name="ck_workforce_position_role_source",
        ),
        CheckConstraint(
            "management_level IN ('STAFF', 'SUPERVISOR', 'MANAGER', 'EXECUTIVE')",
            name="ck_workforce_position_management_level",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(64), nullable=False)
    canonical_title = Column(String(255), nullable=False)
    job_family_id = Column(
        String(36),
        ForeignKey("workforce_job_families.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    grade_id = Column(
        String(36),
        ForeignKey("workforce_grades.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    description = Column(Text, nullable=True)
    role_source = Column(String(24), nullable=False, default="TENANT")
    role_key = Column(String(64), nullable=True)
    management_level = Column(String(24), nullable=False, default="STAFF")
    is_supervisory = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    job_family = relationship("WorkforceJobFamily", lazy="joined")
    grade = relationship("WorkforceGrade", lazy="joined")


class WorkforcePersonPlacement(Base):
    __tablename__ = "workforce_person_placements"
    __table_args__ = (
        UniqueConstraint(
            "amo_id",
            "user_id",
            "placement_type",
            "org_unit_id",
            "effective_from",
            name="uq_workforce_person_placement",
        ),
        Index("ix_workforce_placement_user_effective", "amo_id", "user_id", "effective_from", "effective_to"),
        Index("ix_workforce_placement_org_effective", "amo_id", "org_unit_id", "effective_from", "effective_to"),
        Index("ix_workforce_placement_position", "amo_id", "position_id", "effective_from", "effective_to"),
        Index("ix_workforce_placement_supervisor", "amo_id", "supervisor_user_id", "effective_from", "effective_to"),
        Index("ix_workforce_placement_base", "amo_id", "base_station_id", "effective_from", "effective_to"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_workforce_placement_dates"),
        CheckConstraint("supervisor_user_id IS NULL OR supervisor_user_id <> user_id", name="ck_workforce_placement_not_self_supervised"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    org_unit_id = Column(
        String(36),
        ForeignKey("workforce_org_units.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    position_id = Column(
        String(36),
        ForeignKey("workforce_positions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    preferred_title = Column(String(255), nullable=True)
    placement_type = Column(String(24), nullable=False, default="PRIMARY", index=True)
    base_station_id = Column(
        String(36),
        ForeignKey("base_stations.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    supervisor_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    effective_from = Column(Date, nullable=False, index=True)
    effective_to = Column(Date, nullable=True, index=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    user = relationship("User", foreign_keys=[user_id], lazy="joined")
    supervisor = relationship("User", foreign_keys=[supervisor_user_id], lazy="joined")
    org_unit = relationship("WorkforceOrgUnit", lazy="joined")
    position = relationship("WorkforcePosition", lazy="joined")
    base_station = relationship("BaseStation", lazy="joined")


class WorkforceOffboardingPlan(Base):
    __tablename__ = "workforce_offboarding_plans"
    __table_args__ = (
        UniqueConstraint("amo_id", "user_id", "effective_on", name="uq_workforce_offboarding_user_date"),
        Index("ix_workforce_offboarding_due", "amo_id", "status", "effective_on"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    effective_on = Column(Date, nullable=False, index=True)
    reason = Column(Text, nullable=False)
    status = Column(String(24), nullable=False, default="SCHEDULED", index=True)
    revoke_access = Column(Boolean, nullable=False, default=True)
    end_contracts = Column(Boolean, nullable=False, default=True)
    remove_groups = Column(Boolean, nullable=False, default=True)
    requested_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
