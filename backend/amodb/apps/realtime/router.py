from __future__ import annotations

import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db, get_read_db
from amodb.security import get_current_active_user, get_current_user

from . import gateway, messaging, presence_service, schemas, services

router = APIRouter(prefix="/api", tags=["realtime"])
realtime_bearer = HTTPBearer(auto_error=False)


def get_current_active_realtime_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(realtime_bearer),
    db: Session = Depends(get_read_db),
) -> account_models.User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token. Send header: Authorization: Bearer <JWT>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    current_user = get_current_user(token=credentials.credentials, db=db)
    return get_current_active_user(current_user=current_user)


def _flush_outbox() -> None:
    gateway.gateway.flush_pending()


@router.post("/realtime/token", response_model=schemas.RealtimeTokenResponse)
def issue_realtime_token(
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
) -> schemas.RealtimeTokenResponse:
    result = services.issue_connect_token(db, user=current_user, request=request)
    _flush_outbox()
    return result


@router.get("/realtime/bootstrap", response_model=schemas.RealtimeBootstrapResponse)
def realtime_bootstrap(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
) -> schemas.RealtimeBootstrapResponse:
    base = services.build_bootstrap(db, user=current_user)
    if not services.effective_amo_id(current_user):
        return base
    threads = messaging.list_threads(db, user=current_user)
    counts = messaging.unread_notification_count(db, user=current_user)
    return schemas.RealtimeBootstrapResponse(
        threads=threads,
        unread_counts={str(row["id"]): int(row["unread_count"]) for row in threads},
        presence=base.presence,
        pending_prompts=base.pending_prompts,
        notification_unread_count=counts["notifications"],
    )


@router.get("/realtime/sync", response_model=schemas.RealtimeSyncResponse)
def realtime_sync(
    since: str = Query(..., description="cursor/timestamp in epoch ms"),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
) -> schemas.RealtimeSyncResponse:
    try:
        since_ms = int(since)
    except ValueError:
        since_ms = int(time.time() * 1000) - 60_000
    return services.sync_since(db, user=current_user, since_ts_ms=since_ms)


@router.post("/realtime/presence", response_model=schemas.PresenceStateRead)
def realtime_presence_update(
    payload: schemas.PresenceStateUpdateRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
) -> schemas.PresenceStateRead:
    result = presence_service.update_presence_state(db, user=current_user, payload=payload)
    _flush_outbox()
    return result


@router.get("/chat/directory")
def chat_directory(
    db: Session = Depends(get_read_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
):
    return messaging.directory(db, user=current_user)


@router.post("/chat/direct/{peer_user_id}", status_code=status.HTTP_201_CREATED)
def chat_direct_open(
    peer_user_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
):
    result = messaging.open_direct_thread(db, user=current_user, peer_user_id=peer_user_id)
    _flush_outbox()
    return result


@router.post("/chat/departments/{department_id}", status_code=status.HTTP_201_CREATED)
def chat_department_open(
    department_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
):
    result = messaging.open_department_thread(db, user=current_user, department_id=department_id)
    _flush_outbox()
    return result


@router.post("/chat/groups/{group_id}", status_code=status.HTTP_201_CREATED)
def chat_user_group_open(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
):
    result = messaging.open_user_group_thread(db, user=current_user, group_id=group_id)
    _flush_outbox()
    return result


@router.post("/chat/threads", response_model=schemas.ThreadRead, status_code=status.HTTP_201_CREATED)
def create_thread(
    payload: schemas.ThreadCreateRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
) -> schemas.ThreadRead:
    result = messaging.create_group_thread(
        db,
        user=current_user,
        title=payload.title,
        member_user_ids=payload.member_user_ids,
    )
    _flush_outbox()
    return result


@router.get("/chat/threads", response_model=list[schemas.ThreadRead])
def list_threads(
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
) -> list[schemas.ThreadRead]:
    return messaging.list_threads(db, user=current_user, limit=limit)


@router.get("/chat/threads/{thread_id}/messages", response_model=list[schemas.ChatMessageRead])
def list_thread_messages(
    thread_id: str,
    limit: int = Query(default=100, ge=1, le=250),
    before: datetime | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
) -> list[schemas.ChatMessageRead]:
    return messaging.list_messages(
        db,
        user=current_user,
        thread_id=thread_id,
        limit=limit,
        before=before,
    )


@router.post("/chat/threads/{thread_id}/messages", response_model=schemas.ChatMessageRead, status_code=status.HTTP_201_CREATED)
def chat_message_create(
    thread_id: str,
    payload: schemas.ChatMessageCreateRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
) -> schemas.ChatMessageRead:
    result = messaging.send_message(
        db,
        user=current_user,
        thread_id=thread_id,
        body=payload.body,
        client_msg_id=payload.client_msg_id,
        reply_to_message_id=payload.reply_to_message_id,
        metadata=payload.metadata,
    )
    _flush_outbox()
    return result


@router.patch("/chat/messages/{message_id}", response_model=schemas.ChatMessageRead)
def chat_message_update(
    message_id: str,
    payload: schemas.ChatMessageUpdateRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
) -> schemas.ChatMessageRead:
    result = messaging.edit_message(db, user=current_user, message_id=message_id, body=payload.body)
    _flush_outbox()
    return result


@router.delete("/chat/messages/{message_id}", response_model=schemas.ChatMessageRead)
def chat_message_delete(
    message_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
) -> schemas.ChatMessageRead:
    result = messaging.delete_message(db, user=current_user, message_id=message_id)
    _flush_outbox()
    return result


@router.post("/chat/threads/{thread_id}/read")
def chat_thread_read(
    thread_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
):
    result = messaging.mark_thread_read(db, user=current_user, thread_id=thread_id)
    _flush_outbox()
    return result


@router.patch("/chat/threads/{thread_id}/notifications")
def chat_thread_notifications(
    thread_id: str,
    payload: schemas.ThreadNotificationUpdateRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
):
    return messaging.update_thread_notifications(
        db,
        user=current_user,
        thread_id=thread_id,
        notification_level=payload.notification_level,
        muted_until=payload.muted_until,
    )


@router.get("/notifications/me")
def notification_list(
    unread_only: bool = False,
    limit: int = Query(100, ge=1, le=250),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_read_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
):
    return messaging.list_notifications(
        db,
        user=current_user,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )


@router.get("/notifications/me/unread-count")
def notification_unread_count(
    db: Session = Depends(get_read_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
):
    return messaging.unread_notification_count(db, user=current_user)


@router.post("/notifications/{notification_id}/read")
def notification_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
):
    result = messaging.mark_notification_read(db, user=current_user, notification_id=notification_id)
    _flush_outbox()
    return result


@router.post("/notifications/read-all")
def notification_read_all(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
):
    result = messaging.mark_all_notifications_read(db, user=current_user)
    _flush_outbox()
    return result


@router.get("/notifications/preferences")
def notification_preferences_get(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
):
    return messaging.get_preferences(db, user=current_user)


@router.put("/notifications/preferences")
def notification_preferences_update(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
):
    return messaging.update_preferences(db, user=current_user, payload=payload)


@router.post("/prompts/{prompt_id}/action")
def prompt_action(
    prompt_id: str,
    payload: schemas.PromptActionRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
) -> dict[str, str]:
    return services.perform_prompt_action(
        db,
        user=current_user,
        prompt_id=prompt_id,
        action=payload.action,
    )
