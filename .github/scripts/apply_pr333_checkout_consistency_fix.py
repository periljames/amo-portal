from __future__ import annotations

from pathlib import Path


def replace_exact(path: str, old: str, new: str, expected: int = 1) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    actual = text.count(old)
    if actual != expected:
        raise SystemExit(f"{path}: expected {expected} occurrences, found {actual}: {old!r}")
    file_path.write_text(text.replace(old, new), encoding="utf-8")


def main() -> None:
    replace_exact(
        "backend/amodb/jobs/saas_worker.py",
        '''CHECKOUT_SESSION_EVENTS = {
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "checkout.session.async_payment_failed",
}
''',
        '''CHECKOUT_SESSION_EVENTS = {
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "checkout.session.async_payment_failed",
    "checkout.session.expired",
}
''',
    )

    replace_exact(
        "backend/amodb/jobs/saas_worker.py",
        '''    price = _checkout_price(db, module_price_id=expected_module_price_id)
    if (
        price is None
        or saas_services.normalize_module_code(str(price.module_code or ""))
        != saas_services.normalize_module_code(module_code)
        or str(price.external_price_ref or "") != expected_price_ref
    ):
        raise ValueError("Stripe checkout price does not match the portal module price")
    return account, pending, module_code, module_price_id, external_price_ref
''',
        '''    return account, pending, module_code, module_price_id, external_price_ref
''',
    )

    replace_exact(
        "backend/amodb/jobs/saas_worker.py",
        '''        failed = event_type == "checkout.session.async_payment_failed"
        if succeeded:
            checkout_status = "ACTIVE"
        elif failed:
            checkout_status = "CHECKOUT_FAILED"
        else:
            checkout_status = "CHECKOUT_PENDING"
''',
        '''        failed = event_type == "checkout.session.async_payment_failed"
        expired = event_type == "checkout.session.expired"
        if succeeded:
            checkout_status = "ACTIVE"
        elif failed:
            checkout_status = "CHECKOUT_FAILED"
        elif expired:
            checkout_status = "CHECKOUT_EXPIRED"
        else:
            checkout_status = "CHECKOUT_PENDING"
''',
    )

    replace_exact(
        "backend/amodb/jobs/saas_worker.py",
        '''    elif event_type in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
        subscription_status = str(obj.get("status") or "").lower()
        active = event_type != "customer.subscription.deleted" and subscription_status not in {"canceled", "unpaid", "incomplete_expired"}
        _upsert_billing_account(
            db,
            tenant_id=tenant_id,
            provider="stripe",
            customer_ref=customer_ref,
            subscription_ref=subscription_ref or str(obj.get("id") or "") or None,
            status="ACTIVE" if active else "CANCELLED",
            metadata={"event_type": event_type, "stripe_status": subscription_status},
        )
        if module_code:
            _set_module_state(
                db,
                tenant_id=tenant_id,
                module_code=module_code,
                status="ENABLED" if active else "DISABLED",
                provider="stripe",
                external_subscription_ref=subscription_ref or str(obj.get("id") or "") or None,
            )
        outcome.update({"tenant_id": tenant_id, "module_code": module_code or None, "active": active})
''',
        '''    elif event_type in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
        subscription_status = str(obj.get("status") or "").lower()
        active = event_type != "customer.subscription.deleted" and subscription_status not in {"canceled", "unpaid", "incomplete_expired"}
        existing_account = _stripe_billing_account(db, tenant_id=tenant_id, lock=True)
        preserve_pending = bool(
            existing_account is not None
            and str(existing_account.status or "").upper() == "CHECKOUT_PENDING"
        )
        existing_metadata = (
            dict(existing_account.metadata_json)
            if preserve_pending and isinstance(existing_account.metadata_json, dict)
            else {}
        )
        account_status = "CHECKOUT_PENDING" if preserve_pending else ("ACTIVE" if active else "CANCELLED")
        account_metadata = (
            {
                **existing_metadata,
                "last_subscription_event": event_type,
                "last_subscription_status": subscription_status,
            }
            if preserve_pending
            else {"event_type": event_type, "stripe_status": subscription_status}
        )
        _upsert_billing_account(
            db,
            tenant_id=tenant_id,
            provider="stripe",
            customer_ref=customer_ref,
            subscription_ref=subscription_ref or str(obj.get("id") or "") or None,
            status=account_status,
            metadata=account_metadata,
        )
        if module_code:
            _set_module_state(
                db,
                tenant_id=tenant_id,
                module_code=module_code,
                status="ENABLED" if active else "DISABLED",
                provider="stripe",
                external_subscription_ref=subscription_ref or str(obj.get("id") or "") or None,
            )
        outcome.update(
            {
                "tenant_id": tenant_id,
                "module_code": module_code or None,
                "active": active,
                "checkout_pending_preserved": preserve_pending,
            }
        )
''',
    )

    replace_exact(
        "backend/amodb/apps/platform/saas_services.py",
        '''    row.external_price_ref = str(payload.get("external_price_ref") or "").strip() or None
    row.is_active = bool(payload.get("is_active", True))
''',
        '''    if "external_price_ref" in payload:
        row.external_price_ref = str(payload.get("external_price_ref") or "").strip() or None
    elif not price_id:
        row.external_price_ref = None
    if "is_active" in payload:
        row.is_active = bool(payload.get("is_active"))
    elif not price_id:
        row.is_active = True
''',
    )

    replace_exact(
        "backend/amodb/apps/platform/saas_services.py",
        '''    price = db.get(models.SaaSModulePrice, module_price_id)
    if not tenant or not price or not price.is_active:
        raise ValueError("Tenant or active module price not found")
''',
        '''    existing_job = (
        db.query(models.SaaSJob)
        .filter(
            models.SaaSJob.job_type == "STRIPE_CREATE_CHECKOUT_SESSION",
            models.SaaSJob.tenant_scope == tenant_id,
            models.SaaSJob.idempotency_key == idempotency_key.strip(),
        )
        .first()
    )
    if existing_job is not None:
        return existing_job
    price = db.get(models.SaaSModulePrice, module_price_id)
    if not tenant or not price or not price.is_active:
        raise ValueError("Tenant or active module price not found")
''',
    )

    replace_exact(
        "backend/amodb/apps/platform/saas_services.py",
        '''    if active_job is not None:
        if str(active_job.idempotency_key or "") == idempotency_key.strip():
            return active_job
        raise ValueError("Another Stripe checkout request is already queued for this tenant")
''',
        '''    if active_job is not None:
        raise ValueError("Another Stripe checkout request is already queued for this tenant")
''',
    )

    test_path = Path("backend/amodb/apps/platform/tests/test_saas_checkout_lifecycle.py")
    text = test_path.read_text(encoding="utf-8")
    addition = '''


def test_expired_checkout_releases_pending_state(monkeypatch: pytest.MonkeyPatch):
    result, upsert, set_module = _run_checkout_event(
        monkeypatch, "checkout.session.expired", "unpaid"
    )

    assert result["checkout_status"] == "CHECKOUT_EXPIRED"
    assert upsert.call_args.kwargs["status"] == "CHECKOUT_EXPIRED"
    set_module.assert_not_called()


def test_subscription_update_preserves_pending_checkout_provenance(monkeypatch: pytest.MonkeyPatch):
    event = SimpleNamespace(
        payload=json.dumps({
            "id": "evt-subscription",
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub-existing",
                    "customer": "cus-1",
                    "status": "active",
                    "metadata": {"tenant_id": "amo-1", "module_code": "training"},
                }
            },
        }),
        status=account_models.WebhookStatus.RECEIVED,
        processed_at=None,
        attempt_count=0,
        last_error=None,
    )
    account = _account()
    db = MagicMock()
    db.get.return_value = event
    monkeypatch.setattr(saas_worker, "_stripe_billing_account", lambda *_args, **_kwargs: account)
    upsert = MagicMock(return_value=account)
    monkeypatch.setattr(saas_worker, "_upsert_billing_account", upsert)
    monkeypatch.setattr(saas_worker, "_set_module_state", MagicMock())

    result = saas_worker._process_stripe_webhook(db, _webhook_job())

    assert result["checkout_pending_preserved"] is True
    assert upsert.call_args.kwargs["status"] == "CHECKOUT_PENDING"
    assert upsert.call_args.kwargs["metadata"]["checkout_session_id"] == "cs-1"


def test_checkout_completion_uses_immutable_pending_snapshot(monkeypatch: pytest.MonkeyPatch):
    account = _account()
    obj = {
        "id": "cs-1",
        "metadata": {
            "module_code": "quality",
            "module_price_id": "price-1",
            "external_price_ref": "price_stripe_1",
        },
    }
    monkeypatch.setattr(saas_worker, "_stripe_billing_account", lambda *_args, **_kwargs: account)
    current_price_lookup = MagicMock(side_effect=AssertionError("mutable price must not be read"))
    monkeypatch.setattr(saas_worker, "_checkout_price", current_price_lookup)

    result = saas_worker._validate_pending_checkout(
        MagicMock(),
        tenant_id="amo-1",
        obj=obj,
        metadata=obj["metadata"],
    )

    assert result[2:] == ("quality", "price-1", "price_stripe_1")
    current_price_lookup.assert_not_called()
'''
    if addition.strip() in text:
        raise SystemExit("Checkout consistency tests already present")
    test_path.write_text(text + addition, encoding="utf-8")

    service_test = Path("backend/amodb/apps/platform/tests/test_saas_checkout_service_consistency.py")
    service_test.write_text('''from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from amodb.apps.platform import saas_services


def test_module_price_patch_preserves_omitted_fields():
    row = SimpleNamespace(
        id="price-1",
        module_code="quality",
        plan_code="STANDARD",
        billing_term="MONTHLY",
        currency="USD",
        amount_cents=1000,
        tax_rate_bps=1600,
        trial_days=14,
        external_price_ref="price_stripe_1",
        is_active=False,
        updated_by=None,
    )
    db = MagicMock()
    db.get.return_value = row
    duplicate_query = MagicMock()
    duplicate_query.filter.return_value = duplicate_query
    duplicate_query.first.return_value = None
    db.query.return_value = duplicate_query

    saas_services.upsert_module_price(
        db,
        price_id="price-1",
        payload={"amount_cents": 2000},
        actor_user_id="admin-1",
    )

    assert row.amount_cents == 2000
    assert row.external_price_ref == "price_stripe_1"
    assert row.is_active is False


def test_matching_completed_checkout_job_is_returned_before_pending_rejection():
    tenant = SimpleNamespace(id="amo-1", primary_email="admin@example.test")
    existing_job = SimpleNamespace(
        id="job-complete",
        status="SUCCEEDED",
        idempotency_key="checkout-action-1",
    )
    tenant_query = MagicMock()
    tenant_query.filter.return_value.with_for_update.return_value.first.return_value = tenant
    job_query = MagicMock()
    job_query.filter.return_value.first.return_value = existing_job
    db = MagicMock()
    db.query.side_effect = [tenant_query, job_query]

    result = saas_services.enqueue_checkout(
        db,
        tenant_id="amo-1",
        module_price_id="price-1",
        actor_user_id="admin-1",
        idempotency_key="checkout-action-1",
    )

    assert result is existing_job
    db.get.assert_not_called()
''', encoding="utf-8")


if __name__ == "__main__":
    main()
