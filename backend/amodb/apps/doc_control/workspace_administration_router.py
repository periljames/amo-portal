from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import models as legacy_models
from .workspace_service import audit, require_control_user, resolve_tenant


router = APIRouter(prefix="/workspace", tags=["Document Control Administration"])
ADMIN_SETTINGS_KEY = "document_control_admin"
DEFAULT_DOCUMENT_CLASSES = ["INTERNAL", "EXTERNAL", "RECORD"]
DEFAULT_RETENTION_CLASSES = [
    {"code": "STANDARD", "label": "Standard controlled record", "years": 5},
    {"code": "PERMANENT", "label": "Permanent retained evidence", "years": 100},
]


class WorkflowPolicy(BaseModel):
    technical_review_required: bool = True
    quality_review_required: bool = True
    management_approval_required: bool = True
    authority_routing: Literal["WHEN_REQUIRED", "ALWAYS", "NEVER"] = "WHEN_REQUIRED"


class IndexingPolicy(BaseModel):
    auto_index_on_publish: bool = True
    require_source_hash: bool = True
    retry_limit: int = Field(default=3, ge=0, le=20)


class PhysicalCopyPolicy(BaseModel):
    default_due_days: int = Field(default=30, ge=1, le=3650)
    custody_acknowledgement_required: bool = True
    location_verification_required: bool = True
    recall_on_supersession: bool = True


class WorkspaceAdministrationIn(BaseModel):
    default_retention_years: int = Field(default=5, ge=1, le=100)
    default_review_interval_months: int = Field(default=24, ge=1, le=120)
    regulated_workflow_enabled: bool = False
    default_ack_required: bool = True
    document_classes: list[str] = Field(default_factory=lambda: list(DEFAULT_DOCUMENT_CLASSES), min_length=1, max_length=24)
    workflow_policy: WorkflowPolicy = Field(default_factory=WorkflowPolicy)
    retention_classes: list[dict] = Field(default_factory=lambda: list(DEFAULT_RETENTION_CLASSES), max_length=32)
    indexing_policy: IndexingPolicy = Field(default_factory=IndexingPolicy)
    integration_modules: list[str] = Field(default_factory=list, max_length=64)
    physical_copy_policy: PhysicalCopyPolicy = Field(default_factory=PhysicalCopyPolicy)


def _extended_settings(tenant) -> dict:
    settings = dict(tenant.settings_json or {})
    raw = settings.get(ADMIN_SETTINGS_KEY)
    return dict(raw) if isinstance(raw, dict) else {}


def _normalize_classes(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        item = str(value or "").strip().upper().replace(" ", "_")
        if item and item not in normalized:
            normalized.append(item)
    return normalized or list(DEFAULT_DOCUMENT_CLASSES)


def _normalize_modules(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        item = str(value or "").strip().upper().replace(" ", "_")
        if item and item not in normalized:
            normalized.append(item)
    return normalized


def _settings_payload(tenant, row) -> dict:
    extended = _extended_settings(tenant)
    workflow = WorkflowPolicy.model_validate(extended.get("workflow_policy") or {}).model_dump()
    indexing = IndexingPolicy.model_validate(extended.get("indexing_policy") or {}).model_dump()
    physical = PhysicalCopyPolicy.model_validate(extended.get("physical_copy_policy") or {}).model_dump()
    return {
        "tenant_id": tenant.amo_id,
        "default_retention_years": row.default_retention_years if row else 5,
        "default_review_interval_months": row.default_review_interval_months if row else 24,
        "regulated_workflow_enabled": row.regulated_workflow_enabled if row else False,
        "default_ack_required": row.default_ack_required if row else True,
        "document_classes": _normalize_classes(list(extended.get("document_classes") or DEFAULT_DOCUMENT_CLASSES)),
        "workflow_policy": workflow,
        "retention_classes": list(extended.get("retention_classes") or DEFAULT_RETENTION_CLASSES),
        "indexing_policy": indexing,
        "integration_modules": _normalize_modules(list(extended.get("integration_modules") or [])),
        "physical_copy_policy": physical,
        "configured": bool(row or extended),
    }


@router.get("/t/{tenant_slug}/administration")
def get_administration(
    tenant_slug: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = db.query(legacy_models.DocControlSettings).filter(legacy_models.DocControlSettings.tenant_id == tenant.amo_id).first()
    return _settings_payload(tenant, row)


@router.put("/t/{tenant_slug}/administration")
def update_administration(
    tenant_slug: str,
    payload: WorkspaceAdministrationIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = db.query(legacy_models.DocControlSettings).filter(legacy_models.DocControlSettings.tenant_id == tenant.amo_id).first()
    before = _settings_payload(tenant, row)
    if not row:
        row = legacy_models.DocControlSettings(tenant_id=tenant.amo_id)
        db.add(row)
    row.default_retention_years = payload.default_retention_years
    row.default_review_interval_months = payload.default_review_interval_months
    row.regulated_workflow_enabled = payload.regulated_workflow_enabled
    row.default_ack_required = payload.default_ack_required

    extended = _extended_settings(tenant)
    extended.update({
        "document_classes": _normalize_classes(payload.document_classes),
        "workflow_policy": payload.workflow_policy.model_dump(),
        "retention_classes": payload.retention_classes,
        "indexing_policy": payload.indexing_policy.model_dump(),
        "integration_modules": _normalize_modules(payload.integration_modules),
        "physical_copy_policy": payload.physical_copy_policy.model_dump(),
    })
    tenant_settings = dict(tenant.settings_json or {})
    tenant_settings[ADMIN_SETTINGS_KEY] = extended
    tenant.settings_json = tenant_settings

    after = _settings_payload(tenant, row)
    audit(db, tenant, request, "document.administration.updated", "document_control_administration", tenant.amo_id, {"before": before, "after": after})
    db.commit()
    return after
