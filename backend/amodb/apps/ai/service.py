from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from amodb.apps.platform import models as platform_models
from amodb.apps.platform import saas_services
from amodb.apps.platform.saas_models import SaaSProviderCredential
from amodb.apps.platform.saas_secrets import SecretConfigurationError, decrypt_secret

from .config import AIConfiguration, get_ai_configuration
from .contracts import (
    AIRequestContext,
    CompletionRequest,
    CompletionResult,
    EmbeddingRequest,
    EmbeddingResult,
)
from .errors import AIConfigurationError, AIPermissionError, AIQuotaError, AIServiceError
from .features import FEATURE_CODES
from .models import AIUsageRecord, TenantAISettings
from .provider_registry import provider_registry
from .schemas import AISettingsUpdate


logger = logging.getLogger(__name__)
_TENANT_CONTEXT_KEY = "quality_tenant_context"


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def apply_tenant_db_context(db: Session, *, tenant_id: str, user_id: str) -> None:
    """Apply the existing transaction-local tenant context before touching AI tables."""

    db.info[_TENANT_CONTEXT_KEY] = (str(tenant_id), str(user_id))
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": str(tenant_id)})
        db.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": str(user_id)})


@dataclass(frozen=True)
class EffectiveAISettings:
    tenant_id: str
    enabled: bool
    provider: str
    default_model: str
    lightweight_model: str
    embedding_model: str
    plan_type: str
    monthly_token_allowance: int
    monthly_request_allowance: int
    max_input_tokens_per_request: int
    max_output_tokens_per_request: int
    usage_limits: dict[str, Any]
    enabled_features: tuple[str, ...]
    allow_external_document_context: bool
    persisted: bool


@dataclass(frozen=True)
class CredentialResolution:
    provider: str
    secret: dict[str, object]
    config: dict[str, object]
    source: str
    row: SaaSProviderCredential | None


def _provider_row(db: Session, *, tenant_id: str, provider: str) -> SaaSProviderCredential | None:
    return saas_services.get_provider_credential(
        db,
        provider=provider,
        tenant_id=tenant_id,
        allow_platform_fallback=True,
    )


def get_effective_settings(
    db: Session,
    *,
    tenant_id: str,
    application_config: AIConfiguration | None = None,
) -> EffectiveAISettings:
    config = application_config or get_ai_configuration()
    row = (
        db.query(TenantAISettings)
        .filter(TenantAISettings.tenant_id == str(tenant_id))
        .first()
    )
    provider_code = str(row.provider if row else "openai").strip().lower()
    credential = _provider_row(db, tenant_id=str(tenant_id), provider=provider_code)
    provider_config = dict(credential.config_json or {}) if credential else {}
    provider_configured = bool(
        credential
        and str(credential.status or "").upper() in {"CONFIGURED", "HEALTHY", "UNHEALTHY"}
        and credential.encrypted_secret
    )
    environment_configured = provider_code == "openai" and bool(config.openai_api_key)

    if row:
        enabled_features = tuple(str(value).upper() for value in (row.enabled_features_json or []))
        return EffectiveAISettings(
            tenant_id=str(tenant_id),
            enabled=bool(row.enabled),
            provider=provider_code,
            default_model=str(row.default_model),
            lightweight_model=str(row.lightweight_model),
            embedding_model=str(row.embedding_model),
            plan_type=str(row.plan_type),
            monthly_token_allowance=int(row.monthly_token_allowance or 0),
            monthly_request_allowance=int(row.monthly_request_allowance or 0),
            max_input_tokens_per_request=int(row.max_input_tokens_per_request or 0),
            max_output_tokens_per_request=int(row.max_output_tokens_per_request or 0),
            usage_limits=dict(row.usage_limits_json or {}),
            enabled_features=enabled_features,
            allow_external_document_context=bool(row.allow_external_document_context),
            persisted=True,
        )

    explicitly_enabled = os.getenv("AI_ENABLED")
    enabled = _truthy(explicitly_enabled) if explicitly_enabled is not None else (
        provider_configured if credential is not None else environment_configured
    )
    configured_default_model = str(
        provider_config.get("default_model") or provider_config.get("model") or config.default_model
    )
    default_model = (
        configured_default_model
        if configured_default_model in config.allowed_chat_models
        else config.default_model
    )
    configured_lightweight_model = str(provider_config.get("lightweight_model") or config.lightweight_model)
    lightweight_model = (
        configured_lightweight_model
        if configured_lightweight_model in config.allowed_chat_models
        else config.lightweight_model
    )
    configured_embedding_model = str(provider_config.get("embedding_model") or config.embedding_model)
    embedding_model = (
        configured_embedding_model
        if configured_embedding_model in config.allowed_embedding_models
        else config.embedding_model
    )
    return EffectiveAISettings(
        tenant_id=str(tenant_id),
        enabled=enabled,
        provider=provider_code,
        default_model=default_model,
        lightweight_model=lightweight_model,
        embedding_model=embedding_model,
        plan_type=config.default_plan_type,
        monthly_token_allowance=config.default_monthly_token_allowance,
        monthly_request_allowance=config.default_monthly_request_allowance,
        max_input_tokens_per_request=config.default_max_input_tokens_per_request,
        max_output_tokens_per_request=config.default_max_output_tokens_per_request,
        usage_limits={},
        enabled_features=tuple(sorted(FEATURE_CODES)),
        allow_external_document_context=_truthy(os.getenv("DOCUMENT_AI_ALLOW_EXTERNAL")),
        persisted=False,
    )


def settings_payload(settings: EffectiveAISettings) -> dict[str, Any]:
    return {
        "tenant_id": settings.tenant_id,
        "enabled": settings.enabled,
        "provider": settings.provider,
        "default_model": settings.default_model,
        "lightweight_model": settings.lightweight_model,
        "embedding_model": settings.embedding_model,
        "plan_type": settings.plan_type,
        "monthly_token_allowance": settings.monthly_token_allowance,
        "monthly_request_allowance": settings.monthly_request_allowance,
        "max_input_tokens_per_request": settings.max_input_tokens_per_request,
        "max_output_tokens_per_request": settings.max_output_tokens_per_request,
        "usage_limits": settings.usage_limits,
        "enabled_features": list(settings.enabled_features),
        "allow_external_document_context": settings.allow_external_document_context,
        "persisted": settings.persisted,
    }


def save_settings(
    db: Session,
    *,
    tenant_id: str,
    actor_user_id: str,
    payload: AISettingsUpdate,
    application_config: AIConfiguration | None = None,
) -> EffectiveAISettings:
    config = application_config or get_ai_configuration()
    provider_code = payload.provider.strip().lower()
    if provider_code not in provider_registry.installed():
        raise AIConfigurationError(
            f"AI provider '{provider_code}' is not installed.",
            code="AI_PROVIDER_NOT_INSTALLED",
        )
    if payload.default_model not in config.allowed_chat_models:
        raise AIConfigurationError("The selected default model is not in the approved model registry.", code="AI_MODEL_NOT_ALLOWED")
    if payload.lightweight_model not in config.allowed_chat_models:
        raise AIConfigurationError("The selected lightweight model is not in the approved model registry.", code="AI_MODEL_NOT_ALLOWED")
    if payload.embedding_model not in config.allowed_embedding_models:
        raise AIConfigurationError("The selected embedding model is not in the approved model registry.", code="AI_MODEL_NOT_ALLOWED")
    unknown_features = set(payload.enabled_features) - FEATURE_CODES
    if unknown_features:
        raise AIConfigurationError(
            f"Unknown AI feature(s): {', '.join(sorted(unknown_features))}",
            code="AI_FEATURE_NOT_ALLOWED",
        )

    row = (
        db.query(TenantAISettings)
        .filter(TenantAISettings.tenant_id == str(tenant_id))
        .first()
    )
    if row is None:
        row = TenantAISettings(
            tenant_id=str(tenant_id),
            created_by=str(actor_user_id),
            default_model=payload.default_model,
            lightweight_model=payload.lightweight_model,
            embedding_model=payload.embedding_model,
        )
        db.add(row)
    row.enabled = payload.enabled
    row.provider = provider_code
    row.default_model = payload.default_model
    row.lightweight_model = payload.lightweight_model
    row.embedding_model = payload.embedding_model
    row.plan_type = payload.plan_type.strip().upper()
    row.monthly_token_allowance = payload.monthly_token_allowance
    row.monthly_request_allowance = payload.monthly_request_allowance
    row.max_input_tokens_per_request = payload.max_input_tokens_per_request
    row.max_output_tokens_per_request = payload.max_output_tokens_per_request
    row.usage_limits_json = dict(payload.usage_limits)
    row.enabled_features_json = list(payload.enabled_features)
    row.allow_external_document_context = payload.allow_external_document_context
    row.updated_by = str(actor_user_id)
    db.flush()
    db.add(
        platform_models.PlatformAuditLog(
            actor_user_id=str(actor_user_id),
            tenant_id=str(tenant_id),
            action="ai.tenant_settings.updated",
            module="ai",
            entity_type="tenant_ai_settings",
            entity_id=str(row.id),
            reason=payload.reason,
            details_json={
                "enabled": payload.enabled,
                "provider": provider_code,
                "default_model": payload.default_model,
                "lightweight_model": payload.lightweight_model,
                "embedding_model": payload.embedding_model,
                "plan_type": row.plan_type,
                "monthly_token_allowance": payload.monthly_token_allowance,
                "monthly_request_allowance": payload.monthly_request_allowance,
                "enabled_features": list(payload.enabled_features),
                "allow_external_document_context": payload.allow_external_document_context,
            },
        )
    )
    db.flush()
    return get_effective_settings(db, tenant_id=str(tenant_id), application_config=config)


def resolve_credential(
    db: Session,
    *,
    tenant_id: str,
    provider: str,
    application_config: AIConfiguration,
) -> CredentialResolution:
    normalized = str(provider).strip().lower()
    row = _provider_row(db, tenant_id=str(tenant_id), provider=normalized)
    if row is not None:
        status = str(row.status or "").strip().upper()
        if status == "DISABLED":
            raise AIConfigurationError("The tenant AI provider is disabled.", code="AI_PROVIDER_DISABLED")
        if status not in {"CONFIGURED", "HEALTHY", "UNHEALTHY"}:
            raise AIConfigurationError("The tenant AI provider is not configured.")
        try:
            secret = decrypt_secret(row.encrypted_secret)
        except SecretConfigurationError as exc:
            raise AIConfigurationError(
                "The stored AI credential is unavailable. Re-enter the provider credential.",
                code="AI_CREDENTIAL_UNAVAILABLE",
            ) from exc
        if normalized == "openai" and not str(secret.get("api_key") or "").strip():
            raise AIConfigurationError("The OpenAI API key is not configured.")
        return CredentialResolution(
            provider=normalized,
            secret=dict(secret),
            config=dict(row.config_json or {}),
            source="TENANT" if row.tenant_id else "PLATFORM",
            row=row,
        )
    if normalized == "openai" and application_config.openai_api_key:
        return CredentialResolution(
            provider=normalized,
            secret={"api_key": application_config.openai_api_key},
            config={"api_base_url": application_config.openai_api_base_url},
            source="ENVIRONMENT",
            row=None,
        )
    raise AIConfigurationError("The OpenAI API key is not configured.")


def _month_start() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc)


def usage_summary(db: Session, *, tenant_id: str) -> dict[str, int]:
    total_tokens, total_requests = (
        db.query(
            func.coalesce(func.sum(AIUsageRecord.total_tokens), 0),
            func.count(AIUsageRecord.id),
        )
        .filter(
            AIUsageRecord.tenant_id == str(tenant_id),
            AIUsageRecord.created_at >= _month_start(),
            AIUsageRecord.status == "SUCCEEDED",
        )
        .one()
    )
    return {"tokens": int(total_tokens or 0), "requests": int(total_requests or 0)}


def _estimated_tokens(text_value: str) -> int:
    return max(1, (len(text_value) + 3) // 4)


def _validate_feature_and_limits(
    db: Session,
    *,
    settings: EffectiveAISettings,
    feature: str,
    estimated_input_tokens: int,
    requested_output_tokens: int,
) -> None:
    normalized_feature = str(feature).strip().upper()
    administrative_test = normalized_feature == "CONNECTIVITY_TEST"
    if not settings.enabled and not administrative_test:
        raise AIPermissionError("AI is disabled for this tenant.")
    if normalized_feature not in FEATURE_CODES:
        raise AIPermissionError("This AI feature is not registered.")
    if not administrative_test and normalized_feature not in settings.enabled_features:
        raise AIPermissionError("This AI feature is disabled for the tenant plan.")
    if settings.max_input_tokens_per_request and estimated_input_tokens > settings.max_input_tokens_per_request:
        raise AIQuotaError("The AI request exceeds the tenant input-token limit.")
    if settings.max_output_tokens_per_request and requested_output_tokens > settings.max_output_tokens_per_request:
        raise AIQuotaError("The AI request exceeds the tenant output-token limit.")
    usage = usage_summary(db, tenant_id=settings.tenant_id)
    if settings.monthly_request_allowance and usage["requests"] >= settings.monthly_request_allowance:
        raise AIQuotaError("The tenant monthly AI request allowance has been reached.")
    projected = usage["tokens"] + estimated_input_tokens + requested_output_tokens
    if settings.monthly_token_allowance and projected > settings.monthly_token_allowance:
        raise AIQuotaError("The tenant monthly AI token allowance would be exceeded.")


def _context_columns(context: AIRequestContext) -> dict[str, Any]:
    document = context.document_context
    workflow = context.workflow_context
    return {
        "document_id": str(document.get("document_id") or "")[:96] or None,
        "document_revision_id": str(document.get("revision_id") or "")[:96] or None,
        "workflow_type": str(workflow.get("workflow_type") or "")[:96] or None,
        "workflow_id": str(workflow.get("workflow_id") or "")[:96] or None,
        "context_json": {
            "document_context_keys": sorted(str(key)[:64] for key in document.keys()),
            "workflow_context_keys": sorted(str(key)[:64] for key in workflow.keys()),
        },
    }


def _record_usage(
    db: Session,
    *,
    context: AIRequestContext,
    request_id: str,
    provider: str,
    model: str,
    feature: str,
    operation_type: str,
    status: str,
    input_tokens: int,
    output_tokens: int,
    estimated_cost_usd,
    latency_ms: float | None,
    provider_response_id: str | None = None,
    failure_code: str | None = None,
) -> AIUsageRecord:
    row = AIUsageRecord(
        tenant_id=str(context.tenant_id),
        user_id=str(context.user_id),
        provider=provider,
        model=model,
        feature=str(feature).upper(),
        operation_type=operation_type,
        request_id=str(request_id)[:96],
        provider_response_id=str(provider_response_id)[:255] if provider_response_id else None,
        status=status,
        input_tokens=max(0, int(input_tokens)),
        output_tokens=max(0, int(output_tokens)),
        total_tokens=max(0, int(input_tokens)) + max(0, int(output_tokens)),
        estimated_cost_usd=estimated_cost_usd,
        latency_ms=round(latency_ms) if latency_ms is not None else None,
        failure_code=failure_code,
        **_context_columns(context),
    )
    db.add(row)
    db.flush()
    return row


class AIService:
    def __init__(self, application_config: AIConfiguration | None = None) -> None:
        try:
            self.config = application_config or get_ai_configuration()
        except ValueError as exc:
            raise AIConfigurationError("AI configuration is invalid.", code="AI_CONFIGURATION_INVALID") from exc

    def complete(
        self,
        db: Session,
        *,
        context: AIRequestContext,
        request_id: str,
        feature: str,
        instructions: str,
        input_text: str,
        model: str | None = None,
        max_output_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> CompletionResult:
        apply_tenant_db_context(db, tenant_id=context.tenant_id, user_id=context.user_id)
        settings = get_effective_settings(db, tenant_id=context.tenant_id, application_config=self.config)
        selected_model = str(model or settings.default_model)
        if selected_model not in self.config.allowed_chat_models:
            raise AIConfigurationError("The selected AI model is not approved.", code="AI_MODEL_NOT_ALLOWED")
        estimated_input = _estimated_tokens(instructions) + _estimated_tokens(input_text)
        requested_output = max(0, int(max_output_tokens or 0))
        try:
            _validate_feature_and_limits(
                db,
                settings=settings,
                feature=feature,
                estimated_input_tokens=estimated_input,
                requested_output_tokens=requested_output,
            )
        except AIServiceError as exc:
            logger.warning(
                "ai_request_rejected",
                extra={
                    "request_id": request_id,
                    "tenant_id": context.tenant_id,
                    "user_id": context.user_id,
                    "provider": settings.provider,
                    "model": selected_model,
                    "feature": str(feature).upper(),
                    "failure_code": exc.code,
                },
            )
            raise
        started = time.perf_counter()
        try:
            resolution = resolve_credential(
                db,
                tenant_id=context.tenant_id,
                provider=settings.provider,
                application_config=self.config,
            )
            provider = provider_registry.create(
                settings.provider,
                secret=resolution.secret,
                provider_config=resolution.config,
                application_config=self.config,
            )
            result = provider.complete(
                CompletionRequest(
                    feature=str(feature).upper(),
                    instructions=instructions,
                    input_text=input_text,
                    model=selected_model,
                    max_output_tokens=max_output_tokens,
                    response_format=response_format,
                )
            )
        except AIServiceError as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            _record_usage(
                db,
                context=context,
                request_id=request_id,
                provider=settings.provider,
                model=selected_model,
                feature=feature,
                operation_type="COMPLETION",
                status="FAILED",
                input_tokens=estimated_input,
                output_tokens=0,
                estimated_cost_usd=self.config.estimate_cost(selected_model, estimated_input, 0),
                latency_ms=latency_ms,
                failure_code=exc.code,
            )
            logger.warning(
                "ai_request_failed",
                extra={
                    "request_id": request_id,
                    "tenant_id": context.tenant_id,
                    "user_id": context.user_id,
                    "provider": settings.provider,
                    "model": selected_model,
                    "feature": str(feature).upper(),
                    "failure_code": exc.code,
                    "latency_ms": round(latency_ms),
                },
            )
            raise

        _record_usage(
            db,
            context=context,
            request_id=request_id,
            provider=result.provider,
            model=result.model,
            feature=feature,
            operation_type="COMPLETION",
            status="SUCCEEDED",
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            estimated_cost_usd=self.config.estimate_cost(result.model, result.input_tokens, result.output_tokens),
            latency_ms=result.latency_ms,
            provider_response_id=result.response_id,
        )
        logger.info(
            "ai_request_completed",
            extra={
                "request_id": request_id,
                "tenant_id": context.tenant_id,
                "user_id": context.user_id,
                "provider": result.provider,
                "model": result.model,
                "feature": str(feature).upper(),
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "latency_ms": round(result.latency_ms),
            },
        )
        return result

    def embed(
        self,
        db: Session,
        *,
        context: AIRequestContext,
        request_id: str,
        feature: str,
        input_texts: tuple[str, ...],
        model: str | None = None,
    ) -> EmbeddingResult:
        apply_tenant_db_context(db, tenant_id=context.tenant_id, user_id=context.user_id)
        settings = get_effective_settings(db, tenant_id=context.tenant_id, application_config=self.config)
        selected_model = str(model or settings.embedding_model)
        if selected_model not in self.config.allowed_embedding_models:
            raise AIConfigurationError("The selected embedding model is not approved.", code="AI_MODEL_NOT_ALLOWED")
        estimated_input = sum(_estimated_tokens(value) for value in input_texts)
        try:
            _validate_feature_and_limits(
                db,
                settings=settings,
                feature=feature,
                estimated_input_tokens=estimated_input,
                requested_output_tokens=0,
            )
        except AIServiceError as exc:
            logger.warning(
                "ai_request_rejected",
                extra={
                    "request_id": request_id,
                    "tenant_id": context.tenant_id,
                    "user_id": context.user_id,
                    "provider": settings.provider,
                    "model": selected_model,
                    "feature": str(feature).upper(),
                    "failure_code": exc.code,
                },
            )
            raise
        started = time.perf_counter()
        try:
            resolution = resolve_credential(
                db,
                tenant_id=context.tenant_id,
                provider=settings.provider,
                application_config=self.config,
            )
            provider = provider_registry.create(
                settings.provider,
                secret=resolution.secret,
                provider_config=resolution.config,
                application_config=self.config,
            )
            result = provider.embed(
                EmbeddingRequest(feature=str(feature).upper(), input_texts=input_texts, model=selected_model)
            )
        except AIServiceError as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            _record_usage(
                db,
                context=context,
                request_id=request_id,
                provider=settings.provider,
                model=selected_model,
                feature=feature,
                operation_type="EMBEDDING",
                status="FAILED",
                input_tokens=estimated_input,
                output_tokens=0,
                estimated_cost_usd=self.config.estimate_cost(selected_model, estimated_input, 0),
                latency_ms=latency_ms,
                failure_code=exc.code,
            )
            logger.warning(
                "ai_request_failed",
                extra={
                    "request_id": request_id,
                    "tenant_id": context.tenant_id,
                    "user_id": context.user_id,
                    "provider": settings.provider,
                    "model": selected_model,
                    "feature": str(feature).upper(),
                    "failure_code": exc.code,
                    "latency_ms": round(latency_ms),
                },
            )
            raise
        _record_usage(
            db,
            context=context,
            request_id=request_id,
            provider=result.provider,
            model=result.model,
            feature=feature,
            operation_type="EMBEDDING",
            status="SUCCEEDED",
            input_tokens=result.input_tokens,
            output_tokens=0,
            estimated_cost_usd=self.config.estimate_cost(result.model, result.input_tokens, 0),
            latency_ms=result.latency_ms,
            provider_response_id=result.response_id,
        )
        logger.info(
            "ai_request_completed",
            extra={
                "request_id": request_id,
                "tenant_id": context.tenant_id,
                "user_id": context.user_id,
                "provider": result.provider,
                "model": result.model,
                "feature": str(feature).upper(),
                "input_tokens": result.input_tokens,
                "output_tokens": 0,
                "latency_ms": round(result.latency_ms),
            },
        )
        return result


def connection_status(db: Session, *, tenant_id: str, user_id: str) -> dict[str, Any]:
    apply_tenant_db_context(db, tenant_id=tenant_id, user_id=user_id)
    config = get_ai_configuration()
    settings = get_effective_settings(db, tenant_id=tenant_id, application_config=config)
    row = _provider_row(db, tenant_id=tenant_id, provider=settings.provider)
    if row:
        credential_source = "TENANT" if row.tenant_id else "PLATFORM"
        provider_status = str(row.status or "NOT_CONFIGURED").upper()
        configured = bool(row.encrypted_secret) and provider_status != "DISABLED"
    else:
        credential_source = "ENVIRONMENT" if config.openai_api_key else "NONE"
        provider_status = "CONFIGURED" if config.openai_api_key else "NOT_CONFIGURED"
        configured = bool(config.openai_api_key)
    if provider_status == "DISABLED":
        status = "DISABLED"
    elif not settings.enabled:
        status = "DISABLED"
    elif provider_status == "HEALTHY":
        status = "CONNECTED"
    elif provider_status == "UNHEALTHY":
        status = "ERROR"
    elif configured:
        status = "NOT_TESTED"
    else:
        status = "NOT_CONFIGURED"
    return {
        "provider": settings.provider,
        "active_model": settings.default_model,
        "embedding_model": settings.embedding_model,
        "connection_status": status,
        "configured": configured,
        "enabled": settings.enabled,
        "credential_source": credential_source,
        "provider_status": provider_status,
    }


def mark_connection_test(
    db: Session,
    *,
    tenant_id: str,
    succeeded: bool,
    latency_ms: float | None,
    detail: str,
) -> None:
    row = _provider_row(db, tenant_id=tenant_id, provider="openai")
    if row is None or str(row.tenant_id or "") != str(tenant_id):
        return
    row.status = "HEALTHY" if succeeded else "UNHEALTHY"
    row.last_checked_at = datetime.now(timezone.utc)
    row.last_latency_ms = round(latency_ms) if latency_ms is not None else None
    row.last_health_detail = str(detail)[:1000]
