from __future__ import annotations

import re
import uuid
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.accounts.admin_profile_guard import require_active_admin_profile
from amodb.database import get_db
from amodb.security import get_current_active_user

from .config import get_ai_configuration
from .contracts import AIRequestContext
from .errors import AIServiceError
from .features import FEATURES
from .schemas import AISettingsUpdate, AITestRequest
from .service import (
    AIService,
    apply_tenant_db_context,
    connection_status,
    get_effective_settings,
    mark_connection_test,
    save_settings,
    settings_payload,
    usage_summary,
)


router = APIRouter(prefix="/ai", tags=["AI Administration"])
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{8,96}$")
_AI_ADMIN_ROLES = frozenset({"QUALITY_MANAGER"})


def _role(user: account_models.User) -> str:
    raw = getattr(user, "role", "")
    return str(getattr(raw, "value", raw) or "").strip().upper()


def require_ai_admin(
    request: Request,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> account_models.User:
    if getattr(current_user, "is_system_account", False):
        raise HTTPException(status_code=403, detail="System/service accounts cannot manage AI configuration.")
    if getattr(current_user, "is_superuser", False):
        return current_user
    if _role(current_user) in _AI_ADMIN_ROLES:
        if not getattr(current_user, "amo_id", None):
            raise HTTPException(status_code=403, detail="AI administrator is not assigned to a tenant.")
        return current_user
    return require_active_admin_profile(request=request, current_user=current_user, db=db)


def _tenant_scope(db: Session, *, user: account_models.User, requested_tenant_id: str | None) -> str:
    if getattr(user, "is_superuser", False):
        if not requested_tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required for platform AI administration.")
        tenant_id = str(requested_tenant_id)
    else:
        tenant_id = str(getattr(user, "amo_id", "") or "")
        if requested_tenant_id and str(requested_tenant_id) != tenant_id:
            raise HTTPException(status_code=403, detail="Cannot access AI settings for another tenant.")
    if not tenant_id or db.get(account_models.AMO, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant not found.")
    apply_tenant_db_context(db, tenant_id=tenant_id, user_id=str(user.id))
    return tenant_id


def _request_id(request: Request) -> str:
    supplied = str(request.headers.get("X-Request-ID") or "").strip()
    return supplied if _REQUEST_ID.fullmatch(supplied) else str(uuid.uuid4())


def _raise_ai_error(exc: AIServiceError, request_id: str) -> NoReturn:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail(request_id=request_id)) from exc


@router.get("/health")
def ai_health(
    request: Request,
    response: Response,
    tenant_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: account_models.User = Depends(require_ai_admin),
):
    correlation_id = _request_id(request)
    response.headers["X-Request-ID"] = correlation_id
    scope = _tenant_scope(db, user=user, requested_tenant_id=tenant_id)
    try:
        health = connection_status(db, tenant_id=scope, user_id=str(user.id))
        monthly_usage = usage_summary(db, tenant_id=scope)
    except (AIServiceError, ValueError) as exc:
        error = exc if isinstance(exc, AIServiceError) else AIServiceError(
            "AI_CONFIGURATION_INVALID",
            "AI configuration is invalid.",
            status_code=503,
        )
        _raise_ai_error(error, correlation_id)
    return {**health, "monthly_usage": monthly_usage, "request_id": correlation_id}


@router.get("/models")
def ai_models(
    request: Request,
    response: Response,
    tenant_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: account_models.User = Depends(require_ai_admin),
):
    correlation_id = _request_id(request)
    response.headers["X-Request-ID"] = correlation_id
    _tenant_scope(db, user=user, requested_tenant_id=tenant_id)
    try:
        config = get_ai_configuration()
    except ValueError as exc:
        _raise_ai_error(
            AIServiceError("AI_CONFIGURATION_INVALID", "AI configuration is invalid.", status_code=503),
            correlation_id,
        )
    return {
        "items": [
            {
                "model": definition.model,
                "purpose": definition.purpose,
                "premium": definition.premium,
            }
            for definition in config.model_registry
        ],
        "features": [
            {"code": feature.code, "label": feature.label, "context_kind": feature.context_kind}
            for feature in FEATURES
        ],
        "request_id": correlation_id,
    }


@router.get("/settings")
def ai_settings(
    request: Request,
    response: Response,
    tenant_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: account_models.User = Depends(require_ai_admin),
):
    correlation_id = _request_id(request)
    response.headers["X-Request-ID"] = correlation_id
    scope = _tenant_scope(db, user=user, requested_tenant_id=tenant_id)
    try:
        settings = get_effective_settings(db, tenant_id=scope)
        monthly_usage = usage_summary(db, tenant_id=scope)
    except (AIServiceError, ValueError) as exc:
        error = exc if isinstance(exc, AIServiceError) else AIServiceError(
            "AI_CONFIGURATION_INVALID",
            "AI configuration is invalid.",
            status_code=503,
        )
        _raise_ai_error(error, correlation_id)
    return {**settings_payload(settings), "monthly_usage": monthly_usage, "request_id": correlation_id}


@router.put("/settings")
def update_ai_settings(
    payload: AISettingsUpdate,
    request: Request,
    response: Response,
    tenant_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: account_models.User = Depends(require_ai_admin),
):
    correlation_id = _request_id(request)
    response.headers["X-Request-ID"] = correlation_id
    scope = _tenant_scope(db, user=user, requested_tenant_id=tenant_id)
    try:
        settings = save_settings(
            db,
            tenant_id=scope,
            actor_user_id=str(user.id),
            payload=payload,
        )
        db.commit()
    except (AIServiceError, ValueError) as exc:
        db.rollback()
        error = exc if isinstance(exc, AIServiceError) else AIServiceError(
            "AI_CONFIGURATION_INVALID",
            "AI configuration is invalid.",
            status_code=503,
        )
        _raise_ai_error(error, correlation_id)
    return {**settings_payload(settings), "request_id": correlation_id}


@router.post("/test")
def test_ai_connection(
    payload: AITestRequest,
    request: Request,
    response: Response,
    tenant_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: account_models.User = Depends(require_ai_admin),
):
    correlation_id = _request_id(request)
    response.headers["X-Request-ID"] = correlation_id
    scope = _tenant_scope(db, user=user, requested_tenant_id=tenant_id)
    try:
        service = AIService()
        result = service.complete(
            db,
            context=AIRequestContext(
                tenant_id=scope,
                user_id=str(user.id),
                workflow_context={"workflow_type": "AI_ADMINISTRATION", "workflow_id": correlation_id},
            ),
            request_id=correlation_id,
            feature="CONNECTIVITY_TEST",
            instructions="Return only the word CONNECTED. Do not add punctuation or explanation.",
            input_text="Verify this server-side AI provider connection.",
            model=payload.model,
            max_output_tokens=64,
        )
        mark_connection_test(
            db,
            tenant_id=scope,
            succeeded=True,
            latency_ms=result.latency_ms,
            detail="Authenticated AI connectivity test succeeded.",
        )
        db.commit()
    except AIServiceError as exc:
        if exc.code.startswith("AI_PROVIDER_") and exc.code != "AI_PROVIDER_DISABLED":
            mark_connection_test(
                db,
                tenant_id=scope,
                succeeded=False,
                latency_ms=None,
                detail=f"Connectivity test failed: {exc.code}",
            )
        db.commit()
        _raise_ai_error(exc, correlation_id)
    return {
        "provider": result.provider,
        "active_model": result.model,
        "connection_status": "CONNECTED",
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "latency_ms": result.latency_ms,
        "request_id": correlation_id,
    }
