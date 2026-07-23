from __future__ import annotations

import base64
import hashlib
import hmac
import json
import smtplib
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any

from .saas_secrets import redact_mapping


@dataclass(frozen=True)
class ProviderDefinition:
    code: str
    display_name: str
    category: str
    secret_fields: tuple[str, ...]
    config_fields: tuple[str, ...]
    description: str


_PROVIDER_DEFINITIONS = (
    ProviderDefinition("stripe", "Stripe", "BILLING", ("secret_key", "webhook_secret"), ("api_base_url", "success_url", "cancel_url"), "Recurring card subscriptions and invoice webhooks."),
    ProviderDefinition("mpesa_daraja", "M-PESA Daraja", "PAYMENTS", ("consumer_secret", "passkey"), ("consumer_key", "shortcode", "environment", "callback_url"), "M-PESA collection APIs through Safaricom Daraja."),
    ProviderDefinition("etims_oscu", "KRA eTIMS OSCU", "TAX", ("client_secret", "certificate_password"), ("endpoint", "client_id", "device_serial", "certified", "integrator_name"), "KRA eTIMS online sales control unit system-to-system bridge."),
    ProviderDefinition("etims_vscu", "KRA eTIMS VSCU", "TAX", ("client_secret", "certificate_password"), ("endpoint", "client_id", "device_serial", "certified", "integrator_name"), "KRA eTIMS virtual sales control unit system-to-system bridge."),
    ProviderDefinition("smtp", "SMTP server", "EMAIL", ("password",), ("host", "port", "username", "from_email", "from_name", "use_tls", "use_ssl", "allow_self_signed"), "Transactional email through a tenant or platform SMTP server."),
    ProviderDefinition("sendgrid", "SendGrid", "EMAIL", ("api_key",), ("api_base_url", "from_email", "from_name"), "Transactional email through the SendGrid API."),
    ProviderDefinition("openai", "OpenAI", "AI", ("api_key",), ("api_base_url", "model", "project", "organization"), "Server-side support assistant and controlled AI workflows."),
    ProviderDefinition("azure_openai", "Azure OpenAI", "AI", ("api_key",), ("endpoint", "deployment", "api_version"), "Server-side Azure OpenAI deployment."),
    ProviderDefinition("zendesk", "Zendesk", "SUPPORT", ("api_token",), ("subdomain", "email"), "External support desk synchronization."),
    ProviderDefinition("jira", "Jira Service Management", "SUPPORT", ("api_token",), ("base_url", "email", "project_key"), "External service desk synchronization."),
    ProviderDefinition("freshdesk", "Freshdesk", "SUPPORT", ("api_key",), ("domain",), "External support desk synchronization."),
)

PROVIDERS = {definition.code: definition for definition in _PROVIDER_DEFINITIONS}


def provider_catalog() -> list[dict[str, Any]]:
    return [
        {
            "provider": definition.code,
            "display_name": definition.display_name,
            "category": definition.category,
            "secret_fields": list(definition.secret_fields),
            "config_fields": list(definition.config_fields),
            "description": definition.description,
        }
        for definition in _PROVIDER_DEFINITIONS
    ]


def _safe_url(url: str, *, allowed_schemes: tuple[str, ...] = ("https",)) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in allowed_schemes or not parsed.hostname:
        raise ValueError("Provider endpoint must be an absolute HTTPS URL")
    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "127.0.0.1", "::1"} or hostname.endswith(".local"):
        raise ValueError("Provider endpoints cannot target localhost or private development names")
    return url.rstrip("/")


def _json_request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | bytes | None = None,
    timeout: float = 8.0,
) -> tuple[int, dict[str, Any] | list[Any] | str, float]:
    if isinstance(body, dict):
        data = json.dumps(body).encode("utf-8")
        effective_headers = {"Content-Type": "application/json", **(headers or {})}
    else:
        data = body
        effective_headers = headers or {}
    request = urllib.request.Request(_safe_url(url), data=data, method=method, headers=effective_headers)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=max(1.0, min(timeout, 20.0))) as response:
            raw = response.read(2 * 1024 * 1024)
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read(2 * 1024 * 1024)
        status = int(exc.code)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    text = raw.decode("utf-8", errors="replace")
    try:
        parsed: dict[str, Any] | list[Any] | str = json.loads(text) if text else {}
    except json.JSONDecodeError:
        parsed = text[:4000]
    return status, parsed, elapsed_ms


def _form_request(
    url: str,
    *,
    headers: dict[str, str],
    fields: list[tuple[str, str]],
    timeout: float = 10.0,
) -> tuple[int, dict[str, Any] | list[Any] | str, float]:
    payload = urllib.parse.urlencode(fields).encode("utf-8")
    return _json_request(
        url,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", **headers},
        body=payload,
        timeout=timeout,
    )


def verify_stripe_signature(
    payload: bytes,
    signature_header: str,
    webhook_secret: str,
    *,
    tolerance_seconds: int = 300,
    now_epoch: int | None = None,
) -> bool:
    if not payload or not signature_header or not webhook_secret:
        return False
    timestamp: int | None = None
    signatures: list[str] = []
    for item in signature_header.split(","):
        key, _, value = item.strip().partition("=")
        if key == "t" and value.isdigit():
            timestamp = int(value)
        elif key == "v1" and value:
            signatures.append(value)
    if timestamp is None or not signatures:
        return False
    now_epoch = int(time.time()) if now_epoch is None else int(now_epoch)
    if abs(now_epoch - timestamp) > max(30, int(tolerance_seconds)):
        return False
    signed = f"{timestamp}.".encode("utf-8") + payload
    expected = hmac.new(webhook_secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, candidate) for candidate in signatures)


def create_stripe_checkout_session(
    *,
    secret: dict[str, Any],
    config: dict[str, Any],
    tenant_id: str,
    tenant_email: str | None,
    module_code: str,
    module_price_id: str,
    price_ref: str,
    idempotency_key: str,
) -> dict[str, Any]:
    secret_key = str(secret.get("secret_key") or "").strip()
    if not secret_key:
        raise ValueError("Stripe secret_key is not configured")
    if not price_ref:
        raise ValueError("Stripe external price reference is not configured for this module price")
    if not module_price_id:
        raise ValueError("Portal module price id is required for Stripe checkout")
    api_base = _safe_url(str(config.get("api_base_url") or "https://api.stripe.com"))
    success_url = str(config.get("success_url") or "").strip()
    cancel_url = str(config.get("cancel_url") or "").strip()
    if not success_url or not cancel_url:
        raise ValueError("Stripe success_url and cancel_url must be configured")
    _safe_url(success_url, allowed_schemes=("https", "http"))
    _safe_url(cancel_url, allowed_schemes=("https", "http"))

    fields = [
        ("mode", "subscription"),
        ("line_items[0][price]", price_ref),
        ("line_items[0][quantity]", "1"),
        ("success_url", success_url),
        ("cancel_url", cancel_url),
        ("client_reference_id", tenant_id),
        ("metadata[tenant_id]", tenant_id),
        ("metadata[module_code]", module_code),
        ("metadata[module_price_id]", module_price_id),
        ("metadata[external_price_ref]", price_ref),
        ("subscription_data[metadata][tenant_id]", tenant_id),
        ("subscription_data[metadata][module_code]", module_code),
        ("subscription_data[metadata][module_price_id]", module_price_id),
        ("subscription_data[metadata][external_price_ref]", price_ref),
    ]
    if tenant_email:
        fields.append(("customer_email", tenant_email))
    status, response, elapsed = _form_request(
        f"{api_base}/v1/checkout/sessions",
        headers={"Authorization": f"Bearer {secret_key}", "Idempotency-Key": idempotency_key},
        fields=fields,
    )
    if status < 200 or status >= 300 or not isinstance(response, dict):
        raise RuntimeError(f"Stripe checkout request failed ({status}): {redact_mapping(response if isinstance(response, dict) else {'detail': response})}")
    return {
        "provider": "stripe",
        "session_id": response.get("id"),
        "checkout_url": response.get("url"),
        "customer": response.get("customer"),
        "subscription": response.get("subscription"),
        "latency_ms": elapsed,
    }


def openai_support_response(
    *,
    secret: dict[str, Any],
    config: dict[str, Any],
    instructions: str,
    user_message: str,
) -> dict[str, Any]:
    api_key = str(secret.get("api_key") or "").strip()
    if not api_key:
        raise ValueError("OpenAI api_key is not configured")
    api_base = _safe_url(str(config.get("api_base_url") or "https://api.openai.com"))
    model = str(config.get("model") or "gpt-5-mini").strip()
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if config.get("project"):
        headers["OpenAI-Project"] = str(config["project"])
    if config.get("organization"):
        headers["OpenAI-Organization"] = str(config["organization"])
    status, response, elapsed = _json_request(
        f"{api_base}/v1/responses",
        method="POST",
        headers=headers,
        body={"model": model, "instructions": instructions, "input": user_message},
        timeout=20,
    )
    if status < 200 or status >= 300 or not isinstance(response, dict):
        raise RuntimeError(f"OpenAI request failed ({status})")
    text = response.get("output_text")
    if not text:
        parts: list[str] = []
        for item in response.get("output") or []:
            for content in item.get("content") or []:
                if content.get("type") in {"output_text", "text"} and content.get("text"):
                    parts.append(str(content["text"]))
        text = "\n".join(parts).strip()
    return {
        "provider": "openai",
        "response_id": response.get("id"),
        "model": response.get("model") or model,
        "text": text or "No assistant response was returned.",
        "usage": response.get("usage") or {},
        "latency_ms": elapsed,
    }


def send_smtp_email(
    *,
    secret: dict[str, Any],
    config: dict[str, Any],
    to_email: str,
    subject: str,
    body: str,
) -> dict[str, Any]:
    host = str(config.get("host") or "").strip()
    port = int(config.get("port") or (465 if config.get("use_ssl") else 587))
    username = str(config.get("username") or "").strip()
    password = str(secret.get("password") or "")
    from_email = str(config.get("from_email") or username).strip()
    if not host or not from_email or not to_email:
        raise ValueError("SMTP host, from_email and recipient are required")
    context = ssl.create_default_context()
    if config.get("allow_self_signed"):
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    started = time.perf_counter()
    if config.get("use_ssl"):
        client: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=10, context=context)
    else:
        client = smtplib.SMTP(host, port, timeout=10)
    try:
        client.ehlo()
        if config.get("use_tls", True) and not config.get("use_ssl"):
            client.starttls(context=context)
            client.ehlo()
        if username:
            client.login(username, password)
        message = EmailMessage()
        message["From"] = f"{config.get('from_name')} <{from_email}>" if config.get("from_name") else from_email
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)
        client.send_message(message)
    finally:
        try:
            client.quit()
        except Exception:
            client.close()
    return {"provider": "smtp", "recipient": to_email, "latency_ms": round((time.perf_counter() - started) * 1000, 2)}


def _basic_auth(username: str, password: str) -> str:
    return base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")


def check_provider(provider: str, *, secret: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    provider = provider.strip().lower()
    started = time.perf_counter()
    if provider == "stripe":
        key = str(secret.get("secret_key") or "").strip()
        if not key:
            raise ValueError("Stripe secret_key is not configured")
        base = _safe_url(str(config.get("api_base_url") or "https://api.stripe.com"))
        status, response, elapsed = _json_request(f"{base}/v1/account", headers={"Authorization": f"Bearer {key}"})
        if not 200 <= status < 300:
            raise RuntimeError(f"Stripe health check failed ({status})")
        return {"ok": True, "provider": provider, "latency_ms": elapsed, "account_id": response.get("id") if isinstance(response, dict) else None}

    if provider == "openai":
        key = str(secret.get("api_key") or "").strip()
        if not key:
            raise ValueError("OpenAI api_key is not configured")
        base = _safe_url(str(config.get("api_base_url") or "https://api.openai.com"))
        headers = {"Authorization": f"Bearer {key}"}
        if config.get("project"):
            headers["OpenAI-Project"] = str(config["project"])
        status, _, elapsed = _json_request(f"{base}/v1/models", headers=headers)
        if not 200 <= status < 300:
            raise RuntimeError(f"OpenAI health check failed ({status})")
        return {"ok": True, "provider": provider, "latency_ms": elapsed}

    if provider == "mpesa_daraja":
        consumer_key = str(config.get("consumer_key") or "").strip()
        consumer_secret = str(secret.get("consumer_secret") or "").strip()
        if not consumer_key or not consumer_secret:
            raise ValueError("Daraja consumer_key and consumer_secret are required")
        environment = str(config.get("environment") or "sandbox").lower()
        base = "https://sandbox.safaricom.co.ke" if environment != "production" else "https://api.safaricom.co.ke"
        status, _, elapsed = _json_request(
            f"{base}/oauth/v1/generate?grant_type=client_credentials",
            headers={"Authorization": f"Basic {_basic_auth(consumer_key, consumer_secret)}"},
        )
        if not 200 <= status < 300:
            raise RuntimeError(f"Daraja health check failed ({status})")
        return {"ok": True, "provider": provider, "latency_ms": elapsed, "environment": environment}

    if provider == "smtp":
        host = str(config.get("host") or "").strip()
        port = int(config.get("port") or 587)
        if not host:
            raise ValueError("SMTP host is required")
        client = smtplib.SMTP(host, port, timeout=8)
        try:
            code, _ = client.noop()
        finally:
            client.close()
        if int(code) >= 400:
            raise RuntimeError(f"SMTP health check failed ({code})")
        return {"ok": True, "provider": provider, "latency_ms": round((time.perf_counter() - started) * 1000, 2)}

    if provider in {"etims_oscu", "etims_vscu"}:
        if not bool(config.get("certified")):
            raise ValueError("eTIMS adapter is not marked as KRA-tested/certified")
        endpoint = str(config.get("endpoint") or "").strip()
        if not endpoint:
            raise ValueError("eTIMS endpoint is required")
        status, _, elapsed = _json_request(endpoint, method="HEAD", timeout=8)
        if status >= 500:
            raise RuntimeError(f"eTIMS endpoint health check failed ({status})")
        return {"ok": True, "provider": provider, "latency_ms": elapsed, "certified": True}

    definition = PROVIDERS.get(provider)
    if not definition:
        raise ValueError("Unknown provider")
    endpoint = str(config.get("base_url") or config.get("api_base_url") or config.get("endpoint") or "").strip()
    if not endpoint:
        return {"ok": True, "provider": provider, "latency_ms": 0, "detail": "Configuration is stored; no generic endpoint was supplied."}
    status, _, elapsed = _json_request(endpoint, method="HEAD", timeout=8)
    if status >= 500:
        raise RuntimeError(f"Provider health check failed ({status})")
    return {"ok": True, "provider": provider, "latency_ms": elapsed}


def fiscalize_etims_invoice(
    *,
    provider: str,
    secret: dict[str, Any],
    config: dict[str, Any],
    invoice_payload: dict[str, Any],
) -> dict[str, Any]:
    if provider not in {"etims_oscu", "etims_vscu"}:
        raise ValueError("Unsupported fiscalization provider")
    if not bool(config.get("certified")):
        raise RuntimeError("eTIMS fiscalization is blocked until a KRA-tested/certified OSCU or VSCU adapter is configured")
    endpoint = _safe_url(str(config.get("endpoint") or ""))
    token = str(secret.get("client_secret") or "").strip()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    status, response, elapsed = _json_request(endpoint, method="POST", headers=headers, body=invoice_payload, timeout=20)
    if not 200 <= status < 300 or not isinstance(response, dict):
        raise RuntimeError(f"eTIMS fiscalization failed ({status})")
    return {
        "provider": provider,
        "latency_ms": elapsed,
        "fiscal_document_number": response.get("fiscal_document_number") or response.get("invoice_number") or response.get("rcptNo"),
        "control_unit_serial": response.get("control_unit_serial") or response.get("cuSerialNumber"),
        "receipt_signature": response.get("receipt_signature") or response.get("signature"),
        "raw": redact_mapping(response),
    }
