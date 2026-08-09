from __future__ import annotations

import logging
import os
import queue
import re
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import WriteSessionLocal, close_session_safely
from amodb.security import get_current_active_user
from amodb.user_id import generate_user_id

from . import ops_data_models as ops_models


logger = logging.getLogger(__name__)
router = APIRouter(tags=["product-analytics"])

EVENT_TYPES = frozenset({
    "module_opened",
    "workflow_started",
    "workflow_completed",
    "workflow_failed",
    "report_generated",
    "search_used",
    "export_used",
    "ai_assist_used",
    "bulk_action_used",
    "approval_completed",
})
OUTCOMES = frozenset({"SUCCESS", "FAILED", "CANCELLED", "UNKNOWN"})
SAFE_METADATA_KEYS = frozenset({"source", "workflow", "feature", "route_name", "document_type", "aircraft_family", "result_code", "entry_point"})
_MODULE_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
_QUEUE = queue.Queue(maxsize=max(1000, min(100000, int(os.getenv("PRODUCT_ANALYTICS_BUFFER_SIZE", "10000") or "10000"))))
_STOP = threading.Event()
_THREAD: threading.Thread | None = None
_STATE_LOCK = threading.Lock()
_STATE = {"accepted": 0, "dropped": 0, "persisted": 0, "flush_failures": 0, "last_flush_at": None}


@dataclass(frozen=True)
class ProductEvent:
    tenant_id: str
    event_type: str
    module: str
    outcome: str
    duration_ms: int | None
    session_class: str
    metadata: dict[str, Any]
    occurred_at: datetime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _bucket(value: datetime, kind: str) -> datetime:
    value = value.astimezone(timezone.utc)
    if kind == "hour":
        return value.replace(minute=0, second=0, microsecond=0)
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _safe_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for key in SAFE_METADATA_KEYS:
        raw = value.get(key)
        if raw is None or isinstance(raw, (dict, list, tuple, set)):
            continue
        result[key] = str(raw)[:128]
    return result


def _normalise_event(*, tenant_id: str, event_type: str, module: str, outcome: str | None, duration_ms: Any, session_class: str, metadata: Any, occurred_at: datetime | None = None) -> ProductEvent:
    event = str(event_type or "").strip().lower()
    if event not in EVENT_TYPES:
        raise ValueError("Unsupported product analytics event_type")
    module_value = str(module or "").strip().lower()
    if not _MODULE_RE.fullmatch(module_value):
        raise ValueError("module must be a bounded lowercase application module code")
    outcome_value = str(outcome or "UNKNOWN").strip().upper()
    if outcome_value not in OUTCOMES:
        raise ValueError("Unsupported product analytics outcome")
    duration = None
    if duration_ms is not None:
        duration = max(0, min(86_400_000, int(duration_ms)))
    return ProductEvent(
        tenant_id=str(tenant_id),
        event_type=event,
        module=module_value,
        outcome=outcome_value,
        duration_ms=duration,
        session_class=str(session_class or "tenant_user")[:32],
        metadata=_safe_metadata(metadata),
        occurred_at=occurred_at or _utcnow(),
    )


def record_product_event(**kwargs: Any) -> bool:
    """Enqueue a bounded product event without synchronously writing to storage."""
    try:
        event = _normalise_event(**kwargs)
        _QUEUE.put_nowait(event)
        with _STATE_LOCK:
            _STATE["accepted"] += 1
        return True
    except queue.Full:
        with _STATE_LOCK:
            _STATE["dropped"] += 1
        return False


def _upsert_rollup(db: Session, event: ProductEvent, *, kind: str) -> None:
    bucket_start = _bucket(event.occurred_at, kind)
    duration_total = int(event.duration_ms or 0)
    duration_count = 1 if event.duration_ms is not None else 0
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        values = {
            "id": generate_user_id(),
            "bucket_start": bucket_start,
            "bucket_kind": kind,
            "tenant_id": event.tenant_id,
            "module": event.module,
            "event_type": event.event_type,
            "outcome": event.outcome,
            "event_count": 1,
            "duration_total_ms": duration_total,
            "duration_count": duration_count,
            "duration_max_ms": event.duration_ms,
            "updated_at": _utcnow(),
        }
        stmt = pg_insert(ops_models.PlatformProductRollup).values(**values)
        excluded = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            constraint="uq_platform_product_rollup_bucket",
            set_={
                "event_count": ops_models.PlatformProductRollup.event_count + 1,
                "duration_total_ms": ops_models.PlatformProductRollup.duration_total_ms + duration_total,
                "duration_count": ops_models.PlatformProductRollup.duration_count + duration_count,
                "duration_max_ms": func.greatest(func.coalesce(ops_models.PlatformProductRollup.duration_max_ms, 0), func.coalesce(excluded.duration_max_ms, 0)),
                "updated_at": _utcnow(),
            },
        )
        db.execute(stmt)
        return

    row = (
        db.query(ops_models.PlatformProductRollup)
        .filter(
            ops_models.PlatformProductRollup.bucket_start == bucket_start,
            ops_models.PlatformProductRollup.bucket_kind == kind,
            ops_models.PlatformProductRollup.tenant_id == event.tenant_id,
            ops_models.PlatformProductRollup.module == event.module,
            ops_models.PlatformProductRollup.event_type == event.event_type,
            ops_models.PlatformProductRollup.outcome == event.outcome,
        )
        .first()
    )
    if row is None:
        row = ops_models.PlatformProductRollup(
            bucket_start=bucket_start,
            bucket_kind=kind,
            tenant_id=event.tenant_id,
            module=event.module,
            event_type=event.event_type,
            outcome=event.outcome,
            event_count=0,
            duration_total_ms=0,
            duration_count=0,
        )
        db.add(row)
    row.event_count = int(row.event_count or 0) + 1
    row.duration_total_ms = int(row.duration_total_ms or 0) + duration_total
    row.duration_count = int(row.duration_count or 0) + duration_count
    row.duration_max_ms = max(int(row.duration_max_ms or 0), int(event.duration_ms or 0)) if event.duration_ms is not None else row.duration_max_ms


def _persist(events: list[ProductEvent]) -> None:
    if not events:
        return
    db = WriteSessionLocal()
    try:
        for event in events:
            db.add(
                ops_models.PlatformProductEvent(
                    tenant_id=event.tenant_id,
                    event_type=event.event_type,
                    module=event.module,
                    outcome=event.outcome,
                    duration_ms=event.duration_ms,
                    session_class=event.session_class,
                    metadata_json=event.metadata,
                    occurred_at=event.occurred_at,
                )
            )
            _upsert_rollup(db, event, kind="hour")
            _upsert_rollup(db, event, kind="day")
        db.commit()
        with _STATE_LOCK:
            _STATE["persisted"] += len(events)
            _STATE["last_flush_at"] = _utcnow().isoformat()
    except Exception:
        db.rollback()
        with _STATE_LOCK:
            _STATE["flush_failures"] += 1
            _STATE["dropped"] += len(events)
        logger.exception("Product analytics batch flush failed; tenant requests remain unaffected")
    finally:
        close_session_safely(db)


def _worker() -> None:
    interval = max(0.5, min(10.0, float(os.getenv("PRODUCT_ANALYTICS_FLUSH_SECONDS", "2") or "2")))
    batch_size = max(10, min(1000, int(os.getenv("PRODUCT_ANALYTICS_BATCH_SIZE", "200") or "200")))
    while not _STOP.is_set():
        batch: list[ProductEvent] = []
        try:
            first = _QUEUE.get(timeout=interval)
            batch.append(first)
        except queue.Empty:
            continue
        while len(batch) < batch_size:
            try:
                batch.append(_QUEUE.get_nowait())
            except queue.Empty:
                break
        _persist(batch)
        for _ in batch:
            _QUEUE.task_done()


def start_sink() -> None:
    global _THREAD
    if _THREAD and _THREAD.is_alive():
        return
    _STOP.clear()
    _THREAD = threading.Thread(target=_worker, name="product-analytics-sink", daemon=True)
    _THREAD.start()


def stop_sink() -> None:
    global _THREAD
    _STOP.set()
    if _THREAD and _THREAD.is_alive():
        _THREAD.join(timeout=5)
    _THREAD = None


def sink_status() -> dict[str, Any]:
    with _STATE_LOCK:
        state = dict(_STATE)
    state.update({"buffer_depth": _QUEUE.qsize(), "buffer_capacity": _QUEUE.maxsize, "running": bool(_THREAD and _THREAD.is_alive())})
    return state


@router.on_event("startup")
def _start_product_sink() -> None:
    start_sink()


@router.on_event("shutdown")
def _stop_product_sink() -> None:
    stop_sink()


@router.post("/product-events", status_code=status.HTTP_202_ACCEPTED)
def ingest_product_event(payload: dict[str, Any], current_user=Depends(get_current_active_user)):
    tenant_id = str(getattr(current_user, "amo_id", "") or "").strip()
    if not tenant_id and getattr(current_user, "is_superuser", False):
        tenant_id = str(payload.get("tenant_id") or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=422, detail="A tenant context is required for product analytics")
    session_class = "platform_superuser" if getattr(current_user, "is_superuser", False) else "tenant_admin" if getattr(current_user, "is_amo_admin", False) else "tenant_user"
    try:
        accepted = record_product_event(
            tenant_id=tenant_id,
            event_type=payload.get("event_type"),
            module=payload.get("module"),
            outcome=payload.get("outcome"),
            duration_ms=payload.get("duration_ms"),
            session_class=session_class,
            metadata=payload.get("metadata"),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"accepted": accepted, "event_type": str(payload.get("event_type") or "").lower(), "buffered": True}


def analytics_summary(db: Session, *, data_mode: str = "REAL", days: int = 30) -> dict[str, Any]:
    mode = str(data_mode or "REAL").upper()
    if mode not in {"REAL", "DEMO"}:
        raise ValueError("data_mode must be REAL or DEMO")
    days = max(1, min(int(days), 90))
    since = _utcnow() - timedelta(days=days)
    query = (
        db.query(ops_models.PlatformProductRollup, account_models.AMO.is_demo)
        .join(account_models.AMO, account_models.AMO.id == ops_models.PlatformProductRollup.tenant_id)
        .filter(
            ops_models.PlatformProductRollup.bucket_kind == "day",
            ops_models.PlatformProductRollup.bucket_start >= since,
            account_models.AMO.is_demo.is_(mode == "DEMO"),
        )
    )
    rows = [row for row, _is_demo in query.limit(100000).all()]
    event_types: dict[str, int] = defaultdict(int)
    modules: dict[str, dict[str, Any]] = defaultdict(lambda: {"events": 0, "tenants": set(), "success": 0, "failed": 0, "duration_total_ms": 0, "duration_count": 0})
    tenants: set[str] = set()
    daily_tenants: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        count = int(row.event_count or 0)
        event_types[row.event_type] += count
        item = modules[row.module]
        item["events"] += count
        item["tenants"].add(row.tenant_id)
        if row.outcome == "SUCCESS":
            item["success"] += count
        elif row.outcome == "FAILED":
            item["failed"] += count
        item["duration_total_ms"] += int(row.duration_total_ms or 0)
        item["duration_count"] += int(row.duration_count or 0)
        tenants.add(row.tenant_id)
        daily_tenants[row.bucket_start.date().isoformat()].add(row.tenant_id)
    module_rows = []
    for module, item in modules.items():
        duration_count = int(item["duration_count"])
        module_rows.append({
            "module": module,
            "events": int(item["events"]),
            "active_tenants": len(item["tenants"]),
            "success": int(item["success"]),
            "failed": int(item["failed"]),
            "avg_duration_ms": round(int(item["duration_total_ms"]) / duration_count, 2) if duration_count else None,
        })
    module_rows.sort(key=lambda item: (-item["active_tenants"], -item["events"], item["module"]))
    started = int(event_types.get("workflow_started", 0))
    completed = int(event_types.get("workflow_completed", 0))
    failed = int(event_types.get("workflow_failed", 0))
    return {
        "data_mode": mode,
        "window_days": days,
        "active_tenants": len(tenants),
        "events": sum(event_types.values()),
        "event_types": dict(sorted(event_types.items())),
        "modules": module_rows,
        "workflow_funnel": {
            "started": started,
            "completed": completed,
            "failed": failed,
            "completion_rate": 0.0 if started <= 0 else min(1.0, completed / started),
            "failure_rate": 0.0 if started <= 0 else min(1.0, failed / started),
        },
        "daily_active_tenants": [{"date": day, "tenants": len(ids)} for day, ids in sorted(daily_tenants.items())],
        "privacy": "Aggregated tenant/module/workflow metrics only; no user-level drilldown is retained.",
        "sink": sink_status(),
    }
