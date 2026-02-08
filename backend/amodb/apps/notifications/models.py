from __future__ import annotations

from datetime import datetime, timezone
import enum

from sqlalchemy import Column, DateTime, Enum as SAEnum, ForeignKey, Index, JSON, String, Text

from amodb.database import Base
from amodb.utils.identifiers import generate_uuid7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EmailStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED_NO_PROVIDER = "SKIPPED_NO_PROVIDER"


class EmailLog(Base):
    __tablename__ = "email_logs"
    __table_args__ = (
        Index("ix_email_logs_amo_created", "amo_id", "created_at"),
        Index("ix_email_logs_amo_status", "amo_id", "status"),
        Index("ix_email_logs_amo_template", "amo_id", "template_key"),
        Index("ix_email_logs_amo_recipient", "amo_id", "recipient"),
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

    def __repr__(self) -> str:
        return f"<EmailLog id={self.id} recipient={self.recipient} status={self.status}>"
