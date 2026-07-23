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
        "backend/amodb/apps/platform/saas_providers.py",
        "    module_code: str,\n    price_ref: str,\n    idempotency_key: str,\n",
        "    module_code: str,\n    module_price_id: str,\n    price_ref: str,\n    idempotency_key: str,\n",
    )
    replace_exact(
        "backend/amodb/apps/platform/saas_providers.py",
        "    if not price_ref:\n        raise ValueError(\"Stripe external price reference is not configured for this module price\")\n",
        "    if not price_ref:\n        raise ValueError(\"Stripe external price reference is not configured for this module price\")\n"
        "    if not module_price_id:\n        raise ValueError(\"Portal module price id is required for Stripe checkout\")\n",
    )
    replace_exact(
        "backend/amodb/apps/platform/saas_providers.py",
        "        (\"metadata[tenant_id]\", tenant_id),\n"
        "        (\"metadata[module_code]\", module_code),\n"
        "        (\"subscription_data[metadata][tenant_id]\", tenant_id),\n"
        "        (\"subscription_data[metadata][module_code]\", module_code),\n",
        "        (\"metadata[tenant_id]\", tenant_id),\n"
        "        (\"metadata[module_code]\", module_code),\n"
        "        (\"metadata[module_price_id]\", module_price_id),\n"
        "        (\"metadata[external_price_ref]\", price_ref),\n"
        "        (\"subscription_data[metadata][tenant_id]\", tenant_id),\n"
        "        (\"subscription_data[metadata][module_code]\", module_code),\n"
        "        (\"subscription_data[metadata][module_price_id]\", module_price_id),\n"
        "        (\"subscription_data[metadata][external_price_ref]\", price_ref),\n",
    )

    replace_exact(
        "backend/amodb/apps/platform/saas_services.py",
        "    row = get_provider_credential(db, provider=provider, tenant_id=tenant_id)\n"
        "    if not row:\n"
        "        raise ValueError(\"Provider is not configured\")\n"
        "    return saas_queue.enqueue_job(\n"
        "        db,\n"
        "        job_type=\"PROVIDER_HEALTH_CHECK\",\n"
        "        queue_name=\"integrations\",\n"
        "        tenant_id=tenant_id,\n"
        "        payload={\"provider\": row.provider, \"credential_id\": row.id},\n",
        "    normalized = (provider or \"\").strip().lower()\n"
        "    exact_row = get_provider_credential(\n"
        "        db,\n"
        "        provider=normalized,\n"
        "        tenant_id=tenant_id,\n"
        "        allow_platform_fallback=False,\n"
        "    ) if tenant_id else get_provider_credential(db, provider=normalized, tenant_id=None)\n"
        "    row = exact_row or get_provider_credential(db, provider=normalized, tenant_id=tenant_id)\n"
        "    if not row:\n"
        "        raise ValueError(\"Provider is not configured\")\n"
        "    status = str(row.status or \"\").strip().upper()\n"
        "    if status == \"DISABLED\":\n"
        "        raise ValueError(\"Disabled providers cannot be health checked\")\n"
        "    if status not in {\"CONFIGURED\", \"HEALTHY\", \"UNHEALTHY\"}:\n"
        "        raise ValueError(\"Provider is not configured for a health check\")\n"
        "    inherited_platform_credential = bool(tenant_id and row.tenant_id is None)\n"
        "    return saas_queue.enqueue_job(\n"
        "        db,\n"
        "        job_type=\"PROVIDER_HEALTH_CHECK\",\n"
        "        queue_name=\"integrations\",\n"
        "        tenant_id=tenant_id,\n"
        "        payload={\n"
        "            \"provider\": row.provider,\n"
        "            \"credential_id\": row.id,\n"
        "            \"mutate_credential_status\": not inherited_platform_credential,\n"
        "            \"credential_scope\": provider_scope(row.tenant_id),\n"
        "        },\n",
    )

    replace_exact(
        "backend/amodb/jobs/saas_worker.py",
        "def _process_provider_health(db: Session, job: models.SaaSJob) -> dict[str, Any]:\n"
        "    credential = _credential(db, str((job.payload_json or {}).get(\"credential_id\") or \"\"))\n"
        "    try:\n"
        "        result = saas_providers.check_provider(\n"
        "            credential.provider,\n"
        "            secret=saas_services.provider_secrets(credential),\n"
        "            config=credential.config_json or {},\n"
        "        )\n"
        "    except Exception as exc:\n"
        "        credential.status = \"UNHEALTHY\"\n"
        "        credential.last_checked_at = utcnow()\n"
        "        credential.last_health_detail = str(exc)[:2000]\n"
        "        credential.last_latency_ms = None\n"
        "        db.flush()\n"
        "        raise\n"
        "    credential.status = \"HEALTHY\"\n"
        "    credential.last_checked_at = utcnow()\n"
        "    credential.last_latency_ms = int(float(result.get(\"latency_ms\") or 0))\n"
        "    credential.last_health_detail = \"Provider health check passed.\"\n"
        "    db.flush()\n"
        "    return result\n",
        "def _process_provider_health(db: Session, job: models.SaaSJob) -> dict[str, Any]:\n"
        "    payload = job.payload_json or {}\n"
        "    credential = _credential(db, str(payload.get(\"credential_id\") or \"\"))\n"
        "    db.refresh(credential)\n"
        "    status = str(credential.status or \"\").strip().upper()\n"
        "    if status == \"DISABLED\":\n"
        "        raise ValueError(\"Disabled providers cannot be health checked\")\n"
        "    if status not in {\"CONFIGURED\", \"HEALTHY\", \"UNHEALTHY\"}:\n"
        "        raise ValueError(\"Provider is not configured for a health check\")\n"
        "    inherited_platform_credential = bool(job.tenant_id and credential.tenant_id is None)\n"
        "    mutate_status = bool(payload.get(\"mutate_credential_status\", True)) and not inherited_platform_credential\n"
        "    try:\n"
        "        result = saas_providers.check_provider(\n"
        "            credential.provider,\n"
        "            secret=saas_services.provider_secrets(credential),\n"
        "            config=credential.config_json or {},\n"
        "        )\n"
        "    except Exception as exc:\n"
        "        if mutate_status:\n"
        "            credential.status = \"UNHEALTHY\"\n"
        "            credential.last_checked_at = utcnow()\n"
        "            credential.last_health_detail = str(exc)[:2000]\n"
        "            credential.last_latency_ms = None\n"
        "            db.flush()\n"
        "        raise\n"
        "    if mutate_status:\n"
        "        credential.status = \"HEALTHY\"\n"
        "        credential.last_checked_at = utcnow()\n"
        "        credential.last_latency_ms = int(float(result.get(\"latency_ms\") or 0))\n"
        "        credential.last_health_detail = \"Provider health check passed.\"\n"
        "        db.flush()\n"
        "    return result\n",
    )

    replace_exact(
        "backend/amodb/jobs/saas_worker.py",
        "    credential = _credential(db, str(payload.get(\"provider_credential_id\") or \"\"))\n"
        "    result = saas_providers.create_stripe_checkout_session(\n"
        "        secret=saas_services.provider_secrets(credential),\n"
        "        config=credential.config_json or {},\n"
        "        tenant_id=str(job.tenant_id),\n"
        "        tenant_email=payload.get(\"tenant_email\"),\n"
        "        module_code=str(payload.get(\"module_code\") or \"\"),\n"
        "        price_ref=str(payload.get(\"external_price_ref\") or \"\"),\n"
        "        idempotency_key=job.idempotency_key,\n"
        "    )\n"
        "    _upsert_billing_account(\n",
        "    credential = _credential(db, str(payload.get(\"provider_credential_id\") or \"\"))\n"
        "    db.refresh(credential)\n"
        "    saas_services.require_operational_provider(credential, label=\"Stripe\")\n"
        "    module_price_id = str(payload.get(\"module_price_id\") or \"\").strip()\n"
        "    module_code = str(payload.get(\"module_code\") or \"\").strip()\n"
        "    external_price_ref = str(payload.get(\"external_price_ref\") or \"\").strip()\n"
        "    result = saas_providers.create_stripe_checkout_session(\n"
        "        secret=saas_services.provider_secrets(credential),\n"
        "        config=credential.config_json or {},\n"
        "        tenant_id=str(job.tenant_id),\n"
        "        tenant_email=payload.get(\"tenant_email\"),\n"
        "        module_code=module_code,\n"
        "        module_price_id=module_price_id,\n"
        "        price_ref=external_price_ref,\n"
        "        idempotency_key=job.idempotency_key,\n"
        "    )\n"
        "    session_id = str(result.get(\"session_id\") or \"\").strip()\n"
        "    if not session_id:\n"
        "        raise ValueError(\"Stripe checkout did not return a session id\")\n"
        "    _upsert_billing_account(\n",
    )
    replace_exact(
        "backend/amodb/jobs/saas_worker.py",
        "        metadata={\"checkout_session_id\": result.get(\"session_id\"), \"module_code\": payload.get(\"module_code\")},\n",
        "        metadata={\n"
        "            \"checkout_session_id\": session_id,\n"
        "            \"module_code\": module_code,\n"
        "            \"module_price_id\": module_price_id,\n"
        "            \"external_price_ref\": external_price_ref,\n"
        "            \"provider_credential_id\": credential.id,\n"
        "        },\n",
    )

    checkout_marker = "    if event_type == \"checkout.session.completed\":\n        if not module_code:\n            raise ValueError(\"Stripe checkout metadata is missing module_code\")\n        payment_status = str(obj.get(\"payment_status\") or \"\").lower()\n"
    checkout_replacement = "    if event_type == \"checkout.session.completed\":\n        if not module_code:\n            raise ValueError(\"Stripe checkout metadata is missing module_code\")\n        session_id = str(obj.get(\"id\") or \"\").strip()\n        module_price_id = str(metadata.get(\"module_price_id\") or \"\").strip()\n        external_price_ref = str(metadata.get(\"external_price_ref\") or \"\").strip()\n        account = (\n            db.query(models.SaaSBillingAccount)\n            .filter(\n                models.SaaSBillingAccount.tenant_id == tenant_id,\n                models.SaaSBillingAccount.provider == \"stripe\",\n            )\n            .first()\n        )\n        pending = account.metadata_json if account and isinstance(account.metadata_json, dict) else {}\n        if account is None or str(account.status or \"\").upper() != \"CHECKOUT_PENDING\":\n            raise ValueError(\"Stripe checkout completion has no pending portal checkout\")\n        expected_session_id = str(pending.get(\"checkout_session_id\") or \"\").strip()\n        expected_module_code = str(pending.get(\"module_code\") or \"\").strip()\n        expected_module_price_id = str(pending.get(\"module_price_id\") or \"\").strip()\n        expected_price_ref = str(pending.get(\"external_price_ref\") or \"\").strip()\n        if not session_id or session_id != expected_session_id:\n            raise ValueError(\"Stripe checkout session does not match the pending portal checkout\")\n        if module_code != expected_module_code or module_price_id != expected_module_price_id or external_price_ref != expected_price_ref:\n            raise ValueError(\"Stripe checkout metadata does not match the pending portal checkout\")\n        price = db.get(models.SaaSModulePrice, expected_module_price_id)\n        if (\n            price is None\n            or saas_services.normalize_module_code(str(price.module_code or \"\")) != saas_services.normalize_module_code(module_code)\n            or str(price.external_price_ref or \"\") != expected_price_ref\n        ):\n            raise ValueError(\"Stripe checkout price does not match the portal module price\")\n        payment_status = str(obj.get(\"payment_status\") or \"\").lower()\n"
    replace_exact("backend/amodb/jobs/saas_worker.py", checkout_marker, checkout_replacement)

    tests = Path("backend/amodb/apps/platform/tests/test_saas_final_review_safeguards.py")
    tests.write_text('''from __future__ import annotations\n\nimport json\nfrom types import SimpleNamespace\nfrom unittest.mock import MagicMock\n\nimport pytest\n\nfrom amodb.apps.accounts import models as account_models\nfrom amodb.apps.platform import saas_models, saas_services\nfrom amodb.jobs import saas_worker\n\n\ndef _webhook_job(event_id: str = "event-1") -> SimpleNamespace:\n    return SimpleNamespace(\n        id="webhook-job",\n        tenant_id="amo-1",\n        payload_json={\n            "webhook_event_id": event_id,\n            "verified_tenant_id": "amo-1",\n        },\n    )\n\n\ndef _checkout_event(session_id: str) -> SimpleNamespace:\n    return SimpleNamespace(\n        payload=json.dumps({\n            "id": "evt-checkout",\n            "type": "checkout.session.completed",\n            "data": {\n                "object": {\n                    "id": session_id,\n                    "client_reference_id": "amo-1",\n                    "payment_status": "paid",\n                    "customer": "cus-1",\n                    "subscription": "sub-1",\n                    "metadata": {\n                        "tenant_id": "amo-1",\n                        "module_code": "quality",\n                        "module_price_id": "price-row-1",\n                        "external_price_ref": "price_stripe_1",\n                    },\n                }\n            },\n        }),\n        status=account_models.WebhookStatus.RECEIVED,\n        processed_at=None,\n        attempt_count=0,\n        last_error=None,\n    )\n\n\ndef _pending_checkout_account() -> SimpleNamespace:\n    return SimpleNamespace(\n        tenant_id="amo-1",\n        provider="stripe",\n        status="CHECKOUT_PENDING",\n        metadata_json={\n            "checkout_session_id": "cs_portal",\n            "module_code": "quality",\n            "module_price_id": "price-row-1",\n            "external_price_ref": "price_stripe_1",\n        },\n    )\n\n\ndef test_checkout_completion_rejects_non_portal_session():\n    event = _checkout_event("cs_external")\n    account = _pending_checkout_account()\n    db = MagicMock()\n    db.get.return_value = event\n    query = MagicMock()\n    query.filter.return_value.first.return_value = account\n    db.query.return_value = query\n\n    with pytest.raises(ValueError, match="does not match the pending portal checkout"):\n        saas_worker._process_stripe_webhook(db, _webhook_job())\n\n\ndef test_checkout_completion_accepts_matching_pending_session(monkeypatch: pytest.MonkeyPatch):\n    event = _checkout_event("cs_portal")\n    account = _pending_checkout_account()\n    price = SimpleNamespace(id="price-row-1", module_code="quality", external_price_ref="price_stripe_1")\n    db = MagicMock()\n\n    def get(model, identifier):\n        if model is account_models.WebhookEvent:\n            return event\n        if model is saas_models.SaaSModulePrice:\n            return price\n        raise AssertionError((model, identifier))\n\n    db.get.side_effect = get\n    query = MagicMock()\n    query.filter.return_value.first.return_value = account\n    db.query.return_value = query\n    set_module_state = MagicMock()\n    monkeypatch.setattr(saas_worker, "_set_module_state", set_module_state)\n    monkeypatch.setattr(saas_worker, "_upsert_billing_account", lambda *args, **kwargs: account)\n\n    result = saas_worker._process_stripe_webhook(db, _webhook_job())\n\n    assert result["module_code"] == "quality"\n    set_module_state.assert_called_once()\n    assert event.status is account_models.WebhookStatus.PROCESSED\n\n\ndef test_tenant_health_check_marks_inherited_credential_non_mutating(monkeypatch: pytest.MonkeyPatch):\n    platform_credential = SimpleNamespace(id="platform-smtp", provider="smtp", tenant_id=None, status="HEALTHY")\n\n    def resolve(db, *, provider, tenant_id=None, allow_platform_fallback=True):\n        if tenant_id and not allow_platform_fallback:\n            return None\n        return platform_credential\n\n    captured: dict[str, object] = {}\n    monkeypatch.setattr(saas_services, "get_provider_credential", resolve)\n    monkeypatch.setattr(\n        saas_services.saas_queue,\n        "enqueue_job",\n        lambda db, **kwargs: captured.update(kwargs) or SimpleNamespace(id="health-job"),\n    )\n\n    saas_services.enqueue_provider_health(\n        MagicMock(), provider="smtp", tenant_id="amo-1", actor_user_id="admin-1"\n    )\n\n    assert captured["payload"]["mutate_credential_status"] is False\n    assert captured["payload"]["credential_scope"] == "PLATFORM"\n\n\ndef test_disabled_provider_cannot_enqueue_health_check(monkeypatch: pytest.MonkeyPatch):\n    disabled = SimpleNamespace(id="tenant-disabled", provider="stripe", tenant_id="amo-1", status="DISABLED")\n    monkeypatch.setattr(saas_services, "get_provider_credential", lambda *args, **kwargs: disabled)\n    enqueue = MagicMock()\n    monkeypatch.setattr(saas_services.saas_queue, "enqueue_job", enqueue)\n\n    with pytest.raises(ValueError, match="Disabled providers cannot be health checked"):\n        saas_services.enqueue_provider_health(\n            MagicMock(), provider="stripe", tenant_id="amo-1", actor_user_id="admin-1"\n        )\n\n    enqueue.assert_not_called()\n\n\ndef test_inherited_health_check_does_not_mutate_platform_row(monkeypatch: pytest.MonkeyPatch):\n    credential = SimpleNamespace(\n        id="platform-smtp",\n        provider="smtp",\n        tenant_id=None,\n        status="CONFIGURED",\n        encrypted_secret="encrypted",\n        config_json={},\n        last_checked_at=None,\n        last_latency_ms=None,\n        last_health_detail=None,\n    )\n    job = SimpleNamespace(\n        tenant_id="amo-1",\n        payload_json={"credential_id": credential.id, "mutate_credential_status": False},\n    )\n    db = MagicMock()\n    db.get.return_value = credential\n    monkeypatch.setattr(saas_worker.saas_services, "provider_secrets", lambda row: {"password": "secret"})\n    monkeypatch.setattr(saas_worker.saas_providers, "check_provider", lambda *args, **kwargs: {"ok": True, "latency_ms": 5})\n\n    result = saas_worker._process_provider_health(db, job)\n\n    assert result["ok"] is True\n    assert credential.status == "CONFIGURED"\n    assert credential.last_checked_at is None\n    db.flush.assert_not_called()\n\n\ndef test_disabled_provider_is_not_revived_by_queued_health_job(monkeypatch: pytest.MonkeyPatch):\n    credential = SimpleNamespace(\n        id="tenant-stripe", provider="stripe", tenant_id="amo-1", status="DISABLED"\n    )\n    job = SimpleNamespace(tenant_id="amo-1", payload_json={"credential_id": credential.id})\n    db = MagicMock()\n    db.get.return_value = credential\n    check = MagicMock()\n    monkeypatch.setattr(saas_worker.saas_providers, "check_provider", check)\n\n    with pytest.raises(ValueError, match="Disabled providers cannot be health checked"):\n        saas_worker._process_provider_health(db, job)\n\n    check.assert_not_called()\n    assert credential.status == "DISABLED"\n\n\ndef test_checkout_worker_rechecks_current_stripe_status(monkeypatch: pytest.MonkeyPatch):\n    credential = SimpleNamespace(\n        id="tenant-stripe",\n        provider="stripe",\n        tenant_id="amo-1",\n        status="DISABLED",\n        encrypted_secret="encrypted",\n        config_json={},\n    )\n    job = SimpleNamespace(\n        tenant_id="amo-1",\n        idempotency_key="checkout-1",\n        payload_json={\n            "provider_credential_id": credential.id,\n            "module_price_id": "price-row-1",\n            "module_code": "quality",\n            "external_price_ref": "price_stripe_1",\n        },\n    )\n    db = MagicMock()\n    db.get.return_value = credential\n    create_session = MagicMock()\n    monkeypatch.setattr(saas_worker.saas_providers, "create_stripe_checkout_session", create_session)\n\n    with pytest.raises(ValueError, match="Stripe provider is disabled or not operational"):\n        saas_worker._process_checkout(db, job)\n\n    create_session.assert_not_called()\n''', encoding="utf-8")


if __name__ == "__main__":
    main()
