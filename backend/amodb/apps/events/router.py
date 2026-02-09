from __future__ import annotations

import asyncio
import queue
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import JWT_ALGORITHM, SECRET_KEY, get_user_by_id
from amodb.apps.accounts import models as account_models
from .broker import broker, format_sse, keepalive_message

router = APIRouter(prefix="/api", tags=["events"])


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _get_user_from_token(token: str, db: Session) -> account_models.User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise _credentials_exception()
    except JWTError:
        raise _credentials_exception()
    user = get_user_by_id(db, user_id)
    if user is None:
        raise _credentials_exception()
    if not getattr(user, "is_active", False):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user account")
    effective_amo_id = user.amo_id
    if getattr(user, "is_superuser", False):
        context = (
            db.query(account_models.UserActiveContext)
            .filter(account_models.UserActiveContext.user_id == user.id)
            .first()
        )
        if context and context.active_amo_id:
            effective_amo_id = context.active_amo_id
    setattr(user, "effective_amo_id", effective_amo_id)
    return user


def get_current_active_user_from_query(
    request: Request,
    db: Session = Depends(get_db),
) -> account_models.User:
    token = request.query_params.get("token")
    if not token:
        raise _credentials_exception()
    return _get_user_from_token(token, db)


async def _event_generator(
    request: Request,
    user: account_models.User,
) -> AsyncGenerator[str, None]:
    q = broker.subscribe()
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.to_thread(q.get, True, 15)
                amo_id = event.metadata.get("amoId") if isinstance(event.metadata, dict) else None
                effective_amo_id = getattr(user, "effective_amo_id", None) or getattr(user, "amo_id", "")
                if amo_id and str(amo_id) != str(effective_amo_id):
                    continue
                yield format_sse(event.to_json(), event=event.type)
            except queue.Empty:
                yield keepalive_message()
    finally:
        broker.unsubscribe(q)


@router.get("/events")
async def stream_events(
    request: Request,
    user: account_models.User = Depends(get_current_active_user_from_query),
) -> StreamingResponse:
    return StreamingResponse(
        _event_generator(request, user),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
