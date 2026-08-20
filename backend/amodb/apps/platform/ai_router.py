from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from amodb.database import get_db, get_read_db

from . import ai_gateway, saas_services
from .router import require_platform_superuser


router = APIRouter(prefix="/saas/ai", tags=["platform-ai-control"])


class AIPlaygroundRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=50_000)
    instructions: str = Field(
        default=(
            "You are the AMO Portal administrative AI test assistant. Be factual and concise. "
            "Do not claim that portal actions were performed. Do not invent controlled-document content."
        ),
        max_length=12_000,
    )
    tenant_id: str | None = None
    model: str | None = None
    charge_tenant: bool = False
    feature_code: str = Field(default="platform.playground", min_length=2, max_length=96)

    @field_validator("prompt", "instructions", "feature_code")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class AITenantPolicyRequest(BaseModel):
    enabled: bool = False
    plan_code: Literal["STANDARD", "ADVANCED", "PROFESSIONAL"] = "STANDARD"
    model: str | None = None
    monthly_budget_microusd: int = Field(default=0, ge=0, le=10_000_000_000_000)
    hard_limit: bool = True
    allow_external_documents: bool = False
    markup_bps: int = Field(default=0, ge=0, le=100_000)
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


@router.get("/catalog")
def ai_catalog(user=Depends(require_platform_superuser)):
    return {
        "provider": ai_gateway.AI_PROVIDER,
        "default_model": ai_gateway.DEFAULT_MODEL,
        "models": ai_gateway.model_catalog(),
        "tiers": ["STANDARD", "ADVANCED", "PROFESSIONAL"],
    }


@router.get("/tenants/{tenant_id}/policy")
def ai_tenant_policy(
    tenant_id: str,
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    try:
        return ai_gateway.tenant_policy(db, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/tenants/{tenant_id}/policy")
def ai_tenant_policy_update(
    tenant_id: str,
    payload: AITenantPolicyRequest,
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    model = payload.model or ai_gateway.PLAN_DEFAULT_MODEL[payload.plan_code]
    definition = ai_gateway.AI_MODELS.get(model)
    if definition is None:
        raise HTTPException(status_code=422, detail="Selected AI model is not in the approved portal catalogue")
    if ai_gateway.AI_TIER_ORDER[definition.tier] > ai_gateway.AI_TIER_ORDER[payload.plan_code]:
        raise HTTPException(status_code=422, detail="Selected AI model exceeds the tenant plan tier")

    try:
        rows = saas_services.update_tenant_modules(
            db,
            tenant_id=tenant_id,
            changes=[
                {
                    "module_code": ai_gateway.AI_MODULE_CODE,
                    "status": "ENABLED" if payload.enabled else "DISABLED",
                    "plan_code": payload.plan_code,
                    "metadata": {
                        "provider": ai_gateway.AI_PROVIDER,
                        "model": model,
                        "max_model_tier": payload.plan_code,
                        "monthly_budget_microusd": payload.monthly_budget_microusd,
                        "hard_limit": payload.hard_limit,
                        "allow_external_documents": payload.allow_external_documents,
                        "markup_bps": payload.markup_bps,
                    },
                }
            ],
            actor_user_id=str(user.id),
            reason=payload.reason,
        )
        policy = ai_gateway.tenant_policy(db, tenant_id)
        return {"policy": policy, "subscription": rows[0] if rows else None}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/tenants/{tenant_id}/usage")
def ai_tenant_usage(
    tenant_id: str,
    month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    try:
        return ai_gateway.usage_summary(db, tenant_id, month)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/playground")
def ai_playground(
    payload: AIPlaygroundRequest,
    db: Session = Depends(get_db),
    user=Depends(require_platform_superuser),
):
    if payload.charge_tenant and not payload.tenant_id:
        raise HTTPException(status_code=422, detail="charge_tenant requires a tenant_id")
    if payload.tenant_id and not payload.charge_tenant:
        raise HTTPException(
            status_code=422,
            detail="tenant_id is only accepted for explicitly tenant-metered playground requests",
        )
    billing_scope: ai_gateway.BillingScope = "TENANT" if payload.charge_tenant else "PLATFORM_TEST"
    try:
        return ai_gateway.run_ai(
            db,
            prompt=payload.prompt,
            instructions=payload.instructions,
            actor_user_id=str(user.id),
            tenant_id=payload.tenant_id if payload.charge_tenant else None,
            requested_model=payload.model,
            billing_scope=billing_scope,
            feature_code=payload.feature_code,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/status")
def ai_status(
    tenant_id: str | None = None,
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    credential = saas_services.get_provider_credential(
        db,
        provider=ai_gateway.AI_PROVIDER,
        tenant_id=tenant_id,
        allow_platform_fallback=True,
    )
    provider: dict[str, Any] | None = saas_services.provider_payload(credential) if credential else None
    return {
        "provider": provider,
        "default_model": ai_gateway.DEFAULT_MODEL,
        "tenant_policy": ai_gateway.tenant_policy(db, tenant_id) if tenant_id else None,
    }
