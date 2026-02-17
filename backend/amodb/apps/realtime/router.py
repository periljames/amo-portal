from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Query, Request
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import schemas, services

# Backwards-compat alias: some local/dev copies referenced
# get_current_active_realtime_user in Depends(...).
# Keep this alias to avoid runtime import crashes during hot-reload
# if stale code paths still reference the older symbol.
get_current_active_realtime_user = get_current_active_user

router = APIRouter(prefix="/api", tags=["realtime"])
realtime_bearer = HTTPBearer(auto_error=False)


@router.post("/realtime/token", response_model=schemas.RealtimeTokenResponse)
def issue_realtime_token(
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> schemas.RealtimeTokenResponse:
    scheme = "wss" if request.url.scheme == "https" else "ws"
    fallback_origin = f"{scheme}://{request.url.netloc}"
    return services.issue_connect_token(db, user=current_user, broker_ws_url=fallback_origin)


@router.get("/realtime/bootstrap", response_model=schemas.RealtimeBootstrapResponse)
def realtime_bootstrap(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> schemas.RealtimeBootstrapResponse:
    return services.build_bootstrap(db, user=current_user)


@router.get("/realtime/sync", response_model=schemas.RealtimeSyncResponse)
def realtime_sync(
    since: str = Query(..., description="cursor/timestamp in epoch ms"),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
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
    current_user: account_models.User = Depends(get_current_active_user),
) -> schemas.PresenceStateRead:
    return services.update_presence_state(db, user=current_user, payload=payload)


@router.post("/chat/threads", response_model=schemas.ThreadRead)
def create_thread(
    payload: schemas.ThreadCreateRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> schemas.ThreadRead:
    return services.create_thread(db, user=current_user, payload=payload)


@router.get("/chat/threads", response_model=list[schemas.ThreadRead])
def list_threads(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> list[schemas.ThreadRead]:
    return services.list_threads(db, user=current_user)


@router.get("/chat/threads/{thread_id}/messages", response_model=list[schemas.ChatMessageRead])
def list_thread_messages(
    thread_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> list[schemas.ChatMessageRead]:
    return services.list_thread_messages(db, user=current_user, thread_id=thread_id, limit=limit)


@router.post("/prompts/{prompt_id}/action")
def prompt_action(
    prompt_id: str,
    payload: schemas.PromptActionRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> dict[str, str]:
    return services.perform_prompt_action(db, user=current_user, prompt_id=prompt_id, action=payload.action)
