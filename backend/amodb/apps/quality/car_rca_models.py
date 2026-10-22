"""Tenant-bound, revisioned CAR investigation and corrective-action records.

These records extend quality_cars; they do not create another authoritative CAR.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Column, String, Integer, Date, DateTime, Text, ForeignKey,
    UniqueConstraint, Index, CheckConstraint, JSON, func
)
from sqlalchemy.dialects.postgresql import UUID

from amodb.database import Base


class QualityCarRcaDocument(Base):
    __tablename__ = "quality_car_rca_documents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    car_id = Column(UUID(as_uuid=True), ForeignKey("quality_cars.id", ondelete="CASCADE"), nullable=False)
    revision = Column(Integer, nullable=False, default=0)
    draft = Column(JSON, nullable=False, default=dict)
    submitted_revision = Column(Integer, nullable=True)
    submitted_snapshot = Column(JSON, nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        UniqueConstraint("amo_id", "car_id", name="uq_quality_car_rca_document"),
        CheckConstraint("revision >= 0", name="ck_quality_car_rca_revision_nonnegative"),
        Index("ix_quality_car_rca_doc_lookup", "amo_id", "car_id"),
    )


class QualityCarRcaRevision(Base):
    __tablename__ = "quality_car_rca_revisions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    car_id = Column(UUID(as_uuid=True), ForeignKey("quality_cars.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("quality_car_rca_documents.id", ondelete="RESTRICT"), nullable=False)
    revision = Column(Integer, nullable=False)
    event_type = Column(String(32), nullable=False)
    snapshot = Column(JSON, nullable=False)
    actor_kind = Column(String(16), nullable=False)
    actor_ref = Column(String(255), nullable=True)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        UniqueConstraint("document_id", "revision", name="uq_quality_car_rca_revision_sequence"),
        Index("ix_quality_car_rca_revision_history", "amo_id", "car_id", "created_at"),
    )


class QualityCarRcaAction(Base):
    __tablename__ = "quality_car_rca_actions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    car_id = Column(UUID(as_uuid=True), ForeignKey("quality_cars.id", ondelete="CASCADE"), nullable=False)
    sequence_no = Column(Integer, nullable=False)
    kind = Column(String(20), nullable=False)
    description = Column(Text, nullable=False)
    cause_node_ids = Column(JSON, nullable=False, default=list)
    evidence_references = Column(JSON, nullable=False, default=list)
    owner_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    external_owner_name = Column(String(255), nullable=True)
    target_date = Column(Date, nullable=True)
    priority = Column(String(12), nullable=False, default="MEDIUM")
    state = Column(String(24), nullable=False, default="PROPOSED")
    completion_note = Column(Text, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    quality_review_note = Column(Text, nullable=True)
    reviewed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        UniqueConstraint("amo_id", "car_id", "sequence_no", name="uq_quality_car_rca_action_number"),
        CheckConstraint("kind IN ('CORRECTIVE','PREVENTIVE','CONTAINMENT')", name="ck_quality_car_rca_action_kind"),
        CheckConstraint("state IN ('PROPOSED','ACCEPTED','IN_PROGRESS','SUBMITTED','VERIFIED','REJECTED','CANCELLED')", name="ck_quality_car_rca_action_state"),
        CheckConstraint("priority IN ('LOW','MEDIUM','HIGH','CRITICAL')", name="ck_quality_car_rca_action_priority"),
        Index("ix_quality_car_rca_action_due", "amo_id", "state", "target_date"),
    )


class QualityCarRcaMutation(Base):
    __tablename__ = "quality_car_rca_mutations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    car_id = Column(UUID(as_uuid=True), ForeignKey("quality_cars.id", ondelete="CASCADE"), nullable=False)
    mutation_key = Column(String(100), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    result_revision = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        UniqueConstraint("amo_id", "car_id", "mutation_key", name="uq_quality_car_rca_mutation_key"),
        Index("ix_quality_car_rca_mutations", "amo_id", "car_id", "created_at"),
    )

class QualityCarRcaActionEvent(Base):
    """Immutable history of proposed, approved, implemented and verified actions."""
    __tablename__ = "quality_car_rca_action_events"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    car_id = Column(UUID(as_uuid=True), ForeignKey("quality_cars.id", ondelete="CASCADE"), nullable=False)
    action_id = Column(UUID(as_uuid=True), ForeignKey("quality_car_rca_actions.id", ondelete="RESTRICT"), nullable=False)
    previous_state = Column(String(24), nullable=True)
    next_state = Column(String(24), nullable=False)
    snapshot = Column(JSON, nullable=False)
    actor_kind = Column(String(16), nullable=False)
    actor_ref = Column(String(255), nullable=True)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        Index("ix_quality_car_rca_action_history", "amo_id", "car_id", "action_id", "created_at"),
    )
