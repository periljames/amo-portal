from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import msgpack
from fastapi import HTTPException
from starlette.requests import Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.utils.identifiers import generate_uuid7

from . import models, schemas

DEFAULT_TOKEN_TTL_SECONDS = int(os.getenv("REALTIME_CONNECT_TOKEN_TTL_SECONDS", "300"))
MAX_PAYLOAD_BYTES = int(os.getenv("REALTIME_PAYLOAD_MAX_BYTES", "8192"))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def effective_amo_id(user: account_models.User) -> str:
    return str(getattr(user, "effective_amo_id", None) or user.amo_id)


def _infer_public_hostname(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded_host = (request.headers.get("x-forwarded-host") or "").strip()
    if forwarded_host:
        # Can be a list in multi-proxy setups: "host1, host2"
        first = forwarded_host.split(",", 1)[0].strip()
        return first.split(":", 1)[0].strip() or None

    if request.url.hostname:
        return request.url.hostname
    host = (request.headers.get("host") or "").strip()
    if not host:
        return None
    return host.split(":", 1)[0].strip() or None


def resolve_broker_ws_url(request: Request | None) -> str:
    configured = (os.getenv("MQTT_BROKER_WS_URL") or "").strip()
    public_host = _infer_public_hostname(request)

    if configured:
        parsed = urlparse(configured)
        host = (parsed.hostname or "").lower()
        if public_host and host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
            port = f":{parsed.port}" if parsed.port else ""
            return f"{parsed.scheme}://{public_host}{port}{parsed.path or '/mqtt'}"
        return configured

    scheme = "wss"
    if request and (request.url.scheme or "").lower() == "http":
        scheme = "ws"
    host = public_host or "localhost"
    default_port = os.getenv("MQTT_BROKER_WS_PORT", "8084").strip()
    port_segment = f":{default_port}" if default_port else ""
    return f"{scheme}://{host}{port_segment}/mqtt"


def issue_connect_token(
    db: Session,
    *,
    user: account_models.User,
    request: Request | None = None,
) -> schemas.RealtimeTokenResponse:
    amo_id = effective_amo_id(user)
    ttl = max(30, DEFAULT_TOKEN_TTL_SECONDS)
    expires_at = utcnow() + timedelta(seconds=ttl)
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    session_id = generate_uuid7()
    db.add(
        models.RealtimeConnectToken(
            amo_id=amo_id,
            user_id=str(user.id),
            token_hash=token_hash,
            session_id=session_id,
            expires_at=expires_at,
        )
    )
    db.commit()
    broker_url = resolve_broker_ws_url(request)
    return schemas.RealtimeTokenResponse(
        token=raw,
        broker_ws_url=broker_url,
        client_id=f"amo-{amo_id}-user-{user.id}-{session_id[:8]}",
        amo_id=amo_id,
        expires_at=expires_at,
        ttl_seconds=ttl,
    )


def build_bootstrap(db: Session, *, user: account_models.User) -> schemas.RealtimeBootstrapResponse:
    amo_id = effective_amo_id(user)
    memberships = (
        db.query(models.ChatThreadMember, models.ChatThread)
        .join(models.ChatThread, models.ChatThread.id == models.ChatThreadMember.thread_id)
        .filter(models.ChatThread.amo_id == amo_id, models.ChatThreadMember.user_id == str(user.id))
        .all()
    )
    threads: list[schemas.ThreadRead] = []
    unread_counts: dict[str, int] = {}
    for _, thread in memberships:
        members = (
            db.query(models.ChatThreadMember.user_id)
            .filter(models.ChatThreadMember.thread_id == thread.id)
            .all()
        )
        threads.append(
            schemas.ThreadRead(
                id=thread.id,
                title=thread.title,
                created_by=thread.created_by,
                created_at=thread.created_at,
                member_user_ids=[row[0] for row in members],
            )
        )
        unread = (
            db.query(func.count(models.ChatMessage.id))
            .filter(models.ChatMessage.thread_id == thread.id)
            .scalar()
            or 0
        )
        read = (
            db.query(func.count(models.MessageReceipt.id))
            .join(models.ChatMessage, models.ChatMessage.id == models.MessageReceipt.message_id)
            .filter(models.ChatMessage.thread_id == thread.id, models.MessageReceipt.user_id == str(user.id), models.MessageReceipt.read_at.isnot(None))
            .scalar()
            or 0
        )
        unread_counts[thread.id] = max(0, int(unread - read))

    presence_rows = (
        db.query(models.PresenceState)
        .filter(models.PresenceState.amo_id == amo_id)
        .all()
    )
    pending_prompts = (
        db.query(models.PromptDelivery, models.Prompt)
        .join(models.Prompt, models.Prompt.id == models.PromptDelivery.prompt_id)
        .filter(models.PromptDelivery.amo_id == amo_id, models.PromptDelivery.user_id == str(user.id), models.PromptDelivery.actioned_at.is_(None))
        .all()
    )
    return schemas.RealtimeBootstrapResponse(
        threads=threads,
        unread_counts=unread_counts,
        presence={row.user_id: row.state.value for row in presence_rows},
        pending_prompts=[
            {
                "promptId": prompt.id,
                "kind": prompt.kind,
                "status": prompt.status.value,
                "subjectRef": prompt.subject_ref,
                "deliveredAt": delivery.delivered_at.isoformat() if delivery.delivered_at else None,
                "readAt": delivery.read_at.isoformat() if delivery.read_at else None,
            }
            for delivery, prompt in pending_prompts
        ],
    )


def update_presence_state(
    db: Session,
    *,
    user: account_models.User,
    payload: schemas.PresenceStateUpdateRequest,
) -> schemas.PresenceStateRead:
    amo_id = effective_amo_id(user)
    now = utcnow()

    row = (
        db.query(models.PresenceState)
        .filter(models.PresenceState.amo_id == amo_id, models.PresenceState.user_id == str(user.id))
        .first()
    )
    if not row:
        row = models.PresenceState(
            amo_id=amo_id,
            user_id=str(user.id),
            state=models.PresenceKind.ONLINE,
            last_seen_at=now,
        )
        db.add(row)

    row.state = models.PresenceKind.ONLINE if payload.state == "online" else models.PresenceKind.AWAY
    row.last_seen_at = now
    row.updated_at = now
    db.commit()
    db.refresh(row)

    return schemas.PresenceStateRead(
        user_id=row.user_id,
        amo_id=row.amo_id,
        state=row.state.value,
        last_seen_at=row.last_seen_at,
        updated_at=row.updated_at,
        reason=payload.reason,
    )


def create_thread(db: Session, *, user: account_models.User, payload: schemas.ThreadCreateRequest) -> schemas.ThreadRead:
    amo_id = effective_amo_id(user)
    thread = models.ChatThread(amo_id=amo_id, title=payload.title, created_by=str(user.id))
    db.add(thread)
    db.flush()
    member_ids = {str(user.id), *[str(member) for member in payload.member_user_ids]}
    for member_id in member_ids:
        db.add(models.ChatThreadMember(thread_id=thread.id, user_id=member_id))
    db.commit()
    return schemas.ThreadRead(
        id=thread.id,
        title=thread.title,
        created_by=thread.created_by,
        created_at=thread.created_at,
        member_user_ids=sorted(member_ids),
    )


def list_threads(db: Session, *, user: account_models.User) -> list[schemas.ThreadRead]:
    amo_id = effective_amo_id(user)
    rows = (
        db.query(models.ChatThread)
        .join(models.ChatThreadMember, models.ChatThreadMember.thread_id == models.ChatThread.id)
        .filter(models.ChatThread.amo_id == amo_id, models.ChatThreadMember.user_id == str(user.id))
        .order_by(models.ChatThread.created_at.desc())
        .all()
    )
    result: list[schemas.ThreadRead] = []
    for thread in rows:
        members = db.query(models.ChatThreadMember.user_id).filter(models.ChatThreadMember.thread_id == thread.id).all()
        result.append(
            schemas.ThreadRead(
                id=thread.id,
                title=thread.title,
                created_by=thread.created_by,
                created_at=thread.created_at,
                member_user_ids=[m[0] for m in members],
            )
        )
    return result


def _ensure_thread_member(db: Session, *, thread_id: str, user_id: str) -> None:
    exists = (
        db.query(models.ChatThreadMember)
        .filter(models.ChatThreadMember.thread_id == thread_id, models.ChatThreadMember.user_id == user_id)
        .first()
    )
    if not exists:
        raise HTTPException(status_code=403, detail="User is not a member of this thread")


def list_thread_messages(db: Session, *, user: account_models.User, thread_id: str, limit: int = 200) -> list[schemas.ChatMessageRead]:
    _ensure_thread_member(db, thread_id=thread_id, user_id=str(user.id))
    rows = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.thread_id == thread_id)
        .order_by(models.ChatMessage.created_at.desc())
        .limit(min(limit, 500))
        .all()
    )
    return [
        schemas.ChatMessageRead(
            id=row.id,
            thread_id=row.thread_id,
            sender_id=row.sender_id,
            body_text=row.body_bin.decode("utf-8", errors="ignore"),
            body_mime=row.body_mime,
            client_msg_id=row.client_msg_id,
            created_at=row.created_at,
            edited_at=row.edited_at,
            deleted_at=row.deleted_at,
        )
        for row in rows
    ]


def perform_prompt_action(db: Session, *, user: account_models.User, prompt_id: str, action: dict[str, Any]) -> dict[str, Any]:
    amo_id = effective_amo_id(user)
    delivery = (
        db.query(models.PromptDelivery)
        .filter(models.PromptDelivery.prompt_id == prompt_id, models.PromptDelivery.user_id == str(user.id), models.PromptDelivery.amo_id == amo_id)
        .first()
    )
    if not delivery:
        raise HTTPException(status_code=404, detail="Prompt delivery not found")
    delivery.delivered_at = delivery.delivered_at or utcnow()
    delivery.read_at = delivery.read_at or utcnow()
    delivery.actioned_at = utcnow()
    delivery.action_mime = "application/msgpack"
    delivery.action_bin = msgpack.packb(action, use_bin_type=True)
    prompt = db.query(models.Prompt).filter(models.Prompt.id == prompt_id, models.Prompt.amo_id == amo_id).first()
    if prompt:
        prompt.status = models.PromptStatus.ACTIONED
    db.commit()
    return {"status": "ok", "promptId": prompt_id, "actionedAt": delivery.actioned_at.isoformat()}


def store_chat_send(db: Session, *, envelope: schemas.RealtimeEnvelope) -> models.ChatMessage:
    payload = envelope.payload
    thread_id = str(payload.get("threadId") or "")
    body = str(payload.get("body") or "")
    client_msg_id = str(payload.get("clientMsgId") or envelope.id)
    if not thread_id or not body:
        raise HTTPException(status_code=422, detail="threadId and body required")

    _ensure_thread_member(db, thread_id=thread_id, user_id=envelope.userId)

    existing = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.sender_id == envelope.userId, models.ChatMessage.client_msg_id == client_msg_id)
        .first()
    )
    if existing:
        return existing

    row = models.ChatMessage(
        amo_id=envelope.amoId,
        thread_id=thread_id,
        sender_id=envelope.userId,
        body_bin=body.encode("utf-8"),
        body_mime="text/plain",
        client_msg_id=client_msg_id,
    )
    db.add(row)
    db.flush()
    return row


def apply_ack(db: Session, *, envelope: schemas.RealtimeEnvelope) -> dict[str, Any]:
    now = utcnow()
    kind = envelope.kind
    payload = envelope.payload

    if "promptId" in payload:
        delivery = (
            db.query(models.PromptDelivery)
            .filter(models.PromptDelivery.prompt_id == payload["promptId"], models.PromptDelivery.user_id == envelope.userId, models.PromptDelivery.amo_id == envelope.amoId)
            .first()
        )
        if not delivery:
            raise HTTPException(status_code=404, detail="Prompt delivery not found")
        if kind == schemas.RealtimeKind.ACK_DELIVERED:
            delivery.delivered_at = delivery.delivered_at or now
        elif kind == schemas.RealtimeKind.ACK_READ:
            delivery.delivered_at = delivery.delivered_at or now
            delivery.read_at = delivery.read_at or now
        elif kind == schemas.RealtimeKind.ACK_ACTIONED:
            delivery.delivered_at = delivery.delivered_at or now
            delivery.read_at = delivery.read_at or now
            delivery.actioned_at = delivery.actioned_at or now
            action_payload = payload.get("action") or {}
            packed = msgpack.packb(action_payload, use_bin_type=True)
            if len(packed) > MAX_PAYLOAD_BYTES:
                raise HTTPException(status_code=413, detail="Action payload too large")
            delivery.action_bin = packed
            delivery.action_mime = "application/msgpack"
        db.flush()
        return {"entity": "prompt", "promptId": payload["promptId"]}

    message_id = payload.get("messageId")
    if not message_id:
        raise HTTPException(status_code=422, detail="messageId or promptId required")
    receipt = (
        db.query(models.MessageReceipt)
        .filter(models.MessageReceipt.message_id == message_id, models.MessageReceipt.user_id == envelope.userId, models.MessageReceipt.amo_id == envelope.amoId)
        .first()
    )
    if not receipt:
        receipt = models.MessageReceipt(amo_id=envelope.amoId, message_id=str(message_id), user_id=envelope.userId)
        db.add(receipt)
    if kind == schemas.RealtimeKind.ACK_DELIVERED:
        receipt.delivered_at = receipt.delivered_at or now
    elif kind == schemas.RealtimeKind.ACK_READ:
        receipt.delivered_at = receipt.delivered_at or now
        receipt.read_at = receipt.read_at or now
    db.flush()
    return {"entity": "message", "messageId": str(message_id)}


def enqueue_outbox(db: Session, *, amo_id: str, kind: str, topic: str, payload: dict[str, Any]) -> models.RealtimeOutbox:
    packed = msgpack.packb(payload, use_bin_type=True)
    if len(packed) > MAX_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Payload exceeds realtime limit")
    row = models.RealtimeOutbox(amo_id=amo_id, kind=kind, topic=topic, payload_bin=packed)
    db.add(row)
    return row


def sync_since(db: Session, *, user: account_models.User, since_ts_ms: int) -> schemas.RealtimeSyncResponse:
    amo_id = effective_amo_id(user)
    since_dt = datetime.fromtimestamp(since_ts_ms / 1000.0, tz=timezone.utc)
    messages = (
        db.query(models.ChatMessage)
        .join(models.ChatThreadMember, models.ChatThreadMember.thread_id == models.ChatMessage.thread_id)
        .filter(models.ChatMessage.amo_id == amo_id, models.ChatThreadMember.user_id == str(user.id), models.ChatMessage.created_at >= since_dt)
        .order_by(models.ChatMessage.created_at.asc())
        .limit(1000)
        .all()
    )
    prompt_deliveries = (
        db.query(models.PromptDelivery)
        .filter(models.PromptDelivery.amo_id == amo_id, models.PromptDelivery.user_id == str(user.id), models.PromptDelivery.delivered_at >= since_dt)
        .all()
    )
    receipt_updates = (
        db.query(models.MessageReceipt)
        .filter(models.MessageReceipt.amo_id == amo_id, models.MessageReceipt.user_id == str(user.id), models.MessageReceipt.delivered_at >= since_dt)
        .all()
    )

    latest_ms = max([since_ts_ms] + [int(row.created_at.timestamp() * 1000) for row in messages])
    return schemas.RealtimeSyncResponse(
        messages=[
            schemas.ChatMessageRead(
                id=row.id,
                thread_id=row.thread_id,
                sender_id=row.sender_id,
                body_text=row.body_bin.decode("utf-8", errors="ignore"),
                body_mime=row.body_mime,
                client_msg_id=row.client_msg_id,
                created_at=row.created_at,
                edited_at=row.edited_at,
                deleted_at=row.deleted_at,
            )
            for row in messages
        ],
        prompt_deliveries=[
            {
                "promptId": row.prompt_id,
                "deliveredAt": row.delivered_at.isoformat() if row.delivered_at else None,
                "readAt": row.read_at.isoformat() if row.read_at else None,
                "actionedAt": row.actioned_at.isoformat() if row.actioned_at else None,
            }
            for row in prompt_deliveries
        ],
        receipt_updates=[
            {
                "messageId": row.message_id,
                "deliveredAt": row.delivered_at.isoformat() if row.delivered_at else None,
                "readAt": row.read_at.isoformat() if row.read_at else None,
            }
            for row in receipt_updates
        ],
        cursor=str(latest_ms),
    )


def validate_topic_access(*, amo_id: str, user_id: str, topic: str, subscribe: bool) -> bool:
    user_prefix = f"amo/{amo_id}/user/{user_id}/"
    if topic.startswith(user_prefix + "inbox"):
        return subscribe
    if topic.startswith(user_prefix + "outbox") or topic.startswith(user_prefix + "ack"):
        return not subscribe
    return topic.startswith(f"amo/{amo_id}/chat/")
