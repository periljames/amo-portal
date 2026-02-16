from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Integer,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)

from amodb.database import Base
from amodb.utils.identifiers import generate_uuid7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PromptStatus(str, enum.Enum):
    OPEN = "OPEN"
    ACTIONED = "ACTIONED"
    CANCELLED = "CANCELLED"


class PresenceKind(str, enum.Enum):
    ONLINE = "online"
    AWAY = "away"
    OFFLINE = "offline"


class ChatThread(Base):
    __tablename__ = "chat_threads"

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ChatThreadMember(Base):
    __tablename__ = "chat_thread_members"
    __table_args__ = (
        UniqueConstraint("thread_id", "user_id", name="uq_chat_thread_members_thread_user"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    thread_id = Column(String(36), ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(32), nullable=True)
    joined_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        UniqueConstraint("sender_id", "client_msg_id", name="uq_chat_messages_sender_client_msg"),
        Index("ix_chat_messages_amo_thread_created_at", "amo_id", "thread_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    thread_id = Column(String(36), ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    body_bin = Column(LargeBinary, nullable=False)
    body_mime = Column(String(64), nullable=False, default="text/plain")
    client_msg_id = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    edited_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class MessageReceipt(Base):
    __tablename__ = "message_receipts"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_message_receipts_message_user"),
        Index("ix_message_receipts_message_user", "message_id", "user_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    message_id = Column(String(36), ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)


class Prompt(Base):
    __tablename__ = "prompts"

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(64), nullable=False)
    subject_ref = Column(String(255), nullable=False)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    status = Column(SAEnum(PromptStatus, name="prompt_status_enum", native_enum=False), nullable=False, default=PromptStatus.OPEN)


class PromptDelivery(Base):
    __tablename__ = "prompt_deliveries"
    __table_args__ = (
        UniqueConstraint("prompt_id", "user_id", name="uq_prompt_deliveries_prompt_user"),
        Index("ix_prompt_deliveries_prompt_user", "prompt_id", "user_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    prompt_id = Column(String(36), ForeignKey("prompts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    actioned_at = Column(DateTime(timezone=True), nullable=True)
    action_bin = Column(LargeBinary, nullable=True)
    action_mime = Column(String(64), nullable=True)


class PresenceState(Base):
    __tablename__ = "presence_state"
    __table_args__ = (
        UniqueConstraint("amo_id", "user_id", name="uq_presence_state_amo_user"),
        Index("ix_presence_state_amo_user", "amo_id", "user_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    state = Column(SAEnum(PresenceKind, name="presence_kind_enum", native_enum=False), nullable=False, default=PresenceKind.ONLINE)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    session_id = Column(String(64), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class RealtimeOutbox(Base):
    __tablename__ = "realtime_outbox"
    __table_args__ = (
        Index("ix_realtime_outbox_pending", "published_at", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(64), nullable=False, index=True)
    topic = Column(String(255), nullable=False)
    payload_bin = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    published_at = Column(DateTime(timezone=True), nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True)


class RealtimeConnectToken(Base):
    __tablename__ = "realtime_connect_tokens"
    __table_args__ = (
        Index("ix_realtime_connect_tokens_user_exp", "user_id", "expires_at"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid7)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(128), nullable=False, unique=True)
    session_id = Column(String(64), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
