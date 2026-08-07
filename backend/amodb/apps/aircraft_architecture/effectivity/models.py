from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
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


class EffectivityRuleSet(Base):
    __tablename__ = "aircraft_effectivity_rule_sets"
    __table_args__ = (
        UniqueConstraint("code", name="uq_aircraft_effectivity_rule_set_code"),
        Index("ix_aircraft_effectivity_rule_set_target", "target_kind", "status"),
        CheckConstraint(
            "status IN ('ACTIVE','INACTIVE')",
            name="ck_aircraft_effectivity_rule_set_status",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    code = Column(String(80), nullable=False)
    name = Column(String(200), nullable=False)
    target_kind = Column(String(40), nullable=False)
    target_reference = Column(String(160), nullable=False)
    aircraft_type_template_id = Column(
        String(36),
        ForeignKey("aircraft_type_templates.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    description = Column(Text, nullable=True)
    status = Column(String(16), nullable=False, default="ACTIVE")
    created_by_user_id = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    versions = relationship(
        "EffectivityRuleVersion",
        back_populates="rule_set",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
        order_by="EffectivityRuleVersion.created_at.desc()",
    )


class EffectivityRuleVersion(Base):
    __tablename__ = "aircraft_effectivity_rule_versions"
    __table_args__ = (
        UniqueConstraint(
            "rule_set_id",
            "version_code",
            name="uq_aircraft_effectivity_rule_version",
        ),
        Index(
            "ix_aircraft_effectivity_rule_version_status",
            "rule_set_id",
            "status",
        ),
        CheckConstraint(
            "status IN ('DRAFT','PUBLISHED','SUPERSEDED','WITHDRAWN')",
            name="ck_aircraft_effectivity_rule_version_status",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    rule_set_id = Column(
        String(36),
        ForeignKey("aircraft_effectivity_rule_sets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_code = Column(String(40), nullable=False)
    status = Column(String(16), nullable=False, default="DRAFT")
    effective_date = Column(Date, nullable=True)
    expression_json = Column(JSON, nullable=False, default=dict)
    content_hash = Column(String(64), nullable=True)
    source_reference = Column(String(255), nullable=False)
    source_revision = Column(String(80), nullable=False)
    source_checksum_sha256 = Column(String(64), nullable=True)
    change_summary = Column(Text, nullable=True)
    supersedes_version_id = Column(
        String(36),
        ForeignKey("aircraft_effectivity_rule_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_by_user_id = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    published_by_user_id = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    published_at = Column(DateTime(timezone=True), nullable=True)

    rule_set = relationship(
        "EffectivityRuleSet", back_populates="versions", lazy="joined"
    )
