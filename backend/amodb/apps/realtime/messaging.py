from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

import msgpack
from fastapi import HTTPException
from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.utils.identifiers import generate_uuid7

from . import models, schemas

MAX_MESSAGE_CHARS = 8000
THREAD_KINDS = {"DIRECT", "DEPARTMENT", "GROUP"}
NOTIFICATION_LEVELS = {"ALL", "MENTIONS", "NONE"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def effective_amo_id(user: account_models.User) -> str:
    raw = getattr(user, "effective_amo_id", None) or getattr(user, "amo_id", None)
    if raw in (None, "", "None", "none", "null", "NULL"):
        raise HTTPException(status_code=403, detail="Messaging requires an active AMO tenant context")
    return str(raw)


def _is_tenant_admin(user: account_models.User) -> bool:
    return bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_amo_admin", False)
        or getattr(user, "role", None) == account_models.AccountRole.AMO_ADMIN
    )


def _active_user(db: Session, *, amo_id: str, user_id: str) -> account_models.User:
    row = (
        db.query(account_models.User)
        .filter(
            account_models.User.id == str(user_id),
            account_models.User.amo_id == amo_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found in this AMO")
    return row


def _member_row(db: Session, *, thread_id: str, user_id: str) -> models.ChatThreadMember | None:
    return (
        db.query(models.ChatThreadMember)
        .filter(
            models.ChatThreadMember.thread_id == thread_id,
            models.ChatThreadMember.user_id == str(user_id),
            models.ChatThreadMember.left_at.is_(None),
        )
        .first()
    )


def _thread_for_user(
    db: Session,
    *,
    amo_id: str,
    thread_id: str,
    user_id: str,
    for_update: bool = False,
) -> tuple[models.ChatThread, models.ChatThreadMember]:
    query = (
        db.query(models.ChatThread, models.ChatThreadMember)
        .join(models.ChatThreadMember, models.ChatThreadMember.thread_id == models.ChatThread.id)
        .filter(
            models.ChatThread.id == thread_id,
            models.ChatThread.amo_id == amo_id,
            models.ChatThread.is_archived.is_(False),
            models.ChatThreadMember.user_id == str(user_id),
            models.ChatThreadMember.left_at.is_(None),
        )
    )
    if for_update:
        query = query.with_for_update()
    row = query.first()
    if not row:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return row[0], row[1]


def _ensure_members(
    db: Session,
    *,
    thread: models.ChatThread,
    member_ids: Iterable[str],
    added_by_user_id: str,
    owner_user_id: str | None = None,
) -> list[str]:
    normalized = sorted({str(value) for value in member_ids if str(value).strip()})
    valid: list[str] = []
    for user_id in normalized:
        _active_user(db, amo_id=thread.amo_id, user_id=user_id)
        valid.append(user_id)
        member = (
            db.query(models.ChatThreadMember)
            .filter(
                models.ChatThreadMember.thread_id == thread.id,
                models.ChatThreadMember.user_id == user_id,
            )
            .first()
        )
        if member:
            member.left_at = None
            member.added_by_user_id = member.added_by_user_id or added_by_user_id
            if owner_user_id and user_id == owner_user_id:
                member.role = "OWNER"
        else:
            db.add(
                models.ChatThreadMember(
                    thread_id=thread.id,
                    user_id=user_id,
                    role="OWNER" if owner_user_id and user_id == owner_user_id else "MEMBER",
                    added_by_user_id=added_by_user_id,
                )
            )
    return valid


def _scope_thread(db: Session, *, amo_id: str, scope_key: str) -> models.ChatThread | None:
    return (
        db.query(models.ChatThread)
        .filter(
            models.ChatThread.amo_id == amo_id,
            models.ChatThread.scope_key == scope_key,
            models.ChatThread.is_archived.is_(False),
        )
        .first()
    )


def open_direct_thread(db: Session, *, user: account_models.User, peer_user_id: str) -> dict[str, Any]:
    amo_id = effective_amo_id(user)
    peer = _active_user(db, amo_id=amo_id, user_id=peer_user_id)
    if str(peer.id) == str(user.id):
        raise HTTPException(status_code=422, detail="A direct conversation requires another user")
    pair = sorted((str(user.id), str(peer.id)))
    scope_key = f"direct:{pair[0]}:{pair[1]}"
    thread = _scope_thread(db, amo_id=amo_id, scope_key=scope_key)
    if not thread:
        thread = models.ChatThread(
            amo_id=amo_id,
            title=None,
            kind="DIRECT",
            scope_key=scope_key,
            created_by=str(user.id),
            updated_at=utcnow(),
        )
        db.add(thread)
        db.flush()
    _ensure_members(
        db,
        thread=thread,
        member_ids=pair,
        added_by_user_id=str(user.id),
        owner_user_id=str(user.id),
    )
    db.commit()
    return thread_payload(db, thread=thread, viewer_user_id=str(user.id))


def open_department_thread(db: Session, *, user: account_models.User, department_id: str) -> dict[str, Any]:
    amo_id = effective_amo_id(user)
    department = (
        db.query(account_models.Department)
        .filter(
            account_models.Department.id == department_id,
            account_models.Department.amo_id == amo_id,
            account_models.Department.is_active.is_(True),
        )
        .first()
    )
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")
    if str(user.department_id or "") != department_id and not _is_tenant_admin(user):
        raise HTTPException(status_code=403, detail="Only department members or AMO administrators may open this channel")

    scope_key = f"department:{department_id}"
    thread = _scope_thread(db, amo_id=amo_id, scope_key=scope_key)
    if not thread:
        thread = models.ChatThread(
            amo_id=amo_id,
            title=department.name,
            kind="DEPARTMENT",
            scope_key=scope_key,
            department_id=department.id,
            created_by=str(user.id),
            updated_at=utcnow(),
        )
        db.add(thread)
        db.flush()
    users = (
        db.query(account_models.User.id)
        .filter(
            account_models.User.amo_id == amo_id,
            account_models.User.department_id == department.id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        )
        .all()
    )
    _ensure_members(
        db,
        thread=thread,
        member_ids=[str(row[0]) for row in users],
        added_by_user_id=str(user.id),
    )
    db.commit()
    return thread_payload(db, thread=thread, viewer_user_id=str(user.id))


def _group_record(db: Session, *, amo_id: str, group_id: str) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT id, amo_id, owner_user_id, code, name, description, group_type, is_active
            FROM user_groups
            WHERE id = :group_id AND amo_id = :amo_id AND is_active = true
            """
        ),
        {"group_id": group_id, "amo_id": amo_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="User group not found")
    return dict(row)


def _group_member_ids(db: Session, *, amo_id: str, group_id: str) -> list[str]:
    rows = db.execute(
        text(
            """
            SELECT DISTINCT m.user_id
            FROM user_group_members AS m
            JOIN users AS u ON u.id = m.user_id
            WHERE m.group_id = :group_id
              AND u.amo_id = :amo_id
              AND u.is_active = true
              AND COALESCE(u.is_system_account, false) = false
            """
        ),
        {"group_id": group_id, "amo_id": amo_id},
    ).all()
    return [str(row[0]) for row in rows]


def open_user_group_thread(db: Session, *, user: account_models.User, group_id: str) -> dict[str, Any]:
    amo_id = effective_amo_id(user)
    group = _group_record(db, amo_id=amo_id, group_id=group_id)
    member_ids = _group_member_ids(db, amo_id=amo_id, group_id=group_id)
    allowed = str(user.id) in member_ids or str(group.get("owner_user_id") or "") == str(user.id) or _is_tenant_admin(user)
    if not allowed:
        raise HTTPException(status_code=403, detail="User is not a member of this group")
    if str(user.id) not in member_ids:
        member_ids.append(str(user.id))

    scope_key = f"group:{group_id}"
    thread = _scope_thread(db, amo_id=amo_id, scope_key=scope_key)
    if not thread:
        thread = models.ChatThread(
            amo_id=amo_id,
            title=str(group["name"]),
            kind="GROUP",
            scope_key=scope_key,
            user_group_id=group_id,
            created_by=str(user.id),
            updated_at=utcnow(),
        )
        db.add(thread)
        db.flush()
    _ensure_members(
        db,
        thread=thread,
        member_ids=member_ids,
        added_by_user_id=str(user.id),
        owner_user_id=str(group.get("owner_user_id") or "") or None,
    )
    db.commit()
    return thread_payload(db, thread=thread, viewer_user_id=str(user.id))


def create_group_thread(
    db: Session,
    *,
    user: account_models.User,
    title: str | None,
    member_user_ids: Iterable[str],
) -> dict[str, Any]:
    amo_id = effective_amo_id(user)
    clean_title = (title or "").strip()
    if not clean_title:
        raise HTTPException(status_code=422, detail="A group name is required")
    member_ids = {str(user.id), *[str(value) for value in member_user_ids]}
    if len(member_ids) < 2:
        raise HTTPException(status_code=422, detail="A group conversation requires at least two users")
    thread = models.ChatThread(
        amo_id=amo_id,
        title=clean_title[:255],
        kind="GROUP",
        scope_key=None,
        created_by=str(user.id),
        updated_at=utcnow(),
    )
    db.add(thread)
    db.flush()
    _ensure_members(
        db,
        thread=thread,
        member_ids=member_ids,
        added_by_user_id=str(user.id),
        owner_user_id=str(user.id),
    )
    db.commit()
    return thread_payload(db, thread=thread, viewer_user_id=str(user.id))


def directory(db: Session, *, user: account_models.User) -> dict[str, Any]:
    amo_id = effective_amo_id(user)
    users = (
        db.query(account_models.User)
        .filter(
            account_models.User.amo_id == amo_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
            account_models.User.id != str(user.id),
        )
        .order_by(account_models.User.full_name.asc())
        .limit(2000)
        .all()
    )
    departments = (
        db.query(account_models.Department)
        .filter(
            account_models.Department.amo_id == amo_id,
            account_models.Department.is_active.is_(True),
        )
        .order_by(account_models.Department.sort_order.asc(), account_models.Department.name.asc())
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
              AND (:is_admin OR g.owner_user_id = :user_id OR m.user_id = :user_id)
            ORDER BY g.name
            LIMIT 1000
            """
        ),
        {"amo_id": amo_id, "user_id": str(user.id), "is_admin": _is_tenant_admin(user)},
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
            if _is_tenant_admin(user) or str(user.department_id or "") == str(row.id)
        ],
        "groups": [dict(row) for row in group_rows],
    }


def _member_ids(db: Session, *, thread_id: str) -> list[str]:
    rows = (
        db.query(models.ChatThreadMember.user_id)
        .filter(
            models.ChatThreadMember.thread_id == thread_id,
            models.ChatThreadMember.left_at.is_(None),
        )
        .all()
    )
    return [str(row[0]) for row in rows]


def _user_labels(db: Session, user_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    values = sorted({str(value) for value in user_ids})
    if not values:
        return {}
    rows = db.query(account_models.User).filter(account_models.User.id.in_(values)).all()
    return {
        str(row.id): {
            "id": str(row.id),
            "full_name": row.full_name,
            "position_title": row.position_title,
            "department_id": row.department_id,
            "is_active": bool(row.is_active),
        }
        for row in rows
    }


def thread_payload(db: Session, *, thread: models.ChatThread, viewer_user_id: str) -> dict[str, Any]:
    member_ids = _member_ids(db, thread_id=thread.id)
    labels = _user_labels(db, member_ids)
    last_message = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.thread_id == thread.id)
        .order_by(models.ChatMessage.created_at.desc(), models.ChatMessage.id.desc())
        .first()
    )
    unread = (
        db.query(func.count(models.MessageReceipt.id))
        .join(models.ChatMessage, models.ChatMessage.id == models.MessageReceipt.message_id)
        .filter(
            models.ChatMessage.thread_id == thread.id,
            models.MessageReceipt.user_id == viewer_user_id,
            models.MessageReceipt.read_at.is_(None),
        )
        .scalar()
        or 0
    )
    membership = _member_row(db, thread_id=thread.id, user_id=viewer_user_id)
    title = thread.title
    if thread.kind == "DIRECT":
        peer = next((labels[value] for value in member_ids if value != viewer_user_id and value in labels), None)
        title = (peer or {}).get("full_name") or "Direct conversation"
    preview = ""
    if last_message and not last_message.deleted_at:
        preview = last_message.body_bin.decode("utf-8", errors="replace")[:160]
    return {
        "id": thread.id,
        "title": title,
        "kind": thread.kind,
        "scope_key": thread.scope_key,
        "department_id": thread.department_id,
        "user_group_id": thread.user_group_id,
        "created_by": thread.created_by,
        "created_at": thread.created_at,
        "updated_at": thread.updated_at or thread.created_at,
        "last_message_at": thread.last_message_at,
        "last_message_preview": preview,
        "member_user_ids": member_ids,
        "members": [labels[value] for value in member_ids if value in labels],
        "unread_count": int(unread),
        "notification_level": membership.notification_level if membership else "ALL",
        "muted_until": membership.muted_until if membership else None,
    }


def list_threads(db: Session, *, user: account_models.User, limit: int = 200) -> list[dict[str, Any]]:
    amo_id = effective_amo_id(user)
    rows = (
        db.query(models.ChatThread)
        .join(models.ChatThreadMember, models.ChatThreadMember.thread_id == models.ChatThread.id)
        .filter(
            models.ChatThread.amo_id == amo_id,
            models.ChatThread.is_archived.is_(False),
            models.ChatThreadMember.user_id == str(user.id),
            models.ChatThreadMember.left_at.is_(None),
        )
        .order_by(
            func.coalesce(models.ChatThread.last_message_at, models.ChatThread.updated_at, models.ChatThread.created_at).desc(),
            models.ChatThread.id.desc(),
        )
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return [thread_payload(db, thread=row, viewer_user_id=str(user.id)) for row in rows]


def message_payload(row: models.ChatMessage) -> dict[str, Any]:
    return {
        "id": row.id,
        "thread_id": row.thread_id,
        "sender_id": row.sender_id,
        "body_text": "" if row.deleted_at else row.body_bin.decode("utf-8", errors="replace"),
        "body_mime": row.body_mime,
        "message_type": row.message_type,
        "reply_to_message_id": row.reply_to_message_id,
        "metadata": row.metadata_json or {},
        "client_msg_id": row.client_msg_id,
        "created_at": row.created_at,
        "edited_at": row.edited_at,
        "deleted_at": row.deleted_at,
    }


def list_messages(
    db: Session,
    *,
    user: account_models.User,
    thread_id: str,
    limit: int = 100,
    before: datetime | None = None,
) -> list[dict[str, Any]]:
    amo_id = effective_amo_id(user)
    _thread_for_user(db, amo_id=amo_id, thread_id=thread_id, user_id=str(user.id))
    query = db.query(models.ChatMessage).filter(
        models.ChatMessage.amo_id == amo_id,
        models.ChatMessage.thread_id == thread_id,
    )
    if before:
        query = query.filter(models.ChatMessage.created_at < before)
    rows = (
        query.order_by(models.ChatMessage.created_at.desc(), models.ChatMessage.id.desc())
        .limit(max(1, min(limit, 250)))
        .all()
    )
    now = utcnow()
    message_ids = [row.id for row in rows]
    if message_ids:
        db.query(models.MessageReceipt).filter(
            models.MessageReceipt.amo_id == amo_id,
            models.MessageReceipt.user_id == str(user.id),
            models.MessageReceipt.message_id.in_(message_ids),
            models.MessageReceipt.delivered_at.is_(None),
        ).update({models.MessageReceipt.delivered_at: now}, synchronize_session=False)
        db.commit()
    return [message_payload(row) for row in reversed(rows)]


def _preferences(db: Session, *, amo_id: str, user_id: str) -> models.NotificationPreference:
    row = (
        db.query(models.NotificationPreference)
        .filter(
            models.NotificationPreference.amo_id == amo_id,
            models.NotificationPreference.user_id == user_id,
        )
        .first()
    )
    if not row:
        row = models.NotificationPreference(amo_id=amo_id, user_id=user_id)
        db.add(row)
        db.flush()
    return row


def preference_payload(row: models.NotificationPreference) -> dict[str, Any]:
    return {
        "in_app_enabled": bool(row.in_app_enabled),
        "desktop_enabled": bool(row.desktop_enabled),
        "sound_enabled": bool(row.sound_enabled),
        "email_enabled": bool(row.email_enabled),
        "chat_enabled": bool(row.chat_enabled),
        "quiet_hours_start": row.quiet_hours_start,
        "quiet_hours_end": row.quiet_hours_end,
        "updated_at": row.updated_at,
    }


def get_preferences(db: Session, *, user: account_models.User) -> dict[str, Any]:
    amo_id = effective_amo_id(user)
    row = _preferences(db, amo_id=amo_id, user_id=str(user.id))
    db.commit()
    return preference_payload(row)


def update_preferences(db: Session, *, user: account_models.User, payload: dict[str, Any]) -> dict[str, Any]:
    amo_id = effective_amo_id(user)
    row = _preferences(db, amo_id=amo_id, user_id=str(user.id))
    for key in ("in_app_enabled", "desktop_enabled", "sound_enabled", "email_enabled", "chat_enabled"):
        if key in payload:
            setattr(row, key, bool(payload[key]))
    for key in ("quiet_hours_start", "quiet_hours_end"):
        if key in payload:
            value = str(payload.get(key) or "").strip() or None
            if value and (len(value) != 5 or value[2] != ":"):
                raise HTTPException(status_code=422, detail=f"{key} must use HH:MM")
            setattr(row, key, value)
    row.updated_at = utcnow()
    db.commit()
    return preference_payload(row)


def _notification_allowed(
    db: Session,
    *,
    amo_id: str,
    member: models.ChatThreadMember,
) -> bool:
    if member.notification_level == "NONE":
        return False
    if member.muted_until and member.muted_until > utcnow():
        return False
    prefs = _preferences(db, amo_id=amo_id, user_id=member.user_id)
    return bool(prefs.in_app_enabled and prefs.chat_enabled)


def _create_notification(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    title: str,
    body: str,
    thread_id: str,
    message_id: str,
) -> models.PortalNotification | None:
    dedupe_key = f"chat:{message_id}:{user_id}"
    existing = (
        db.query(models.PortalNotification)
        .filter(
            models.PortalNotification.amo_id == amo_id,
            models.PortalNotification.user_id == user_id,
            models.PortalNotification.dedupe_key == dedupe_key,
        )
        .first()
    )
    if existing:
        return existing
    row = models.PortalNotification(
        amo_id=amo_id,
        user_id=user_id,
        kind="CHAT_MESSAGE",
        title=title[:255],
        body=body[:1000],
        entity_type="chat_thread",
        entity_id=thread_id,
        action_url=f"/messages?thread={thread_id}",
        dedupe_key=dedupe_key,
        metadata_json={"message_id": message_id, "thread_id": thread_id},
    )
    db.add(row)
    return row


def _queue_user_event(
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    kind: schemas.RealtimeKind,
    payload: dict[str, Any],
) -> models.RealtimeOutbox:
    envelope = schemas.RealtimeEnvelope(
        v=1,
        id=generate_uuid7(),
        ts=int(utcnow().timestamp() * 1000),
        amoId=amo_id,
        userId=user_id,
        kind=kind,
        payload=payload,
    )
    row = models.RealtimeOutbox(
        amo_id=amo_id,
        kind=kind.value,
        topic=f"amo/{amo_id}/user/{user_id}/inbox",
        payload_bin=msgpack.packb(envelope.model_dump(mode="python"), use_bin_type=True),
        metadata_json={"user_id": user_id},
    )
    db.add(row)
    return row


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
    amo_id = effective_amo_id(user)
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
    if len(clean_body) > MAX_MESSAGE_CHARS:
        raise HTTPException(status_code=413, detail=f"Message exceeds {MAX_MESSAGE_CHARS} characters")
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
        return message_payload(existing)

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
        if not reply:
            raise HTTPException(status_code=422, detail="Reply target is not part of this conversation")

    now = utcnow()
    row = models.ChatMessage(
        amo_id=amo_id,
        thread_id=thread_id,
        sender_id=str(user.id),
        body_bin=clean_body.encode("utf-8"),
        body_mime="text/plain",
        message_type="TEXT",
        reply_to_message_id=reply_to_message_id,
        metadata_json=metadata or {},
        client_msg_id=clean_client_id,
        created_at=now,
    )
    db.add(row)
    db.flush()
    thread.last_message_at = now
    thread.updated_at = now

    memberships = (
        db.query(models.ChatThreadMember)
        .filter(
            models.ChatThreadMember.thread_id == thread_id,
            models.ChatThreadMember.left_at.is_(None),
        )
        .all()
    )
    title = thread.title or "New direct message"
    payload = message_payload(row)
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
            if _notification_allowed(db, amo_id=amo_id, member=member):
                _create_notification(
                    db,
                    amo_id=amo_id,
                    user_id=member.user_id,
                    title=title,
                    body=clean_body,
                    thread_id=thread_id,
                    message_id=row.id,
                )
        _queue_user_event(
            db,
            amo_id=amo_id,
            user_id=member.user_id,
            kind=schemas.RealtimeKind.CHAT_MESSAGE,
            payload=payload,
        )
    db.commit()
    return message_payload(row)


def mark_thread_read(db: Session, *, user: account_models.User, thread_id: str) -> dict[str, Any]:
    amo_id = effective_amo_id(user)
    _, member = _thread_for_user(db, amo_id=amo_id, thread_id=thread_id, user_id=str(user.id))
    now = utcnow()
    message_ids = db.query(models.ChatMessage.id).filter(
        models.ChatMessage.amo_id == amo_id,
        models.ChatMessage.thread_id == thread_id,
    )
    updated = db.query(models.MessageReceipt).filter(
        models.MessageReceipt.amo_id == amo_id,
        models.MessageReceipt.user_id == str(user.id),
        models.MessageReceipt.message_id.in_(message_ids),
        models.MessageReceipt.read_at.is_(None),
    ).update(
        {models.MessageReceipt.delivered_at: now, models.MessageReceipt.read_at: now},
        synchronize_session=False,
    )
    db.query(models.PortalNotification).filter(
        models.PortalNotification.amo_id == amo_id,
        models.PortalNotification.user_id == str(user.id),
        models.PortalNotification.entity_type == "chat_thread",
        models.PortalNotification.entity_id == thread_id,
        models.PortalNotification.read_at.is_(None),
    ).update({models.PortalNotification.read_at: now}, synchronize_session=False)
    member.last_read_at = now
    db.commit()
    return {"thread_id": thread_id, "read_at": now, "updated_receipts": int(updated)}


def update_thread_notifications(
    db: Session,
    *,
    user: account_models.User,
    thread_id: str,
    notification_level: str,
    muted_until: datetime | None,
) -> dict[str, Any]:
    amo_id = effective_amo_id(user)
    _, member = _thread_for_user(db, amo_id=amo_id, thread_id=thread_id, user_id=str(user.id))
    level = notification_level.strip().upper()
    if level not in NOTIFICATION_LEVELS:
        raise HTTPException(status_code=422, detail="notification_level must be ALL, MENTIONS or NONE")
    member.notification_level = level
    member.muted_until = muted_until
    db.commit()
    return {"thread_id": thread_id, "notification_level": level, "muted_until": muted_until}


def edit_message(db: Session, *, user: account_models.User, message_id: str, body: str) -> dict[str, Any]:
    amo_id = effective_amo_id(user)
    row = db.query(models.ChatMessage).filter(models.ChatMessage.id == message_id, models.ChatMessage.amo_id == amo_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Message not found")
    _thread_for_user(db, amo_id=amo_id, thread_id=row.thread_id, user_id=str(user.id))
    if str(row.sender_id or "") != str(user.id) and not _is_tenant_admin(user):
        raise HTTPException(status_code=403, detail="Only the sender or an AMO administrator may edit this message")
    clean = body.strip()
    if not clean:
        raise HTTPException(status_code=422, detail="Message body is required")
    if len(clean) > MAX_MESSAGE_CHARS:
        raise HTTPException(status_code=413, detail=f"Message exceeds {MAX_MESSAGE_CHARS} characters")
    row.body_bin = clean.encode("utf-8")
    row.edited_at = utcnow()
    payload = message_payload(row)
    for member_id in _member_ids(db, thread_id=row.thread_id):
        _queue_user_event(db, amo_id=amo_id, user_id=member_id, kind=schemas.RealtimeKind.CHAT_MESSAGE_EDITED, payload=payload)
    db.commit()
    return payload


def delete_message(db: Session, *, user: account_models.User, message_id: str) -> dict[str, Any]:
    amo_id = effective_amo_id(user)
    row = db.query(models.ChatMessage).filter(models.ChatMessage.id == message_id, models.ChatMessage.amo_id == amo_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Message not found")
    _thread_for_user(db, amo_id=amo_id, thread_id=row.thread_id, user_id=str(user.id))
    if str(row.sender_id or "") != str(user.id) and not _is_tenant_admin(user):
        raise HTTPException(status_code=403, detail="Only the sender or an AMO administrator may delete this message")
    row.deleted_at = row.deleted_at or utcnow()
    row.body_bin = b""
    row.message_type = "DELETED"
    payload = message_payload(row)
    for member_id in _member_ids(db, thread_id=row.thread_id):
        _queue_user_event(db, amo_id=amo_id, user_id=member_id, kind=schemas.RealtimeKind.CHAT_MESSAGE_DELETED, payload=payload)
    db.commit()
    return payload


def notification_payload(row: models.PortalNotification) -> dict[str, Any]:
    return {
        "id": row.id,
        "kind": row.kind,
        "title": row.title,
        "body": row.body,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "action_url": row.action_url,
        "metadata": row.metadata_json or {},
        "created_at": row.created_at,
        "read_at": row.read_at,
        "archived_at": row.archived_at,
    }


def list_notifications(
    db: Session,
    *,
    user: account_models.User,
    unread_only: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    amo_id = effective_amo_id(user)
    query = db.query(models.PortalNotification).filter(
        models.PortalNotification.amo_id == amo_id,
        models.PortalNotification.user_id == str(user.id),
        models.PortalNotification.archived_at.is_(None),
    )
    if unread_only:
        query = query.filter(models.PortalNotification.read_at.is_(None))
    total = query.count()
    rows = (
        query.order_by(models.PortalNotification.created_at.desc(), models.PortalNotification.id.desc())
        .offset(max(0, offset))
        .limit(max(1, min(limit, 250)))
        .all()
    )
    return {"items": [notification_payload(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def unread_notification_count(db: Session, *, user: account_models.User) -> dict[str, int]:
    amo_id = effective_amo_id(user)
    count = (
        db.query(func.count(models.PortalNotification.id))
        .filter(
            models.PortalNotification.amo_id == amo_id,
            models.PortalNotification.user_id == str(user.id),
            models.PortalNotification.read_at.is_(None),
            models.PortalNotification.archived_at.is_(None),
        )
        .scalar()
        or 0
    )
    chat_count = (
        db.query(func.count(models.MessageReceipt.id))
        .filter(
            models.MessageReceipt.amo_id == amo_id,
            models.MessageReceipt.user_id == str(user.id),
            models.MessageReceipt.read_at.is_(None),
        )
        .scalar()
        or 0
    )
    return {"notifications": int(count), "messages": int(chat_count), "total": int(count) + int(chat_count)}


def mark_notification_read(db: Session, *, user: account_models.User, notification_id: str) -> dict[str, Any]:
    amo_id = effective_amo_id(user)
    row = (
        db.query(models.PortalNotification)
        .filter(
            models.PortalNotification.id == notification_id,
            models.PortalNotification.amo_id == amo_id,
            models.PortalNotification.user_id == str(user.id),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Notification not found")
    row.read_at = row.read_at or utcnow()
    db.commit()
    return notification_payload(row)


def mark_all_notifications_read(db: Session, *, user: account_models.User) -> dict[str, Any]:
    amo_id = effective_amo_id(user)
    now = utcnow()
    updated = db.query(models.PortalNotification).filter(
        models.PortalNotification.amo_id == amo_id,
        models.PortalNotification.user_id == str(user.id),
        models.PortalNotification.read_at.is_(None),
        models.PortalNotification.archived_at.is_(None),
    ).update({models.PortalNotification.read_at: now}, synchronize_session=False)
    db.commit()
    return {"read_at": now, "updated": int(updated)}


def acknowledge_message(
    db: Session,
    *,
    user: account_models.User,
    message_id: str,
    read: bool,
) -> dict[str, Any]:
    amo_id = effective_amo_id(user)
    message = db.query(models.ChatMessage).filter(models.ChatMessage.id == message_id, models.ChatMessage.amo_id == amo_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    _thread_for_user(db, amo_id=amo_id, thread_id=message.thread_id, user_id=str(user.id))
    receipt = (
        db.query(models.MessageReceipt)
        .filter(
            models.MessageReceipt.message_id == message_id,
            models.MessageReceipt.user_id == str(user.id),
            models.MessageReceipt.amo_id == amo_id,
        )
        .first()
    )
    if not receipt:
        if str(message.sender_id or "") == str(user.id):
            return {"message_id": message_id, "delivered_at": None, "read_at": None}
        receipt = models.MessageReceipt(amo_id=amo_id, message_id=message_id, user_id=str(user.id))
        db.add(receipt)
    now = utcnow()
    receipt.delivered_at = receipt.delivered_at or now
    if read:
        receipt.read_at = receipt.read_at or now
    db.commit()
    return {"message_id": message_id, "delivered_at": receipt.delivered_at, "read_at": receipt.read_at}


def process_inbound_envelope(db: Session, envelope: schemas.RealtimeEnvelope) -> dict[str, Any]:
    user = _active_user(db, amo_id=envelope.amoId, user_id=envelope.userId)
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
        return edit_message(db, user=user, message_id=str(payload.get("messageId") or ""), body=str(payload.get("body") or ""))
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
