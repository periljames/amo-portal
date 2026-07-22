from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RealtimeKind(str, Enum):
    CHAT_MESSAGE = "chat.message"
    CHAT_MESSAGE_EDITED = "chat.message.edited"
    CHAT_MESSAGE_DELETED = "chat.message.deleted"
    CHAT_THREAD_CREATED = "chat.thread.created"
    CHAT_THREAD_UPDATED = "chat.thread.updated"
    NOTIFICATION_CREATED = "notification.created"
    NOTIFICATION_READ = "notification.read"
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


def _wire_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _wire_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_wire_value(item) for item in value]
    return value


class RealtimeEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    v: int = Field(ge=1)
    id: str = Field(min_length=4, max_length=64)
    ts: int = Field(ge=0)
    amoId: str = Field(min_length=2, max_length=64)
    userId: str = Field(min_length=2, max_length=64)
    kind: RealtimeKind
    payload: dict[str, Any] = Field(default_factory=dict)
    # Present only on client-to-gateway outbox messages. Server fan-out strips it.
    authToken: str | None = Field(default=None, min_length=20, max_length=256, repr=False)

    @field_validator("payload")
    @classmethod
    def _payload_size_and_wire_values(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > 64:
            raise ValueError("payload has too many keys")
        return _wire_value(value)


class RealtimeTokenResponse(BaseModel):
    token: str
    broker_ws_url: str
    client_id: str
    amo_id: str
    expires_at: datetime
    ttl_seconds: int


class ThreadCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    member_user_ids: list[str] = Field(default_factory=list, max_length=500)


class ThreadRead(BaseModel):
    id: str
    title: str | None = None
    kind: str = "GROUP"
    scope_key: str | None = None
    department_id: str | None = None
    user_group_id: str | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    last_message_at: datetime | None = None
    last_message_preview: str = ""
    member_user_ids: list[str] = Field(default_factory=list)
    members: list[dict[str, Any]] = Field(default_factory=list)
    unread_count: int = 0
    notification_level: str = "ALL"
    muted_until: datetime | None = None


class ChatMessageCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=8000)
    client_msg_id: str = Field(min_length=4, max_length=64)
    reply_to_message_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatMessageUpdateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


class ThreadNotificationUpdateRequest(BaseModel):
    notification_level: str = Field(default="ALL", pattern="^(ALL|MENTIONS|NONE)$")
    muted_until: datetime | None = None


class ChatMessageRead(BaseModel):
    id: str
    thread_id: str
    sender_id: str | None
    body_text: str
    body_mime: str
    message_type: str = "TEXT"
    reply_to_message_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
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
    notification_unread_count: int = 0


class RealtimeSyncResponse(BaseModel):
    messages: list[ChatMessageRead] = Field(default_factory=list)
    prompt_deliveries: list[dict[str, Any]] = Field(default_factory=list)
    receipt_updates: list[dict[str, Any]] = Field(default_factory=list)
    cursor: str


class PresenceStateUpdateRequest(BaseModel):
    state: str = Field(pattern="^(online|away)$")
    reason: str | None = Field(default=None, max_length=64)


class PresenceStateRead(BaseModel):
    user_id: str
    amo_id: str
    state: str
    last_seen_at: datetime
    updated_at: datetime
    reason: str | None = None
