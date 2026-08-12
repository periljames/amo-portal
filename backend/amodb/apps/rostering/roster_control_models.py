from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint

from ...database import Base
from ...user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RosterShiftAlias(Base):
    __tablename__ = "roster_shift_aliases"
    __table_args__ = (
        UniqueConstraint("amo_id", "alias", name="uq_roster_shift_alias_amo_alias"),
        Index("ix_roster_shift_alias_amo_template", "amo_id", "shift_template_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    alias = Column(String(64), nullable=False)
    shift_template_id = Column(String(36), ForeignKey("shift_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    context_label = Column(String(128), nullable=True)
    aircraft_registration = Column(String(64), nullable=True)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class RosterControlledDocumentSettings(Base):
    __tablename__ = "roster_controlled_document_settings"
    __table_args__ = (UniqueConstraint("amo_id", name="uq_roster_controlled_settings_amo"),)

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    form_number = Column(String(64), nullable=False, default="ROSTER")
    revision_label = Column(String(64), nullable=True)
    revision_date = Column(Date, nullable=True)
    footer_note = Column(Text, nullable=True)
    prepared_by_label = Column(String(64), nullable=False, default="Prepared by")
    approved_by_label = Column(String(64), nullable=False, default="Approved by")
    page_size = Column(String(8), nullable=False, default="A3")
    updated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class RosterPublicationSnapshot(Base):
    __tablename__ = "roster_publication_snapshots"
    __table_args__ = (
        UniqueConstraint("version_id", name="uq_roster_publication_snapshot_version"),
        Index("ix_roster_publication_snapshot_amo_version", "amo_id", "version_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    version_id = Column(String(36), ForeignKey("roster_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_json = Column(JSON, nullable=False)
    snapshot_hash = Column(String(64), nullable=False, index=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class RosterCalendarSubscription(Base):
    __tablename__ = "roster_calendar_subscriptions"
    __table_args__ = (
        UniqueConstraint("amo_id", "user_id", name="uq_roster_calendar_subscription_user"),
        UniqueConstraint("token_hash", name="uq_roster_calendar_subscription_token_hash"),
        Index("ix_roster_calendar_subscription_active", "amo_id", "user_id", "revoked_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, index=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    rotated_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)


class RosterAssignmentLineage(Base):
    __tablename__ = "roster_assignment_lineages"
    __table_args__ = (
        UniqueConstraint("assignment_id", name="uq_roster_assignment_lineage_assignment"),
        Index("ix_roster_assignment_lineage_amo_key", "amo_id", "lineage_key"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    assignment_id = Column(String(36), ForeignKey("roster_assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    source_assignment_id = Column(String(36), ForeignKey("roster_assignments.id", ondelete="SET NULL"), nullable=True, index=True)
    lineage_key = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
