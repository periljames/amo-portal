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
        '''TENANT_MUTATING_STRIPE_EVENTS = {
    "checkout.session.completed",
    "customer.subscription.created",
''',
        '''CHECKOUT_SESSION_EVENTS = {
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "checkout.session.async_payment_failed",
}
TENANT_MUTATING_STRIPE_EVENTS = {
    *CHECKOUT_SESSION_EVENTS,
    "customer.subscription.created",
''',
    )

    replace_exact(
        "backend/amodb/jobs/saas_worker.py",
        '''def _stripe_metadata(obj: dict[str, Any]) -> dict[str, Any]:
    metadata = obj.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    parent = obj.get("subscription_details") or {}
    parent_metadata = parent.get("metadata") if isinstance(parent, dict) else None
    if isinstance(parent_metadata, dict):
        metadata = {**parent_metadata, **metadata}
    return metadata


''',
        '''def _stripe_metadata(obj: dict[str, Any]) -> dict[str, Any]:
    metadata = obj.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    parent = obj.get("subscription_details") or {}
    parent_metadata = parent.get("metadata") if isinstance(parent, dict) else None
    if isinstance(parent_metadata, dict):
        metadata = {**parent_metadata, **metadata}
    return metadata


def _stripe_billing_account(
    db: Session,
    *,
    tenant_id: str,
    lock: bool = False,
) -> models.SaaSBillingAccount | None:
    query = db.query(models.SaaSBillingAccount).filter(
        models.SaaSBillingAccount.tenant_id == tenant_id,
        models.SaaSBillingAccount.provider == "stripe",
    )
    if lock:
        query = query.with_for_update()
    return query.first()


def _lock_checkout_tenant(db: Session, tenant_id: str) -> account_models.AMO:
    tenant = (
        db.query(account_models.AMO)
        .filter(account_models.AMO.id == tenant_id)
        .with_for_update()
        .first()
    )
    if tenant is None:
        raise ValueError("Checkout tenant not found")
    return tenant


def _checkout_price(
    db: Session,
    *,
    module_price_id: str,
    lock: bool = False,
) -> models.SaaSModulePrice | None:
    query = db.query(models.SaaSModulePrice).filter(models.SaaSModulePrice.id == module_price_id)
    if lock:
        query = query.with_for_update()
    return query.first()


def _validate_pending_checkout(
    db: Session,
    *,
    tenant_id: str,
    obj: dict[str, Any],
    metadata: dict[str, Any],
) -> tuple[models.SaaSBillingAccount, dict[str, Any], str, str, str]:
    module_code = str(metadata.get("module_code") or "").strip()
    session_id = str(obj.get("id") or "").strip()
    module_price_id = str(metadata.get("module_price_id") or "").strip()
    external_price_ref = str(metadata.get("external_price_ref") or "").strip()
    if not module_code:
        raise ValueError("Stripe checkout metadata is missing module_code")
    account = _stripe_billing_account(db, tenant_id=tenant_id, lock=True)
    pending = account.metadata_json if account and isinstance(account.metadata_json, dict) else {}
    if account is None or str(account.status or "").upper() != "CHECKOUT_PENDING":
        raise ValueError("Stripe checkout event has no pending portal checkout")
    expected_session_id = str(pending.get("checkout_session_id") or "").strip()
    expected_module_code = str(pending.get("module_code") or "").strip()
    expected_module_price_id = str(pending.get("module_price_id") or "").strip()
    expected_price_ref = str(pending.get("external_price_ref") or "").strip()
    if not session_id or session_id != expected_session_id:
        raise ValueError("Stripe checkout session does not match the pending portal checkout")
    if (
        module_code != expected_module_code
        or module_price_id != expected_module_price_id
        or external_price_ref != expected_price_ref
    ):
        raise ValueError("Stripe checkout metadata does not match the pending portal checkout")
    price = _checkout_price(db, module_price_id=expected_module_price_id)
    if (
        price is None
        or saas_services.normalize_module_code(str(price.module_code or ""))
        != saas_services.normalize_module_code(module_code)
        or str(price.external_price_ref or "") != expected_price_ref
    ):
        raise ValueError("Stripe checkout price does not match the portal module price")
    return account, pending, module_code, module_price_id, external_price_ref


''',
    )

    old_webhook = '''    if event_type == "checkout.session.completed":
        if not module_code:
            raise ValueError("Stripe checkout metadata is missing module_code")
        session_id = str(obj.get("id") or "").strip()
        module_price_id = str(metadata.get("module_price_id") or "").strip()
        external_price_ref = str(metadata.get("external_price_ref") or "").strip()
        account = (
            db.query(models.SaaSBillingAccount)
            .filter(
                models.SaaSBillingAccount.tenant_id == tenant_id,
                models.SaaSBillingAccount.provider == "stripe",
            )
            .first()
        )
        pending = account.metadata_json if account and isinstance(account.metadata_json, dict) else {}
        if account is None or str(account.status or "").upper() != "CHECKOUT_PENDING":
            raise ValueError("Stripe checkout completion has no pending portal checkout")
        expected_session_id = str(pending.get("checkout_session_id") or "").strip()
        expected_module_code = str(pending.get("module_code") or "").strip()
        expected_module_price_id = str(pending.get("module_price_id") or "").strip()
        expected_price_ref = str(pending.get("external_price_ref") or "").strip()
        if not session_id or session_id != expected_session_id:
            raise ValueError("Stripe checkout session does not match the pending portal checkout")
        if module_code != expected_module_code or module_price_id != expected_module_price_id or external_price_ref != expected_price_ref:
            raise ValueError("Stripe checkout metadata does not match the pending portal checkout")
        price = db.get(models.SaaSModulePrice, expected_module_price_id)
        if (
            price is None
            or saas_services.normalize_module_code(str(price.module_code or "")) != saas_services.normalize_module_code(module_code)
            or str(price.external_price_ref or "") != expected_price_ref
        ):
            raise ValueError("Stripe checkout price does not match the portal module price")
        payment_status = str(obj.get("payment_status") or "").lower()
        _upsert_billing_account(
            db,
            tenant_id=tenant_id,
            provider="stripe",
            customer_ref=customer_ref,
            subscription_ref=subscription_ref,
            status="ACTIVE" if payment_status in {"paid", "no_payment_required"} else "CHECKOUT_COMPLETED",
            metadata={"checkout_session_id": obj.get("id"), "module_code": module_code},
        )
        if payment_status in {"paid", "no_payment_required"}:
            _set_module_state(
                db,
                tenant_id=tenant_id,
                module_code=module_code,
                status="ENABLED",
                provider="stripe",
                external_subscription_ref=subscription_ref,
            )
        outcome.update({"tenant_id": tenant_id, "module_code": module_code, "payment_status": payment_status})

'''
    new_webhook = '''    if event_type in CHECKOUT_SESSION_EVENTS:
        account, pending, module_code, module_price_id, external_price_ref = _validate_pending_checkout(
            db,
            tenant_id=tenant_id,
            obj=obj,
            metadata=metadata,
        )
        payment_status = str(obj.get("payment_status") or "").lower()
        succeeded = event_type == "checkout.session.async_payment_succeeded" or (
            event_type == "checkout.session.completed"
            and payment_status in {"paid", "no_payment_required"}
        )
        failed = event_type == "checkout.session.async_payment_failed"
        if succeeded:
            checkout_status = "ACTIVE"
        elif failed:
            checkout_status = "CHECKOUT_FAILED"
        else:
            checkout_status = "CHECKOUT_PENDING"
        lifecycle_metadata = {
            **pending,
            "checkout_session_id": str(obj.get("id") or ""),
            "module_code": module_code,
            "module_price_id": module_price_id,
            "external_price_ref": external_price_ref,
            "last_checkout_event": event_type,
            "payment_status": payment_status,
        }
        _upsert_billing_account(
            db,
            tenant_id=tenant_id,
            provider="stripe",
            customer_ref=customer_ref,
            subscription_ref=subscription_ref,
            status=checkout_status,
            metadata=lifecycle_metadata,
        )
        if succeeded:
            _set_module_state(
                db,
                tenant_id=tenant_id,
                module_code=module_code,
                status="ENABLED",
                provider="stripe",
                external_subscription_ref=subscription_ref,
            )
        outcome.update(
            {
                "tenant_id": tenant_id,
                "module_code": module_code,
                "payment_status": payment_status,
                "checkout_status": checkout_status,
            }
        )

'''
    replace_exact("backend/amodb/jobs/saas_worker.py", old_webhook, new_webhook)

    old_checkout = '''def _process_checkout(db: Session, job: models.SaaSJob) -> dict[str, Any]:
    payload = job.payload_json or {}
    credential = _credential(db, str(payload.get("provider_credential_id") or ""))
    db.refresh(credential)
    saas_services.require_operational_provider(credential, label="Stripe")
    module_price_id = str(payload.get("module_price_id") or "").strip()
    module_code = str(payload.get("module_code") or "").strip()
    external_price_ref = str(payload.get("external_price_ref") or "").strip()
    result = saas_providers.create_stripe_checkout_session(
        secret=saas_services.provider_secrets(credential),
        config=credential.config_json or {},
        tenant_id=str(job.tenant_id),
        tenant_email=payload.get("tenant_email"),
        module_code=module_code,
        module_price_id=module_price_id,
        price_ref=external_price_ref,
        idempotency_key=job.idempotency_key,
    )
    session_id = str(result.get("session_id") or "").strip()
    if not session_id:
        raise ValueError("Stripe checkout did not return a session id")
    _upsert_billing_account(
        db,
        tenant_id=str(job.tenant_id),
        provider="stripe",
        customer_ref=result.get("customer"),
        subscription_ref=result.get("subscription"),
        status="CHECKOUT_PENDING",
        metadata={
            "checkout_session_id": session_id,
            "module_code": module_code,
            "module_price_id": module_price_id,
            "external_price_ref": external_price_ref,
            "provider_credential_id": credential.id,
        },
    )
    db.flush()
    return result
'''
    new_checkout = '''def _process_checkout(db: Session, job: models.SaaSJob) -> dict[str, Any]:
    payload = job.payload_json or {}
    tenant_id = str(job.tenant_id or "").strip()
    _lock_checkout_tenant(db, tenant_id)
    pending_account = _stripe_billing_account(db, tenant_id=tenant_id, lock=True)
    if pending_account is not None and str(pending_account.status or "").upper() == "CHECKOUT_PENDING":
        pending = pending_account.metadata_json if isinstance(pending_account.metadata_json, dict) else {}
        if str(pending.get("checkout_idempotency_key") or "") == str(job.idempotency_key or ""):
            return {
                "provider": "stripe",
                "session_id": pending.get("checkout_session_id"),
                "checkout_url": pending.get("checkout_url"),
                "customer": pending_account.external_customer_ref,
                "subscription": pending_account.external_subscription_ref,
                "reused": True,
            }
        raise ValueError("Another Stripe checkout is already pending for this tenant")

    credential = _credential(db, str(payload.get("provider_credential_id") or ""))
    db.refresh(credential)
    saas_services.require_operational_provider(credential, label="Stripe")
    module_price_id = str(payload.get("module_price_id") or "").strip()
    module_code = str(payload.get("module_code") or "").strip()
    external_price_ref = str(payload.get("external_price_ref") or "").strip()
    price = _checkout_price(db, module_price_id=module_price_id, lock=True)
    if (
        price is None
        or not bool(price.is_active)
        or saas_services.normalize_module_code(str(price.module_code or ""))
        != saas_services.normalize_module_code(module_code)
        or str(price.external_price_ref or "") != external_price_ref
    ):
        raise ValueError("Module price is no longer active or no longer matches the queued checkout")

    result = saas_providers.create_stripe_checkout_session(
        secret=saas_services.provider_secrets(credential),
        config=credential.config_json or {},
        tenant_id=tenant_id,
        tenant_email=payload.get("tenant_email"),
        module_code=module_code,
        module_price_id=module_price_id,
        price_ref=external_price_ref,
        idempotency_key=job.idempotency_key,
    )
    session_id = str(result.get("session_id") or "").strip()
    if not session_id:
        raise ValueError("Stripe checkout did not return a session id")
    _upsert_billing_account(
        db,
        tenant_id=tenant_id,
        provider="stripe",
        customer_ref=result.get("customer"),
        subscription_ref=result.get("subscription"),
        status="CHECKOUT_PENDING",
        metadata={
            "checkout_session_id": session_id,
            "checkout_url": result.get("checkout_url"),
            "checkout_job_id": job.id,
            "checkout_idempotency_key": job.idempotency_key,
            "module_code": module_code,
            "module_price_id": module_price_id,
            "external_price_ref": external_price_ref,
            "provider_credential_id": credential.id,
        },
    )
    db.flush()
    return result
'''
    replace_exact("backend/amodb/jobs/saas_worker.py", old_checkout, new_checkout)

    old_enqueue = '''    tenant = db.get(account_models.AMO, tenant_id)
    price = db.get(models.SaaSModulePrice, module_price_id)
    if not tenant or not price or not price.is_active:
        raise ValueError("Tenant or active module price not found")
'''
    new_enqueue = '''    tenant = (
        db.query(account_models.AMO)
        .filter(account_models.AMO.id == tenant_id)
        .with_for_update()
        .first()
    )
    price = db.get(models.SaaSModulePrice, module_price_id)
    if not tenant or not price or not price.is_active:
        raise ValueError("Tenant or active module price not found")
    pending_account = (
        db.query(models.SaaSBillingAccount)
        .filter(
            models.SaaSBillingAccount.tenant_id == tenant_id,
            models.SaaSBillingAccount.provider == "stripe",
            models.SaaSBillingAccount.status == "CHECKOUT_PENDING",
        )
        .first()
    )
    if pending_account is not None:
        raise ValueError("Another Stripe checkout is already pending for this tenant")
    active_job = (
        db.query(models.SaaSJob)
        .filter(
            models.SaaSJob.job_type == "STRIPE_CREATE_CHECKOUT_SESSION",
            models.SaaSJob.tenant_scope == tenant_id,
            models.SaaSJob.status.in_({"PENDING", "RETRY", "RUNNING"}),
        )
        .order_by(models.SaaSJob.created_at.desc())
        .first()
    )
    if active_job is not None:
        if str(active_job.idempotency_key or "") == idempotency_key.strip():
            return active_job
        raise ValueError("Another Stripe checkout request is already queued for this tenant")
'''
    replace_exact("backend/amodb/apps/platform/saas_services.py", old_enqueue, new_enqueue)

    test_path = Path("backend/amodb/apps/platform/tests/test_saas_checkout_lifecycle.py")
    test_path.write_text('''from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from amodb.apps.accounts import models as account_models
from amodb.apps.platform import saas_models
from amodb.jobs import saas_worker


def _job() -> SimpleNamespace:
    return SimpleNamespace(
        id="job-1",
        tenant_id="amo-1",
        idempotency_key="checkout-action-1",
        payload_json={
            "provider_credential_id": "credential-1",
            "module_price_id": "price-1",
            "module_code": "quality",
            "external_price_ref": "price_stripe_1",
            "tenant_email": "admin@example.test",
        },
    )


def _credential(status: str = "HEALTHY") -> SimpleNamespace:
    return SimpleNamespace(
        id="credential-1",
        provider="stripe",
        tenant_id="amo-1",
        status=status,
        encrypted_secret="encrypted",
        config_json={},
    )


def _price(*, active: bool = True, module_code: str = "quality", price_ref: str = "price_stripe_1") -> SimpleNamespace:
    return SimpleNamespace(
        id="price-1",
        is_active=active,
        module_code=module_code,
        external_price_ref=price_ref,
    )


def _account(status: str = "CHECKOUT_PENDING") -> SimpleNamespace:
    return SimpleNamespace(
        tenant_id="amo-1",
        provider="stripe",
        status=status,
        external_customer_ref="cus-1",
        external_subscription_ref=None,
        metadata_json={
            "checkout_session_id": "cs-1",
            "checkout_url": "https://checkout.stripe.test/session",
            "checkout_job_id": "job-1",
            "checkout_idempotency_key": "checkout-action-1",
            "module_code": "quality",
            "module_price_id": "price-1",
            "external_price_ref": "price_stripe_1",
        },
    )


def test_worker_rejects_second_checkout_while_first_session_is_pending(monkeypatch: pytest.MonkeyPatch):
    job = _job()
    job.id = "job-2"
    job.idempotency_key = "checkout-action-2"
    pending = _account()
    db = MagicMock()
    monkeypatch.setattr(saas_worker, "_lock_checkout_tenant", lambda *_args, **_kwargs: SimpleNamespace(id="amo-1"))
    monkeypatch.setattr(saas_worker, "_stripe_billing_account", lambda *_args, **_kwargs: pending)
    create_session = MagicMock()
    monkeypatch.setattr(saas_worker.saas_providers, "create_stripe_checkout_session", create_session)

    with pytest.raises(ValueError, match="already pending"):
        saas_worker._process_checkout(db, job)

    create_session.assert_not_called()


def test_worker_returns_existing_session_for_same_idempotent_checkout(monkeypatch: pytest.MonkeyPatch):
    pending = _account()
    monkeypatch.setattr(saas_worker, "_lock_checkout_tenant", lambda *_args, **_kwargs: SimpleNamespace(id="amo-1"))
    monkeypatch.setattr(saas_worker, "_stripe_billing_account", lambda *_args, **_kwargs: pending)

    result = saas_worker._process_checkout(MagicMock(), _job())

    assert result["session_id"] == "cs-1"
    assert result["reused"] is True


@pytest.mark.parametrize(
    "price",
    [
        _price(active=False),
        _price(module_code="training"),
        _price(price_ref="price_changed"),
    ],
)
def test_worker_revalidates_module_price_before_stripe(monkeypatch: pytest.MonkeyPatch, price: SimpleNamespace):
    db = MagicMock()
    credential = _credential()
    monkeypatch.setattr(saas_worker, "_lock_checkout_tenant", lambda *_args, **_kwargs: SimpleNamespace(id="amo-1"))
    monkeypatch.setattr(saas_worker, "_stripe_billing_account", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(saas_worker, "_credential", lambda *_args, **_kwargs: credential)
    monkeypatch.setattr(saas_worker, "_checkout_price", lambda *_args, **_kwargs: price)
    create_session = MagicMock()
    monkeypatch.setattr(saas_worker.saas_providers, "create_stripe_checkout_session", create_session)

    with pytest.raises(ValueError, match="no longer active"):
        saas_worker._process_checkout(db, _job())

    create_session.assert_not_called()


def _webhook_event(event_type: str, payment_status: str) -> SimpleNamespace:
    return SimpleNamespace(
        payload=json.dumps({
            "id": f"evt-{event_type}",
            "type": event_type,
            "data": {
                "object": {
                    "id": "cs-1",
                    "client_reference_id": "amo-1",
                    "payment_status": payment_status,
                    "customer": "cus-1",
                    "subscription": "sub-1",
                    "metadata": {
                        "tenant_id": "amo-1",
                        "module_code": "quality",
                        "module_price_id": "price-1",
                        "external_price_ref": "price_stripe_1",
                    },
                }
            },
        }),
        status=account_models.WebhookStatus.RECEIVED,
        processed_at=None,
        attempt_count=0,
        last_error=None,
    )


def _webhook_job(event_id: str = "stored-event") -> SimpleNamespace:
    return SimpleNamespace(
        id="webhook-job",
        tenant_id="amo-1",
        payload_json={"webhook_event_id": event_id, "verified_tenant_id": "amo-1"},
    )


def _run_checkout_event(monkeypatch: pytest.MonkeyPatch, event_type: str, payment_status: str):
    event = _webhook_event(event_type, payment_status)
    account = _account()
    db = MagicMock()
    db.get.return_value = event
    monkeypatch.setattr(
        saas_worker,
        "_validate_pending_checkout",
        lambda *_args, **_kwargs: (account, dict(account.metadata_json), "quality", "price-1", "price_stripe_1"),
    )
    upsert = MagicMock(return_value=account)
    set_module = MagicMock()
    monkeypatch.setattr(saas_worker, "_upsert_billing_account", upsert)
    monkeypatch.setattr(saas_worker, "_set_module_state", set_module)
    result = saas_worker._process_stripe_webhook(db, _webhook_job())
    return result, upsert, set_module


def test_unpaid_completed_checkout_remains_pending(monkeypatch: pytest.MonkeyPatch):
    result, upsert, set_module = _run_checkout_event(
        monkeypatch, "checkout.session.completed", "unpaid"
    )

    assert result["checkout_status"] == "CHECKOUT_PENDING"
    assert upsert.call_args.kwargs["status"] == "CHECKOUT_PENDING"
    set_module.assert_not_called()


def test_async_payment_success_enables_module(monkeypatch: pytest.MonkeyPatch):
    result, upsert, set_module = _run_checkout_event(
        monkeypatch, "checkout.session.async_payment_succeeded", "paid"
    )

    assert result["checkout_status"] == "ACTIVE"
    assert upsert.call_args.kwargs["status"] == "ACTIVE"
    set_module.assert_called_once()


def test_async_payment_failure_releases_pending_checkout(monkeypatch: pytest.MonkeyPatch):
    result, upsert, set_module = _run_checkout_event(
        monkeypatch, "checkout.session.async_payment_failed", "unpaid"
    )

    assert result["checkout_status"] == "CHECKOUT_FAILED"
    assert upsert.call_args.kwargs["status"] == "CHECKOUT_FAILED"
    set_module.assert_not_called()
''', encoding="utf-8")


if __name__ == "__main__":
    main()
