from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from amodb.apps.accounts.models import InvoiceStatus
from amodb.apps.platform import router, services


def test_provisioning_requires_identified_administrator_and_reason():
    db = MagicMock()
    with pytest.raises(ValueError, match="owner_full_name"):
        services.create_tenant(
            db,
            payload={
                "name": "Example AMO", "amo_code": "EXM", "login_slug": "example",
                "owner_email": "owner@example.test", "reason": "Commercial activation",
            },
            actor_id="superuser-1",
        )
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize("status", [InvoiceStatus.VOID])
def test_offline_payment_refuses_nonpending_invoice(status):
    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = SimpleNamespace(
        status=status, id="invoice-1"
    )
    with pytest.raises(ValueError, match="Only pending"):
        services.mark_invoice_paid(
            db, invoice_id="invoice-1", actor_id="root", reason="Bank evidence",
        )
    db.commit.assert_not_called()


def test_void_does_not_reverse_a_paid_invoice():
    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = SimpleNamespace(
        status=InvoiceStatus.PAID, id="invoice-1"
    )
    with pytest.raises(ValueError, match="Paid invoices cannot be voided"):
        services.void_invoice(
            db, invoice_id="invoice-1", actor_id="root", reason="Mistake",
        )
    db.commit.assert_not_called()


def test_invoice_filter_rejects_unsupported_status():
    db = MagicMock()
    with pytest.raises(ValueError, match="Unsupported invoice status"):
        services.list_invoices(db, data_mode="REAL", status_filter="ANYTHING")


def test_platform_console_includes_operator_billing_and_owner_endpoints():
    paths = {(route.path, method) for route in router.router.routes for method in getattr(route, "methods", set())}
    for entry in [
        ("/platform/tenants/{tenant_id}/owner-invitation", "POST"),
        ("/platform/billing/invoices", "GET"),
        ("/platform/billing/invoices/export", "GET"),
        ("/platform/billing/invoices/{invoice_id}/document", "GET"),
        ("/platform/billing/invoices/{invoice_id}/void", "POST"),
        ("/platform/billing/invoices/{invoice_id}/mark-paid", "POST"),
    ]:
        assert entry in paths
