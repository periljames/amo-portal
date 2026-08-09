from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.exceptions import HTTPException
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from amodb.database import ReadSessionLocal, WriteSessionLocal, close_session_safely, get_read_db
from amodb.security import get_current_user

from .console_router import (
    _audit_event,
    _bootstrap_snapshot,
    _event_cursor,
    _event_rows,
    _parse_cursor,
    console_search as _legacy_console_search,
)
from .ops_broker import PreparedMessage, PreparedSnapshotBroker, RefreshBatch
from .router import require_platform_superuser

router = APIRouter(prefix="/console", tags=["platform-operations-gateway"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

POLL_INTERVAL_SECONDS = max(1.0, float(os.getenv("PLATFORM_OPS_POLL_INTERVAL_SEC", "2") or "2"))
SNAPSHOT_INTERVAL_SECONDS = max(
    POLL_INTERVAL_SECONDS,
    float(os.getenv("PLATFORM_OPS_SNAPSHOT_INTERVAL_SEC", "10") or "10"),
)


def _refresh_prepared_snapshot(cursor: str | None, include_snapshot: bool) -> RefreshBatch:
    """Perform one control-plane read pass for every connected browser."""
    db = ReadSessionLocal()
    try:
        cursor_time, cursor_id = _parse_cursor(cursor)
        rows = _event_rows(db, cursor_time=cursor_time, cursor_id=cursor_id)
        events: list[tuple[str, dict[str, Any]]] = []
        next_cursor = cursor
        for row in rows:
            payload = _audit_event(row)
            events.append(("platform.audit", payload))
            next_cursor = _event_cursor(row)

        snapshot: dict[str, Any] | None = None
        if include_snapshot:
            snapshot = _bootstrap_snapshot(db)
            snapshot["data_mode"] = "REAL"
            snapshot["control_plane"] = {
                "prepared": True,
                "browser_independent_refresh": True,
                "poll_interval_seconds": POLL_INTERVAL_SECONDS,
                "snapshot_interval_seconds": SNAPSHOT_INTERVAL_SECONDS,
            }
        return RefreshBatch(snapshot=snapshot, events=tuple(events), cursor=next_cursor)
    finally:
        close_session_safely(db)


broker = PreparedSnapshotBroker(
    _refresh_prepared_snapshot,
    poll_interval_seconds=POLL_INTERVAL_SECONDS,
    snapshot_interval_seconds=SNAPSHOT_INTERVAL_SECONDS,
)


def _sse_message(message: PreparedMessage) -> str:
    encoded = json.dumps(message.payload, default=str, separators=(",", ":"))
    return f"id: ops:{message.sequence}\nevent: {message.event}\ndata: {encoded}\n\n"


def _require_stream_superuser(token: str = Depends(oauth2_scheme)) -> dict[str, str]:
    """Authenticate once without retaining a DB dependency for the SSE lifetime."""
    db = WriteSessionLocal()
    try:
        user = get_current_user(token=token, db=db)
        if not getattr(user, "is_active", False):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user account")
        if not getattr(user, "is_superuser", False):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform superuser access is required")
        if getattr(user, "amo_id", None):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform user must not be tenant-bound")
        return {"id": str(user.id)}
    finally:
        close_session_safely(db)


@router.get("/bootstrap")
async def console_bootstrap(user=Depends(require_platform_superuser)):
    return await broker.snapshot()


@router.get("/search")
def console_search(
    q: str = Query(..., min_length=2, max_length=120),
    limit: int = Query(12, ge=1, le=25),
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    return _legacy_console_search(q=q, limit=limit, db=db, user=user)


@router.get("/broker-health")
def broker_health(user=Depends(require_platform_superuser)):
    return broker.health()


async def _event_stream(request: Request, last_event_id: str | None) -> AsyncGenerator[str, None]:
    async for message in broker.stream(last_event_id):
        if await request.is_disconnected():
            break
        if message is None:
            yield ": keepalive\n\n"
        else:
            yield _sse_message(message)


@router.get("/events")
async def console_events(
    request: Request,
    last_event_id: str | None = Query(None),
    user=Depends(_require_stream_superuser),
) -> StreamingResponse:
    cursor = last_event_id or request.headers.get("last-event-id")
    return StreamingResponse(
        _event_stream(request, cursor),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
