from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import ReadSessionLocal, get_read_db

from . import models as platform_models
from . import saas_services, services
from .router import require_platform_superuser


router = APIRouter(prefix="/console", tags=["platform-superadmin-console"])

SNAPSHOT_INTERVAL_SECONDS = 10
POLL_INTERVAL_SECONDS = 2
MAX_EVENT_BATCH = 100


NAVIGATION_RESULTS: tuple[dict[str, str], ...] = (
    {"id": "overview", "title": "Platform overview", "subtitle": "Health, work queue and platform status", "path": "/platform/control"},
    {"id": "tenants", "title": "Tenants & institutions", "subtitle": "Tenant lifecycle, access and module controls", "path": "/platform/tenants"},
    {"id": "users", "title": "Global user hub", "subtitle": "Users, sessions and account controls", "path": "/platform/users"},
    {"id": "billing", "title": "Subscription & billing", "subtitle": "Plans, invoices, fiscalization and revenue", "path": "/platform/billing"},
    {"id": "analytics", "title": "Platform analytics", "subtitle": "Traffic, latency, usage and tenant load", "path": "/platform/analytics"},
    {"id": "security", "title": "Security & compliance", "subtitle": "Alerts and privileged security controls", "path": "/platform/security"},
    {"id": "audit", "title": "Audit logs", "subtitle": "Privileged and platform activity trail", "path": "/platform/security?tab=audit"},
    {"id": "integrations", "title": "Integrations & API", "subtitle": "Providers, email, API keys and webhooks", "path": "/platform/integrations"},
    {"id": "email", "title": "Email delivery", "subtitle": "Resend health, domains, templates and delivery mode", "path": "/platform/integrations?tab=email"},
    {"id": "providers", "title": "Provider registry", "subtitle": "Payments, tax, AI and external services", "path": "/platform/integrations?tab=providers"},
    {"id": "webhooks", "title": "Webhook inspector", "subtitle": "Endpoints, signing and delivery state", "path": "/platform/integrations?tab=webhooks"},
    {"id": "support", "title": "Support center", "subtitle": "Tenant tickets, internal notes and AI drafts", "path": "/platform/integrations?tab=support"},
    {"id": "infrastructure", "title": "System infrastructure", "subtitle": "Workers, maintenance, flags and diagnostics", "path": "/platform/infrastructure"},
)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return _iso(value) or ""
    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        return str(enum_value)
    return str(value)


def _sse(event: str, payload: dict[str, Any], *, event_id: str | None = None) -> str:
    lines: list[str] = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    encoded = json.dumps(payload, default=_json_default, separators=(",", ":"))
    for line in encoded.splitlines() or [encoded]:
        lines.append(f"data: {line}")
    return "\n".join(lines) + "\n\n"


def _bootstrap_snapshot(db: Session) -> dict[str, Any]:
    dashboard = services.dashboard_summary(db, data_mode="REAL")
    try:
        capabilities = saas_services.platform_capabilities(db)
    except Exception:
        capabilities = {"providers": [], "queue": {}, "counts": {}, "controls": {}}

    providers = capabilities.get("providers") if isinstance(capabilities, dict) else []
    providers = providers if isinstance(providers, list) else []
    queue = capabilities.get("queue") if isinstance(capabilities, dict) else {}
    queue = queue if isinstance(queue, dict) else {}
    counts = capabilities.get("counts") if isinstance(capabilities, dict) else {}
    counts = counts if isinstance(counts, dict) else {}

    configured_providers = sum(
        1
        for provider in providers
        if str((provider or {}).get("status") or "NOT_CONFIGURED").upper() != "NOT_CONFIGURED"
    )
    email_provider = next(
        (
            provider
            for provider in providers
            if str((provider or {}).get("provider") or "").lower() == "resend"
        ),
        None,
    )

    snapshot = {
        **dashboard,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "queue_depth": int(queue.get("queue_depth") or 0),
        "configured_providers": configured_providers,
        "open_support_tickets": int(counts.get("open_support_tickets") or dashboard.get("active_support_tickets") or 0),
        "pending_fiscalizations": int(counts.get("pending_fiscalizations") or 0),
        "email_status": (email_provider or {}).get("status") if isinstance(email_provider, dict) else "NOT_CONFIGURED",
        "email_latency_ms": (email_provider or {}).get("last_latency_ms") if isinstance(email_provider, dict) else None,
        "provider_count": len(providers),
        "controls": capabilities.get("controls", {}) if isinstance(capabilities, dict) else {},
    }
    return snapshot


def _event_cursor(row: platform_models.PlatformAuditLog) -> str:
    return f"{_iso(row.created_at)}|{row.id}"


def _parse_cursor(raw: str | None) -> tuple[datetime, str]:
    if raw:
        timestamp, separator, row_id = raw.partition("|")
        if separator and timestamp and row_id:
            try:
                parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed, row_id
            except ValueError:
                pass
    return datetime.now(timezone.utc), ""


def _audit_event(row: platform_models.PlatformAuditLog) -> dict[str, Any]:
    return {
        "id": _event_cursor(row),
        "type": "platform.audit",
        "action": row.action,
        "module": row.module,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "tenant_id": row.tenant_id,
        "actor_user_id": row.actor_user_id,
        "reason": row.reason,
        "details": row.details_json or {},
        "created_at": _iso(row.created_at),
    }


def _event_rows(db: Session, *, cursor_time: datetime, cursor_id: str) -> list[platform_models.PlatformAuditLog]:
    query = db.query(platform_models.PlatformAuditLog)
    if cursor_id:
        query = query.filter(
            or_(
                platform_models.PlatformAuditLog.created_at > cursor_time,
                and_(
                    platform_models.PlatformAuditLog.created_at == cursor_time,
                    platform_models.PlatformAuditLog.id > cursor_id,
                ),
            )
        )
    else:
        query = query.filter(platform_models.PlatformAuditLog.created_at > cursor_time)
    return (
        query.order_by(
            platform_models.PlatformAuditLog.created_at.asc(),
            platform_models.PlatformAuditLog.id.asc(),
        )
        .limit(MAX_EVENT_BATCH)
        .all()
    )


@router.get("/bootstrap")
def console_bootstrap(
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    return _bootstrap_snapshot(db)


@router.get("/search")
def console_search(
    q: str = Query(..., min_length=2, max_length=120),
    limit: int = Query(12, ge=1, le=25),
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    clean = q.strip()
    like = f"%{clean}%"
    items: list[dict[str, Any]] = []

    lower = clean.lower()
    for entry in NAVIGATION_RESULTS:
        haystack = f"{entry['title']} {entry['subtitle']}".lower()
        if lower in haystack:
            items.append({"kind": "navigation", **entry, "status": None})
            if len(items) >= limit:
                return {"items": items}

    tenant_rows = (
        db.query(account_models.AMO)
        .filter(
            or_(
                account_models.AMO.name.ilike(like),
                account_models.AMO.amo_code.ilike(like),
                account_models.AMO.login_slug.ilike(like),
            )
        )
        .order_by(account_models.AMO.name.asc())
        .limit(limit)
        .all()
    )
    for tenant in tenant_rows:
        items.append(
            {
                "kind": "tenant",
                "id": str(tenant.id),
                "title": tenant.name,
                "subtitle": f"{tenant.amo_code} · {tenant.login_slug}",
                "path": f"/platform/tenants?q={quote(str(tenant.amo_code or tenant.name))}",
                "status": "ACTIVE" if tenant.is_active else "INACTIVE",
            }
        )
        if len(items) >= limit:
            return {"items": items}

    user_rows = (
        db.query(account_models.User)
        .filter(
            or_(
                account_models.User.email.ilike(like),
                account_models.User.full_name.ilike(like),
            )
        )
        .order_by(account_models.User.full_name.asc(), account_models.User.email.asc())
        .limit(limit)
        .all()
    )
    for account in user_rows:
        role = getattr(getattr(account, "role", None), "value", getattr(account, "role", "USER"))
        items.append(
            {
                "kind": "user",
                "id": str(account.id),
                "title": account.full_name or account.email,
                "subtitle": f"{account.email} · {role}",
                "path": f"/platform/users?q={quote(str(account.email))}",
                "status": "ACTIVE" if account.is_active else "INACTIVE",
            }
        )
        if len(items) >= limit:
            return {"items": items}

    ticket_rows = (
        db.query(platform_models.PlatformSupportTicket)
        .filter(
            or_(
                platform_models.PlatformSupportTicket.title.ilike(like),
                platform_models.PlatformSupportTicket.external_id.ilike(like),
            )
        )
        .order_by(platform_models.PlatformSupportTicket.updated_at.desc())
        .limit(limit)
        .all()
    )
    for ticket in ticket_rows:
        items.append(
            {
                "kind": "support",
                "id": str(ticket.id),
                "title": ticket.title,
                "subtitle": ticket.external_id or f"Priority {ticket.priority}",
                "path": f"/platform/integrations?tab=support&ticket={quote(str(ticket.id))}",
                "status": ticket.status,
            }
        )
        if len(items) >= limit:
            break

    return {"items": items}


async def _console_event_stream(
    request: Request,
    *,
    last_event_id: str | None,
) -> AsyncGenerator[str, None]:
    cursor_time, cursor_id = _parse_cursor(last_event_id)
    last_snapshot_at = 0.0

    with ReadSessionLocal() as db:
        yield _sse(
            "snapshot",
            {
                "type": "platform.snapshot",
                "snapshot": _bootstrap_snapshot(db),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    loop = asyncio.get_running_loop()
    last_snapshot_at = loop.time()

    while not await request.is_disconnected():
        emitted = False
        with ReadSessionLocal() as db:
            rows = _event_rows(db, cursor_time=cursor_time, cursor_id=cursor_id)
            for row in rows:
                payload = _audit_event(row)
                cursor_time = row.created_at
                if cursor_time.tzinfo is None:
                    cursor_time = cursor_time.replace(tzinfo=timezone.utc)
                cursor_id = row.id
                yield _sse("platform.audit", payload, event_id=payload["id"])
                emitted = True

            now_monotonic = loop.time()
            if now_monotonic - last_snapshot_at >= SNAPSHOT_INTERVAL_SECONDS:
                yield _sse(
                    "snapshot",
                    {
                        "type": "platform.snapshot",
                        "snapshot": _bootstrap_snapshot(db),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                last_snapshot_at = now_monotonic
                emitted = True

        if not emitted:
            yield ": keepalive\n\n"
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


@router.get("/events")
async def console_events(
    request: Request,
    last_event_id: str | None = Query(None),
    user=Depends(require_platform_superuser),
) -> StreamingResponse:
    cursor = last_event_id or request.headers.get("last-event-id")
    return StreamingResponse(
        _console_event_stream(request, last_event_id=cursor),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
