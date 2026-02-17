from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user, get_current_user

from . import schemas, services

router = APIRouter(prefix="/api", tags=["realtime"])
realtime_bearer = HTTPBearer(auto_error=False)


def get_current_active_realtime_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(realtime_bearer),
    db: Session = Depends(get_db),
) -> account_models.User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token. Send header: Authorization: Bearer <JWT>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    current_user = get_current_user(token=credentials.credentials, db=db)
    return get_current_active_user(current_user=current_user, db=db)


@router.post("/realtime/token", response_model=schemas.RealtimeTokenResponse)
def issue_realtime_token(
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_realtime_user),
) -> schemas.RealtimeTokenResponse:
    return services.issue_connect_token(db, user=current_user, request=request)


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
