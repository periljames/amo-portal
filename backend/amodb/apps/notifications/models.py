from __future__ import annotations

from datetime import datetime, timezone
import enum

from sqlalchemy import Column, DateTime, Enum as SAEnum, ForeignKey, Index, JSON, String, Text, UniqueConstraint

from amodb.database import Base
from amodb.utils.identifiers import generate_uuid7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EmailStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED_NO_PROVIDER = "SKIPPED_NO_PROVIDER"
    SKIPPED_BY_PREFERENCE = "SKIPPED_BY_PREFERENCE"


class EmailLog(Base):
    __tablename__ = "email_logs"
    __table_args__ = (
        Index("ix_email_logs_amo_created", "amo_id", "created_at"),
        Index("ix_email_logs_amo_status", "amo_id", "status"),
        Index("ix_email_logs_amo_template", "amo_id", "template_key"),
        Index("ix_email_logs_amo_recipient", "amo_id", "recipient"),
        Index("ix_email_logs_provider_message", "provider", "provider_message_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7, index=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)

    recipient = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=False)
    template_key = Column(String(128), nullable=False, index=True)
    status = Column(
        SAEnum(EmailStatus, name="email_status_enum", native_enum=False),
        nullable=False,
        index=True,
    )
    error = Column(Text, nullable=True)
    context_json = Column(JSON, nullable=True)
    correlation_id = Column(String(64), nullable=True, index=True)
    provider = Column(String(32), nullable=True, index=True)
    provider_message_id = Column(String(255), nullable=True, index=True)
    delivery_status = Column(String(64), nullable=True, index=True)
    last_delivery_event_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<EmailLog id={self.id} recipient={self.recipient} status={self.status}>"


class EmailDeliveryEvent(Base):
    __tablename__ = "email_delivery_events"
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_email_delivery_provider_event"),
        Index("ix_email_delivery_events_message", "provider", "provider_message_id"),
        Index("ix_email_delivery_events_log_created", "email_log_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    email_log_id = Column(
        String(36),
        ForeignKey("email_logs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    provider = Column(String(32), nullable=False, default="resend", server_default="resend")
    provider_event_id = Column(String(255), nullable=False)
    provider_message_id = Column(String(255), nullable=True)
    event_type = Column(String(128), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    payload_json = Column(JSON, nullable=True)
