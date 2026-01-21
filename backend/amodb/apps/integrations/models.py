from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)

from amodb.database import Base
from amodb.user_id import generate_user_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IntegrationConfigStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class IntegrationOutboundStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"


class IntegrationConfig(Base):
    __tablename__ = "integration_configs"
    __table_args__ = (
        UniqueConstraint(
            "amo_id",
            "integration_key",
            name="uq_integration_configs_amo_key",
        ),
        Index(
            "ix_integration_configs_amo_key",
            "amo_id",
            "integration_key",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    integration_key = Column(String(64), nullable=False, index=True)
    display_name = Column(String(128), nullable=False)
    status = Column(
        SAEnum(IntegrationConfigStatus, name="integration_config_status", native_enum=False),
        nullable=False,
        default=IntegrationConfigStatus.ACTIVE,
        index=True,
    )
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    base_url = Column(String(255), nullable=True)
    signing_secret = Column(String(255), nullable=True)
    allowed_ips = Column(Text, nullable=True)
    credentials_json = Column(JSON, nullable=True)
    metadata_json = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    created_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<IntegrationConfig id={self.id} key={self.integration_key}>"


class IntegrationOutboundEvent(Base):
    __tablename__ = "integration_outbound_events"
    __table_args__ = (
        UniqueConstraint(
            "amo_id",
            "idempotency_key",
            name="uq_integration_outbound_amo_idempotency",
        ),
        Index("ix_integration_outbound_amo_status", "amo_id", "status"),
        Index("ix_integration_outbound_next_attempt_at", "next_attempt_at"),
        Index("ix_integration_outbound_created_at", "created_at"),
        Index("ix_integration_outbound_amo_integration", "amo_id", "integration_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    integration_id = Column(
        String(36),
        ForeignKey("integration_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type = Column(String(128), nullable=False, index=True)
    payload_json = Column(JSON, nullable=False)
    status = Column(
        SAEnum(IntegrationOutboundStatus, name="integration_outbound_status", native_enum=False),
        nullable=False,
        default=IntegrationOutboundStatus.PENDING,
        index=True,
    )
    attempt_count = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    idempotency_key = Column(String(128), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    created_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<IntegrationOutboundEvent id={self.id} type={self.event_type} status={self.status}>"


class IntegrationInboundEvent(Base):
    __tablename__ = "integration_inbound_events"
    __table_args__ = (
        UniqueConstraint(
            "amo_id",
            "integration_id",
            "idempotency_key",
            name="uq_integration_inbound_amo_integration_idempotency",
        ),
        Index(
            "ix_integration_inbound_amo_integration_received",
            "amo_id",
            "integration_id",
            "received_at",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    integration_id = Column(
        String(36),
        ForeignKey("integration_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type = Column(String(128), nullable=False, index=True)
    payload_json = Column(JSON, nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    idempotency_key = Column(String(128), nullable=False, index=True)
    signature_valid = Column(Boolean, nullable=False, default=False, index=True)
    source_ip = Column(String(64), nullable=True)
    payload_hash = Column(String(64), nullable=False, index=True)
    error = Column(Text, nullable=True)
    created_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<IntegrationInboundEvent id={self.id} type={self.event_type} valid={self.signature_valid}>"
