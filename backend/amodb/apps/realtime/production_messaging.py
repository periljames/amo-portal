from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import messaging as legacy
from . import models, notification_preferences, schemas, secure_messaging as core


def send_message(
    db: Session,
    *,
    user: account_models.User,
    thread_id: str,
    body: str,
    client_msg_id: str,
    reply_to_message_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    amo_id = legacy.effective_amo_id(user)
    thread, _ = core._thread_for_user(
        db,
        amo_id=amo_id,
        thread_id=thread_id,
        user_id=str(user.id),
        for_update=True,
    )
    clean_body = body.strip()
    if not clean_body:
        raise HTTPException(status_code=422, detail="Message body is required")
    if len(clean_body) > legacy.MAX_MESSAGE_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"Message exceeds {legacy.MAX_MESSAGE_CHARS} characters",
        )
    clean_client_id = client_msg_id.strip()[:64]
    if not clean_client_id:
        raise HTTPException(status_code=422, detail="client_msg_id is required")

    existing = (
        db.query(models.ChatMessage)
        .filter(
            models.ChatMessage.sender_id == str(user.id),
            models.ChatMessage.client_msg_id == clean_client_id,
        )
        .first()
    )
    if existing:
        if existing.thread_id != thread_id:
            raise HTTPException(
                status_code=409,
                detail="client_msg_id is already used in another conversation",
            )
        return legacy.message_payload(existing)

    if reply_to_message_id:
        reply = (
            db.query(models.ChatMessage)
            .filter(
                models.ChatMessage.id == reply_to_message_id,
                models.ChatMessage.thread_id == thread_id,
                models.ChatMessage.amo_id == amo_id,
            )
            .first()
        )
        if reply is None:
            raise HTTPException(
                status_code=422,
                detail="Reply target is not part of this conversation",
            )

    clean_metadata, mentioned_user_ids = core._validated_metadata(
        db,
        thread_id=thread_id,
        sender_id=str(user.id),
        metadata=metadata,
    )
    memberships = (
        db.query(models.ChatThreadMember)
        .filter(
            models.ChatThreadMember.thread_id == thread_id,
            models.ChatThreadMember.left_at.is_(None),
        )
        .all()
    )
    if thread.kind == "DIRECT" and len(memberships) < 2:
        raise HTTPException(
            status_code=409,
            detail="The direct-message recipient is no longer active",
        )

    now = legacy.utcnow()
    row = models.ChatMessage(
        amo_id=amo_id,
        thread_id=thread_id,
        sender_id=str(user.id),
        body_bin=clean_body.encode("utf-8"),
        body_mime="text/plain",
        message_type="TEXT",
        reply_to_message_id=reply_to_message_id,
        metadata_json=clean_metadata,
        client_msg_id=clean_client_id,
        created_at=now,
    )
    db.add(row)
    db.flush()
    thread.last_message_at = now
    thread.updated_at = now

    title = thread.title or "New direct message"
    event_payload = legacy.message_payload(row)
    event_payload["thread"] = {
        "id": thread.id,
        "title": thread.title,
        "kind": thread.kind,
    }
    for member in memberships:
        if member.user_id != str(user.id):
            db.add(
                models.MessageReceipt(
                    amo_id=amo_id,
                    message_id=row.id,
                    user_id=member.user_id,
                )
            )
            if notification_preferences.allows_chat_notification(
                db,
                amo_id=amo_id,
                member=member,
                mentioned_user_ids=mentioned_user_ids,
                now=now,
            ):
                legacy._create_notification(
                    db,
                    amo_id=amo_id,
                    user_id=member.user_id,
                    title=title,
                    body=clean_body,
                    thread_id=thread_id,
                    message_id=row.id,
                )
        legacy._queue_user_event(
            db,
            amo_id=amo_id,
            user_id=member.user_id,
            kind=schemas.RealtimeKind.CHAT_MESSAGE,
            payload=event_payload,
        )
    db.commit()
    return legacy.message_payload(row)


def process_inbound_envelope(
    db: Session,
    envelope: schemas.RealtimeEnvelope,
) -> dict[str, Any]:
    user = legacy._active_user(
        db,
        amo_id=envelope.amoId,
        user_id=envelope.userId,
    )
    payload = envelope.payload
    if envelope.kind == schemas.RealtimeKind.CHAT_SEND:
        return send_message(
            db,
            user=user,
            thread_id=str(payload.get("threadId") or ""),
            body=str(payload.get("body") or ""),
            client_msg_id=str(payload.get("clientMsgId") or envelope.id),
            reply_to_message_id=(
                str(payload.get("replyToMessageId") or "") or None
            ),
            metadata=(
                payload.get("metadata")
                if isinstance(payload.get("metadata"), dict)
                else None
            ),
        )
    if envelope.kind == schemas.RealtimeKind.CHAT_EDIT:
        return core.edit_message(
            db,
            user=user,
            message_id=str(payload.get("messageId") or ""),
            body=str(payload.get("body") or ""),
        )
    if envelope.kind == schemas.RealtimeKind.CHAT_DELETE:
        return core.delete_message(
            db,
            user=user,
            message_id=str(payload.get("messageId") or ""),
        )
    if envelope.kind in {
        schemas.RealtimeKind.ACK_DELIVERED,
        schemas.RealtimeKind.ACK_READ,
    }:
        return core.acknowledge_message(
            db,
            user=user,
            message_id=str(payload.get("messageId") or ""),
            read=envelope.kind == schemas.RealtimeKind.ACK_READ,
        )
    raise HTTPException(
        status_code=422,
        detail="Unsupported realtime messaging envelope",
    )


# Explicitly compose the already-hardened membership operations with the
# production notification policy above.
directory = core.directory
open_direct_thread = core.open_direct_thread
open_department_thread = core.open_department_thread
open_user_group_thread = core.open_user_group_thread
create_group_thread = core.create_group_thread
list_threads = core.list_threads
list_messages = core.list_messages
mark_thread_read = core.mark_thread_read
update_thread_notifications = core.update_thread_notifications
edit_message = core.edit_message
delete_message = core.delete_message
acknowledge_message = core.acknowledge_message
list_notifications = core.list_notifications
unread_notification_count = core.unread_notification_count
mark_notification_read = core.mark_notification_read
mark_all_notifications_read = core.mark_all_notifications_read
get_preferences = notification_preferences.get_preferences
update_preferences = notification_preferences.update_preferences
