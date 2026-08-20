from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import services as account_services
from amodb.observability import operation_span, record_provider_call

from . import models as platform_models
from . import saas_providers, saas_services


AI_MODULE_CODE = "ai"
DEFAULT_MODEL = "gpt-5.6-luna"
DEFAULT_TIER = "STANDARD"
AI_PROVIDER = "openai"
LONG_CONTEXT_THRESHOLD = 272_000

AI_TIER_ORDER = {
    "STANDARD": 10,
    "ADVANCED": 20,
    "PROFESSIONAL": 30,
}


@dataclass(frozen=True)
class AIModelDefinition:
    model: str
    display_name: str
    tier: str
    input_microusd_per_million: int
    cached_input_microusd_per_million: int
    output_microusd_per_million: int
    context_window: int
    max_output_tokens: int
    effective_from: str


# Rate snapshots are deliberately explicit and versioned by effective date. They
# are used for portal cost accounting only; provider invoices remain the final
# external billing source of truth. Rates are stored in micro-USD to preserve
# sub-cent accuracy without floating-point money arithmetic.
AI_MODELS: dict[str, AIModelDefinition] = {
    "gpt-5.6-luna": AIModelDefinition(
        model="gpt-5.6-luna",
        display_name="GPT-5.6 Luna",
        tier="STANDARD",
        input_microusd_per_million=200_000,
        cached_input_microusd_per_million=20_000,
        output_microusd_per_million=1_200_000,
        context_window=1_050_000,
        max_output_tokens=128_000,
        effective_from="2026-08-20",
    ),
    "gpt-5.6-terra": AIModelDefinition(
        model="gpt-5.6-terra",
        display_name="GPT-5.6 Terra",
        tier="ADVANCED",
        input_microusd_per_million=2_000_000,
        cached_input_microusd_per_million=200_000,
        output_microusd_per_million=12_000_000,
        context_window=1_050_000,
        max_output_tokens=128_000,
        effective_from="2026-08-20",
    ),
    "gpt-5.6-sol": AIModelDefinition(
        model="gpt-5.6-sol",
        display_name="GPT-5.6 Sol",
        tier="PROFESSIONAL",
        input_microusd_per_million=5_000_000,
        cached_input_microusd_per_million=500_000,
        output_microusd_per_million=30_000_000,
        context_window=1_050_000,
        max_output_tokens=128_000,
        effective_from="2026-08-20",
    ),
}

PLAN_DEFAULT_MODEL = {
    "STANDARD": "gpt-5.6-luna",
    "ADVANCED": "gpt-5.6-terra",
    "PROFESSIONAL": "gpt-5.6-sol",
}

BillingScope = Literal["PLATFORM_TEST", "PLATFORM", "TENANT"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def current_usage_month() -> str:
    return utcnow().strftime("%Y-%m")


def _safe_month(value: str | None) -> str:
    month = (value or current_usage_month()).strip()
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise ValueError("month must use YYYY-MM format")
    return month


def _subscription_metadata(row: account_models.ModuleSubscription | None) -> dict[str, Any]:
    if row is None or not row.metadata_json:
        return {}
    try:
        value = json.loads(row.metadata_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _ai_subscription(db: Session, tenant_id: str) -> account_models.ModuleSubscription | None:
    return (
        db.query(account_models.ModuleSubscription)
        .filter(
            account_models.ModuleSubscription.amo_id == tenant_id,
            account_models.ModuleSubscription.module_code == AI_MODULE_CODE,
        )
        .first()
    )


def model_catalog() -> list[dict[str, Any]]:
    return [
        {
            "provider": AI_PROVIDER,
            "model": definition.model,
            "display_name": definition.display_name,
            "tier": definition.tier,
            "input_microusd_per_million": definition.input_microusd_per_million,
            "cached_input_microusd_per_million": definition.cached_input_microusd_per_million,
            "output_microusd_per_million": definition.output_microusd_per_million,
            "context_window": definition.context_window,
            "max_output_tokens": definition.max_output_tokens,
            "effective_from": definition.effective_from,
            "long_context_threshold": LONG_CONTEXT_THRESHOLD,
            "long_context_input_multiplier": 2.0,
            "long_context_output_multiplier": 1.5,
        }
        for definition in AI_MODELS.values()
    ]


def tenant_policy(db: Session, tenant_id: str) -> dict[str, Any]:
    tenant = db.get(account_models.AMO, tenant_id)
    if tenant is None:
        raise ValueError("Tenant not found")
    row = _ai_subscription(db, tenant_id)
    metadata = _subscription_metadata(row)
    status = str(getattr(getattr(row, "status", None), "value", getattr(row, "status", "DISABLED")) or "DISABLED").upper()
    plan = str(getattr(row, "plan_code", None) or metadata.get("max_model_tier") or DEFAULT_TIER).upper()
    if plan not in AI_TIER_ORDER:
        plan = DEFAULT_TIER
    model = str(metadata.get("model") or PLAN_DEFAULT_MODEL[plan]).strip()
    if model not in AI_MODELS or AI_TIER_ORDER[AI_MODELS[model].tier] > AI_TIER_ORDER[plan]:
        model = PLAN_DEFAULT_MODEL[plan]
    budget = int(metadata.get("monthly_budget_microusd") or 0)
    markup_bps = int(metadata.get("markup_bps") or 0)
    return {
        "tenant_id": tenant_id,
        "tenant_name": tenant.name,
        "enabled": status in {"ENABLED", "TRIAL"},
        "status": status,
        "plan_code": plan,
        "provider": str(metadata.get("provider") or AI_PROVIDER).lower(),
        "model": model,
        "max_model_tier": plan,
        "monthly_budget_microusd": max(0, budget),
        "hard_limit": bool(metadata.get("hard_limit", True)),
        "allow_external_documents": bool(metadata.get("allow_external_documents", False)),
        "markup_bps": max(0, min(markup_bps, 100_000)),
    }


def _meter_key(metric: str, month: str) -> str:
    return f"ai.{metric}:{month}"


def _meter_value(db: Session, tenant_id: str, metric: str, month: str) -> int:
    row = (
        db.query(account_models.UsageMeter)
        .filter(
            account_models.UsageMeter.amo_id == tenant_id,
            account_models.UsageMeter.meter_key == _meter_key(metric, month),
        )
        .first()
    )
    return int(row.used_units if row else 0)


def usage_summary(db: Session, tenant_id: str, month: str | None = None) -> dict[str, Any]:
    month = _safe_month(month)
    policy = tenant_policy(db, tenant_id)
    values = {
        "requests": _meter_value(db, tenant_id, "requests", month),
        "input_tokens": _meter_value(db, tenant_id, "input_tokens", month),
        "cached_input_tokens": _meter_value(db, tenant_id, "cached_input_tokens", month),
        "output_tokens": _meter_value(db, tenant_id, "output_tokens", month),
        "provider_cost_microusd": _meter_value(db, tenant_id, "provider_cost_microusd", month),
        "customer_charge_microusd": _meter_value(db, tenant_id, "customer_charge_microusd", month),
    }
    budget = int(policy["monthly_budget_microusd"])
    charge = int(values["customer_charge_microusd"])
    return {
        "tenant_id": tenant_id,
        "month": month,
        "policy": policy,
        **values,
        "remaining_budget_microusd": max(0, budget - charge) if budget else None,
        "budget_used_percent": round((charge / budget) * 100, 2) if budget else None,
    }


def _usage_numbers(raw_usage: Any) -> dict[str, int]:
    usage = raw_usage if isinstance(raw_usage, dict) else {}
    details = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
    input_tokens = max(0, int(usage.get("input_tokens") or 0))
    cached_tokens = max(0, int(details.get("cached_tokens") or 0))
    cached_tokens = min(input_tokens, cached_tokens)
    output_tokens = max(0, int(usage.get("output_tokens") or 0))
    total_tokens = max(0, int(usage.get("total_tokens") or (input_tokens + output_tokens)))
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _ceil_rate(tokens: int, microusd_per_million: int) -> int:
    if tokens <= 0 or microusd_per_million <= 0:
        return 0
    return math.ceil((tokens * microusd_per_million) / 1_000_000)


def calculate_provider_cost(model: str, raw_usage: Any) -> dict[str, Any]:
    definition = AI_MODELS.get(model)
    if definition is None:
        raise ValueError(f"No audited price snapshot is configured for model {model!r}")
    usage = _usage_numbers(raw_usage)
    non_cached_input = max(0, usage["input_tokens"] - usage["cached_input_tokens"])
    long_context = usage["input_tokens"] > LONG_CONTEXT_THRESHOLD
    input_multiplier = 2 if long_context else 1
    output_num, output_den = (3, 2) if long_context else (1, 1)

    input_rate = definition.input_microusd_per_million * input_multiplier
    cached_rate = definition.cached_input_microusd_per_million * input_multiplier
    output_rate = definition.output_microusd_per_million * output_num // output_den
    provider_cost = (
        _ceil_rate(non_cached_input, input_rate)
        + _ceil_rate(usage["cached_input_tokens"], cached_rate)
        + _ceil_rate(usage["output_tokens"], output_rate)
    )
    return {
        "usage": usage,
        "provider_cost_microusd": provider_cost,
        "rate_snapshot": {
            "currency": "USD",
            "effective_from": definition.effective_from,
            "input_microusd_per_million": input_rate,
            "cached_input_microusd_per_million": cached_rate,
            "output_microusd_per_million": output_rate,
            "long_context": long_context,
            "long_context_threshold": LONG_CONTEXT_THRESHOLD,
        },
    }


def _resolve_model(policy: dict[str, Any] | None, requested_model: str | None) -> AIModelDefinition:
    model = str(requested_model or (policy or {}).get("model") or DEFAULT_MODEL).strip()
    definition = AI_MODELS.get(model)
    if definition is None:
        raise ValueError("Requested AI model is not in the approved portal catalogue")
    if policy is not None:
        max_tier = str(policy.get("max_model_tier") or DEFAULT_TIER).upper()
        if AI_TIER_ORDER[definition.tier] > AI_TIER_ORDER.get(max_tier, AI_TIER_ORDER[DEFAULT_TIER]):
            raise PermissionError(f"Tenant plan {max_tier} does not permit {definition.display_name}")
    return definition


def _record_tenant_usage(
    db: Session,
    *,
    tenant_id: str,
    month: str,
    usage: dict[str, int],
    provider_cost_microusd: int,
    customer_charge_microusd: int,
) -> None:
    increments = {
        "requests": 1,
        "input_tokens": usage["input_tokens"],
        "cached_input_tokens": usage["cached_input_tokens"],
        "output_tokens": usage["output_tokens"],
        "provider_cost_microusd": provider_cost_microusd,
        "customer_charge_microusd": customer_charge_microusd,
    }
    for metric, quantity in increments.items():
        account_services.record_usage(
            db,
            amo_id=tenant_id,
            meter_key=_meter_key(metric, month),
            quantity=max(0, int(quantity)),
            commit=False,
        )


def _audit(
    db: Session,
    *,
    actor_user_id: str | None,
    tenant_id: str | None,
    action: str,
    entity_id: str | None,
    details: dict[str, Any],
    reason: str,
) -> None:
    db.add(
        platform_models.PlatformAuditLog(
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            action=action,
            module="ai",
            entity_type="ai_request",
            entity_id=entity_id,
            reason=reason[:1000],
            details_json=details,
        )
    )


def run_ai(
    db: Session,
    *,
    prompt: str,
    instructions: str,
    actor_user_id: str | None,
    tenant_id: str | None = None,
    requested_model: str | None = None,
    billing_scope: BillingScope = "PLATFORM_TEST",
    feature_code: str = "platform.playground",
    requires_external_documents: bool = False,
) -> dict[str, Any]:
    prompt = str(prompt or "").strip()
    instructions = str(instructions or "").strip()
    if not prompt:
        raise ValueError("AI prompt cannot be empty")
    if len(prompt) > 50_000:
        raise ValueError("AI prompt exceeds the portal safety limit")
    if len(instructions) > 12_000:
        raise ValueError("AI instructions exceed the portal safety limit")
    if billing_scope not in {"PLATFORM_TEST", "PLATFORM", "TENANT"}:
        raise ValueError("Unknown AI billing scope")

    policy: dict[str, Any] | None = None
    if billing_scope == "TENANT":
        if not tenant_id:
            raise ValueError("Tenant billing requires a tenant_id")
        policy = tenant_policy(db, tenant_id)
        if not policy["enabled"]:
            raise PermissionError("AI is not enabled for this tenant")
        if policy["provider"] != AI_PROVIDER:
            raise ValueError("The tenant AI provider is not supported by this gateway")
        if requires_external_documents and not policy["allow_external_documents"]:
            raise PermissionError("Tenant policy does not permit controlled documents to be sent to an external AI provider")
        month = current_usage_month()
        budget = int(policy["monthly_budget_microusd"])
        if budget and policy["hard_limit"]:
            used = _meter_value(db, tenant_id, "customer_charge_microusd", month)
            if used >= budget:
                raise PermissionError("Tenant monthly AI budget has been exhausted")

    definition = _resolve_model(policy, requested_model)

    # Platform tests deliberately use only the platform credential even when a
    # tenant context is supplied. Tenant-billed calls may use a tenant override
    # and otherwise inherit the platform credential.
    credential_tenant_id = tenant_id if billing_scope == "TENANT" else None
    credential = saas_services.get_provider_credential(
        db,
        provider=AI_PROVIDER,
        tenant_id=credential_tenant_id,
        allow_platform_fallback=True,
    )
    saas_services.require_operational_provider(credential, label="OpenAI")
    assert credential is not None

    config = dict(credential.config_json or {})
    config["model"] = definition.model
    secret = saas_services.provider_secrets(credential)
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    started = time.perf_counter()
    provider_status = "ERROR"

    try:
        with operation_span("provider.ai.fetch", provider="AI", operation="FETCH"):
            draft = saas_providers.openai_support_response(
                secret=secret,
                config=config,
                instructions=instructions,
                user_message=prompt,
            )
        provider_status = "SUCCESS"
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        _audit(
            db,
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            action="ai.request.failed",
            entity_id=None,
            reason="AI provider request failed",
            details={
                "provider": AI_PROVIDER,
                "model": definition.model,
                "tier": definition.tier,
                "feature_code": feature_code,
                "billing_scope": billing_scope,
                "prompt_sha256": prompt_hash,
                "prompt_chars": len(prompt),
                "latency_ms": elapsed_ms,
                "error_type": type(exc).__name__,
            },
        )
        db.commit()
        raise
    finally:
        record_provider_call(
            provider="AI",
            operation="FETCH",
            status=provider_status,
            duration_seconds=time.perf_counter() - started,
        )

    actual_model = str(draft.get("model") or definition.model)
    if actual_model not in AI_MODELS:
        # Do not silently calculate money against a different provider-returned
        # model. A changed/aliased model must first be added to the catalogue.
        raise RuntimeError(f"Provider returned unpriced model {actual_model!r}")
    cost = calculate_provider_cost(actual_model, draft.get("usage") or {})
    usage = cost["usage"]
    provider_cost = int(cost["provider_cost_microusd"])
    markup_bps = int((policy or {}).get("markup_bps") or 0)
    customer_charge = math.ceil(provider_cost * (10_000 + markup_bps) / 10_000)
    month = current_usage_month()

    if billing_scope == "TENANT":
        assert tenant_id is not None and policy is not None
        _record_tenant_usage(
            db,
            tenant_id=tenant_id,
            month=month,
            usage=usage,
            provider_cost_microusd=provider_cost,
            customer_charge_microusd=customer_charge,
        )

    response_id = str(draft.get("response_id") or "") or None
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    _audit(
        db,
        actor_user_id=actor_user_id,
        tenant_id=tenant_id,
        action="ai.request.completed",
        entity_id=response_id,
        reason="AI request completed through the governed portal gateway",
        details={
            "provider": AI_PROVIDER,
            "model": actual_model,
            "tier": AI_MODELS[actual_model].tier,
            "feature_code": feature_code,
            "billing_scope": billing_scope,
            "usage_month": month,
            "usage": usage,
            "provider_cost_microusd": provider_cost,
            "customer_charge_microusd": customer_charge if billing_scope == "TENANT" else 0,
            "markup_bps": markup_bps if billing_scope == "TENANT" else 0,
            "rate_snapshot": cost["rate_snapshot"],
            "prompt_sha256": prompt_hash,
            "prompt_chars": len(prompt),
            "response_chars": len(str(draft.get("text") or "")),
            "latency_ms": elapsed_ms,
            "credential_scope": "TENANT" if credential.tenant_id else "PLATFORM",
        },
    )
    db.commit()

    return {
        "provider": AI_PROVIDER,
        "model": actual_model,
        "tier": AI_MODELS[actual_model].tier,
        "response_id": response_id,
        "text": str(draft.get("text") or ""),
        "usage": usage,
        "provider_cost_microusd": provider_cost,
        "customer_charge_microusd": customer_charge if billing_scope == "TENANT" else 0,
        "billing_scope": billing_scope,
        "tenant_id": tenant_id,
        "feature_code": feature_code,
        "latency_ms": elapsed_ms,
        "rate_snapshot": cost["rate_snapshot"],
    }
