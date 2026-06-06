from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import logging
import os
import re
import time
import urllib.request
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path as FsPath
from typing import Any, Iterable

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from amodb.database import get_read_db, get_write_db
from amodb.apps.audit import services as audit_services
from amodb.apps.accounts import models as accounts_models
from amodb.apps.quality import models as quality_models
from amodb.apps.quality.enums import CARStatus, QMSAuditStatus, QMSDocStatus
from amodb.apps.training import models as training_models
from .security import TenantContext, assert_qms_permission, has_qms_permission, require_qms_permission, resolve_tenant_context, set_postgres_tenant_context


router = APIRouter(prefix="/api/maintenance/{amo_code}/qms", tags=["Canonical QMS"])
logger = logging.getLogger("amodb.qms")
_TABLE_COLUMNS_CACHE: dict[str, set[str]] = {}


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return str(raw)


def _as_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _is_open_status(value: Any) -> bool:
    status = (_as_text(value) or "").upper()
    return status not in {"CLOSED", "CANCELLED", "OBSOLETE", "REJECTED"}


def _row_id(value: Any) -> str:
    return str(getattr(value, "id", value))


def _event(
    module: str,
    entity_type: str,
    entity_id: str,
    title: str,
    when: Any,
    event_type: str,
    link: str | None = None,
    *,
    status_value: Any = None,
    owner_label: str | None = None,
    detail: str | None = None,
    source: str | None = None,
    due_state: str | None = None,
    actionable: bool = True,
) -> dict[str, Any]:
    return {
        "id": f"{module}:{entity_type}:{entity_id}:{event_type}",
        "module": module,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "title": title,
        "date": _as_date(when),
        "event_type": event_type,
        "status": _as_text(status_value),
        "owner_label": owner_label,
        "detail": detail,
        "source": source or module,
        "due_state": due_state,
        "actionable": actionable,
        "link": link,
    }


def _limit(qs, limit: int):
    return qs.limit(max(1, min(limit, 500)))


def _safe_rollback(db: Session) -> None:
    try:
        db.rollback()
    except Exception:
        logger.exception("QMS database rollback failed after an error")


def _valid_zoneinfo(name: str | None) -> ZoneInfo:
    candidate = (name or "").strip() or "UTC"
    try:
        return ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        logger.warning("Invalid AMO time zone %r; falling back to UTC", candidate)
        return ZoneInfo("UTC")


def _tenant_calendar_context(db: Session, *, amo_id: str) -> dict[str, Any]:
    row = (
        db.query(accounts_models.AMO.id, accounts_models.AMO.amo_code, accounts_models.AMO.name, accounts_models.AMO.country, accounts_models.AMO.time_zone)
        .filter(accounts_models.AMO.id == amo_id)
        .first()
    )
    tz_name = getattr(row, "time_zone", None) if row else None
    zone = _valid_zoneinfo(tz_name)
    now_local = datetime.now(timezone.utc).astimezone(zone)
    return {
        "timezone": zone.key,
        "country": getattr(row, "country", None) if row else None,
        "today": now_local.date(),
        "now": now_local,
    }


def _qms_table_exists(db: Session, table: str) -> bool:
    try:
        row = db.execute(
            text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = :table
                )
            """),
            {"table": table},
        ).scalar()
        return bool(row)
    except SQLAlchemyError:
        _safe_rollback(db)
        return False


def _qms_count(db: Session, *, sql: str, params: dict[str, Any], label: str, trace_id: str, source_errors: list[dict[str, Any]], amo_id: str | None = None, user_id: str | None = None) -> int | None:
    try:
        return int(db.execute(text(sql), params).scalar() or 0)
    except SQLAlchemyError as exc:
        _safe_rollback(db)
        if amo_id and user_id:
            try:
                set_postgres_tenant_context(db, amo_id=amo_id, user_id=user_id)
            except Exception:
                logger.exception("QMS tenant context recovery failed after counter error")
        detail = str(getattr(exc, "orig", exc))
        logger.error("QMS dashboard counter failed trace_id=%s label=%s error=%s", trace_id, label, detail)
        source_errors.append({"source": label, "error": detail, "trace_id": trace_id})
        return None


def _calendar_fetch_rows(
    db: Session,
    *,
    sql: str,
    params: dict[str, Any],
    label: str,
    trace_id: str,
    source_errors: list[dict[str, Any]],
    required: bool = False,
    amo_id: str | None = None,
    user_id: str | None = None,
) -> list[dict[str, Any]]:
    try:
        return [dict(row) for row in db.execute(text(sql), params).mappings().all()]
    except SQLAlchemyError as exc:
        _safe_rollback(db)
        if amo_id and user_id:
            try:
                set_postgres_tenant_context(db, amo_id=amo_id, user_id=user_id)
            except Exception:
                logger.exception("QMS tenant context recovery failed after calendar source error")
        detail = str(getattr(exc, "orig", exc))
        logger.error("QMS calendar source failed trace_id=%s label=%s error=%s", trace_id, label, detail)
        source_errors.append({"source": label, "error": detail, "trace_id": trace_id, "required": required})
        if required:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"message": f"Required calendar source '{label}' failed.", "trace_id": trace_id, "error": detail},
            )
        return []


def _due_state_for(when: date | None, today: date, *, event_type: str, status_value: Any = None) -> str:
    if event_type == "public_holiday":
        return "holiday"
    normalized = (_as_text(status_value) or "").upper()
    if normalized in {"CLOSED", "COMPLETED", "COMPLETE", "CANCELLED", "APPROVED", "IMPLEMENTED"}:
        return "complete"
    if when is None:
        return "scheduled"
    if when < today:
        return "overdue"
    if when == today:
        return "today"
    return "due"


def _source_filter_for_view(view: str) -> set[str] | None:
    if view == "audits":
        return {"audits"}
    if view == "cars":
        return {"cars"}
    if view == "training":
        return {"training"}
    if view in {"management-review", "reviews"}:
        return {"reviews"}
    if view in {"holidays", "public-holidays"}:
        return {"holidays"}
    return None


def _read_calendar_settings(db: Session, *, amo_id: str) -> dict[str, Any]:
    if not _qms_table_exists(db, "qms_calendar_settings"):
        return {}
    row = db.execute(
        text("""
            SELECT amo_id, holidays_enabled, holiday_source_url, holiday_provider,
                   holiday_country_code, holiday_region_code, cache_ttl_hours, updated_at
            FROM qms_calendar_settings
            WHERE amo_id = :amo_id
            LIMIT 1
        """),
        {"amo_id": amo_id},
    ).mappings().first()
    return dict(row) if row else {}


def _parse_ics_date(raw_value: str) -> date | None:
    value = (raw_value or "").strip()
    if not value:
        return None
    if ":" in value:
        value = value.split(":", 1)[1]
    value = value.strip()
    try:
        if "T" in value:
            return datetime.strptime(value[:8], "%Y%m%d").date()
        return datetime.strptime(value[:8], "%Y%m%d").date()
    except Exception:
        return None


def _unescape_ics_text(value: str) -> str:
    return (value or "").replace("\\n", " ").replace("\\,", ",").replace("\\;", ";").strip()


def _parse_public_holiday_ics(payload: str, *, start_date: date, end_date: date) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    current: dict[str, str] | None = None
    for raw_line in payload.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current:
                dt = _parse_ics_date(current.get("DTSTART", ""))
                title = _unescape_ics_text(current.get("SUMMARY", "Public holiday")) or "Public holiday"
                uid = current.get("UID") or hashlib.sha1(f"{title}:{dt}".encode("utf-8")).hexdigest()
                if dt and start_date <= dt <= end_date:
                    events.append({"uid": uid, "date": dt, "title": title})
            current = None
            continue
        if current is not None and ":" in line:
            key, value = line.split(":", 1)
            key = key.split(";", 1)[0].upper()
            if key in {"DTSTART", "SUMMARY", "UID"}:
                current[key] = value
    return events


def _refresh_public_holidays_if_needed(
    db: Session,
    *,
    amo_id: str,
    settings_row: dict[str, Any],
    start_date: date,
    end_date: date,
    trace_id: str,
    source_errors: list[dict[str, Any]],
) -> None:
    if not _qms_table_exists(db, "qms_public_holidays"):
        return
    if not settings_row or not bool(settings_row.get("holidays_enabled")):
        return
    source_url = (settings_row.get("holiday_source_url") or "").strip()
    if not source_url:
        source_errors.append({"source": "public_holidays", "error": "Public holiday source URL is not configured in qms_calendar_settings.", "trace_id": trace_id})
        return
    ttl_hours = int(settings_row.get("cache_ttl_hours") or 168)
    stale_before = datetime.now(timezone.utc) - timedelta(hours=max(1, ttl_hours))
    cached = db.execute(
        text("""
            SELECT COUNT(*)
            FROM qms_public_holidays
            WHERE amo_id = :amo_id
              AND holiday_date >= :start_date
              AND holiday_date <= :end_date
              AND source_updated_at >= :stale_before
        """),
        {"amo_id": amo_id, "start_date": start_date, "end_date": end_date, "stale_before": stale_before},
    ).scalar()
    if cached:
        return
    try:
        req = urllib.request.Request(source_url, headers={"User-Agent": "AMO-Portal-QMS-Calendar/1.0"})
        with urllib.request.urlopen(req, timeout=4) as response:
            payload = response.read(1_500_000).decode("utf-8", errors="replace")
        parsed = _parse_public_holiday_ics(payload, start_date=start_date, end_date=end_date)
        now = datetime.now(timezone.utc)
        for item in parsed:
            db.execute(
                text("""
                    INSERT INTO qms_public_holidays
                        (id, amo_id, holiday_date, title, source_uid, source_url, source_updated_at, created_at, updated_at)
                    VALUES
                        (:id, :amo_id, :holiday_date, :title, :source_uid, :source_url, :source_updated_at, NOW(), NOW())
                    ON CONFLICT (amo_id, holiday_date, source_uid)
                    DO UPDATE SET title = EXCLUDED.title, source_url = EXCLUDED.source_url,
                                  source_updated_at = EXCLUDED.source_updated_at, updated_at = NOW()
                """),
                {
                    "id": str(uuid.uuid4()),
                    "amo_id": amo_id,
                    "holiday_date": item["date"],
                    "title": item["title"],
                    "source_uid": item["uid"],
                    "source_url": source_url,
                    "source_updated_at": now,
                },
            )
        db.commit()
    except Exception as exc:
        _safe_rollback(db)
        detail = str(exc)
        logger.error("QMS public holiday refresh failed trace_id=%s error=%s", trace_id, detail)
        source_errors.append({"source": "public_holidays", "error": detail, "trace_id": trace_id})


@router.get("/dashboard")
def qms_dashboard(
    ctx: TenantContext = Depends(require_qms_permission("qms.dashboard.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    trace_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    if _is_postgres(db):
        db.execute(text("SET LOCAL statement_timeout = '9000ms'"))
    calendar_context = _tenant_calendar_context(db, amo_id=ctx.amo_id)
    today = calendar_context["today"]
    due_soon = today + timedelta(days=30)
    source_errors: list[dict[str, Any]] = []

    counters = {
        "open_audits": _qms_count(db, sql="SELECT COUNT(*) FROM qms_audits WHERE amo_id = :amo_id AND status <> 'CLOSED'", params={"amo_id": ctx.amo_id}, label="open_audits", trace_id=trace_id, source_errors=source_errors, amo_id=ctx.amo_id, user_id=ctx.user_id),
        "audits_due_soon": _qms_count(db, sql="""
            SELECT COUNT(*) FROM qms_audits
            WHERE amo_id = :amo_id AND planned_start IS NOT NULL
              AND planned_start >= :today AND planned_start <= :due_soon
              AND status <> 'CLOSED'
        """, params={"amo_id": ctx.amo_id, "today": today, "due_soon": due_soon}, label="audits_due_soon", trace_id=trace_id, source_errors=source_errors, amo_id=ctx.amo_id, user_id=ctx.user_id),
        "active_audit_fieldwork": _qms_count(db, sql="SELECT COUNT(*) FROM qms_audits WHERE amo_id = :amo_id AND status = 'IN_PROGRESS'", params={"amo_id": ctx.amo_id}, label="active_audit_fieldwork", trace_id=trace_id, source_errors=source_errors, amo_id=ctx.amo_id, user_id=ctx.user_id),
        "open_cars": _qms_count(db, sql="SELECT COUNT(*) FROM quality_cars WHERE amo_id = :amo_id AND status NOT IN ('CLOSED', 'CANCELLED')", params={"amo_id": ctx.amo_id}, label="open_cars", trace_id=trace_id, source_errors=source_errors, amo_id=ctx.amo_id, user_id=ctx.user_id),
        "overdue_cars": _qms_count(db, sql="""
            SELECT COUNT(*) FROM quality_cars
            WHERE amo_id = :amo_id AND due_date IS NOT NULL AND due_date < :today
              AND status NOT IN ('CLOSED', 'CANCELLED')
        """, params={"amo_id": ctx.amo_id, "today": today}, label="overdue_cars", trace_id=trace_id, source_errors=source_errors, amo_id=ctx.amo_id, user_id=ctx.user_id),
        "cars_due_soon": _qms_count(db, sql="""
            SELECT COUNT(*) FROM quality_cars
            WHERE amo_id = :amo_id AND due_date IS NOT NULL
              AND due_date >= :today AND due_date <= :due_soon
              AND status NOT IN ('CLOSED', 'CANCELLED')
        """, params={"amo_id": ctx.amo_id, "today": today, "due_soon": due_soon}, label="cars_due_soon", trace_id=trace_id, source_errors=source_errors, amo_id=ctx.amo_id, user_id=ctx.user_id),
        "open_findings": _qms_count(db, sql="SELECT COUNT(*) FROM qms_audit_findings WHERE amo_id = :amo_id AND closed_at IS NULL", params={"amo_id": ctx.amo_id}, label="open_findings", trace_id=trace_id, source_errors=source_errors, amo_id=ctx.amo_id, user_id=ctx.user_id),
        "draft_documents": _qms_count(db, sql="SELECT COUNT(*) FROM qms_documents WHERE amo_id = :amo_id AND status = 'DRAFT'", params={"amo_id": ctx.amo_id}, label="draft_documents", trace_id=trace_id, source_errors=source_errors, amo_id=ctx.amo_id, user_id=ctx.user_id),
        "active_documents": _qms_count(db, sql="SELECT COUNT(*) FROM qms_documents WHERE amo_id = :amo_id AND status = 'ACTIVE'", params={"amo_id": ctx.amo_id}, label="active_documents", trace_id=trace_id, source_errors=source_errors, amo_id=ctx.amo_id, user_id=ctx.user_id),
        "training_expired_records": _qms_count(db, sql="""
            WITH latest AS (
                SELECT DISTINCT ON (user_id, course_id) user_id, course_id, valid_until
                FROM training_records
                WHERE amo_id = :amo_id AND valid_until IS NOT NULL
                ORDER BY user_id, course_id, completion_date DESC NULLS LAST, valid_until DESC NULLS LAST, created_at DESC NULLS LAST
            )
            SELECT COUNT(*) FROM latest WHERE valid_until < :today
        """, params={"amo_id": ctx.amo_id, "today": today}, label="training_expired_records", trace_id=trace_id, source_errors=source_errors, amo_id=ctx.amo_id, user_id=ctx.user_id),
    }

    return {
        "tenant": {"amo_code": ctx.amo_code, "amo_id": ctx.amo_id},
        "source": "tenant_scoped_backend",
        "as_of": calendar_context["now"].isoformat(),
        "timezone": calendar_context["timezone"],
        "health": "degraded" if source_errors else "ok",
        "source_errors": source_errors,
        "counters": {key: (0 if value is None else value) for key, value in counters.items()},
        "links": {
            "open_cars": f"/maintenance/{ctx.amo_code}/qms/cars/overdue",
            "audits_due_soon": f"/maintenance/{ctx.amo_code}/qms/audits/schedule",
            "documents": f"/maintenance/{ctx.amo_code}/qms/documents/library",
            "training": f"/maintenance/{ctx.amo_code}/qms/training-competence/overdue",
        },
        "trace_id": trace_id,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


@router.get("/inbox")
def qms_inbox(
    status_filter: str | None = Query(None, alias="status"),
    ctx: TenantContext = Depends(require_qms_permission("qms.inbox.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    qs = (
        db.query(quality_models.QMSNotification)
        .filter(
            quality_models.QMSNotification.amo_id == ctx.amo_id,
            quality_models.QMSNotification.user_id == ctx.user_id,
        )
        .order_by(quality_models.QMSNotification.created_at.desc())
    )
    if status_filter == "unread":
        qs = qs.filter(quality_models.QMSNotification.read_at.is_(None))
    rows = _limit(qs, 100).all()
    return {
        "items": [
            {
                "id": _row_id(row),
                "message": row.message,
                "severity": _as_text(row.severity),
                "created_at": _as_date(row.created_at),
                "read_at": _as_date(row.read_at),
            }
            for row in rows
        ]
    }


@router.get("/inbox/{view}")
def qms_inbox_view(
    view: str,
    ctx: TenantContext = Depends(require_qms_permission("qms.inbox.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    mapped_status = "unread" if view in {"assigned-to-me", "approvals", "overdue", "watching"} else None
    data = qms_inbox(status_filter=mapped_status, ctx=ctx, db=db)
    data["view"] = view
    return data


@router.get("/calendar")
def qms_calendar(
    start: date | None = Query(None),
    end: date | None = Query(None),
    limit: int = Query(120, ge=1, le=500),
    offset: int = Query(0, ge=0, le=100_000),
    source: str | None = Query(None),
    ctx: TenantContext = Depends(require_qms_permission("qms.calendar.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    trace_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    if _is_postgres(db):
        db.execute(text("SET LOCAL statement_timeout = '9000ms'"))
    calendar_context = _tenant_calendar_context(db, amo_id=ctx.amo_id)
    today = calendar_context["today"]
    start_date = start or today.replace(day=1) - timedelta(days=10)
    end_date = end or today + timedelta(days=90)
    if end_date < start_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Calendar end date cannot be before start date.")
    bounded_limit = max(1, min(limit, 500))
    bounded_offset = max(0, offset)
    source_filter = {source} if source else None
    events, source_errors = _build_calendar_events(
        db,
        ctx=ctx,
        start_date=start_date,
        end_date=end_date,
        today=today,
        source_filter=source_filter,
        trace_id=trace_id,
        required_sources=source_filter or set(),
    )
    events.sort(key=lambda item: (item.get("date") or "9999-12-31", item.get("source") or "", item.get("title") or ""))
    visible = events[bounded_offset:bounded_offset + bounded_limit]
    return {
        "module": "calendar",
        "view": "list" if not source else source,
        "calendar_meta": {
            "today": today.isoformat(),
            "timezone": calendar_context["timezone"],
            "country": calendar_context.get("country"),
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "week_starts_on": "MONDAY",
        },
        "summary": {
            "total": len(events),
            "overdue": sum(1 for item in events if item.get("due_state") == "overdue"),
            "audits": sum(1 for item in events if item.get("source") == "audits"),
            "cars": sum(1 for item in events if item.get("source") == "cars"),
            "training": sum(1 for item in events if item.get("source") == "training"),
            "holidays": sum(1 for item in events if item.get("source") == "holidays"),
        },
        "items": visible,
        "columns": ["date", "title", "owner_label", "event_type", "status", "due_state"],
        "limit": bounded_limit,
        "offset": bounded_offset,
        "next_offset": bounded_offset + bounded_limit if len(events) > bounded_offset + bounded_limit else None,
        "has_more": len(events) > bounded_offset + bounded_limit,
        "source_errors": source_errors,
        "warning": f"{len(source_errors)} calendar source(s) failed. See diagnostics." if source_errors else None,
        "trace_id": trace_id,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def _build_calendar_events(
    db: Session,
    *,
    ctx: TenantContext,
    start_date: date,
    end_date: date,
    today: date,
    source_filter: set[str] | None,
    trace_id: str,
    required_sources: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    source_errors: list[dict[str, Any]] = []
    source_limit = 500

    def want(name: str) -> bool:
        return source_filter is None or name in source_filter

    if want("audits"):
        audit_start_rows = _calendar_fetch_rows(
            db,
            sql="""
                SELECT id::text AS id, audit_ref, title, status, kind, planned_start AS event_date, lead_auditor_user_id
                FROM qms_audits
                WHERE amo_id = :amo_id
                  AND planned_start IS NOT NULL
                  AND planned_start >= :start_date
                  AND planned_start <= :end_date
                ORDER BY planned_start ASC, created_at DESC NULLS LAST
                LIMIT :limit
            """,
            params={"amo_id": ctx.amo_id, "start_date": start_date, "end_date": end_date, "limit": source_limit},
            label="audit_start",
            trace_id=trace_id,
            source_errors=source_errors,
            required="audits" in required_sources,
            amo_id=ctx.amo_id,
            user_id=ctx.user_id,
        )
        audit_end_rows = _calendar_fetch_rows(
            db,
            sql="""
                SELECT id::text AS id, audit_ref, title, status, kind, planned_end AS event_date, lead_auditor_user_id
                FROM qms_audits
                WHERE amo_id = :amo_id
                  AND planned_end IS NOT NULL
                  AND planned_end >= :start_date
                  AND planned_end <= :end_date
                ORDER BY planned_end ASC, created_at DESC NULLS LAST
                LIMIT :limit
            """,
            params={"amo_id": ctx.amo_id, "start_date": start_date, "end_date": end_date, "limit": source_limit},
            label="audit_end",
            trace_id=trace_id,
            source_errors=source_errors,
            required="audits" in required_sources,
            amo_id=ctx.amo_id,
            user_id=ctx.user_id,
        )
        for row in audit_start_rows:
            when = row.get("event_date")
            title = row.get("title") or row.get("audit_ref") or "Audit"
            events.append(_event("audits", "audit", row["id"], str(title), when, "audit_start", f"/maintenance/{ctx.amo_code}/qms/audits/{row['id']}/overview", status_value=row.get("status"), detail=row.get("audit_ref"), source="audits", due_state=_due_state_for(when, today, event_type="audit_start", status_value=row.get("status"))))
        for row in audit_end_rows:
            when = row.get("event_date")
            title = row.get("title") or row.get("audit_ref") or "Audit"
            events.append(_event("audits", "audit", row["id"], str(title), when, "audit_end", f"/maintenance/{ctx.amo_code}/qms/audits/{row['id']}/overview", status_value=row.get("status"), detail=row.get("audit_ref"), source="audits", due_state=_due_state_for(when, today, event_type="audit_end", status_value=row.get("status"))))

    if want("cars"):
        car_rows = _calendar_fetch_rows(
            db,
            sql="""
                SELECT id::text AS id, car_number, title, status, priority, due_date AS event_date, assigned_to_user_id
                FROM quality_cars
                WHERE amo_id = :amo_id
                  AND due_date IS NOT NULL
                  AND due_date >= :start_date
                  AND due_date <= :end_date
                ORDER BY due_date ASC, created_at DESC NULLS LAST
                LIMIT :limit
            """,
            params={"amo_id": ctx.amo_id, "start_date": start_date, "end_date": end_date, "limit": source_limit},
            label="cars",
            trace_id=trace_id,
            source_errors=source_errors,
            required="cars" in required_sources,
            amo_id=ctx.amo_id,
            user_id=ctx.user_id,
        )
        for row in car_rows:
            when = row.get("event_date")
            title = row.get("title") or row.get("car_number") or "Corrective action"
            events.append(_event("cars", "car", row["id"], str(title), when, "car_due", f"/maintenance/{ctx.amo_code}/qms/cars/{row['id']}/overview", status_value=row.get("status"), detail=row.get("car_number"), source="cars", due_state=_due_state_for(when, today, event_type="car_due", status_value=row.get("status"))))

    if want("training"):
        training_session_rows = _calendar_fetch_rows(
            db,
            sql="""
                SELECT e.id::text AS id, e.title, e.status, e.starts_on AS event_date, e.ends_on,
                       c.course_id AS course_code, c.course_name,
                       COUNT(p.id) AS participant_count
                FROM training_events e
                LEFT JOIN training_courses c ON c.id = e.course_id
                LEFT JOIN training_event_participants p ON p.event_id = e.id
                WHERE e.amo_id = :amo_id
                  AND e.starts_on >= :start_date
                  AND e.starts_on <= :end_date
                GROUP BY e.id, e.title, e.status, e.starts_on, e.ends_on, c.course_id, c.course_name
                ORDER BY e.starts_on ASC, e.created_at DESC NULLS LAST
                LIMIT :limit
            """,
            params={"amo_id": ctx.amo_id, "start_date": start_date, "end_date": end_date, "limit": source_limit},
            label="training_sessions",
            trace_id=trace_id,
            source_errors=source_errors,
            required="training" in required_sources,
            amo_id=ctx.amo_id,
            user_id=ctx.user_id,
        )
        for row in training_session_rows:
            when = row.get("event_date")
            title = row.get("title") or row.get("course_name") or row.get("course_code") or "Training session"
            participant_count = int(row.get("participant_count") or 0)
            events.append(_event("training", "training_event", row["id"], str(title), when, "training_session", f"/maintenance/{ctx.amo_code}/qms/training-competence/schedule", status_value=row.get("status"), detail=f"{participant_count} participant(s)", source="training", due_state=_due_state_for(when, today, event_type="training_session", status_value=row.get("status"))))

        training_expiry_rows = _calendar_fetch_rows(
            db,
            sql="""
                WITH latest AS (
                    SELECT DISTINCT ON (r.user_id, r.course_id)
                        r.id::text AS id,
                        r.user_id,
                        r.course_id,
                        r.valid_until AS event_date,
                        r.completion_date,
                        r.verification_status,
                        r.created_at
                    FROM training_records r
                    WHERE r.amo_id = :amo_id
                      AND r.valid_until IS NOT NULL
                    ORDER BY r.user_id, r.course_id,
                             r.completion_date DESC NULLS LAST,
                             r.valid_until DESC NULLS LAST,
                             r.created_at DESC NULLS LAST
                )
                SELECT latest.id, latest.user_id, latest.event_date, latest.verification_status,
                       u.full_name, u.staff_code,
                       c.course_id AS course_code, c.course_name
                FROM latest
                JOIN users u ON u.id = latest.user_id
                LEFT JOIN training_courses c ON c.id = latest.course_id
                WHERE u.amo_id = :amo_id
                  AND latest.event_date >= :start_date
                  AND latest.event_date <= :end_date
                ORDER BY latest.event_date ASC, u.full_name ASC
                LIMIT :limit
            """,
            params={"amo_id": ctx.amo_id, "start_date": start_date, "end_date": end_date, "limit": source_limit},
            label="training_expiry",
            trace_id=trace_id,
            source_errors=source_errors,
            required="training" in required_sources,
            amo_id=ctx.amo_id,
            user_id=ctx.user_id,
        )
        for row in training_expiry_rows:
            when = row.get("event_date")
            person = row.get("full_name") or row.get("staff_code") or row.get("user_id") or "Personnel"
            course = row.get("course_name") or row.get("course_code") or "Training"
            title = f"{person}: {course} expires"
            events.append(_event("training", "training_record", row["id"], title, when, "training_expiry", f"/maintenance/{ctx.amo_code}/qms/training-competence/people/{row['user_id']}/course-history", status_value=row.get("verification_status"), owner_label=str(person), detail=str(course), source="training", due_state=_due_state_for(when, today, event_type="training_expiry", status_value=None)))

    if want("holidays"):
        settings_row = _read_calendar_settings(db, amo_id=ctx.amo_id)
        _refresh_public_holidays_if_needed(db, amo_id=ctx.amo_id, settings_row=settings_row, start_date=start_date, end_date=end_date, trace_id=trace_id, source_errors=source_errors)
        if _qms_table_exists(db, "qms_public_holidays"):
            holiday_rows = _calendar_fetch_rows(
                db,
                sql="""
                    SELECT id::text AS id, holiday_date AS event_date, title, source_uid, source_url
                    FROM qms_public_holidays
                    WHERE amo_id = :amo_id
                      AND holiday_date >= :start_date
                      AND holiday_date <= :end_date
                    ORDER BY holiday_date ASC, title ASC
                    LIMIT :limit
                """,
                params={"amo_id": ctx.amo_id, "start_date": start_date, "end_date": end_date, "limit": source_limit},
                label="public_holidays",
                trace_id=trace_id,
                source_errors=source_errors,
                required="holidays" in required_sources,
                amo_id=ctx.amo_id,
                user_id=ctx.user_id,
            )
            for row in holiday_rows:
                when = row.get("event_date")
                events.append(_event("holidays", "public_holiday", row["id"], str(row.get("title") or "Public holiday"), when, "public_holiday", None, status_value="HOLIDAY", detail="Public holiday", source="holidays", due_state="holiday", actionable=False))

    return events, source_errors


@router.get("/calendar/{view}")
def qms_calendar_view(
    view: str,
    start: date | None = Query(None),
    end: date | None = Query(None),
    limit: int = Query(120, ge=1, le=500),
    offset: int = Query(0, ge=0, le=100_000),
    ctx: TenantContext = Depends(require_qms_permission("qms.calendar.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    source_filter = _source_filter_for_view(view)
    source = next(iter(source_filter)) if source_filter and len(source_filter) == 1 else None
    data = qms_calendar(start=start, end=end, limit=limit, offset=offset, source=source, ctx=ctx, db=db)
    data["view"] = view
    return data


@router.get("/calendar/settings")
def get_calendar_settings(
    ctx: TenantContext = Depends(require_qms_permission("qms.settings.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    calendar_context = _tenant_calendar_context(db, amo_id=ctx.amo_id)
    return {
        "tenant": {"amo_code": ctx.amo_code, "amo_id": ctx.amo_id},
        "timezone": calendar_context["timezone"],
        "country": calendar_context.get("country"),
        "settings": _read_calendar_settings(db, amo_id=ctx.amo_id),
    }


@router.patch("/calendar/settings")
def update_calendar_settings(
    payload: dict[str, Any] = Body(default_factory=dict),
    ctx: TenantContext = Depends(require_qms_permission("qms.settings.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    if not _qms_table_exists(db, "qms_calendar_settings"):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="qms_calendar_settings table is missing. Run migrations first.")
    allowed = {"holidays_enabled", "holiday_source_url", "holiday_provider", "holiday_country_code", "holiday_region_code", "cache_ttl_hours"}
    values = {key: payload[key] for key in allowed if key in payload}
    if not values:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No supported calendar settings supplied.")
    params = {"amo_id": ctx.amo_id, **values}
    set_sql = ", ".join(f"{key} = :{key}" for key in values)
    row = db.execute(
        text(f"""
            INSERT INTO qms_calendar_settings (amo_id, {', '.join(values.keys())}, created_at, updated_at)
            VALUES (:amo_id, {', '.join(':' + key for key in values)}, NOW(), NOW())
            ON CONFLICT (amo_id)
            DO UPDATE SET {set_sql}, updated_at = NOW()
            RETURNING *
        """),
        params,
    ).mappings().first()
    db.commit()
    return {"settings": dict(row) if row else _read_calendar_settings(db, amo_id=ctx.amo_id)}


@router.get("/audits")
def list_audits(
    limit: int = Query(100, ge=1, le=500),
    ctx: TenantContext = Depends(require_qms_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rows = (
        db.query(quality_models.QMSAudit)
        .filter(quality_models.QMSAudit.amo_id == ctx.amo_id)
        .order_by(quality_models.QMSAudit.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": _row_id(row),
                "audit_ref": row.audit_ref,
                "title": row.title,
                "status": _as_text(row.status),
                "kind": _as_text(row.kind),
                "planned_start": _as_date(row.planned_start),
                "planned_end": _as_date(row.planned_end),
            }
            for row in rows
        ]
    }


@router.get("/findings")
def list_findings(
    limit: int = Query(100, ge=1, le=500),
    ctx: TenantContext = Depends(require_qms_permission("qms.finding.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rows = (
        db.query(quality_models.QMSAuditFinding)
        .filter(quality_models.QMSAuditFinding.amo_id == ctx.amo_id)
        .order_by(quality_models.QMSAuditFinding.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": _row_id(row),
                "finding_ref": row.finding_ref,
                "severity": _as_text(row.severity),
                "level": _as_text(row.level),
                "description": row.description,
                "closed_at": _as_date(row.closed_at),
                "target_close_date": _as_date(row.target_close_date),
            }
            for row in rows
        ]
    }


@router.get("/cars")
def list_cars(
    limit: int = Query(100, ge=1, le=500),
    ctx: TenantContext = Depends(require_qms_permission("qms.car.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rows = (
        db.query(quality_models.CorrectiveActionRequest)
        .filter(quality_models.CorrectiveActionRequest.amo_id == ctx.amo_id)
        .order_by(quality_models.CorrectiveActionRequest.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": _row_id(row),
                "car_number": row.car_number,
                "title": row.title,
                "status": _as_text(row.status),
                "priority": _as_text(row.priority),
                "due_date": _as_date(row.due_date),
                "closed_at": _as_date(row.closed_at),
            }
            for row in rows
        ]
    }


@router.get("/documents")
def list_documents(
    limit: int = Query(100, ge=1, le=500),
    ctx: TenantContext = Depends(require_qms_permission("qms.document.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rows = (
        db.query(quality_models.QMSDocument)
        .filter(quality_models.QMSDocument.amo_id == ctx.amo_id)
        .order_by(quality_models.QMSDocument.updated_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": _row_id(row),
                "doc_code": row.doc_code,
                "title": row.title,
                "doc_type": _as_text(row.doc_type),
                "status": _as_text(row.status),
                "effective_date": _as_date(row.effective_date),
                "updated_at": _as_date(row.updated_at),
            }
            for row in rows
        ]
    }


@router.get("/training-competence/dashboard")
def training_dashboard(
    ctx: TenantContext = Depends(require_qms_permission("qms.training.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    today = date.today()
    due_soon = today + timedelta(days=30)
    total_records = db.query(training_models.TrainingRecord).filter(training_models.TrainingRecord.amo_id == ctx.amo_id).count()
    expired = db.query(training_models.TrainingRecord).filter(training_models.TrainingRecord.amo_id == ctx.amo_id, training_models.TrainingRecord.valid_until < today).count()
    expiring = db.query(training_models.TrainingRecord).filter(training_models.TrainingRecord.amo_id == ctx.amo_id, training_models.TrainingRecord.valid_until >= today, training_models.TrainingRecord.valid_until <= due_soon).count()
    return {"total_records": total_records, "expired_records": expired, "expiring_records": expiring}


@router.post("/reports/export")
def log_report_export(
    request: Request,
    ctx: TenantContext = Depends(require_qms_permission("qms.reports.export")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit_services.log_event(
        db,
        amo_id=ctx.amo_id,
        actor_user_id=ctx.user_id,
        entity_type="qms.report",
        entity_id="export",
        action="export_requested",
        metadata={
            "module": "qms",
            "ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        },
        critical=True,
    )
    db.commit()
    return {"status": "logged", "message": "Report export request was logged. Actual export generation remains with the report service."}


@router.get("/settings")
def get_qms_settings(
    ctx: TenantContext = Depends(require_qms_permission("qms.settings.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.execute(
        text("""
            SELECT id, numbering_rules, workflow_rules, approval_matrix, notification_rules,
                   retention_rules, risk_matrix, created_at, updated_at
            FROM qms_settings
            WHERE amo_id = :amo_id
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"amo_id": ctx.amo_id},
    ).mappings().first()
    return {
        "tenant": {"amo_code": ctx.amo_code, "amo_id": ctx.amo_id},
        "settings": dict(row) if row else None,
    }

# ---------------------------------------------------------------------------
# Phase 3/4 canonical QMS route registry
# ---------------------------------------------------------------------------

QMS_ROUTE_TREE: dict[str, dict[str, Any]] = {
    "cockpit": {
        "label": "QMS Cockpit",
        "path": "",
        "permission": "qms.dashboard.view",
        "children": [],
    },
    "inbox": {
        "label": "My QMS Work",
        "path": "inbox",
        "permission": "qms.inbox.view",
        "children": ["assigned-to-me", "approvals", "overdue", "watching", "completed"],
    },
    "calendar": {
        "label": "Calendar",
        "path": "calendar",
        "permission": "qms.calendar.view",
        "children": ["month", "week", "list", "audits", "cars", "training", "management-review", "regulatory-deadlines"],
    },
    "system": {
        "label": "System & Processes",
        "path": "system",
        "permission": "qms.risk.view",
        "children": [
            "overview", "qms-scope", "organization-context", "interested-parties", "process-map",
            "processes", "processes/:processId", "processes/:processId/risks",
            "processes/:processId/kpis", "processes/:processId/documents",
            "processes/:processId/audits", "quality-policy", "quality-objectives",
            "risk-register", "opportunities",
        ],
    },
    "documents": {
        "label": "Controlled Documents",
        "path": "documents",
        "permission": "qms.document.view",
        "children": [
            "library", "reader/:documentId", "reader/:documentId/sections/:sectionId",
            "change-requests", "change-requests/new", "change-requests/:changeRequestId",
            "approvals", "approval-letters", "templates", "forms", "obsolete",
            "revision-history", "distribution", "document-matrix",
        ],
    },
    "audits": {
        "label": "Audits",
        "path": "audits",
        "permission": "qms.audit.view",
        "children": [
            "dashboard", "program", "schedule", "calendar", "new", "templates", "checklists",
            "auditors", "auditor-competence", ":auditId/overview", ":auditId/planning",
            ":auditId/scope", ":auditId/team", ":auditId/notice", ":auditId/war-room",
            ":auditId/document-review", ":auditId/checklist", ":auditId/fieldwork",
            ":auditId/evidence", ":auditId/findings", ":auditId/post-brief", ":auditId/report",
            ":auditId/cars", ":auditId/follow-up", ":auditId/archive", ":auditId/activity-log",
        ],
    },
    "findings": {
        "label": "Findings",
        "path": "findings",
        "permission": "qms.finding.view",
        "children": [
            "register", "new", ":findingId/overview", ":findingId/evidence",
            ":findingId/classification", ":findingId/linked-cars",
            ":findingId/linked-documents", ":findingId/activity-log",
            "by-process", "by-severity", "by-source", "trends",
        ],
    },
    "cars": {
        "label": "CAR / CAPA",
        "path": "cars",
        "permission": "qms.car.view",
        "children": [
            "register", "new", "overdue", "due-soon", "awaiting-auditee",
            "awaiting-quality-review", "awaiting-effectiveness-review", "closed", "rejected",
            ":carId/overview", ":carId/containment", ":carId/root-cause",
            ":carId/corrective-action-plan", ":carId/implementation", ":carId/evidence",
            ":carId/quality-review", ":carId/effectiveness-review", ":carId/closure",
            ":carId/activity-log", "trends",
        ],
    },
    "risk": {
        "label": "Risk & Opportunities",
        "path": "risk",
        "permission": "qms.risk.view",
        "children": [
            "register", "new", ":riskId/overview", ":riskId/controls", ":riskId/actions",
            ":riskId/linked-findings", ":riskId/linked-audits", ":riskId/history",
            "risk-matrix", "opportunities", "treatment-plans", "trends",
        ],
    },
    "change-control": {
        "label": "Change Control",
        "path": "change-control",
        "permission": "qms.change.view",
        "children": [
            "register", "new", ":changeId/overview", ":changeId/impact-assessment",
            ":changeId/risk-assessment", ":changeId/approvals", ":changeId/implementation",
            ":changeId/post-implementation-review", ":changeId/activity-log",
            "pending-approval", "implemented", "rejected",
        ],
    },
    "training-competence": {
        "label": "Training & Competence",
        "path": "training-competence",
        "permission": "qms.training.view",
        "children": [
            "dashboard", "people", "people/:personId/profile", "people/:personId/course-history",
            "people/:personId/competence-matrix", "people/:personId/gaps",
            "people/:personId/export", "courses", "requirements", "matrix", "expiring",
            "overdue", "evaluations", "reports",
        ],
    },
    "suppliers": {
        "label": "Suppliers",
        "path": "suppliers",
        "permission": "qms.supplier.view",
        "children": [
            "approved-list", "new", ":supplierId/profile", ":supplierId/approvals",
            ":supplierId/scope", ":supplierId/evaluations", ":supplierId/audits",
            ":supplierId/findings", ":supplierId/performance", ":supplierId/documents",
            "evaluations", "supplier-audits", "supplier-findings", "performance-trends",
            "expired-approvals",
        ],
    },
    "equipment-calibration": {
        "label": "Equipment & Calibration",
        "path": "equipment-calibration",
        "permission": "qms.equipment.view",
        "children": [
            "register", "new", ":equipmentId/profile", ":equipmentId/calibration-history",
            ":equipmentId/certificates", ":equipmentId/maintenance",
            ":equipmentId/out-of-tolerance", ":equipmentId/activity-log", "due-soon",
            "overdue", "out-of-service", "reports",
        ],
    },
    "external-interface": {
        "label": "External Interface",
        "path": "external-interface",
        "permission": "qms.finding.view",
        "children": [
            "regulator-findings", "customer-complaints", "customer-feedback",
            "authority-correspondence", "responses", "commitments", "external-audits",
        ],
    },
    "management-review": {
        "label": "Management Review",
        "path": "management-review",
        "permission": "qms.management_review.view",
        "children": [
            "dashboard", "meetings", "meetings/new", "meetings/:reviewId/agenda",
            "meetings/:reviewId/inputs", "meetings/:reviewId/minutes",
            "meetings/:reviewId/decisions", "meetings/:reviewId/actions",
            "meetings/:reviewId/attachments", "meetings/:reviewId/approval",
            "actions", "open-actions", "closed-actions", "reports",
        ],
    },
    "reports": {
        "label": "Reports & Analytics",
        "path": "reports",
        "permission": "qms.reports.view",
        "children": [
            "executive-dashboard", "audit-performance", "car-performance", "finding-trends",
            "process-performance", "risk-trends", "supplier-performance", "training-compliance",
            "document-control", "management-review", "regulator-readiness", "custom-builder",
            "exports",
        ],
    },
    "evidence-vault": {
        "label": "Evidence Vault",
        "path": "evidence-vault",
        "permission": "qms.evidence.view",
        "children": [
            "search", "audit-packages", "car-packages", "document-approval-packages",
            "management-review-packages", "regulator-packages", "immutable-archive",
            "retention",
        ],
    },
    "settings": {
        "label": "QMS Settings",
        "path": "settings",
        "permission": "qms.settings.view",
        "children": [
            "general", "numbering", "workflow-rules", "approval-matrix", "roles-permissions",
            "notification-rules", "templates", "forms", "risk-matrix",
            "finding-classifications", "car-rules", "retention-rules", "integrations",
            "audit-log",
        ],
    },
}


# ---------------------------------------------------------------------------
# Phase 2 production consolidation: generic canonical QMS module endpoints
# ---------------------------------------------------------------------------

_MODULES: dict[str, dict[str, Any]] = {
    "documents": {
        "permission": "qms.document.view",
        "manage_permission": "qms.document.create",
        "default_table": "qms_documents",
        "views": {
            "library": "qms_documents",
            "reader": "qms_documents",
            "change-requests": "qms_document_change_requests",
            "approvals": "qms_document_approvals",
            "approval-letters": "qms_document_approval_letters",
            "templates": "qms_document_templates",
            "forms": "qms_form_definitions",
            "obsolete": "qms_document_obsolete_records",
            "revision-history": "qms_document_versions",
            "distribution": "qms_document_distribution",
            "document-matrix": "qms_documents",
        },
    },
    "audits": {
        "permission": "qms.audit.view",
        "manage_permission": "qms.audit.update",
        "default_table": "qms_audits",
        "views": {
            "dashboard": "qms_audits",
            "program": "qms_audit_programs",
            "schedule": "qms_audit_schedules",
            "calendar": "qms_audit_schedules",
            "templates": "qms_audit_checklists",
            "checklists": "qms_audit_checklists",
            "auditors": "qms_audit_team_members",
            "auditor-competence": "qms_audit_team_members",
            "overview": "qms_audits",
            "planning": "qms_audits",
            "scope": "qms_audit_scopes",
            "team": "qms_audit_team_members",
            "notice": "qms_audit_notices",
            "war-room": "qms_audit_war_room_files",
            "document-review": "qms_audit_evidence",
            "checklist": "qms_audit_checklists",
            "fieldwork": "qms_audit_evidence",
            "evidence": "qms_audit_evidence",
            "findings": "qms_audit_findings",
            "post-brief": "qms_audit_post_briefs",
            "report": "qms_audit_reports",
            "cars": "quality_cars",
            "follow-up": "qms_corrective_actions",
            "archive": "qms_audit_archives",
            "activity-log": "qms_activity_logs",
        },
    },
    "findings": {
        "permission": "qms.finding.view",
        "manage_permission": "qms.finding.create",
        "default_table": "qms_audit_findings",
        "views": {
            "register": "qms_audit_findings",
            "overview": "qms_audit_findings",
            "evidence": "qms_finding_evidence",
            "classification": "qms_finding_classifications",
            "linked-cars": "quality_cars",
            "linked-documents": "qms_documents",
            "activity-log": "qms_activity_logs",
            "by-process": "qms_audit_findings",
            "by-severity": "qms_audit_findings",
            "by-source": "qms_audit_findings",
            "trends": "qms_audit_findings",
        },
    },
    "cars": {
        "permission": "qms.car.view",
        "manage_permission": "qms.car.issue",
        "default_table": "quality_cars",
        "views": {
            "register": "quality_cars",
            "new": "quality_cars",
            "overdue": "quality_cars",
            "due-soon": "quality_cars",
            "awaiting-auditee": "quality_cars",
            "awaiting-quality-review": "quality_cars",
            "awaiting-effectiveness-review": "quality_cars",
            "closed": "quality_cars",
            "rejected": "quality_cars",
            "overview": "quality_cars",
            "containment": "qms_car_containment_actions",
            "root-cause": "qms_car_root_causes",
            "corrective-action-plan": "qms_car_corrective_action_plans",
            "implementation": "qms_car_action_items",
            "evidence": "qms_car_evidence",
            "quality-review": "qms_car_reviews",
            "effectiveness-review": "qms_car_effectiveness_reviews",
            "closure": "qms_car_closure_records",
            "activity-log": "qms_activity_logs",
            "trends": "quality_cars",
        },
    },
    "training-competence": {
        "permission": "qms.training.view",
        "manage_permission": "qms.training.manage",
        "default_table": "training_records",
        "views": {
            "dashboard": "training_records",
            "people": "users",
            "profile": "users",
            "course-history": "training_records",
            "competence-matrix": "qms_competence_matrix",
            "gaps": "qms_competence_gaps",
            "courses": "training_courses",
            "requirements": "training_requirements",
            "matrix": "qms_competence_matrix",
            "expiring": "training_records",
            "overdue": "training_records",
            "evaluations": "qms_training_evaluations",
            "reports": "training_records",
        },
    },
    "system": {
        "permission": "qms.risk.view",
        "manage_permission": "qms.risk.manage",
        "default_table": "qms_processes",
        "views": {
            "overview": "qms_processes",
            "processes": "qms_processes",
            "quality-objectives": "qms_quality_objectives",
            "risk-register": "qms_risks",
            "opportunities": "qms_opportunities",
        },
    },
    "risk": {
        "permission": "qms.risk.view",
        "manage_permission": "qms.risk.manage",
        "default_table": "qms_risks",
        "views": {
            "register": "qms_risks",
            "treatment-plans": "qms_risk_actions",
            "actions": "qms_risk_actions",
            "opportunities": "qms_opportunities",
            "risk-matrix": "qms_settings",
            "trends": "qms_risks",
        },
    },
    "change-control": {
        "permission": "qms.change.view",
        "manage_permission": "qms.change.manage",
        "default_table": "qms_change_controls",
        "views": {
            "register": "qms_change_controls",
            "pending-approval": "qms_change_controls",
            "implemented": "qms_change_controls",
            "rejected": "qms_change_controls",
        },
    },
    "suppliers": {
        "permission": "qms.supplier.view",
        "manage_permission": "qms.supplier.manage",
        "default_table": "qms_suppliers",
        "views": {
            "approved-list": "qms_suppliers",
            "evaluations": "qms_supplier_evaluations",
            "supplier-audits": "qms_supplier_audits",
            "supplier-findings": "qms_supplier_findings",
            "performance-trends": "qms_supplier_performance_scores",
            "expired-approvals": "qms_supplier_approvals",
        },
    },
    "equipment-calibration": {
        "permission": "qms.equipment.view",
        "manage_permission": "qms.equipment.manage",
        "default_table": "qms_equipment",
        "views": {
            "register": "qms_equipment",
            "calibration-history": "qms_calibration_records",
            "certificates": "qms_calibration_certificates",
            "out-of-tolerance": "qms_out_of_tolerance_events",
            "due-soon": "qms_calibration_records",
            "overdue": "qms_calibration_records",
            "out-of-service": "qms_equipment",
            "reports": "qms_calibration_records",
        },
    },
    "external-interface": {
        "permission": "qms.finding.view",
        "manage_permission": "qms.finding.create",
        "default_table": "qms_external_items",
        "views": {
            "regulator-findings": "qms_regulator_findings",
            "customer-complaints": "qms_customer_complaints",
            "customer-feedback": "qms_customer_feedback",
            "authority-correspondence": "qms_authority_correspondence",
            "responses": "qms_external_responses",
            "commitments": "qms_external_commitments",
            "external-audits": "qms_external_audits",
        },
    },
    "management-review": {
        "permission": "qms.management_review.view",
        "manage_permission": "qms.management_review.manage",
        "default_table": "qms_management_reviews",
        "views": {
            "dashboard": "qms_management_reviews",
            "meetings": "qms_management_reviews",
            "inputs": "qms_management_review_inputs",
            "minutes": "qms_management_review_minutes",
            "decisions": "qms_management_review_decisions",
            "actions": "qms_management_review_actions",
            "open-actions": "qms_management_review_actions",
            "closed-actions": "qms_management_review_actions",
            "reports": "qms_management_reviews",
        },
    },
    "reports": {
        "permission": "qms.reports.view",
        "manage_permission": "qms.reports.export",
        "default_table": "qms_report_exports",
        "views": {
            "executive-dashboard": "qms_dashboard_widgets",
            "audit-performance": "qms_report_exports",
            "car-performance": "qms_report_exports",
            "finding-trends": "qms_report_exports",
            "process-performance": "qms_report_exports",
            "risk-trends": "qms_report_exports",
            "supplier-performance": "qms_report_exports",
            "training-compliance": "qms_report_exports",
            "document-control": "qms_report_exports",
            "management-review": "qms_report_exports",
            "regulator-readiness": "qms_report_exports",
            "custom-builder": "qms_report_definitions",
            "exports": "qms_report_exports",
        },
    },
    "evidence-vault": {
        "permission": "qms.evidence.view",
        "manage_permission": "qms.evidence.archive",
        "default_table": "qms_archive_packages",
        "views": {
            "search": "qms_evidence_files",
            "audit-packages": "qms_archive_packages",
            "car-packages": "qms_archive_packages",
            "document-approval-packages": "qms_archive_packages",
            "management-review-packages": "qms_archive_packages",
            "regulator-packages": "qms_archive_packages",
            "immutable-archive": "qms_archive_packages",
            "retention": "qms_retention_rules",
            "files": "qms_evidence_files",
        },
    },
    "settings": {
        "permission": "qms.settings.view",
        "manage_permission": "qms.settings.manage",
        "default_table": "qms_settings",
        "views": {
            "general": "qms_settings",
            "numbering": "qms_numbering_rules",
            "workflow-rules": "qms_workflow_rules",
            "approval-matrix": "qms_approval_matrix",
            "roles-permissions": "qms_settings",
            "notification-rules": "qms_notification_rules",
            "templates": "qms_templates",
            "forms": "qms_form_definitions",
            "risk-matrix": "qms_settings",
            "finding-classifications": "qms_finding_classifications",
            "car-rules": "qms_workflow_rules",
            "retention-rules": "qms_retention_rules",
            "integrations": "qms_settings",
            "audit-log": "qms_activity_logs",
        },
    },
}

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_identifier(name: str) -> str:
    if not _IDENTIFIER_RE.match(name):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsafe database identifier.")
    return name


def _module_config(module: str) -> dict[str, Any]:
    try:
        return _MODULES[module]
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown QMS module '{module}'.")


def _resolve_view(module: str, parts: list[str]) -> str | None:
    """Resolve the semantic view/action from a nested QMS URL.

    Examples:
    - cars/overdue -> overdue
    - cars/{carId}/root-cause -> root-cause
    - documents/reader/{documentId}/sections/{sectionId} -> reader
    """
    config = _module_config(module)
    views = set(config.get("views", {}).keys())
    for part in parts:
        if part in {"new"}:
            return None
        if part in views:
            return part
    return None


def _resolve_table(module: str, view: str | None = None) -> str:
    config = _module_config(module)
    table = config.get("views", {}).get(view or "", config["default_table"])
    return _safe_identifier(str(table))


def _record_id_from_parts(parts: list[str], table: str, module: str | None = None) -> str | None:
    skip = {
        "overview", "profile", "history", "actions", "documents", "audits", "findings",
        "approvals", "scope", "performance", "activity-log", "register", "dashboard",
        "new", "reports", "trends", "search", "retention", "approved-list", "evaluations",
        "supplier-audits", "supplier-findings", "performance-trends", "expired-approvals",
        "pending-approval", "implemented", "rejected", "overdue", "due-soon",
        "awaiting-auditee", "awaiting-quality-review", "awaiting-effectiveness-review",
        "closed", "open-actions", "closed-actions", "templates", "checklists",
        "auditors", "auditor-competence", "library", "reader", "sections", "forms",
        "obsolete", "revision-history", "distribution", "document-matrix", "month",
        "week", "list", "training", "management-review", "regulatory-deadlines",
    }
    if module and module in _MODULES:
        skip.update(_MODULES[module].get("views", {}).keys())
    for part in parts:
        if part in skip:
            continue
        if re.fullmatch(r"[0-9a-fA-F-]{32,36}", part) or part.startswith("ID-") or len(part) >= 18:
            return part
    return None


def _json_value(value: Any) -> str:
    return json.dumps(value, default=str)


def _is_postgres(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _ensure_postgres(db: Session) -> None:
    if not _is_postgres(db):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Canonical QMS modules require PostgreSQL.")


def _check_permission(ctx: TenantContext, db: Session, permission: str) -> None:
    # Superuser and the dependency-based high-risk paths are handled before this helper.
    # For generic endpoints we deliberately fail closed when called outside the router dependency.
    return None


def _table_columns(db: Session, table: str) -> set[str]:
    _ensure_postgres(db)
    cached = _TABLE_COLUMNS_CACHE.get(table)
    if cached is not None:
        return cached
    rows = db.execute(
        text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table
        """),
        {"table": table},
    ).scalars().all()
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"QMS table '{table}' is missing. Run the canonical QMS migration before using this module.",
        )
    columns = set(rows)
    _TABLE_COLUMNS_CACHE[table] = columns
    return columns


def _sort_column(columns: set[str]) -> str:
    for candidate in ("updated_at", "created_at", "due_date", "planned_start", "valid_until", "id"):
        if candidate in columns:
            return candidate
    return sorted(columns)[0]


def _select_columns(columns: set[str]) -> list[str]:
    preferred = [
        "id", "audit_ref", "car_number", "finding_ref", "doc_code", "course_code", "reference",
        "title", "name", "message", "description", "summary", "status", "severity", "kind", "doc_type",
        "owner_user_id", "lead_auditor_user_id", "assigned_to_user_id", "user_id",
        "planned_start", "planned_end", "due_date", "valid_until", "effective_date",
        "created_at", "updated_at", "closed_at", "read_at",
    ]
    selected = [column for column in preferred if column in columns]
    if "payload" in columns:
        selected.append("payload")
    if not selected and "id" in columns:
        selected.append("id")
    return selected[:24]


def _select_records(
    db: Session,
    *,
    table: str,
    amo_id: str,
    record_id: str | None,
    limit: int,
    offset: int = 0,
    view: str | None = None,
    q: str | None = None,
    status_filter: str | None = None,
) -> dict[str, Any]:
    columns = _table_columns(db, table)
    order_column = _sort_column(columns)
    projected_columns = _select_columns(columns)
    where = ["amo_id = :amo_id"] if "amo_id" in columns else ["1 = 1"]
    if "deleted_at" in columns:
        where.append("deleted_at IS NULL")
    bounded_limit = max(1, min(limit, 50))
    bounded_offset = max(0, min(offset, 100_000))
    params: dict[str, Any] = {"amo_id": amo_id, "limit": bounded_limit + 1, "offset": bounded_offset}
    if record_id and "id" in columns:
        where.append("id = :record_id")
        params["record_id"] = record_id
    if q:
        searchable = [column for column in ("title", "name", "message", "description", "summary", "audit_ref", "car_number", "finding_ref", "doc_code", "reference") if column in columns]
        if searchable:
            where.append("(" + " OR ".join(f"CAST({column} AS TEXT) ILIKE :q" for column in searchable) + ")")
            params["q"] = f"%{q[:80]}%"
    if status_filter and "status" in columns:
        where.append("status = :status_filter")
        params["status_filter"] = status_filter.upper().replace(" ", "_")
    today = date.today()
    due_soon = today + timedelta(days=30)
    if view in {"pending-approval"} and "status" in columns:
        where.append("status IN ('PENDING_APPROVAL', 'DRAFT', 'OPEN')")
    elif view in {"awaiting-auditee", "awaiting-quality-review", "awaiting-effectiveness-review"} and "status" in columns:
        where.append("status IN ('AWAITING_AUDITEE', 'AWAITING_QUALITY_REVIEW', 'AWAITING_EFFECTIVENESS_REVIEW', 'PENDING_REVIEW', 'OPEN')")
    elif view in {"implemented", "closed", "closed-actions"} and "status" in columns:
        where.append("status IN ('IMPLEMENTED', 'CLOSED', 'APPROVED', 'COMPLETE', 'COMPLETED')")
    elif view in {"rejected"} and "status" in columns:
        where.append("status = 'REJECTED'")
    elif view in {"open-actions"} and "status" in columns:
        where.append("status NOT IN ('CLOSED', 'COMPLETE', 'COMPLETED', 'REJECTED', 'CANCELLED')")
    due_column = "due_date" if "due_date" in columns else "valid_until" if "valid_until" in columns else None
    if view == "overdue" and due_column:
        where.append(f"{due_column} < :today")
        params["today"] = today
    elif view in {"due-soon", "expiring", "expired-approvals"} and due_column:
        where.append(f"{due_column} >= :today AND {due_column} <= :due_soon")
        params["today"] = today
        params["due_soon"] = due_soon
    select_sql = ", ".join(_safe_identifier(column) for column in projected_columns) or "id"
    sql = f"""
        SELECT {select_sql}
        FROM {_safe_identifier(table)}
        WHERE {' AND '.join(where)}
        ORDER BY {_safe_identifier(order_column)} DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """
    rows = [dict(row) for row in db.execute(text(sql), params).mappings().all()]
    has_more = len(rows) > bounded_limit
    if has_more:
        rows = rows[:bounded_limit]
    return {
        "items": rows,
        "limit": bounded_limit,
        "offset": bounded_offset,
        "next_offset": bounded_offset + bounded_limit if has_more else None,
        "has_more": has_more,
        "columns": projected_columns,
    }


def _insert_record(db: Session, *, table: str, amo_id: str, actor_user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    columns = _table_columns(db, table)
    record_id = str(uuid.uuid4())
    payload_data = payload.get("payload") if isinstance(payload.get("payload"), dict) else {
        key: value for key, value in payload.items()
        if key not in {"title", "name", "status", "owner_user_id", "due_date", "description", "source_type"}
    }
    values: dict[str, Any] = {
        "id": record_id,
        "amo_id": amo_id,
        "created_by": actor_user_id,
        "updated_by": actor_user_id,
    }
    for key in ("title", "name", "status", "owner_user_id", "due_date", "description", "source_type", "file_name", "file_path", "storage_path", "sha256", "mime_type", "size_bytes"):
        if key in columns and key in payload:
            values[key] = payload[key]
    if "payload" in columns:
        values["payload"] = _json_value(payload_data)
    insert_cols = [key for key in values if key in columns]
    placeholders = [f":{key}" if key != "payload" else "CAST(:payload AS jsonb)" for key in insert_cols]
    sql = f"INSERT INTO {_safe_identifier(table)} ({', '.join(insert_cols)}) VALUES ({', '.join(placeholders)}) RETURNING *"
    row = db.execute(text(sql), values).mappings().first()
    return dict(row) if row else {"id": record_id}


def _update_record(db: Session, *, table: str, amo_id: str, actor_user_id: str, record_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    columns = _table_columns(db, table)
    allowed = {"title", "name", "status", "owner_user_id", "due_date", "description", "source_type", "file_name", "file_path", "storage_path", "sha256", "mime_type", "size_bytes", "payload"}
    updates = []
    params: dict[str, Any] = {"id": record_id, "amo_id": amo_id, "updated_by": actor_user_id}
    for key, value in payload.items():
        if key not in allowed or key not in columns:
            continue
        params[key] = _json_value(value) if key == "payload" else value
        updates.append(f"{key} = CAST(:{key} AS jsonb)" if key == "payload" else f"{key} = :{key}")
    if "updated_at" in columns:
        updates.append("updated_at = NOW()")
    if "updated_by" in columns:
        updates.append("updated_by = :updated_by")
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No supported fields supplied for update.")
    sql = f"UPDATE {_safe_identifier(table)} SET {', '.join(updates)} WHERE id = :id AND amo_id = :amo_id RETURNING *"
    row = db.execute(text(sql), params).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record was not found in this tenant.")
    return dict(row)


def _soft_delete_record(db: Session, *, table: str, amo_id: str, actor_user_id: str, record_id: str) -> dict[str, Any]:
    columns = _table_columns(db, table)
    if "deleted_at" not in columns:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This table does not support soft deletion.")
    sql = f"""
        UPDATE {_safe_identifier(table)}
        SET deleted_at = NOW(), updated_at = NOW(), updated_by = :actor_user_id
        WHERE id = :id AND amo_id = :amo_id
        RETURNING id, deleted_at
    """
    row = db.execute(text(sql), {"id": record_id, "amo_id": amo_id, "actor_user_id": actor_user_id}).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record was not found in this tenant.")
    return dict(row)


def _log_qms_activity(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
    action: str,
    module: str,
    entity_type: str,
    entity_id: str,
    previous_value: Any = None,
    new_value: Any = None,
    request: Request | None = None,
) -> None:
    if not _is_postgres(db):
        return
    db.execute(
        text("""
            INSERT INTO qms_activity_logs
                (id, amo_id, actor_user_id, action, module, entity_type, entity_id,
                 previous_value, new_value, ip_address, user_agent, created_at)
            VALUES
                (:id, :amo_id, :actor_user_id, :action, :module, :entity_type, :entity_id,
                 CAST(:previous_value AS jsonb), CAST(:new_value AS jsonb), :ip_address, :user_agent, NOW())
        """),
        {
            "id": str(uuid.uuid4()),
            "amo_id": amo_id,
            "actor_user_id": actor_user_id,
            "action": action,
            "module": module,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "previous_value": _json_value(previous_value),
            "new_value": _json_value(new_value),
            "ip_address": request.client.host if request and request.client else None,
            "user_agent": request.headers.get("user-agent") if request else None,
        },
    )


@router.get("/activity-log")
def qms_activity_log(
    limit: int = Query(100, ge=1, le=500),
    ctx: TenantContext = Depends(require_qms_permission("qms.settings.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rows = _select_records(db, table="qms_activity_logs", amo_id=ctx.amo_id, record_id=None, limit=limit)
    return {"module": "activity-log", "items": rows}



@router.get("/route-map")
def qms_route_map(
    ctx: TenantContext = Depends(require_qms_permission("qms.dashboard.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    modules: list[dict[str, Any]] = []
    for key, meta in QMS_ROUTE_TREE.items():
        permission = str(meta["permission"])
        if has_qms_permission(db, ctx, permission):
            modules.append(
                {
                    "key": key,
                    "label": meta["label"],
                    "path": meta["path"],
                    "permission": permission,
                    "children": list(meta.get("children", [])),
                }
            )
    return {
        "base_path": f"/maintenance/{ctx.amo_code}/qms",
        "api_base_path": f"/api/maintenance/{ctx.amo_code}/qms",
        "tenant": {"amo_code": ctx.amo_code, "amo_id": ctx.amo_id},
        "modules": modules,
    }


@router.patch("/settings")
def update_qms_settings(
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
    ctx: TenantContext = Depends(require_qms_permission("qms.settings.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    current = db.execute(text("SELECT id FROM qms_settings WHERE amo_id = :amo_id ORDER BY created_at DESC LIMIT 1"), {"amo_id": ctx.amo_id}).mappings().first()
    allowed = {
        "numbering_rules",
        "workflow_rules",
        "approval_matrix",
        "notification_rules",
        "retention_rules",
        "risk_matrix",
    }
    values = {key: _json_value(payload.get(key, {})) for key in allowed if key in payload}
    if not values:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No supported settings fields supplied.")
    if current:
        sets = ", ".join([f"{key} = CAST(:{key} AS jsonb)" for key in values] + ["updated_at = NOW()", "updated_by = :updated_by"])
        values.update({"id": current["id"], "amo_id": ctx.amo_id, "updated_by": ctx.user_id})
        row = db.execute(text(f"UPDATE qms_settings SET {sets} WHERE id = :id AND amo_id = :amo_id RETURNING *"), values).mappings().first()
    else:
        record_id = str(uuid.uuid4())
        insert_cols = ["id", "amo_id", "created_by", "updated_by"] + list(values.keys())
        insert_values = [":id", ":amo_id", ":created_by", ":updated_by"] + [f"CAST(:{key} AS jsonb)" for key in values.keys()]
        values.update({"id": record_id, "amo_id": ctx.amo_id, "created_by": ctx.user_id, "updated_by": ctx.user_id})
        row = db.execute(text(f"INSERT INTO qms_settings ({', '.join(insert_cols)}) VALUES ({', '.join(insert_values)}) RETURNING *"), values).mappings().first()
    _log_qms_activity(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id, action="settings_changed", module="settings", entity_type="qms_settings", entity_id=str(row["id"]), new_value=dict(row), request=request)
    db.commit()
    return {"settings": dict(row)}



@router.get("/evidence-vault/files/{file_id}/download")
def download_evidence_file(
    file_id: str,
    request: Request,
    ctx: TenantContext = Depends(require_qms_permission("qms.evidence.download")),
    db: Session = Depends(get_write_db),
):
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.execute(
        text("""
            SELECT id, title, name, payload
            FROM qms_evidence_files
            WHERE id = :file_id
              AND amo_id = :amo_id
              AND deleted_at IS NULL
            LIMIT 1
        """),
        {"file_id": file_id, "amo_id": ctx.amo_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence file was not found in this tenant.")

    payload = row.get("payload") or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    raw_path = payload.get("file_path") or payload.get("storage_path")
    if not raw_path:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Evidence file metadata has no storage path.")

    storage_root = FsPath(os.getenv("QMS_STORAGE_ROOT", "/storage/tenants")).resolve()
    candidate = FsPath(str(raw_path)).resolve()
    if storage_root not in candidate.parents and candidate != storage_root:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Evidence file path is outside the configured tenant storage root.")
    expected_segment = FsPath(str(ctx.amo_id))
    if str(ctx.amo_id) not in candidate.parts:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Evidence file path is not tenant scoped.")
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence file is missing from storage.")

    _log_qms_activity(
        db,
        amo_id=ctx.amo_id,
        actor_user_id=ctx.user_id,
        action="file_downloaded",
        module="evidence-vault",
        entity_type="qms_evidence_files",
        entity_id=file_id,
        new_value={"file_path": str(candidate)},
        request=request,
    )
    db.execute(
        text("""
            INSERT INTO qms_file_access_logs
                (id, amo_id, title, name, status, source_type, payload, created_by, created_at)
            VALUES
                (:id, :amo_id, :title, :name, 'DOWNLOADED', 'evidence_file',
                 CAST(:payload AS jsonb), :created_by, NOW())
        """),
        {
            "id": str(uuid.uuid4()),
            "amo_id": ctx.amo_id,
            "title": str(row.get("title") or row.get("name") or file_id),
            "name": str(row.get("name") or row.get("title") or file_id),
            "payload": _json_value({"file_id": file_id, "file_path": str(candidate), "ip": request.client.host if request.client else None}),
            "created_by": ctx.user_id,
        },
    )
    db.commit()
    return FileResponse(path=str(candidate), filename=str(row.get("name") or row.get("title") or candidate.name))



_WORKFLOW_ACTIONS: dict[tuple[str, str], dict[str, Any]] = {
    ("audits", "issue-notice"): {
        "permission": "qms.audit.update",
        "table": "qms_audit_notices",
        "action": "audit_notice_issued",
    },
    ("audits", "complete-fieldwork"): {
        "permission": "qms.audit.execute",
        "table": "qms_audit_evidence",
        "action": "audit_fieldwork_completed",
        "parent_table": "qms_audits",
        "parent_status": "IN_PROGRESS",
    },
    ("audits", "generate-report"): {
        "permission": "qms.audit.report.generate",
        "table": "qms_audit_reports",
        "action": "audit_report_generated",
    },
    ("audits", "archive"): {
        "permission": "qms.audit.archive",
        "table": "qms_audit_archives",
        "action": "audit_archived",
        "parent_table": "qms_audits",
        "parent_status": "CLOSED",
    },
    ("cars", "submit-root-cause"): {
        "permission": "qms.car.respond",
        "table": "qms_car_root_causes",
        "action": "car_root_cause_submitted",
        "parent_table": "quality_cars",
        "parent_status": "IN_PROGRESS",
    },
    ("cars", "submit-corrective-action"): {
        "permission": "qms.car.respond",
        "table": "qms_car_corrective_action_plans",
        "action": "car_corrective_action_submitted",
        "parent_table": "quality_cars",
        "parent_status": "IN_PROGRESS",
    },
    ("cars", "review"): {
        "permission": "qms.car.review",
        "table": "qms_car_reviews",
        "action": "car_reviewed",
        "parent_table": "quality_cars",
        "parent_status": "PENDING_VERIFICATION",
    },
    ("cars", "effectiveness-review"): {
        "permission": "qms.car.review",
        "table": "qms_car_effectiveness_reviews",
        "action": "car_effectiveness_reviewed",
        "parent_table": "quality_cars",
        "parent_status": "PENDING_VERIFICATION",
    },
    ("cars", "close"): {
        "permission": "qms.car.close",
        "table": "qms_car_closure_records",
        "action": "car_closed",
        "parent_table": "quality_cars",
        "parent_status": "CLOSED",
    },
    ("cars", "reject"): {
        "permission": "qms.car.reject",
        "table": "qms_car_rejections",
        "action": "car_rejected",
        "parent_table": "quality_cars",
        "parent_status": "ESCALATED",
    },
    ("documents", "versions"): {
        "permission": "qms.document.create",
        "table": "qms_document_versions",
        "action": "document_version_uploaded",
    },
    ("documents", "submit-approval"): {
        "permission": "qms.document.review",
        "table": "qms_document_approvals",
        "action": "document_approval_submitted",
        "parent_table": "qms_documents",
        "parent_status": "DRAFT",
    },
    ("documents", "approve"): {
        "permission": "qms.document.approve",
        "table": "qms_document_approvals",
        "action": "document_approved",
        "parent_table": "qms_documents",
        "parent_status": "ACTIVE",
    },
    ("documents", "publish"): {
        "permission": "qms.document.publish",
        "table": "qms_document_versions",
        "action": "document_published",
        "parent_table": "qms_documents",
        "parent_status": "ACTIVE",
    },
    ("documents", "obsolete"): {
        "permission": "qms.document.archive",
        "table": "qms_document_obsolete_records",
        "action": "document_obsoleted",
        "parent_table": "qms_documents",
        "parent_status": "OBSOLETE",
    },
}


def _update_parent_status(
    db: Session,
    *,
    table: str,
    amo_id: str,
    record_id: str,
    status_value: str,
    actor_user_id: str,
) -> dict[str, Any] | None:
    columns = _table_columns(db, table)
    if "status" not in columns:
        return None
    updates = ["status = :status"]
    params: dict[str, Any] = {
        "id": record_id,
        "amo_id": amo_id,
        "status": status_value,
        "updated_by": actor_user_id,
    }
    if "updated_at" in columns:
        updates.append("updated_at = NOW()")
    if "updated_by" in columns:
        updates.append("updated_by = :updated_by")
    row = db.execute(
        text(
            f"UPDATE {_safe_identifier(table)} SET {', '.join(updates)} "
            "WHERE id = :id AND amo_id = :amo_id RETURNING *"
        ),
        params,
    ).mappings().first()
    return dict(row) if row else None


@router.post("/{module}/{record_id}/{action}")
def qms_workflow_action(
    module: str,
    record_id: str,
    action: str,
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
    ctx: TenantContext = Depends(resolve_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    action_config = _WORKFLOW_ACTIONS.get((module, action))
    if not action_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unsupported QMS workflow action.")
    assert_qms_permission(db, ctx, str(action_config["permission"]))
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)

    table = str(action_config["table"])
    action_payload = dict(payload)
    action_payload.setdefault("source_type", module)
    action_payload.setdefault("title", action.replace("-", " ").title())
    action_payload["payload"] = {
        **(payload.get("payload") if isinstance(payload.get("payload"), dict) else {}),
        "parent_module": module,
        "parent_record_id": record_id,
        "workflow_action": action,
    }
    row = _insert_record(db, table=table, amo_id=ctx.amo_id, actor_user_id=ctx.user_id, payload=action_payload)

    parent_update = None
    parent_table = action_config.get("parent_table")
    parent_status = action_config.get("parent_status")
    if parent_table and parent_status:
        parent_update = _update_parent_status(
            db,
            table=str(parent_table),
            amo_id=ctx.amo_id,
            record_id=record_id,
            status_value=str(parent_status),
            actor_user_id=ctx.user_id,
        )

    _log_qms_activity(
        db,
        amo_id=ctx.amo_id,
        actor_user_id=ctx.user_id,
        action=str(action_config["action"]),
        module=module,
        entity_type=table,
        entity_id=str(row.get("id")),
        new_value={"workflow_record": row, "parent_update": parent_update},
        request=request,
    )
    db.commit()
    return {
        "module": module,
        "record_id": record_id,
        "action": action,
        "table": table,
        "workflow_record": row,
        "parent_update": parent_update,
    }


@router.get("/{module_path:path}")
def generic_qms_get(
    module_path: str,
    limit: int = Query(25, ge=1, le=50),
    offset: int = Query(0, ge=0, le=100_000),
    q: str | None = Query(None, max_length=80),
    status_filter: str | None = Query(None, alias="status", max_length=40),
    ctx: TenantContext = Depends(resolve_tenant_context),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    started = time.perf_counter()
    trace_id = uuid.uuid4().hex[:12]
    parts = [part for part in module_path.split("/") if part]
    if not parts:
        assert_qms_permission(db, ctx, "qms.dashboard.view")
        return qms_dashboard(ctx=ctx, db=db)
    module = parts[0]
    config = _module_config(module)
    assert_qms_permission(db, ctx, str(config["permission"]))
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    view = _resolve_view(module, parts[1:])
    table = _resolve_table(module, view)
    record_id = _record_id_from_parts(parts[1:], table, module)
    logger.info(
        "QMS module read started trace_id=%s amo=%s module=%s view=%s table=%s limit=%s offset=%s",
        trace_id, ctx.amo_code, module, view or "default", table, limit, offset,
    )
    try:
        if _is_postgres(db):
            db.execute(text("SET LOCAL statement_timeout = '12000ms'"))
        page = _select_records(
            db,
            table=table,
            amo_id=ctx.amo_id,
            record_id=record_id,
            limit=limit,
            offset=offset,
            view=view,
            q=q,
            status_filter=status_filter,
        )
        table_missing = False
        warning = None
    except HTTPException as exc:
        detail = str(exc.detail)
        if exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE and "QMS table" in detail and "is missing" in detail:
            page = {"items": [], "limit": max(1, min(limit, 50)), "offset": offset, "next_offset": None, "has_more": False, "columns": []}
            table_missing = True
            warning = detail
            logger.warning("QMS module read missing table trace_id=%s table=%s detail=%s", trace_id, table, detail)
        else:
            logger.exception("QMS module read failed trace_id=%s module=%s view=%s", trace_id, module, view or "default")
            raise
    except Exception as exc:
        logger.exception("QMS module read crashed trace_id=%s module=%s view=%s table=%s", trace_id, module, view or "default", table)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"QMS read failed for {module}/{view or 'default'} before a usable response was returned. Trace {trace_id}: {exc}",
        ) from exc
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info(
        "QMS module read finished trace_id=%s amo=%s module=%s view=%s rows=%s elapsed_ms=%s",
        trace_id, ctx.amo_code, module, view or "default", len(page.get("items", [])), elapsed_ms,
    )
    return {
        "module": module,
        "view": view or "default",
        "table": table,
        "record_id": record_id,
        "tenant": {"amo_code": ctx.amo_code, "amo_id": ctx.amo_id},
        "items": page["items"],
        "limit": page["limit"],
        "offset": page["offset"],
        "next_offset": page["next_offset"],
        "has_more": page["has_more"],
        "columns": page["columns"],
        "table_missing": table_missing,
        "warning": warning,
        "trace_id": trace_id,
        "elapsed_ms": elapsed_ms,
        "applied_filters": {"q": q or "", "status": status_filter or ""},
    }


@router.post("/{module_path:path}")
def generic_qms_create(
    module_path: str,
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
    ctx: TenantContext = Depends(resolve_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    parts = [part for part in module_path.split("/") if part]
    if not parts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="QMS module is required.")
    module = parts[0]
    config = _module_config(module)
    assert_qms_permission(db, ctx, str(config.get("manage_permission") or config["permission"]))
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    view = _resolve_view(module, parts[1:])
    table = _resolve_table(module, view)
    row = _insert_record(db, table=table, amo_id=ctx.amo_id, actor_user_id=ctx.user_id, payload=payload)
    _log_qms_activity(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id, action="record_created", module=module, entity_type=table, entity_id=str(row.get("id")), new_value=row, request=request)
    db.commit()
    return {"module": module, "table": table, "record": row}


@router.patch("/{module_path:path}")
def generic_qms_update(
    module_path: str,
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
    ctx: TenantContext = Depends(resolve_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    parts = [part for part in module_path.split("/") if part]
    if len(parts) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Record id is required.")
    module = parts[0]
    config = _module_config(module)
    assert_qms_permission(db, ctx, str(config.get("manage_permission") or config["permission"]))
    view = _resolve_view(module, parts[1:])
    table = _resolve_table(module, view)
    record_id = _record_id_from_parts(parts[1:], table, module)
    if not record_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Record id is required.")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    before_page = _select_records(db, table=table, amo_id=ctx.amo_id, record_id=record_id, limit=1)
    before = before_page.get("items", [])
    row = _update_record(db, table=table, amo_id=ctx.amo_id, actor_user_id=ctx.user_id, record_id=record_id, payload=payload)
    _log_qms_activity(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id, action="record_updated", module=module, entity_type=table, entity_id=record_id, previous_value=before[0] if before else None, new_value=row, request=request)
    db.commit()
    return {"module": module, "table": table, "record": row}


@router.delete("/{module_path:path}")
def generic_qms_delete(
    module_path: str,
    request: Request,
    ctx: TenantContext = Depends(resolve_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    parts = [part for part in module_path.split("/") if part]
    if len(parts) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Record id is required.")
    module = parts[0]
    config = _module_config(module)
    assert_qms_permission(db, ctx, str(config.get("manage_permission") or "qms.settings.manage"))
    view = _resolve_view(module, parts[1:])
    table = _resolve_table(module, view)
    record_id = _record_id_from_parts(parts[1:], table, module)
    if not record_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Record id is required.")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = _soft_delete_record(db, table=table, amo_id=ctx.amo_id, actor_user_id=ctx.user_id, record_id=record_id)
    _log_qms_activity(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id, action="record_deleted", module=module, entity_type=table, entity_id=record_id, new_value=row, request=request)
    db.commit()
    return {"module": module, "table": table, "deleted": row}
