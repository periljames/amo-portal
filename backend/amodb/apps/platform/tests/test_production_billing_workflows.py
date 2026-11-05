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


@pytest.mark.parametrize("modules,reason,expected", [
    ([{"module_code": "quality", "status": "ENABLED"}], "", "audited reason"),
    ([], "Governed activation", "at least one"),
    ([{"module_code": "not-installed", "status": "ENABLED"}], "Governed activation", "Unknown platform module"),
    ([{"module_code": "quality", "status": "PERMANENT"}], "Governed activation", "Invalid module state"),
    ([{"module_code": "quality", "status": "ENABLED"},
      {"module_code": "quality", "status": "TRIAL"}], "Governed activation", "Duplicate module"),
])
def test_platform_module_changes_reject_invalid_batches_before_writing(modules, reason, expected):
    db = MagicMock()
    db.get.return_value = SimpleNamespace(id="tenant-1")
    with pytest.raises(ValueError, match=expected):
        services.update_entitlements(
            db, tenant_id="tenant-1", actor_id="platform-operator",
            payload={"modules": modules, "reason": reason},
        )
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_valid_platform_module_change_keeps_enum_and_reason(monkeypatch):
    db = MagicMock()
    db.get.return_value = SimpleNamespace(id="tenant-1")
    db.get_bind.return_value.dialect.name = "sqlite"
    row = SimpleNamespace(status=None, plan_code=None)
    db.query.return_value.filter.return_value.first.return_value = row
    logged = []
    monkeypatch.setattr(services, "audit", lambda *args, **kwargs: logged.append(kwargs))
    monkeypatch.setattr(services, "get_tenant_detail",
                        lambda db, tenant_id: {"id": tenant_id})
    result = services.update_entitlements(
        db, tenant_id="tenant-1", actor_id="platform-operator",
        payload={"modules": [{"module_code": "quality", "status": "ENABLED", "plan_code": "enterprise"}],
                 "reason": "Approved subscription fulfillment"},
    )
    from amodb.apps.accounts.models import ModuleSubscriptionStatus
    assert row.status == ModuleSubscriptionStatus.ENABLED
    assert row.plan_code == "enterprise"
    assert logged[0]["reason"] == "Approved subscription fulfillment"
    db.commit.assert_called_once()
    assert result["id"] == "tenant-1"


def test_activation_readiness_does_not_confuse_s3_configuration_with_live_storage(monkeypatch):
    from amodb import storage
    from amodb.apps.accounts import services as account_services
    from amodb.apps.platform import storage_quota_service
    from amodb.apps.quality import tenant_security

    db = MagicMock()
    db.get.return_value = SimpleNamespace(id="tenant-1", is_active=True)
    owner = SimpleNamespace(is_active=True, must_change_password=False)
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = owner
    db.query.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(module_code="quality"),
    ]
    monkeypatch.setattr(tenant_security, "set_postgres_tenant_context", lambda *a, **kw: None)
    monkeypatch.setattr(account_services, "get_billing_access_status",
                        lambda *a, **kw: SimpleNamespace(has_access=True))
    monkeypatch.setattr(account_services, "resolve_entitlements",
                        lambda *a, **kw: {"quality": SimpleNamespace(is_unlimited=True)})
    monkeypatch.setattr(storage_quota_service, "read_quota",
                        lambda *a, **kw: {"quota_bytes": 5_000_000_000_000, "integrity_state": "OK"})
    monkeypatch.setattr(storage, "shared_storage_enabled", lambda: True)
    monkeypatch.setattr(storage, "health_check", lambda: {"ok": False})

    user = SimpleNamespace(id="superuser-1")
    status = router.tenant_activation_checklist("tenant-1", db=db, user=user)
    assert status["ready"] is False
    by_key = {item["key"]: item["passed"] for item in status["checks"]}
    assert by_key["shared_storage"] is False
    assert by_key["storage"] is True

    monkeypatch.setattr(storage, "health_check", lambda: {"ok": True})
    assert router.tenant_activation_checklist("tenant-1", db=db, user=user)["ready"] is True


def test_activation_rejects_unlicensed_and_expired_module_grants(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from amodb import storage
    from amodb.apps.accounts import services as account_services
    from amodb.apps.platform import storage_quota_service
    from amodb.apps.quality import tenant_security

    db = MagicMock()
    db.get.return_value = SimpleNamespace(id="tenant-1", is_active=True)
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
        SimpleNamespace(is_active=True, must_change_password=False)
    )
    now = datetime.now(timezone.utc)
    enabled = [
        SimpleNamespace(module_code="quality", effective_from=None, effective_to=None),
        SimpleNamespace(module_code="training", effective_from=None, effective_to=None),
    ]
    db.query.return_value.filter.return_value.all.return_value = enabled
    monkeypatch.setattr(tenant_security, "set_postgres_tenant_context", lambda *a, **kw: None)
    monkeypatch.setattr(account_services, "get_billing_access_status",
                        lambda *a, **kw: SimpleNamespace(has_access=True))
    monkeypatch.setattr(account_services, "resolve_entitlements",
                        lambda *a, **kw: {"quality": SimpleNamespace(is_unlimited=True)})
    monkeypatch.setattr(storage_quota_service, "read_quota",
                        lambda *a, **kw: {"quota_bytes": 5_000_000_000_000, "integrity_state": "OK"})
    monkeypatch.setattr(storage, "shared_storage_enabled", lambda: True)
    monkeypatch.setattr(storage, "health_check", lambda: {"ok": True})
    user = SimpleNamespace(id="superuser-1")

    result = router.tenant_activation_checklist("tenant-1", db=db, user=user)
    assert not result["ready"]
    assert result["unready_modules"] == ["training"]
    assert next(c for c in result["checks"] if c["key"] == "module_entitlements")["passed"] is False

    enabled[1].effective_to = now - timedelta(seconds=1)
    monkeypatch.setattr(account_services, "resolve_entitlements",
                        lambda *a, **kw: {
                            "quality": SimpleNamespace(is_unlimited=True),
                            "training": SimpleNamespace(is_unlimited=True),
                        })
    result = router.tenant_activation_checklist("tenant-1", db=db, user=user)
    assert result["unready_modules"] == ["training"]
    assert not result["ready"]
