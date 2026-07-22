from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from fastapi import HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import messaging as legacy
from . import models, schemas

MAX_MENTIONS = 50


def _active_tenant_user_ids(db: Session, *, amo_id: str, user_ids: Iterable[str]) -> set[str]:
    values = sorted({str(value) for value in user_ids if str(value).strip()})
    if not values:
        return set()
    rows = (
        db.query(account_models.User.id)
        .filter(
            account_models.User.id.in_(values),
            account_models.User.amo_id == amo_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        )
        .all()
    )
    return {str(row[0]) for row in rows}


def _department_member_ids(db: Session, *, amo_id: str, department_id: str) -> set[str]:
    rows = (
        db.query(account_models.User.id)
        .filter(
            account_models.User.amo_id == amo_id,
            account_models.User.department_id == department_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        )
        .all()
    )
    return {str(row[0]) for row in rows}


def _managed_group_member_ids(db: Session, *, amo_id: str, group_id: str) -> tuple[set[str], str | None]:
    group = legacy._group_record(db, amo_id=amo_id, group_id=group_id)
    owner_id = str(group.get("owner_user_id") or "") or None
    member_ids = set(legacy._group_member_ids(db, amo_id=amo_id, group_id=group_id))
    if owner_id:
        member_ids.add(owner_id)
    return _active_tenant_user_ids(db, amo_id=amo_id, user_ids=member_ids), owner_id


def _reconcile_thread_memberships(
    db: Session,
    *,
    thread: models.ChatThread,
    actor_user_id: str,
) -> bool:
    """Reconcile scoped membership and remove inactive tenant users.

    Department and managed-group channels are projections of current account
    state. Explicit ad-hoc groups retain their selected members, except users
    who are inactive or no longer belong to the tenant.
    """

    rows = (
        db.query(models.ChatThreadMember)
        .filter(models.ChatThreadMember.thread_id == thread.id)
        .all()
    )
    existing = {str(row.user_id): row for row in rows}
    owner_id: str | None = None

    if thread.kind == "DEPARTMENT" and thread.department_id:
        eligible = _department_member_ids(
            db,
            amo_id=thread.amo_id,
            department_id=str(thread.department_id),
        )
    elif thread.kind == "GROUP" and thread.user_group_id:
        eligible, owner_id = _managed_group_member_ids(
            db,
            amo_id=thread.amo_id,
            group_id=str(thread.user_group_id),
        )
    else:
        eligible = _active_tenant_user_ids(
            db,
            amo_id=thread.amo_id,
            user_ids=existing.keys(),
        )

    changed = False
    now = legacy.utcnow()
    for user_id, membership in existing.items():
        if user_id not in eligible and membership.left_at is None:
            membership.left_at = now
            changed = True
        elif user_id in eligible:
            if membership.left_at is not None:
                membership.left_at = None
                membership.joined_at = now
                changed = True
            expected_role = "OWNER" if owner_id and user_id == owner_id else membership.role or "MEMBER"
            if membership.role != expected_role:
                membership.role = expected_role
                changed = True

    missing = eligible - set(existing)
    for user_id in sorted(missing):
        db.add(
            models.ChatThreadMember(
                thread_id=thread.id,
                user_id=user_id,
                role="OWNER" if owner_id and user_id == owner_id else "MEMBER",
                added_by_user_id=actor_user_id,
            )
        )
        changed = True
    if changed:
        db.flush()
    return changed


def _thread_for_user(
    db: Session,
    *,
    amo_id: str,
    thread_id: str,
    user_id: str,
    for_update: bool = False,
) -> tuple[models.ChatThread, models.ChatThreadMember]:
    query = db.query(models.ChatThread).filter(
        models.ChatThread.id == thread_id,
        models.ChatThread.amo_id == amo_id,
        models.ChatThread.is_archived.is_(False),
    )
    if for_update:
        query = query.with_for_update()
    thread = query.first()
    if thread is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    _reconcile_thread_memberships(db, thread=thread, actor_user_id=user_id)
    membership = (
        db.query(models.ChatThreadMember)
        .filter(
            models.ChatThreadMember.thread_id == thread.id,
            models.ChatThreadMember.user_id == user_id,
            models.ChatThreadMember.left_at.is_(None),
        )
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return thread, membership


def directory(db: Session, *, user: account_models.User) -> dict[str, Any]:
    amo_id = legacy.effective_amo_id(user)
    users = (
        db.query(account_models.User)
        .filter(
            account_models.User.amo_id == amo_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
            account_models.User.id != str(user.id),
        )
        .order_by(account_models.User.full_name.asc(), account_models.User.id.asc())
        .limit(2000)
        .all()
    )
    departments = []
    if user.department_id:
        departments = (
            db.query(account_models.Department)
            .filter(
                account_models.Department.id == str(user.department_id),
                account_models.Department.amo_id == amo_id,
                account_models.Department.is_active.is_(True),
            )
            .all()
        )
    group_rows = db.execute(
        text(
            """
            SELECT DISTINCT g.id, g.code, g.name, g.description, g.group_type
            FROM user_groups AS g
            LEFT JOIN user_group_members AS m ON m.group_id = g.id
            WHERE g.amo_id = :amo_id
              AND g.is_active = true
              AND (g.owner_user_id = :user_id OR m.user_id = :user_id)
            ORDER BY g.name, g.id
            LIMIT 1000
            """
        ),
        {"amo_id": amo_id, "user_id": str(user.id)},
    ).mappings().all()
    return {
        "users": [
            {
                "id": str(row.id),
                "full_name": row.full_name,
                "position_title": row.position_title,
                "department_id": row.department_id,
            }
            for row in users
        ],
        "departments": [
            {"id": str(row.id), "code": row.code, "name": row.name}
            for row in departments
        ],
        "groups": [dict(row) for row in group_rows],
    }


def open_direct_thread(db: Session, *, user: account_models.User, peer_user_id: str) -> dict[str, Any]:
    return legacy.open_direct_thread(db, user=user, peer_user_id=peer_user_id)


def open_department_thread(db: Session, *, user: account_models.User, department_id: str) -> dict[str, Any]:
    amo_id = legacy.effective_amo_id(user)
    department = (
        db.query(account_models.Department)
        .filter(
            account_models.Department.id == department_id,
            account_models.Department.amo_id == amo_id,
            account_models.Department.is_active.is_(True),
        )
        .first()
    )
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")
    if str(user.department_id or "") != str(department.id):
        raise HTTPException(status_code=403, detail="Only current department members may open this channel")

    scope_key = f"department:{department.id}"
    thread = legacy._scope_thread(db, amo_id=amo_id, scope_key=scope_key)
    if thread is None:
        thread = models.ChatThread(
            amo_id=amo_id,
            title=department.name,
            kind="DEPARTMENT",
            scope_key=scope_key,
            department_id=department.id,
            created_by=str(user.id),
            updated_at=legacy.utcnow(),
        )
        db.add(thread)
        db.flush()
    _reconcile_thread_memberships(db, thread=thread, actor_user_id=str(user.id))
    db.commit()
    return legacy.thread_payload(db, thread=thread, viewer_user_id=str(user.id))


def open_user_group_thread(db: Session, *, user: account_models.User, group_id: str) -> dict[str, Any]:
    amo_id = legacy.effective_amo_id(user)
    eligible, owner_id = _managed_group_member_ids(db, amo_id=amo_id, group_id=group_id)
    if str(user.id) not in eligible:
        raise HTTPException(status_code=403, detail="User is not a current member of this group")
    group = legacy._group_record(db, amo_id=amo_id, group_id=group_id)
    scope_key = f"group:{group_id}"
    thread = legacy._scope_thread(db, amo_id=amo_id, scope_key=scope_key)
    if thread is None:
        thread = models.ChatThread(
            amo_id=amo_id,
            title=str(group["name"]),
            kind="GROUP",
            scope_key=scope_key,
            user_group_id=group_id,
            created_by=str(user.id),
            updated_at=legacy.utcnow(),
        )
        db.add(thread)
        db.flush()
    _reconcile_thread_memberships(db, thread=thread, actor_user_id=owner_id or str(user.id))
    db.commit()
    return legacy.thread_payload(db, thread=thread, viewer_user_id=str(user.id))


def create_group_thread(
    db: Session,
    *,
    user: account_models.User,
    title: str | None,
    member_user_ids: Iterable[str],
) -> dict[str, Any]:
    return legacy.create_group_thread(
        db,
        user=user,
        title=title,
        member_user_ids=member_user_ids,
    )


def list_threads(db: Session, *, user: account_models.User, limit: int = 200) -> list[dict[str, Any]]:
    amo_id = legacy.effective_amo_id(user)
    rows = (
        db.query(models.ChatThread)
        .join(models.ChatThreadMember, models.ChatThreadMember.thread_id == models.ChatThread.id)
        .filter(
            models.ChatThread.amo_id == amo_id,
            models.ChatThread.is_archived.is_(False),
            models.ChatThreadMember.user_id == str(user.id),
        )
        .order_by(
            func.coalesce(
                models.ChatThread.last_message_at,
                models.ChatThread.updated_at,
                models.ChatThread.created_at,
            ).desc(),
            models.ChatThread.id.desc(),
        )
        .limit(max(1, min(limit, 500)))
        .all()
    )
    output: list[dict[str, Any]] = []
    changed = False
    for thread in rows:
        changed = _reconcile_thread_memberships(
            db,
            thread=thread,
            actor_user_id=str(user.id),
        ) or changed
        membership = legacy._member_row(db, thread_id=thread.id, user_id=str(user.id))
        if membership and membership.left_at is None:
            output.append(legacy.thread_payload(db, thread=thread, viewer_user_id=str(user.id)))
    if changed:
        db.commit()
    return output


def list_messages(
    db: Session,
    *,
    user: account_models.User,
    thread_id: str,
    limit: int = 100,
    before: datetime | None = None,
) -> list[dict[str, Any]]:
    amo_id = legacy.effective_amo_id(user)
    _thread_for_user(db, amo_id=amo_id, thread_id=thread_id, user_id=str(user.id))
    return legacy.list_messages(db, user=user, thread_id=thread_id, limit=limit, before=before)


def _validated_metadata(
    db: Session,
    *,
    thread_id: str,
    sender_id: str,
    metadata: dict[str, Any] | None,
) -> tuple[dict[str, Any], set[str]]:
    raw_mentions = (metadata or {}).get("mention_user_ids") or []
    if not isinstance(raw_mentions, list):
        raise HTTPException(status_code=422, detail="mention_user_ids must be a list")
    mentions = {str(value) for value in raw_mentions if str(value).strip()}
    if len(mentions) > MAX_MENTIONS:
        raise HTTPException(status_code=422, detail=f"A message may mention at most {MAX_MENTIONS} users")
    active_members = set(legacy._member_ids(db, thread_id=thread_id))
    invalid = mentions - active_members
    if invalid:
        raise HTTPException(status_code=422, detail="Mentioned users must be current conversation members")
    mentions.discard(sender_id)
    return ({"mention_user_ids": sorted(mentions)} if mentions else {}), mentions


def _notification_allowed(
    db: Session,
    *,
    amo_id: str,
    member: models.ChatThreadMember,
    mentioned_user_ids: set[str],
) -> bool:
    level = str(member.notification_level or "ALL").upper()
    if level == "NONE":
        return False
    if level == "MENTIONS" and str(member.user_id) not in mentioned_user_ids:
        return False
    if member.muted_until and member.muted_until > legacy.utcnow():
        return False
    prefs = legacy._preferences(db, amo_id=amo_id, user_id=str(member.user_id))
    return bool(prefs.in_app_enabled and prefs.chat_enabled)


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
    thread, _ = _thread_for_user(
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
        raise HTTPException(status_code=413, detail=f"Message exceeds {legacy.MAX_MESSAGE_CHARS} characters")
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
            raise HTTPException(status_code=409, detail="client_msg_id is already used in another conversation")
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
            raise HTTPException(status_code=422, detail="Reply target is not part of this conversation")

    clean_metadata, mentioned_user_ids = _validated_metadata(
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
        raise HTTPException(status_code=409, detail="The direct-message recipient is no longer active")

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
    payload = legacy.message_payload(row)
    payload["thread"] = {"id": thread.id, "title": thread.title, "kind": thread.kind}
    for member in memberships:
        if member.user_id != str(user.id):
            db.add(
                models.MessageReceipt(
                    amo_id=amo_id,
                    message_id=row.id,
                    user_id=member.user_id,
                )
            )
            if _notification_allowed(
                db,
                amo_id=amo_id,
                member=member,
                mentioned_user_ids=mentioned_user_ids,
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
            payload=payload,
        )
    db.commit()
    return legacy.message_payload(row)


def mark_thread_read(db: Session, *, user: account_models.User, thread_id: str) -> dict[str, Any]:
    amo_id = legacy.effective_amo_id(user)
    _thread_for_user(db, amo_id=amo_id, thread_id=thread_id, user_id=str(user.id))
    return legacy.mark_thread_read(db, user=user, thread_id=thread_id)


def update_thread_notifications(
    db: Session,
    *,
    user: account_models.User,
    thread_id: str,
    notification_level: str,
    muted_until: datetime | None,
) -> dict[str, Any]:
    amo_id = legacy.effective_amo_id(user)
    _thread_for_user(db, amo_id=amo_id, thread_id=thread_id, user_id=str(user.id))
    return legacy.update_thread_notifications(
        db,
        user=user,
        thread_id=thread_id,
        notification_level=notification_level,
        muted_until=muted_until,
    )


def edit_message(db: Session, *, user: account_models.User, message_id: str, body: str) -> dict[str, Any]:
    amo_id = legacy.effective_amo_id(user)
    message = db.query(models.ChatMessage).filter(
        models.ChatMessage.id == message_id,
        models.ChatMessage.amo_id == amo_id,
    ).first()
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    _thread_for_user(db, amo_id=amo_id, thread_id=message.thread_id, user_id=str(user.id))
    return legacy.edit_message(db, user=user, message_id=message_id, body=body)


def delete_message(db: Session, *, user: account_models.User, message_id: str) -> dict[str, Any]:
    amo_id = legacy.effective_amo_id(user)
    message = db.query(models.ChatMessage).filter(
        models.ChatMessage.id == message_id,
        models.ChatMessage.amo_id == amo_id,
    ).first()
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    _thread_for_user(db, amo_id=amo_id, thread_id=message.thread_id, user_id=str(user.id))
    return legacy.delete_message(db, user=user, message_id=message_id)


def acknowledge_message(
    db: Session,
    *,
    user: account_models.User,
    message_id: str,
    read: bool,
) -> dict[str, Any]:
    amo_id = legacy.effective_amo_id(user)
    message = db.query(models.ChatMessage).filter(
        models.ChatMessage.id == message_id,
        models.ChatMessage.amo_id == amo_id,
    ).first()
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    _thread_for_user(db, amo_id=amo_id, thread_id=message.thread_id, user_id=str(user.id))
    return legacy.acknowledge_message(db, user=user, message_id=message_id, read=read)


def process_inbound_envelope(db: Session, envelope: schemas.RealtimeEnvelope) -> dict[str, Any]:
    user = legacy._active_user(db, amo_id=envelope.amoId, user_id=envelope.userId)
    payload = envelope.payload
    if envelope.kind == schemas.RealtimeKind.CHAT_SEND:
        return send_message(
            db,
            user=user,
            thread_id=str(payload.get("threadId") or ""),
            body=str(payload.get("body") or ""),
            client_msg_id=str(payload.get("clientMsgId") or envelope.id),
            reply_to_message_id=str(payload.get("replyToMessageId") or "") or None,
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
        )
    if envelope.kind == schemas.RealtimeKind.CHAT_EDIT:
        return edit_message(
            db,
            user=user,
            message_id=str(payload.get("messageId") or ""),
            body=str(payload.get("body") or ""),
        )
    if envelope.kind == schemas.RealtimeKind.CHAT_DELETE:
        return delete_message(db, user=user, message_id=str(payload.get("messageId") or ""))
    if envelope.kind in {schemas.RealtimeKind.ACK_DELIVERED, schemas.RealtimeKind.ACK_READ}:
        return acknowledge_message(
            db,
            user=user,
            message_id=str(payload.get("messageId") or ""),
            read=envelope.kind == schemas.RealtimeKind.ACK_READ,
        )
    raise HTTPException(status_code=422, detail="Unsupported realtime messaging envelope")


# Notification functions remain tenant-scoped in the original service.
get_preferences = legacy.get_preferences
update_preferences = legacy.update_preferences
list_notifications = legacy.list_notifications
unread_notification_count = legacy.unread_notification_count
mark_notification_read = legacy.mark_notification_read
mark_all_notifications_read = legacy.mark_all_notifications_read
