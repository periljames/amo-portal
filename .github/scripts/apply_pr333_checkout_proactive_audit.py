from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one occurrence, found {count}: {old[:120]!r}")
    file_path.write_text(text.replace(old, new), encoding="utf-8")


def main() -> None:
    worker = "backend/amodb/jobs/saas_worker.py"
    services = "backend/amodb/apps/platform/saas_services.py"
    tests = "backend/amodb/apps/platform/tests/test_saas_checkout_consistency_hardening.py"

    replace_once(
        worker,
        '''    module_code = str(metadata.get("module_code") or "").strip()
    customer_ref = str(obj.get("customer") or "").strip() or None
    subscription_ref = str(obj.get("subscription") or obj.get("id") or "").strip() or None
''',
        '''    module_code = str(metadata.get("module_code") or "").strip()
    customer_ref = str(obj.get("customer") or "").strip() or None
    if event_type.startswith("customer.subscription."):
        subscription_ref = str(obj.get("id") or "").strip() or None
    else:
        subscription_ref = str(obj.get("subscription") or "").strip() or None
''',
    )

    replace_once(
        services,
        '''    if existing_job is not None:
        return existing_job
''',
        '''    if existing_job is not None:
        existing_payload = getattr(existing_job, "payload_json", None) or {}
        existing_price_id = str(existing_payload.get("module_price_id") or "").strip()
        if existing_price_id and existing_price_id != module_price_id:
            raise ValueError("idempotency_key is already used for a different checkout request")
        return existing_job
''',
    )

    path = Path(tests)
    text = path.read_text(encoding="utf-8")
    addition = '''


def test_checkout_session_id_is_not_stored_as_subscription_reference(monkeypatch: pytest.MonkeyPatch):
    event = _checkout_event("checkout.session.expired")
    payload = json.loads(event.payload)
    payload["data"]["object"].pop("subscription", None)
    event.payload = json.dumps(payload)
    account = _pending_account(previous_status="ACTIVE")
    db = MagicMock()
    db.get.return_value = event
    monkeypatch.setattr(
        saas_worker,
        "_validate_pending_checkout",
        lambda *_args, **_kwargs: (account, dict(account.metadata_json), "quality", "price-1", "price_stripe_1"),
    )
    upsert = MagicMock(return_value=account)
    monkeypatch.setattr(saas_worker, "_upsert_billing_account", upsert)
    monkeypatch.setattr(saas_worker, "_set_module_state", MagicMock())
    saas_worker._process_stripe_webhook(db, _webhook_job())
    assert upsert.call_args.kwargs["subscription_ref"] is None


def test_idempotency_key_reuse_with_different_price_is_rejected():
    tenant = SimpleNamespace(id="amo-1", contact_email="admin@example.test")
    existing_job = SimpleNamespace(
        id="job-complete",
        status="SUCCEEDED",
        idempotency_key="checkout-action-1",
        payload_json={"module_price_id": "price-old"},
    )
    tenant_query = MagicMock()
    tenant_query.filter.return_value.with_for_update.return_value.first.return_value = tenant
    job_query = MagicMock()
    job_query.filter.return_value.first.return_value = existing_job
    db = MagicMock()
    db.query.side_effect = [tenant_query, job_query]
    with pytest.raises(ValueError, match="different checkout request"):
        saas_services.enqueue_checkout(
            db,
            tenant_id="amo-1",
            module_price_id="price-new",
            actor_user_id="admin-1",
            idempotency_key="checkout-action-1",
        )
'''
    if addition.strip() in text:
        raise SystemExit("Proactive checkout audit tests already present")
    path.write_text(text + addition, encoding="utf-8")


if __name__ == "__main__":
    main()
