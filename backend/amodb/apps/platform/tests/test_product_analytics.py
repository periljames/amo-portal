from __future__ import annotations

from datetime import datetime, timezone

import pytest

from amodb.apps.platform import product_analytics
from amodb.apps.platform.ops_product_insights_router import _cohort_payload, _retention_payload


def test_product_event_taxonomy_is_explicit_not_generic_click_tracking():
    assert "module_opened" in product_analytics.EVENT_TYPES
    assert "workflow_completed" in product_analytics.EVENT_TYPES
    assert "click" not in product_analytics.EVENT_TYPES
    assert "page_view" not in product_analytics.EVENT_TYPES


def test_product_event_strips_user_level_and_raw_metadata():
    event = product_analytics._normalise_event(
        tenant_id="tenant-a",
        event_type="workflow_completed",
        module="quality",
        outcome="SUCCESS",
        duration_ms=1250,
        session_class="tenant_user",
        metadata={
            "workflow": "audit-closeout",
            "feature": "car",
            "user_id": "must-not-survive",
            "email": "private@example.com",
            "raw_url": "/quality/audits/secret-id",
            "document_id": "doc-secret",
        },
        occurred_at=datetime.now(timezone.utc),
    )
    assert event.metadata == {"workflow": "audit-closeout", "feature": "car"}
    assert event.duration_ms == 1250


def test_product_event_rejects_uncontrolled_taxonomy_and_module_names():
    with pytest.raises(ValueError):
        product_analytics._normalise_event(
            tenant_id="tenant-a",
            event_type="button_clicked",
            module="quality",
            outcome="SUCCESS",
            duration_ms=None,
            session_class="tenant_user",
            metadata={},
        )
    with pytest.raises(ValueError):
        product_analytics._normalise_event(
            tenant_id="tenant-a",
            event_type="module_opened",
            module="Quality / tenant 123",
            outcome="SUCCESS",
            duration_ms=None,
            session_class="tenant_user",
            metadata={},
        )


def test_retention_is_tenant_aggregate_not_user_tracking():
    payload = _retention_payload(
        current={"tenant-a", "tenant-b", "tenant-c"},
        previous={"tenant-a", "tenant-c", "tenant-d"},
        eligible=5,
    )
    assert payload["retained_tenants"] == 2
    assert payload["current_active_tenants"] == 3
    assert payload["previous_active_tenants"] == 3
    assert payload["retention_rate"] == pytest.approx(2 / 3)
    assert payload["current_activation_rate"] == pytest.approx(3 / 5)
    assert "user" not in " ".join(payload.keys()).lower()


def test_cohort_payload_exposes_counts_only():
    tenants = [
        ("tenant-a", datetime(2026, 8, 1, tzinfo=timezone.utc)),
        ("tenant-b", datetime(2026, 8, 2, tzinfo=timezone.utc)),
        ("tenant-c", datetime(2026, 7, 20, tzinfo=timezone.utc)),
    ]
    rows = _cohort_payload(tenants, {"tenant-a", "tenant-c"})
    august = next(row for row in rows if row["cohort"] == "2026-08")
    july = next(row for row in rows if row["cohort"] == "2026-07")
    assert august == {"cohort": "2026-08", "tenants": 2, "active_in_window": 1, "activation_rate": 0.5}
    assert july["tenants"] == 1
    assert july["active_in_window"] == 1
    assert all("tenant_id" not in row for row in rows)
