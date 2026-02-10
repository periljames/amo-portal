from __future__ import annotations

import asyncio
import json
import queue
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import models as audit_models
from amodb.database import get_db
from amodb.security import JWT_ALGORITHM, SECRET_KEY, get_user_by_id
from .broker import EventEnvelope, broker, format_sse, keepalive_message

router = APIRouter(prefix="/api", tags=["events"])

REPLAY_RETENTION_DAYS = 7
REPLAY_MAX_EVENTS = 500


class ActivityEventRead(BaseModel):
    id: str
    type: str
    entityType: str
    entityId: str
    action: str
    timestamp: str
    actor: Optional[dict] = None
    metadata: dict = {}


class ActivityHistoryResponse(BaseModel):
    items: list[ActivityEventRead]
    next_cursor: Optional[str] = None


class ActivityEventRead(BaseModel):
    id: str
    type: str
    entityType: str
    entityId: str
    action: str
    timestamp: str
    actor: Optional[dict] = None
    metadata: dict = {}


class ActivityHistoryResponse(BaseModel):
    items: list[ActivityEventRead]
    next_cursor: Optional[str] = None


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


def _event_to_row(event: audit_models.AuditEvent) -> ActivityEventRead:
    metadata = {"amoId": event.amo_id, **(event.metadata_json or {})}
    event_type = f"{event.entity_type}.{event.action}".lower()
    if metadata.get("module") == "training":
        event_type = f"training.{event.entity_type}.{event.action}".lower()
    return ActivityEventRead(
        id=str(event.id),
        type=event_type,
        entityType=event.entity_type,
        entityId=event.entity_id,
        action=event.action,
        timestamp=(event.occurred_at or event.created_at).isoformat(),
        actor={"userId": event.actor_user_id} if event.actor_user_id else None,
        metadata=metadata,
    )


def _audit_row_to_envelope(event: audit_models.AuditEvent) -> EventEnvelope:
    row = _event_to_row(event)
    return EventEnvelope(
        id=row.id,
        type=row.type,
        entityType=row.entityType,
        entityId=row.entityId,
        action=row.action,
        timestamp=row.timestamp,
        actor=row.actor,
        metadata=row.metadata,
    )


def _replay_events_since(
    db: Session,
    *,
    amo_id: str,
    last_event_id: str,
) -> tuple[list[EventEnvelope], bool]:
    anchor = (
        db.query(audit_models.AuditEvent)
        .filter(
            audit_models.AuditEvent.amo_id == amo_id,
            audit_models.AuditEvent.id == last_event_id,
        )
        .first()
    )
    if not anchor:
        return [], True

    anchor_ts = anchor.occurred_at or anchor.created_at
    replay_threshold = datetime.now(timezone.utc) - timedelta(days=REPLAY_RETENTION_DAYS)
    if anchor_ts < replay_threshold:
        return [], True

    rows = (
        db.query(audit_models.AuditEvent)
        .filter(
            audit_models.AuditEvent.amo_id == amo_id,
            or_(
                audit_models.AuditEvent.occurred_at > anchor_ts,
                and_(audit_models.AuditEvent.occurred_at == anchor_ts, audit_models.AuditEvent.id > anchor.id),
            ),
        )
        .order_by(audit_models.AuditEvent.occurred_at.asc(), audit_models.AuditEvent.id.asc())
        .limit(REPLAY_MAX_EVENTS)
        .all()
    )
    return [_audit_row_to_envelope(row) for row in rows], False


async def _event_generator(
    request: Request,
    user: account_models.User,
    db: Session,
) -> AsyncGenerator[str, None]:
    q = broker.subscribe()
    try:
        last_event_id = request.headers.get("last-event-id") or request.query_params.get("lastEventId")
        effective_amo_id = getattr(user, "effective_amo_id", None) or getattr(user, "amo_id", "")
        if last_event_id:
            replay, requires_reset = _replay_events_since(
                db,
                amo_id=str(effective_amo_id),
                last_event_id=last_event_id,
            )
            if requires_reset:
                yield format_sse(
                    json.dumps({"type": "reset", "reason": "last_event_id_out_of_window", "lastEventId": last_event_id}),
                    event="reset",
                )
            else:
                for event in replay:
                    yield format_sse(event.to_json(), event=event.type, event_id=event.id)
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.to_thread(q.get, True, 15)
                amo_id = event.metadata.get("amoId") if isinstance(event.metadata, dict) else None
                if amo_id and str(amo_id) != str(effective_amo_id):
                    continue
                yield format_sse(event.to_json(), event=event.type, event_id=event.id)
            except queue.Empty:
                yield keepalive_message()
    finally:
        broker.unsubscribe(q)


@router.get("/events")
async def stream_events(
    request: Request,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user_from_query),
) -> StreamingResponse:
    return StreamingResponse(
        _event_generator(request, user, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/events/history", response_model=ActivityHistoryResponse)
def list_event_history(
    request: Request,
    cursor: Optional[str] = Query(default=None, description="Opaque cursor as '<iso_ts>|<id>'"),
    limit: int = Query(default=100, ge=1, le=500),
    entityType: Optional[str] = None,
    entityId: Optional[str] = None,
    timeStart: Optional[datetime] = None,
    timeEnd: Optional[datetime] = None,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user_from_query),
) -> ActivityHistoryResponse:
    effective_amo_id = getattr(user, "effective_amo_id", None) or user.amo_id
    query = db.query(audit_models.AuditEvent).filter(audit_models.AuditEvent.amo_id == effective_amo_id)
    if entityType:
        query = query.filter(audit_models.AuditEvent.entity_type == entityType)
    if entityId:
        query = query.filter(audit_models.AuditEvent.entity_id == entityId)
    if timeStart:
        query = query.filter(audit_models.AuditEvent.occurred_at >= timeStart)
    if timeEnd:
        query = query.filter(audit_models.AuditEvent.occurred_at <= timeEnd)
    if cursor:
        ts_raw, _, event_id = cursor.partition("|")
        if ts_raw:
            try:
                ts = datetime.fromisoformat(ts_raw)
                query = query.filter(
                    or_(
                        audit_models.AuditEvent.occurred_at < ts,
                        and_(audit_models.AuditEvent.occurred_at == ts, audit_models.AuditEvent.id < event_id),
                    )
                )
            except ValueError:
                pass

    rows = (
        query.order_by(audit_models.AuditEvent.occurred_at.desc(), audit_models.AuditEvent.id.desc())
        .limit(limit + 1)
        .all()
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = None
    if has_more and page:
        last = page[-1]
        next_cursor = f"{(last.occurred_at or last.created_at).isoformat()}|{last.id}"
    return ActivityHistoryResponse(items=[_event_to_row(row) for row in page], next_cursor=next_cursor)
