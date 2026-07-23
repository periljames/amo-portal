from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one occurrence, found {count}: {old[:120]!r}")
    file_path.write_text(text.replace(old, new), encoding="utf-8")


def replace_function(path: str, name: str, replacement: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    marker = f"def {name}("
    start = text.find(marker)
    if start < 0:
        raise SystemExit(f"{path}: function {name} not found")
    end = text.find("\ndef ", start + len(marker))
    if end < 0:
        end = len(text)
    updated = text[:start] + replacement.rstrip() + "\n\n" + text[end + 1 :]
    file_path.write_text(updated, encoding="utf-8")


def insert_before(path: str, marker: str, addition: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    if addition.strip() in text:
        raise SystemExit(f"{path}: addition already present")
    index = text.find(marker)
    if index < 0:
        raise SystemExit(f"{path}: marker not found: {marker!r}")
    file_path.write_text(text[:index] + addition.rstrip() + "\n\n" + text[index:], encoding="utf-8")


def main() -> None:
    worker_path = "backend/amodb/jobs/saas_worker.py"
    services_path = "backend/amodb/apps/platform/saas_services.py"

    replace_once(
        worker_path,
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

    replace_function(
        worker_path,
        "_validate_pending_checkout",
        '''def _validate_pending_checkout(
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
    # The portal-created pending record is the immutable commercial snapshot. The
    # mutable catalogue is intentionally not re-read after Stripe created the session.
    return account, pending, module_code, module_price_id, external_price_ref''',
    )

    insert_before(
        worker_path,
        "def _verified_stripe_tenant(",
        '''def _upsert_stripe_account_preserving_pending(
    db: Session,
    *,
    tenant_id: str,
    customer_ref: str | None,
    subscription_ref: str | None,
    status: str,
    event_type: str,
    event_metadata: dict[str, Any],
) -> tuple[models.SaaSBillingAccount, bool]:
    existing = _stripe_billing_account(db, tenant_id=tenant_id, lock=True)
    preserve_pending = bool(
        existing is not None and str(existing.status or "").upper() == "CHECKOUT_PENDING"
    )
    if preserve_pending:
        pending = dict(existing.metadata_json) if isinstance(existing.metadata_json, dict) else {}
        metadata = {
            **pending,
            "previous_account_status": str(status or "UNKNOWN").upper(),
            "previous_account_metadata": dict(event_metadata),
            "last_account_event": event_type,
        }
        effective_status = "CHECKOUT_PENDING"
    else:
        metadata = dict(event_metadata)
        effective_status = status
    account = _upsert_billing_account(
        db,
        tenant_id=tenant_id,
        provider="stripe",
        customer_ref=customer_ref,
        subscription_ref=subscription_ref,
        status=effective_status,
        metadata=metadata,
    )
    return account, preserve_pending''',
    )

    replace_once(
        worker_path,
        '''        failed = event_type == "checkout.session.async_payment_failed"
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
        lifecycle_metadata = {
            **pending,
            "checkout_session_id": str(obj.get("id") or ""),
            "module_code": module_code,
            "module_price_id": module_price_id,
            "external_price_ref": external_price_ref,
            "last_checkout_event": event_type,
            "payment_status": payment_status,
        }
        account_status = checkout_status
        account_metadata: dict[str, Any] = lifecycle_metadata
        if failed or expired:
            previous_status = str(pending.get("previous_account_status") or "").strip().upper()
            previous_metadata = pending.get("previous_account_metadata")
            if previous_status:
                account_status = previous_status
                account_metadata = {
                    **(dict(previous_metadata) if isinstance(previous_metadata, dict) else {}),
                    "last_checkout": lifecycle_metadata,
                }
        _upsert_billing_account(
            db,
            tenant_id=tenant_id,
            provider="stripe",
            customer_ref=customer_ref,
            subscription_ref=subscription_ref,
            status=account_status,
            metadata=account_metadata,
        )
''',
    )

    replace_once(
        worker_path,
        '''        _upsert_billing_account(
            db,
            tenant_id=tenant_id,
            provider="stripe",
            customer_ref=customer_ref,
            subscription_ref=str(obj.get("id") or subscription_ref or "") or None,
            status=subscription_state or "UNKNOWN",
            metadata={"module_code": module_code, "stripe_status": subscription_state},
        )
''',
        '''        _account, checkout_pending_preserved = _upsert_stripe_account_preserving_pending(
            db,
            tenant_id=tenant_id,
            customer_ref=customer_ref,
            subscription_ref=str(obj.get("id") or subscription_ref or "") or None,
            status=subscription_state or "UNKNOWN",
            event_type=event_type,
            event_metadata={"module_code": module_code, "stripe_status": subscription_state},
        )
''',
    )

    replace_once(
        worker_path,
        '''        outcome.update({"tenant_id": tenant_id, "module_code": module_code, "subscription_status": subscription_state})
''',
        '''        outcome.update(
            {
                "tenant_id": tenant_id,
                "module_code": module_code,
                "subscription_status": subscription_state,
                "checkout_pending_preserved": checkout_pending_preserved,
            }
        )
''',
    )

    replace_once(
        worker_path,
        '''        account = _upsert_billing_account(
            db,
            tenant_id=tenant_id,
            provider="stripe",
            customer_ref=customer_ref,
            subscription_ref=subscription_ref,
            status="ACTIVE" if event_type == "invoice.paid" else "PAST_DUE",
            metadata={"last_stripe_invoice": obj.get("id"), "module_code": module_code},
        )
''',
        '''        account, checkout_pending_preserved = _upsert_stripe_account_preserving_pending(
            db,
            tenant_id=tenant_id,
            customer_ref=customer_ref,
            subscription_ref=subscription_ref,
            status="ACTIVE" if event_type == "invoice.paid" else "PAST_DUE",
            event_type=event_type,
            event_metadata={"last_stripe_invoice": obj.get("id"), "module_code": module_code},
        )
''',
    )

    replace_once(
        worker_path,
        '''        outcome.update({"tenant_id": tenant_id, "module_code": module_code or None, "portal_invoice_id": invoice_id or None})
''',
        '''        outcome.update(
            {
                "tenant_id": tenant_id,
                "module_code": module_code or None,
                "portal_invoice_id": invoice_id or None,
                "checkout_pending_preserved": checkout_pending_preserved,
            }
        )
''',
    )

    replace_function(
        worker_path,
        "_process_checkout",
        '''def _process_checkout(db: Session, job: models.SaaSJob) -> dict[str, Any]:
    payload = job.payload_json or {}
    tenant_id = str(job.tenant_id or "").strip()
    _lock_checkout_tenant(db, tenant_id)
    existing_account = _stripe_billing_account(db, tenant_id=tenant_id, lock=True)
    if existing_account is not None and str(existing_account.status or "").upper() == "CHECKOUT_PENDING":
        pending = existing_account.metadata_json if isinstance(existing_account.metadata_json, dict) else {}
        if str(pending.get("checkout_idempotency_key") or "") == str(job.idempotency_key or ""):
            return {
                "provider": "stripe",
                "session_id": pending.get("checkout_session_id"),
                "checkout_url": pending.get("checkout_url"),
                "customer": existing_account.external_customer_ref,
                "subscription": existing_account.external_subscription_ref,
                "reused": True,
            }
        raise ValueError("Another Stripe checkout is already pending for this tenant")

    previous_account_status = (
        str(existing_account.status or "").strip().upper() if existing_account is not None else ""
    )
    previous_account_metadata = (
        dict(existing_account.metadata_json)
        if existing_account is not None and isinstance(existing_account.metadata_json, dict)
        else {}
    )
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
            "checkout_snapshot_created_at": utcnow().isoformat(),
            "module_code": module_code,
            "module_price_id": module_price_id,
            "external_price_ref": external_price_ref,
            "provider_credential_id": credential.id,
            "previous_account_status": previous_account_status or None,
            "previous_account_metadata": previous_account_metadata,
        },
    )
    db.flush()
    return result''',
    )

    replace_once(
        services_path,
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

    replace_function(
        services_path,
        "enqueue_checkout",
        '''def enqueue_checkout(
    db: Session,
    *,
    tenant_id: str,
    module_price_id: str,
    actor_user_id: str,
    idempotency_key: str,
) -> models.SaaSJob:
    normalized_key = idempotency_key.strip()
    if not normalized_key:
        raise ValueError("idempotency_key is required")
    tenant = (
        db.query(account_models.AMO)
        .filter(account_models.AMO.id == tenant_id)
        .with_for_update()
        .first()
    )
    if not tenant:
        raise ValueError("Tenant or active module price not found")
    existing_job = (
        db.query(models.SaaSJob)
        .filter(
            models.SaaSJob.job_type == "STRIPE_CREATE_CHECKOUT_SESSION",
            models.SaaSJob.tenant_scope == tenant_id,
            models.SaaSJob.idempotency_key == normalized_key,
        )
        .first()
    )
    if existing_job is not None:
        return existing_job
    price = db.get(models.SaaSModulePrice, module_price_id)
    if not price or not price.is_active:
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
        raise ValueError("Another Stripe checkout request is already queued for this tenant")
    if not price.external_price_ref:
        raise ValueError("This module price has no external Stripe price reference")
    credential = get_provider_credential(db, provider="stripe", tenant_id=tenant_id)
    if not credential or credential.status not in {"CONFIGURED", "HEALTHY"}:
        raise ValueError("Stripe is not configured for this tenant or platform")
    return saas_queue.enqueue_job(
        db,
        job_type="STRIPE_CREATE_CHECKOUT_SESSION",
        queue_name="billing",
        tenant_id=tenant_id,
        payload={
            "provider_credential_id": credential.id,
            "module_price_id": price.id,
            "module_code": price.module_code,
            "external_price_ref": price.external_price_ref,
            "tenant_email": tenant.contact_email,
        },
        idempotency_key=normalized_key,
        correlation_id=str(uuid.uuid4()),
        created_by=actor_user_id,
        max_attempts=3,
        priority=20,
    )''',
    )

    Path("backend/amodb/apps/platform/tests/test_saas_checkout_consistency_hardening.py").write_text(
        '''from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from amodb.apps.accounts import models as account_models
from amodb.apps.platform import saas_models, saas_services
from amodb.jobs import saas_worker


def _pending_account(*, previous_status: str | None = None) -> SimpleNamespace:
    metadata = {
        "checkout_session_id": "cs-1",
        "checkout_url": "https://checkout.stripe.test/cs-1",
        "checkout_job_id": "job-1",
        "checkout_idempotency_key": "checkout-action-1",
        "module_code": "quality",
        "module_price_id": "price-1",
        "external_price_ref": "price_stripe_1",
    }
    if previous_status:
        metadata["previous_account_status"] = previous_status
        metadata["previous_account_metadata"] = {"stripe_status": previous_status.lower()}
    return SimpleNamespace(
        tenant_id="amo-1",
        provider="stripe",
        status="CHECKOUT_PENDING",
        external_customer_ref="cus-1",
        external_subscription_ref="sub-existing",
        metadata_json=metadata,
    )


def _webhook_job() -> SimpleNamespace:
    return SimpleNamespace(
        id="webhook-job",
        tenant_id="amo-1",
        payload_json={"webhook_event_id": "stored-event", "verified_tenant_id": "amo-1"},
    )


def _checkout_event(event_type: str, payment_status: str = "unpaid") -> SimpleNamespace:
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
                    "subscription": "sub-new",
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


def _run_checkout_event(monkeypatch: pytest.MonkeyPatch, event_type: str, *, previous_status: str | None = None):
    event = _checkout_event(event_type)
    account = _pending_account(previous_status=previous_status)
    db = MagicMock()
    db.get.return_value = event
    monkeypatch.setattr(
        saas_worker,
        "_validate_pending_checkout",
        lambda *_args, **_kwargs: (account, dict(account.metadata_json), "quality", "price-1", "price_stripe_1"),
    )
    upsert = MagicMock(return_value=account)
    monkeypatch.setattr(saas_worker, "_upsert_billing_account", upsert)
    set_module = MagicMock()
    monkeypatch.setattr(saas_worker, "_set_module_state", set_module)
    result = saas_worker._process_stripe_webhook(db, _webhook_job())
    return result, upsert, set_module


def test_expired_checkout_releases_new_account_pending_state(monkeypatch: pytest.MonkeyPatch):
    result, upsert, set_module = _run_checkout_event(monkeypatch, "checkout.session.expired")
    assert result["checkout_status"] == "CHECKOUT_EXPIRED"
    assert upsert.call_args.kwargs["status"] == "CHECKOUT_EXPIRED"
    set_module.assert_not_called()


def test_expired_checkout_restores_existing_account_state(monkeypatch: pytest.MonkeyPatch):
    result, upsert, _set_module = _run_checkout_event(
        monkeypatch, "checkout.session.expired", previous_status="ACTIVE"
    )
    assert result["checkout_status"] == "CHECKOUT_EXPIRED"
    assert upsert.call_args.kwargs["status"] == "ACTIVE"
    assert upsert.call_args.kwargs["metadata"]["last_checkout"]["last_checkout_event"] == "checkout.session.expired"


def test_async_failure_restores_existing_account_state(monkeypatch: pytest.MonkeyPatch):
    result, upsert, _set_module = _run_checkout_event(
        monkeypatch, "checkout.session.async_payment_failed", previous_status="PAST_DUE"
    )
    assert result["checkout_status"] == "CHECKOUT_FAILED"
    assert upsert.call_args.kwargs["status"] == "PAST_DUE"


def test_checkout_completion_uses_immutable_portal_snapshot(monkeypatch: pytest.MonkeyPatch):
    account = _pending_account()
    monkeypatch.setattr(saas_worker, "_stripe_billing_account", lambda *_args, **_kwargs: account)
    lookup = MagicMock(side_effect=AssertionError("mutable catalogue must not be read"))
    monkeypatch.setattr(saas_worker, "_checkout_price", lookup)
    result = saas_worker._validate_pending_checkout(
        MagicMock(),
        tenant_id="amo-1",
        obj={"id": "cs-1"},
        metadata={
            "module_code": "quality",
            "module_price_id": "price-1",
            "external_price_ref": "price_stripe_1",
        },
    )
    assert result[2:] == ("quality", "price-1", "price_stripe_1")
    lookup.assert_not_called()


def test_subscription_event_preserves_pending_checkout(monkeypatch: pytest.MonkeyPatch):
    event = SimpleNamespace(
        payload=json.dumps({
            "id": "evt-sub",
            "type": "customer.subscription.updated",
            "data": {"object": {
                "id": "sub-existing",
                "status": "active",
                "customer": "cus-1",
                "metadata": {"tenant_id": "amo-1", "module_code": "training"},
            }},
        }),
        status=account_models.WebhookStatus.RECEIVED,
        processed_at=None,
        attempt_count=0,
        last_error=None,
    )
    account = _pending_account()
    db = MagicMock()
    db.get.return_value = event
    monkeypatch.setattr(saas_worker, "_stripe_billing_account", lambda *_args, **_kwargs: account)
    upsert = MagicMock(return_value=account)
    monkeypatch.setattr(saas_worker, "_upsert_billing_account", upsert)
    monkeypatch.setattr(saas_worker, "_set_module_state", MagicMock())
    result = saas_worker._process_stripe_webhook(db, _webhook_job())
    assert result["checkout_pending_preserved"] is True
    assert upsert.call_args.kwargs["status"] == "CHECKOUT_PENDING"
    metadata = upsert.call_args.kwargs["metadata"]
    assert metadata["checkout_session_id"] == "cs-1"
    assert metadata["previous_account_status"] == "ACTIVE"


def test_invoice_event_preserves_pending_checkout(monkeypatch: pytest.MonkeyPatch):
    event = SimpleNamespace(
        payload=json.dumps({
            "id": "evt-invoice",
            "type": "invoice.paid",
            "data": {"object": {
                "id": "in-1",
                "customer": "cus-1",
                "subscription": "sub-existing",
                "metadata": {"tenant_id": "amo-1"},
            }},
        }),
        status=account_models.WebhookStatus.RECEIVED,
        processed_at=None,
        attempt_count=0,
        last_error=None,
    )
    account = _pending_account()
    db = MagicMock()
    db.get.return_value = event
    monkeypatch.setattr(saas_worker, "_stripe_billing_account", lambda *_args, **_kwargs: account)
    upsert = MagicMock(return_value=account)
    monkeypatch.setattr(saas_worker, "_upsert_billing_account", upsert)
    result = saas_worker._process_stripe_webhook(db, _webhook_job())
    assert result["checkout_pending_preserved"] is True
    assert upsert.call_args.kwargs["status"] == "CHECKOUT_PENDING"
    assert upsert.call_args.kwargs["metadata"]["previous_account_status"] == "ACTIVE"


def test_worker_records_previous_account_snapshot(monkeypatch: pytest.MonkeyPatch):
    existing = SimpleNamespace(
        tenant_id="amo-1",
        provider="stripe",
        status="ACTIVE",
        external_customer_ref="cus-existing",
        external_subscription_ref="sub-existing",
        metadata_json={"stripe_status": "active"},
    )
    credential = SimpleNamespace(
        id="credential-1", provider="stripe", tenant_id="amo-1", status="HEALTHY",
        encrypted_secret="encrypted", config_json={},
    )
    price = SimpleNamespace(
        id="price-1", is_active=True, module_code="quality", external_price_ref="price_stripe_1"
    )
    job = SimpleNamespace(
        id="job-1", tenant_id="amo-1", idempotency_key="checkout-action-1",
        payload_json={
            "provider_credential_id": "credential-1", "module_price_id": "price-1",
            "module_code": "quality", "external_price_ref": "price_stripe_1",
            "tenant_email": "admin@example.test",
        },
    )
    db = MagicMock()
    monkeypatch.setattr(saas_worker, "_lock_checkout_tenant", lambda *_args, **_kwargs: SimpleNamespace(id="amo-1"))
    monkeypatch.setattr(saas_worker, "_stripe_billing_account", lambda *_args, **_kwargs: existing)
    monkeypatch.setattr(saas_worker, "_credential", lambda *_args, **_kwargs: credential)
    monkeypatch.setattr(saas_worker, "_checkout_price", lambda *_args, **_kwargs: price)
    monkeypatch.setattr(saas_worker.saas_services, "provider_secrets", lambda *_args: {"secret_key": "sk_test"})
    monkeypatch.setattr(
        saas_worker.saas_providers,
        "create_stripe_checkout_session",
        lambda **_kwargs: {"session_id": "cs-new", "checkout_url": "https://checkout.stripe.test/cs-new"},
    )
    upsert = MagicMock(return_value=existing)
    monkeypatch.setattr(saas_worker, "_upsert_billing_account", upsert)
    saas_worker._process_checkout(db, job)
    metadata = upsert.call_args.kwargs["metadata"]
    assert metadata["previous_account_status"] == "ACTIVE"
    assert metadata["previous_account_metadata"] == {"stripe_status": "active"}


def test_module_price_patch_preserves_omitted_fields():
    row = SimpleNamespace(
        id="price-1", module_code="quality", plan_code="STANDARD", billing_term="MONTHLY",
        currency="USD", amount_cents=1000, tax_rate_bps=1600, trial_days=14,
        external_price_ref="price_stripe_1", is_active=False, updated_by=None,
    )
    db = MagicMock()
    db.get.return_value = row
    duplicate = MagicMock()
    duplicate.filter.return_value = duplicate
    duplicate.first.return_value = None
    db.query.return_value = duplicate
    saas_services.upsert_module_price(
        db, price_id="price-1", payload={"amount_cents": 2000}, actor_user_id="admin-1"
    )
    assert row.amount_cents == 2000
    assert row.external_price_ref == "price_stripe_1"
    assert row.is_active is False


def test_module_price_patch_can_explicitly_clear_and_reactivate():
    row = SimpleNamespace(
        id="price-1", module_code="quality", plan_code="STANDARD", billing_term="MONTHLY",
        currency="USD", amount_cents=1000, tax_rate_bps=1600, trial_days=14,
        external_price_ref="price_stripe_1", is_active=False, updated_by=None,
    )
    db = MagicMock()
    db.get.return_value = row
    duplicate = MagicMock()
    duplicate.filter.return_value = duplicate
    duplicate.first.return_value = None
    db.query.return_value = duplicate
    saas_services.upsert_module_price(
        db,
        price_id="price-1",
        payload={"external_price_ref": "", "is_active": True},
        actor_user_id="admin-1",
    )
    assert row.external_price_ref is None
    assert row.is_active is True


def test_matching_completed_checkout_job_is_returned_before_pending_rejection():
    tenant = SimpleNamespace(id="amo-1", contact_email="admin@example.test")
    existing_job = SimpleNamespace(
        id="job-complete", status="SUCCEEDED", idempotency_key="checkout-action-1"
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


def test_checkout_rejects_blank_idempotency_key():
    with pytest.raises(ValueError, match="idempotency_key is required"):
        saas_services.enqueue_checkout(
            MagicMock(),
            tenant_id="amo-1",
            module_price_id="price-1",
            actor_user_id="admin-1",
            idempotency_key="   ",
        )


def test_expired_checkout_is_tenant_mutating():
    assert "checkout.session.expired" in saas_worker.TENANT_MUTATING_STRIPE_EVENTS
''',
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
