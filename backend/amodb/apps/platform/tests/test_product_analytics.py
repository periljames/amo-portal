from __future__ import annotations

from datetime import datetime, timezone

import pytest

from amodb.apps.platform import product_analytics


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
