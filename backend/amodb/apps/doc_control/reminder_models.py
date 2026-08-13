from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from amodb.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.utcnow()


class DocumentReminderDelivery(Base):
    """Immutable idempotency/audit ledger for Document Control reminders."""

    __tablename__ = "document_reminder_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "obligation_type",
            "obligation_id",
            "recipient_user_id",
            "reminder_stage",
            name="uq_document_reminder_obligation_recipient_stage",
        ),
        Index("ix_document_reminders_tenant_created", "tenant_id", "created_at"),
        Index("ix_document_reminders_obligation", "tenant_id", "obligation_type", "obligation_id"),
        Index("ix_document_reminders_recipient", "tenant_id", "recipient_user_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    obligation_type = Column(String(48), nullable=False)
    obligation_id = Column(String(36), nullable=False)
    recipient_user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reminder_stage = Column(String(64), nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=True)
    action_url = Column(String(512), nullable=False)
    delivery_json = Column(JSONB, nullable=False, default=dict)
    error_text = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
