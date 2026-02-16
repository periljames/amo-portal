from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RealtimeKind(str, Enum):
    CHAT_MESSAGE = "chat.message"
    CHAT_MESSAGE_EDITED = "chat.message.edited"
    CHAT_MESSAGE_DELETED = "chat.message.deleted"
    CHAT_THREAD_CREATED = "chat.thread.created"
    PROMPT_AUTHORIZATION = "prompt.authorization"
    PROMPT_TASK_ASSIGNED = "prompt.task_assigned"
    PRESENCE_SNAPSHOT = "presence.snapshot"
    CHAT_SEND = "chat.send"
    CHAT_EDIT = "chat.edit"
    CHAT_DELETE = "chat.delete"
    ACK_DELIVERED = "ack.delivered"
    ACK_READ = "ack.read"
    ACK_ACTIONED = "ack.actioned"
    PRESENCE_ONLINE = "presence.online"
    PRESENCE_AWAY = "presence.away"
    PRESENCE_TYPING = "presence.typing"


class RealtimeEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    v: int = Field(ge=1)
    id: str = Field(min_length=4, max_length=64)
    ts: int = Field(ge=0)
    amoId: str = Field(min_length=2, max_length=64)
    userId: str = Field(min_length=2, max_length=64)
    kind: RealtimeKind
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def _payload_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > 64:
            raise ValueError("payload has too many keys")
        return value


class RealtimeTokenResponse(BaseModel):
    token: str
    broker_ws_url: str
    client_id: str
    expires_at: datetime
    ttl_seconds: int


class ThreadCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    member_user_ids: list[str] = Field(default_factory=list)


class ThreadRead(BaseModel):
    id: str
    title: str | None = None
    created_by: str | None = None
    created_at: datetime
    member_user_ids: list[str] = Field(default_factory=list)


class ChatMessageRead(BaseModel):
    id: str
    thread_id: str
    sender_id: str | None
    body_text: str
    body_mime: str
    client_msg_id: str
    created_at: datetime
    edited_at: datetime | None = None
    deleted_at: datetime | None = None


class PromptActionRequest(BaseModel):
    action: dict[str, Any]


class RealtimeBootstrapResponse(BaseModel):
    threads: list[ThreadRead] = Field(default_factory=list)
    unread_counts: dict[str, int] = Field(default_factory=dict)
    presence: dict[str, str] = Field(default_factory=dict)
    pending_prompts: list[dict[str, Any]] = Field(default_factory=list)


class RealtimeSyncResponse(BaseModel):
    messages: list[ChatMessageRead] = Field(default_factory=list)
    prompt_deliveries: list[dict[str, Any]] = Field(default_factory=list)
    receipt_updates: list[dict[str, Any]] = Field(default_factory=list)
    cursor: str
