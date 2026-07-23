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
        "backend/amodb/apps/platform/saas_services.py",
        "SUPPORT_PRIORITIES = {\"LOW\", \"NORMAL\", \"HIGH\", \"URGENT\", \"CRITICAL\"}\n",
        "SUPPORT_PRIORITIES = {\"LOW\", \"NORMAL\", \"HIGH\", \"URGENT\", \"CRITICAL\"}\n"
        "OPERATIONAL_PROVIDER_STATUSES = frozenset({\"CONFIGURED\", \"HEALTHY\"})\n"
        "ACTIVE_AI_JOB_STATUSES = frozenset({\"PENDING\", \"RUNNING\", \"RETRY\"})\n",
    )
    replace_exact(
        "backend/amodb/apps/platform/saas_services.py",
        "def utcnow() -> datetime:\n    return datetime.now(timezone.utc)\n",
        "def utcnow() -> datetime:\n    return datetime.now(timezone.utc)\n\n\n"
        "def require_operational_provider(credential: Any, *, label: str) -> None:\n"
        "    status = str(getattr(credential, \"status\", \"\") or \"\").strip().upper()\n"
        "    if credential is None or status not in OPERATIONAL_PROVIDER_STATUSES:\n"
        "        raise ValueError(f\"{label} provider is disabled or not operational\")\n\n\n"
        "def _ticket_ai_jobs(db: Session, *, ticket_id: str, tenant_id: str | None) -> list[models.SaaSJob]:\n"
        "    scope = tenant_id or \"__platform__\"\n"
        "    rows = (\n"
        "        db.query(models.SaaSJob)\n"
        "        .filter(\n"
        "            models.SaaSJob.job_type == \"AI_SUPPORT_REPLY\",\n"
        "            models.SaaSJob.tenant_scope == scope,\n"
        "        )\n"
        "        .order_by(models.SaaSJob.created_at.asc(), models.SaaSJob.id.asc())\n"
        "        .all()\n"
        "    )\n"
        "    return [row for row in rows if str((row.payload_json or {}).get(\"ticket_id\") or \"\") == ticket_id]\n",
    )
    replace_exact(
        "backend/amodb/apps/platform/saas_services.py",
        "    if not credential:\n        raise ValueError(\"eTIMS provider is not configured\")\n    config = credential.config_json or {}\n",
        "    if not credential:\n        raise ValueError(\"eTIMS provider is not configured\")\n"
        "    require_operational_provider(credential, label=\"eTIMS\")\n"
        "    config = credential.config_json or {}\n",
    )
    replace_exact(
        "backend/amodb/apps/platform/saas_services.py",
        "    if not credential:\n        raise ValueError(\"OpenAI provider is not configured\")\n    return saas_queue.enqueue_job(\n"
        "        db,\n"
        "        job_type=\"AI_SUPPORT_REPLY\",\n"
        "        queue_name=\"ai\",\n"
        "        tenant_id=ticket.tenant_id,\n"
        "        payload={\"ticket_id\": ticket_id, \"credential_id\": credential.id},\n"
        "        idempotency_key=f\"ticket:{ticket_id}:{int(ticket.updated_at.timestamp()) if ticket.updated_at else 0}\",\n"
        "        correlation_id=str(uuid.uuid4()),\n"
        "        created_by=actor_user_id,\n"
        "        max_attempts=3,\n"
        "        priority=50,\n"
        "    )\n",
        "    if not credential:\n        raise ValueError(\"OpenAI provider is not configured\")\n"
        "    require_operational_provider(credential, label=\"OpenAI\")\n\n"
        "    prior_jobs = _ticket_ai_jobs(db, ticket_id=ticket_id, tenant_id=ticket.tenant_id)\n"
        "    for job in reversed(prior_jobs):\n"
        "        if str(job.status or \"\").strip().upper() in ACTIVE_AI_JOB_STATUSES:\n"
        "            return job\n\n"
        "    request_sequence = len(prior_jobs) + 1\n"
        "    request_version = int(ticket.updated_at.timestamp() * 1_000_000) if ticket.updated_at else 0\n"
        "    action_key = f\"ticket:{ticket_id}:ai-reply:{request_version}:{request_sequence}\"\n"
        "    return saas_queue.enqueue_job(\n"
        "        db,\n"
        "        job_type=\"AI_SUPPORT_REPLY\",\n"
        "        queue_name=\"ai\",\n"
        "        tenant_id=ticket.tenant_id,\n"
        "        payload={\n"
        "            \"ticket_id\": ticket_id,\n"
        "            \"credential_id\": credential.id,\n"
        "            \"request_version\": request_version,\n"
        "            \"request_sequence\": request_sequence,\n"
        "        },\n"
        "        idempotency_key=action_key,\n"
        "        correlation_id=str(uuid.uuid4()),\n"
        "        created_by=actor_user_id,\n"
        "        max_attempts=3,\n"
        "        priority=50,\n"
        "    )\n",
    )

    replace_exact(
        "backend/amodb/apps/platform/saas_side_effects.py",
        "from . import saas_models as models\nfrom . import saas_providers, saas_secrets, saas_services\n",
        "from . import saas_models as models\nfrom . import saas_execution_policy, saas_providers, saas_secrets, saas_services\n",
    )
    replace_exact(
        "backend/amodb/apps/platform/saas_side_effects.py",
        "    if fiscalization is None or credential is None:\n        raise ValueError(\"Fiscalization record or credential is missing\")\n    invoice = db.get(account_models.BillingInvoice, fiscalization.invoice_id)\n",
        "    if fiscalization is None or credential is None:\n        raise ValueError(\"Fiscalization record or credential is missing\")\n"
        "    saas_execution_policy.require_operational_provider(credential, label=\"eTIMS\")\n"
        "    invoice = db.get(account_models.BillingInvoice, fiscalization.invoice_id)\n",
    )
    replace_exact(
        "backend/amodb/apps/platform/saas_side_effects.py",
        "    if credential is None or ticket is None or detail is None:\n        raise ValueError(\"Support ticket or OpenAI credential is missing\")\n\n    messages = list(\n",
        "    if credential is None or ticket is None or detail is None:\n        raise ValueError(\"Support ticket or OpenAI credential is missing\")\n"
        "    saas_execution_policy.require_operational_provider(credential, label=\"OpenAI\")\n\n"
        "    messages = list(\n",
    )

    replace_exact(
        "backend/amodb/apps/platform/tests/test_saas_side_effect_safety.py",
        "        provider=\"etims_oscu\",\n        encrypted_secret=\"encrypted\",\n",
        "        provider=\"etims_oscu\",\n        status=\"CONFIGURED\",\n        encrypted_secret=\"encrypted\",\n",
    )
    replace_exact(
        "backend/amodb/apps/platform/tests/test_saas_side_effect_safety.py",
        "        id=\"credential-1\",\n        encrypted_secret=\"encrypted\",\n        config_json={\"model\": \"test-model\"},\n",
        "        id=\"credential-1\",\n        status=\"HEALTHY\",\n        encrypted_secret=\"encrypted\",\n        config_json={\"model\": \"test-model\"},\n",
    )
    path = Path("backend/amodb/apps/platform/tests/test_saas_side_effect_safety.py")
    text = path.read_text(encoding="utf-8")
    marker = "\ndef test_ai_support_reply_uses_existing_adapter_and_is_deduplicated_by_source_job(\n"
    addition = '''\n\n@pytest.mark.parametrize(\n    ("processor", "job_type", "label"),\n    [\n        (saas_side_effects.process_etims_fiscalization, "ETIMS_FISCALIZE_INVOICE", "eTIMS"),\n        (saas_side_effects.process_ai_support_reply, "AI_SUPPORT_REPLY", "OpenAI"),\n    ],\n)\ndef test_disabled_provider_is_rejected_again_when_worker_executes(\n    monkeypatch: pytest.MonkeyPatch,\n    processor,\n    job_type: str,\n    label: str,\n):\n    credential = SimpleNamespace(\n        id="credential-disabled",\n        provider="etims_oscu" if job_type == "ETIMS_FISCALIZE_INVOICE" else "openai",\n        status="DISABLED",\n        encrypted_secret="encrypted",\n        config_json={"certified": True},\n    )\n    job = SimpleNamespace(\n        id="job-disabled",\n        created_by="support-user",\n        idempotency_key="disabled-side-effect",\n        payload_json={\n            "credential_id": credential.id,\n            "fiscalization_id": "fiscal-disabled",\n            "ticket_id": "ticket-disabled",\n        },\n    )\n    fiscalization = SimpleNamespace(\n        id="fiscal-disabled",\n        invoice_id="invoice-disabled",\n        status="PENDING",\n    )\n    ticket = SimpleNamespace(id="ticket-disabled")\n    detail = SimpleNamespace(description="Support request", category="GENERAL")\n    db = MagicMock()\n\n    def get(model, identifier):\n        if model is saas_models.SaaSProviderCredential:\n            return credential\n        if model is saas_models.SaaSInvoiceFiscalization:\n            return fiscalization\n        if model is platform_models.PlatformSupportTicket:\n            return ticket\n        if model is saas_models.SaaSSupportTicketDetail:\n            return detail\n        if model is account_models.BillingInvoice:\n            return SimpleNamespace(id="invoice-disabled")\n        raise AssertionError((model, identifier))\n\n    db.get.side_effect = get\n    db.query.return_value.filter.return_value.first.return_value = None\n    decrypt = MagicMock()\n    monkeypatch.setattr(saas_side_effects.saas_secrets, "decrypt_secret", decrypt)\n\n    with pytest.raises(ValueError, match=f"{label} provider is disabled"):\n        processor(db, job=job)\n\n    decrypt.assert_not_called()\n'''
    if text.count(marker) != 1:
        raise SystemExit("Expected AI side-effect test marker exactly once")
    path.write_text(text.replace(marker, addition + marker), encoding="utf-8")


if __name__ == "__main__":
    main()
