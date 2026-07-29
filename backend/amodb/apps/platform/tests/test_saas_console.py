from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from amodb.apps.platform import console_router


def test_console_router_exposes_superadmin_bootstrap_search_and_stream() -> None:
    paths = {route.path for route in console_router.router.routes}

    assert "/console/bootstrap" in paths
    assert "/console/search" in paths
    assert "/console/events" in paths


def test_console_sse_frame_is_named_resumable_and_json_encoded() -> None:
    frame = console_router._sse(
        "platform.audit",
        {"type": "platform.audit", "action": "tenant.updated"},
        event_id="2026-07-29T09:00:00+00:00|audit-1",
    )

    assert frame.startswith("id: 2026-07-29T09:00:00+00:00|audit-1\nevent: platform.audit\n")
    data_line = next(line for line in frame.splitlines() if line.startswith("data: "))
    assert json.loads(data_line.removeprefix("data: ")) == {
        "type": "platform.audit",
        "action": "tenant.updated",
    }
    assert frame.endswith("\n\n")


def test_console_audit_cursor_round_trips_timestamp_and_id() -> None:
    created_at = datetime(2026, 7, 29, 9, 1, 2, tzinfo=timezone.utc)
    row = SimpleNamespace(created_at=created_at, id="audit-2")

    cursor = console_router._event_cursor(row)
    cursor_time, cursor_id = console_router._parse_cursor(cursor)

    assert cursor_time == created_at
    assert cursor_id == "audit-2"


def test_console_snapshot_combines_dashboard_queue_provider_and_support_counts(monkeypatch) -> None:
    monkeypatch.setattr(
        console_router.services,
        "dashboard_summary",
        lambda _db, data_mode: {
            "active_tenants": 4,
            "total_users": 21,
            "active_support_tickets": 2,
            "data_mode": data_mode,
        },
    )
    monkeypatch.setattr(
        console_router.saas_services,
        "platform_capabilities",
        lambda _db: {
            "providers": [
                {"provider": "resend", "status": "HEALTHY", "last_latency_ms": 83},
                {"provider": "stripe", "status": "NOT_CONFIGURED"},
                {"provider": "openai", "status": "CONFIGURED"},
            ],
            "queue": {"queue_depth": 7},
            "counts": {"open_support_tickets": 5, "pending_fiscalizations": 3},
            "controls": {"jobs": True},
        },
    )

    snapshot = console_router._bootstrap_snapshot(SimpleNamespace())

    assert snapshot["data_mode"] == "REAL"
    assert snapshot["active_tenants"] == 4
    assert snapshot["queue_depth"] == 7
    assert snapshot["configured_providers"] == 2
    assert snapshot["open_support_tickets"] == 5
    assert snapshot["pending_fiscalizations"] == 3
    assert snapshot["email_status"] == "HEALTHY"
    assert snapshot["email_latency_ms"] == 83
    assert snapshot["provider_count"] == 3
    assert snapshot["controls"] == {"jobs": True}
    assert snapshot["generated_at"]


def test_console_audit_payload_keeps_scope_and_reason() -> None:
    created_at = datetime(2026, 7, 29, 9, 2, 3, tzinfo=timezone.utc)
    row = SimpleNamespace(
        id="audit-3",
        created_at=created_at,
        action="support.message.created",
        module="platform",
        entity_type="support_ticket",
        entity_id="ticket-1",
        tenant_id="tenant-1",
        actor_user_id="root-1",
        reason="Tenant support response",
        details_json={"visibility": "PUBLIC"},
    )

    payload = console_router._audit_event(row)

    assert payload["id"] == f"{created_at.isoformat()}|audit-3"
    assert payload["tenant_id"] == "tenant-1"
    assert payload["entity_type"] == "support_ticket"
    assert payload["entity_id"] == "ticket-1"
    assert payload["reason"] == "Tenant support response"
    assert payload["details"] == {"visibility": "PUBLIC"}
