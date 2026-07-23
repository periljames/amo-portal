from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from amodb.apps.accounts import models as account_models
from amodb.apps.platform import saas_models
from amodb.apps.platform import tenant_saas_router
from amodb.jobs import saas_worker


def _job(*, verified_tenant_id: str | None, event_id: str = "event-1"):
    return SimpleNamespace(
        id="job-1",
        payload_json={
            "webhook_event_id": event_id,
            "verified_tenant_id": verified_tenant_id,
        },
    )


def test_mutating_stripe_event_requires_verified_tenant():
    with pytest.raises(ValueError, match="cryptographically verified tenant"):
        saas_worker._verified_stripe_tenant(
            _job(verified_tenant_id=None),
            event_type="invoice.paid",
            declared_tenant_id="amo-1",
        )


def test_declared_stripe_tenant_cannot_override_verified_tenant():
    with pytest.raises(ValueError, match="does not match"):
        saas_worker._verified_stripe_tenant(
            _job(verified_tenant_id="amo-1"),
            event_type="invoice.paid",
            declared_tenant_id="amo-2",
        )


def test_invoice_webhook_rejects_invoice_outside_verified_tenant():
    event = SimpleNamespace(
        payload=json.dumps(
            {
                "id": "evt_invoice",
                "type": "invoice.paid",
                "data": {
                    "object": {
                        "customer": "cus_1",
                        "metadata": {
                            "tenant_id": "amo-1",
                            "portal_invoice_id": "invoice-other-tenant",
                        },
                    }
                },
            }
        )
    )
    db = MagicMock()
    db.get.return_value = event
    invoice_query = MagicMock()
    invoice_query.filter.return_value.first.return_value = None
    db.query.return_value = invoice_query

    with pytest.raises(ValueError, match="does not belong to the verified Stripe tenant"):
        saas_worker._process_stripe_webhook(
            db,
            _job(verified_tenant_id="amo-1"),
        )

    db.query.assert_called_once_with(account_models.BillingInvoice)
    assert invoice_query.filter.called


def test_invoice_webhook_updates_only_verified_tenant_invoice(monkeypatch: pytest.MonkeyPatch):
    invoice = SimpleNamespace(
        id="invoice-1",
        amo_id="amo-1",
        status=account_models.InvoiceStatus.PENDING,
        paid_at=None,
    )
    event = SimpleNamespace(
        payload=json.dumps(
            {
                "id": "evt_invoice",
                "type": "invoice.paid",
                "data": {
                    "object": {
                        "customer": "cus_1",
                        "metadata": {
                            "tenant_id": "amo-1",
                            "portal_invoice_id": "invoice-1",
                        },
                    }
                },
            }
        ),
        status=account_models.WebhookStatus.RECEIVED,
        processed_at=None,
        attempt_count=0,
        last_error=None,
    )
    db = MagicMock()
    db.get.return_value = event
    invoice_query = MagicMock()
    invoice_query.filter.return_value.first.return_value = invoice
    db.query.return_value = invoice_query
    monkeypatch.setattr(
        saas_worker,
        "_upsert_billing_account",
        lambda *args, **kwargs: SimpleNamespace(external_subscription_ref=None),
    )

    result = saas_worker._process_stripe_webhook(
        db,
        _job(verified_tenant_id="amo-1"),
    )

    assert result["verified_tenant_id"] == "amo-1"
    assert result["portal_invoice_id"] == "invoice-1"
    assert invoice.status is account_models.InvoiceStatus.PAID
    assert invoice.paid_at is not None
    assert event.status is account_models.WebhookStatus.PROCESSED


def test_tenant_queue_summary_excludes_other_tenants_and_returns_depth():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    saas_models.SaaSJob.__table__.create(engine)
    db = sessionmaker(bind=engine, future=True, expire_on_commit=False)()
    now = datetime.now(timezone.utc)
    db.add_all(
        [
            saas_models.SaaSJob(
                id="t1-pending",
                queue_name="billing",
                job_type="TEST",
                tenant_id="amo-1",
                tenant_scope="amo-1",
                status="PENDING",
                priority=10,
                payload_json={},
                idempotency_key="t1-pending",
                available_at=now,
            ),
            saas_models.SaaSJob(
                id="t1-succeeded",
                queue_name="billing",
                job_type="TEST",
                tenant_id="amo-1",
                tenant_scope="amo-1",
                status="SUCCEEDED",
                priority=10,
                payload_json={},
                idempotency_key="t1-succeeded",
                available_at=now,
            ),
            saas_models.SaaSJob(
                id="t2-running",
                queue_name="ai",
                job_type="TEST",
                tenant_id="amo-2",
                tenant_scope="amo-2",
                status="RUNNING",
                priority=10,
                payload_json={},
                idempotency_key="t2-running",
                available_at=now,
            ),
        ]
    )
    db.commit()

    tenant = tenant_saas_router._queue_summary(db, tenant_id="amo-1")
    platform = tenant_saas_router._queue_summary(db, tenant_id=None)

    assert tenant == {
        "scope": "TENANT",
        "tenant_id": "amo-1",
        "counts": {"PENDING": 1, "SUCCEEDED": 1},
        "queues": {"billing": 1},
        "queue_depth": 1,
        "oldest_active_job_at": tenant["oldest_active_job_at"],
    }
    assert tenant["oldest_active_job_at"] is not None
    assert "ai" not in tenant["queues"]
    assert platform["queue_depth"] == 2
    assert platform["queues"] == {"ai": 1, "billing": 1}
