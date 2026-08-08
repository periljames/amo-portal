from pathlib import Path
import ast


def replace_function(path: str, name: str, replacement: str):
    p=Path(path); text=p.read_text(encoding='utf-8'); tree=ast.parse(text)
    node=next((n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name),None)
    if node is None: raise RuntimeError(f'missing {name}: {path}')
    lines=text.splitlines(True)
    p.write_text(''.join(lines[:node.lineno-1]+[replacement.rstrip()+'\n\n']+lines[node.end_lineno:]),encoding='utf-8')

# Commercial summary is currency-safe directly; no accounting monkeypatch.
replace_function('backend/amodb/apps/platform/commercial_services.py','commercial_summary','''def commercial_summary(db: Session, *, data_mode: str = "REAL") -> dict[str, Any]:
    from .commercial_accounting import subledger_summary
    return subledger_summary(db, data_mode=data_mode)''')

# Inbound settlement tolerates transient health alarms but never a disabled provider.
cs=Path('backend/amodb/apps/platform/commercial_services.py')
text=cs.read_text(encoding='utf-8')
if 'def _settlement_credential(' not in text:
    marker='def _billing_account('
    helper='''def _settlement_credential(db: Session, *, provider: str, tenant_id: str, label: str):
    row = saas_services.get_provider_credential(db, provider=provider, tenant_id=tenant_id)
    if row is None:
        raise ValueError(f"{label} is not configured")
    if str(row.status or "").strip().upper() in {"DISABLED", "NOT_CONFIGURED"}:
        raise PermissionError(f"{label} settlement rejected because the provider is disabled")
    return row


'''
    text=text.replace(marker,helper+marker,1)
cs.write_text(text,encoding='utf-8')
replace_function('backend/amodb/apps/platform/commercial_services.py','record_paystack_webhook','''def record_paystack_webhook(db: Session, *, raw_payload: bytes, signature: str):
    payload = json.loads(raw_payload.decode("utf-8"))
    event_type = str(payload.get("event") or "").strip().lower()
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        raise ValueError("Paystack event data is invalid")
    metadata = _metadata_dict(data.get("metadata"))
    tenant_id = str(metadata.get("tenant_id") or "").strip()
    invoice_id = str(metadata.get("portal_invoice_id") or "").strip()
    reference = str(data.get("reference") or "").strip()
    if not tenant_id or not invoice_id or not reference:
        raise ValueError("Paystack event is missing portal tenant, invoice or reference metadata")
    _invoice(db, invoice_id, tenant_id=tenant_id)
    credential = _settlement_credential(db, provider=integrations.PAYSTACK_CODE, tenant_id=tenant_id, label="Paystack")
    secret = saas_services.provider_secrets(credential)
    if not integrations.verify_paystack_signature(raw_payload, signature, str(secret.get("secret_key") or "")):
        raise PermissionError("Invalid Paystack webhook signature")
    return saas_queue.enqueue_job(db, job_type="PAYSTACK_WEBHOOK", queue_name="billing", tenant_id=tenant_id,
        payload={"event_type": event_type, "credential_id": credential.id, "invoice_id": invoice_id, "reference": reference, "data_minimized": True},
        idempotency_key=f"{event_type}:{reference}", correlation_id=reference, max_attempts=6, priority=5)''')
replace_function('backend/amodb/apps/platform/commercial_services.py','_process_paystack_webhook','''def _process_paystack_webhook(db: Session, job: models.SaaSJob) -> dict[str, Any]:
    payload = dict(job.payload_json or {})
    event_type = str(payload.get("event_type") or "").strip().lower()
    reference = str(payload.get("reference") or "").strip()
    tenant_id = str(job.tenant_id or "")
    invoice = _invoice(db, str(payload.get("invoice_id") or ""), tenant_id=tenant_id, lock=True)
    credential = db.get(models.SaaSProviderCredential, str(payload.get("credential_id") or ""))
    if credential is None:
        credential = _settlement_credential(db, provider=integrations.PAYSTACK_CODE, tenant_id=tenant_id, label="Paystack")
    elif str(credential.status or "").strip().upper() in {"DISABLED", "NOT_CONFIGURED"}:
        raise PermissionError("Paystack settlement rejected because the provider is disabled")
    if event_type != "charge.success":
        return {"ignored": True, "event_type": event_type, "reference": reference}
    verification = integrations.paystack_verify_transaction(secret=saas_services.provider_secrets(credential), config=credential.config_json or {}, reference=reference)
    data = verification.get("data") or {}
    if not isinstance(data, dict) or str(data.get("status") or "").lower() != "success":
        raise ValueError("Paystack transaction is not verified as successful")
    metadata = _metadata_dict(data.get("metadata"))
    if str(metadata.get("tenant_id") or "") != invoice.amo_id or str(metadata.get("portal_invoice_id") or "") != invoice.id:
        raise ValueError("Paystack verified transaction metadata does not match the portal invoice")
    paid = mark_invoice_paid(db, invoice_id=invoice.id, provider=integrations.PAYSTACK_CODE, provider_reference=reference,
        actor_user_id=job.created_by, verified_amount_cents=int(data.get("amount") or 0), verified_currency=str(data.get("currency") or ""), reason="Paystack transaction verified server-side")
    return {"verified": True, "reference": reference, "invoice": paid}''')

# QBO and capacity safety are canonical functions.
cs=Path('backend/amodb/apps/platform/commercial_services.py'); text=cs.read_text(encoding='utf-8')
needle='''    if not bool((credential.config_json or {}).get("writeback_enabled")):
        raise ValueError("QuickBooks writeback is disabled; enable it only after account/tax mappings are verified")'''
replacement=needle+'''
    config = dict(credential.config_json or {})
    home_currency = str(config.get("home_currency") or "").strip().upper()
    if not home_currency:
        raise ValueError("QuickBooks home_currency must be configured before writeback is enabled")
    invoice_currency = str(invoice.currency or "USD").strip().upper()
    if invoice_currency != home_currency:
        raise ValueError("QuickBooks writeback is blocked for a non-home-currency invoice until deliberate multi-currency accounting is configured")'''
if needle in text: text=text.replace(needle,replacement,1)
text=text.replace('"status": "VERIFIED" if verified and all(value for key, value in checks.items() if key != "read_replica_or_split_read_dsn") else "NOT_YET_PROVEN",','"status": "VERIFIED" if verified and checks and all(checks.values()) else "NOT_YET_PROVEN",')
cs.write_text(text,encoding='utf-8')

# Provider definition owns QBO secret/config fields.
ci=Path('backend/amodb/apps/platform/commercial_integrations.py'); text=ci.read_text(encoding='utf-8')
text=text.replace('(QUICKBOOKS_CODE, "QuickBooks Online", "ACCOUNTING", ("client_secret", "access_token", "refresh_token"),', '(QUICKBOOKS_CODE, "QuickBooks Online", "ACCOUNTING", ("client_secret",),')
ci.write_text(text,encoding='utf-8')

# Accounting module is a direct service, not installer.
ca=Path('backend/amodb/apps/platform/commercial_accounting.py'); text=ca.read_text(encoding='utf-8')
text=text.replace('_INSTALLED = False\n\n','')
idx=text.find('\ndef install_accounting_summary_policy(')
if idx>=0: text=text[:idx].rstrip()+'\n'
ca.write_text(text,encoding='utf-8')

# commercial_policy retains tenant lifecycle evidence only; remove service monkeypatching.
cp=Path('backend/amodb/apps/platform/commercial_policy.py'); text=cp.read_text(encoding='utf-8')
for line in ['from . import commercial_services\n','from . import services as platform_services\n','_INSTALLED = False\n','_ORIGINAL_BILLING_SUMMARY = None\n','_ORIGINAL_DASHBOARD_SUMMARY = None\n']:
    text=text.replace(line,'')
for fn in ['_billing_summary','_dashboard_summary','install_commercial_control_policy']:
    cp.write_text(text,encoding='utf-8');
    try:
        tree=ast.parse(text); node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==fn)
        lines=text.splitlines(True); start=node.lineno-1; end=node.end_lineno
        while end<len(lines) and not lines[end].strip(): end+=1
        text=''.join(lines[:start]+lines[end:])
    except StopIteration: pass
cp.write_text(text.rstrip()+'\n',encoding='utf-8')

# Remove installers/files superseded by direct code.
init=Path('backend/amodb/apps/platform/__init__.py'); text=init.read_text(encoding='utf-8')
for line in ['from .commercial_accounting import install_accounting_summary_policy\n','from .commercial_safety_policy import install_commercial_safety_policy\n','from .commercial_policy import install_commercial_control_policy\n','install_accounting_summary_policy()\n','install_commercial_safety_policy()\n','install_commercial_control_policy()\n']:
    text=text.replace(line,'')
init.write_text(text.rstrip()+'\n',encoding='utf-8')
p=Path('backend/amodb/apps/platform/commercial_safety_policy.py')
if p.exists(): p.unlink()
