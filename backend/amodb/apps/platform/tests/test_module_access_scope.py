from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import billing_access
from amodb.apps.platform import module_access_router
from amodb.database import WriteSessionLocal


def _tenant(db, suffix: str) -> str:
    amo_id = f"scope-{suffix}"
    db.add(
        account_models.AMO(
            id=amo_id,
            amo_code=f"SC{suffix[:8].upper()}",
            login_slug=f"scope-{suffix}",
            name=f"Scope Test {suffix}",
            country="KE",
            is_demo=True,
            is_active=True,
        )
    )
    db.flush()
    return amo_id


def _module_subscription(db, *, amo_id: str, code: str, start: datetime, end: datetime, contract: str | None = None):
    metadata = {
        "contract_module_code": contract or code,
        "billing_term": "MONTHLY",
        "auto_renew": True,
    }
    row = account_models.ModuleSubscription(
        amo_id=amo_id,
        module_code=code,
        status=account_models.ModuleSubscriptionStatus.ENABLED,
        effective_from=start,
        effective_to=end,
        metadata_json=json.dumps(metadata, separators=(",", ":")),
    )
    db.add(row)
    db.flush()
    return row


def _renewal_invoice(db, *, amo_id: str, module_code: str, due_at: datetime):
    row = account_models.BillingInvoice(
        amo_id=amo_id,
        amount_cents=10000,
        currency="KES",
        status=account_models.InvoiceStatus.PENDING,
        description=json.dumps(
            {
                "module_code": module_code,
                "source": "MODULE_RENEWAL",
                "lock_scope": "MODULE",
                "subtotal_cents": 10000,
                "tax_rate_bps": 0,
                "tax_amount_cents": 0,
                "total_cents": 10000,
            },
            separators=(",", ":"),
        ),
        idempotency_key=f"module-renewal-{uuid.uuid4().hex}",
        issued_at=due_at - timedelta(days=7),
        due_at=due_at,
    )
    db.add(row)
    db.flush()
    return row


def test_module_only_customer_has_account_access_without_legacy_license() -> None:
    db = WriteSessionLocal()
    now = datetime.now(timezone.utc)
    try:
        suffix = uuid.uuid4().hex[:10]
        amo_id = _tenant(db, suffix)
        _module_subscription(
            db,
            amo_id=amo_id,
            code="quality",
            start=now - timedelta(days=5),
            end=now + timedelta(days=25),
        )
        db.commit()

        status = billing_access.get_billing_access_status(db, amo_id=amo_id, as_of=now)
        assert status.has_access is True
        assert status.access_state == "MODULE_SUBSCRIBED"
        assert status.redirect_to_billing is False
    finally:
        db.close()


def test_overdue_module_renewal_does_not_lock_other_active_modules() -> None:
    db = WriteSessionLocal()
    now = datetime.now(timezone.utc)
    try:
        suffix = uuid.uuid4().hex[:10]
        amo_id = _tenant(db, suffix)
        _module_subscription(
            db,
            amo_id=amo_id,
            code="quality",
            start=now - timedelta(days=5),
            end=now + timedelta(days=25),
        )
        _module_subscription(
            db,
            amo_id=amo_id,
            code="reliability",
            start=now - timedelta(days=35),
            end=now - timedelta(minutes=1),
        )
        _renewal_invoice(db, amo_id=amo_id, module_code="reliability", due_at=now - timedelta(minutes=1))
        db.commit()

        account = billing_access.get_billing_access_status(db, amo_id=amo_id, as_of=now)
        quality = module_access_router.module_access_state(db, tenant_id=amo_id, module_code="quality", now=now)
        reliability = module_access_router.module_access_state(db, tenant_id=amo_id, module_code="reliability", now=now)

        assert account.has_access is True
        assert account.overdue_invoice_count == 0
        assert quality["has_access"] is True
        assert reliability["has_access"] is False
        assert reliability["access_state"] == "MODULE_PAYMENT_REQUIRED"
        assert reliability["redirect_to_billing"] is True
    finally:
        db.close()


def test_account_scoped_overdue_invoice_locks_all_modules() -> None:
    db = WriteSessionLocal()
    now = datetime.now(timezone.utc)
    try:
        suffix = uuid.uuid4().hex[:10]
        amo_id = _tenant(db, suffix)
        _module_subscription(
            db,
            amo_id=amo_id,
            code="quality",
            start=now - timedelta(days=5),
            end=now + timedelta(days=25),
        )
        db.add(
            account_models.BillingInvoice(
                amo_id=amo_id,
                amount_cents=50000,
                currency="KES",
                status=account_models.InvoiceStatus.PENDING,
                description=json.dumps(
                    {"source": "ACCOUNT_RENEWAL", "lock_scope": "ACCOUNT", "total_cents": 50000},
                    separators=(",", ":"),
                ),
                idempotency_key=f"account-renewal-{suffix}",
                issued_at=now - timedelta(days=8),
                due_at=now - timedelta(days=1),
            )
        )
        db.commit()

        account = billing_access.get_billing_access_status(db, amo_id=amo_id, as_of=now)
        quality = module_access_router.module_access_state(db, tenant_id=amo_id, module_code="quality", now=now)
        assert account.has_access is False
        assert account.access_state == "PAYMENT_OVERDUE"
        assert account.overdue_invoice_count == 1
        assert quality["has_access"] is False
        assert quality["access_state"] == "ACCOUNT_PAYMENT_REQUIRED"
    finally:
        db.close()
