from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from amodb.database import get_write_db

from .independence_conflict import get_independence_policy, set_independence_policy
from .people_default_rules import (
    ensure_default_quality_privilege_rules,
    sync_default_quality_privilege_rule_competence,
)
from .people_models import QualityPrivilege, QualityPrivilegeRule
from .tenant_security import (
    TenantContext,
    require_quality_permission,
    require_quality_write_permission,
    set_postgres_tenant_context,
    write_tenant_context,
)

router = APIRouter(prefix="/people", tags=["Quality authorization policy"])

PrivilegeType = Literal["AUDITOR", "LEAD_AUDITOR", "QUALITY_INSPECTOR", "AUTHORIZATION_REVIEWER", "CUSTOM"]


class PrivilegeRuleCreate(BaseModel):
    privilege_code: str = Field(min_length=2, max_length=64, pattern=r"^[A-Z0-9_\-]+$")
    title: str = Field(min_length=3, max_length=255)
    privilege_type: PrivilegeType
    description: str | None = None
    required_training_course_codes: list[str] = Field(default_factory=list, max_length=50)
    independence_required: bool = True
    max_concurrent_assignments: int | None = Field(default=None, ge=1, le=100)
    scope_schema: dict[str, Any] = Field(default_factory=dict)


class PrivilegeRuleUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=255)
    description: str | None = None
    required_training_course_codes: list[str] | None = Field(default=None, max_length=50)
    independence_required: bool | None = None
    max_concurrent_assignments: int | None = Field(default=None, ge=1, le=100)
    scope_schema: dict[str, Any] | None = None
    is_active: bool | None = None


class IndependencePolicyUpdate(BaseModel):
    enforced: bool | None = None
    allow_impartiality_form: bool | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _holder_counts(db: Session, *, amo_id: str, rule_ids: list[str]) -> dict[str, dict[str, int]]:
    if not rule_ids:
        return {}
    rows = db.query(QualityPrivilege.rule_id, QualityPrivilege.status).filter(
        QualityPrivilege.amo_id == amo_id,
        QualityPrivilege.rule_id.in_(rule_ids),
    ).all()
    counts: dict[str, dict[str, int]] = {}
    for rule_id, status_value in rows:
        key = str(rule_id)
        bucket = counts.setdefault(key, {"active_holders": 0, "live_holders": 0, "total_holders": 0})
        bucket["total_holders"] += 1
        if status_value == "ACTIVE":
            bucket["active_holders"] += 1
            bucket["live_holders"] += 1
        elif status_value in {"SUSPENDED", "DRAFT"}:
            bucket["live_holders"] += 1
    return counts


def _rule_dict(row: QualityPrivilegeRule, counts: dict[str, int] | None = None) -> dict[str, Any]:
    counts = counts or {}
    return {
        "id": str(row.id),
        "privilege_code": row.privilege_code,
        "title": row.title,
        "privilege_type": row.privilege_type,
        "description": row.description,
        "required_training_course_codes": list(row.required_training_course_codes or []),
        "independence_required": bool(row.independence_required),
        "max_concurrent_assignments": row.max_concurrent_assignments,
        "scope_schema": row.scope_schema or {},
        "is_active": bool(row.is_active),
        "updated_at": row.updated_at,
        "active_holders": int(counts.get("active_holders", 0)),
        "live_holders": int(counts.get("live_holders", 0)),
        "total_holders": int(counts.get("total_holders", 0)),
    }


@router.get("/rules")
def list_rules(
    include_inactive: bool = False,
    ctx: TenantContext = Depends(require_quality_permission("qms.people.view")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    """Administrative authorization policy catalog used by case and assignment engines."""

    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    ensure_default_quality_privilege_rules(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id)
    sync_default_quality_privilege_rule_competence(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id)
    db.flush()
    query = db.query(QualityPrivilegeRule).filter(QualityPrivilegeRule.amo_id == ctx.amo_id)
    if not include_inactive:
        query = query.filter(QualityPrivilegeRule.is_active.is_(True))
    rows = query.order_by(QualityPrivilegeRule.title.asc()).limit(250).all()
    counts = _holder_counts(db, amo_id=ctx.amo_id, rule_ids=[str(row.id) for row in rows])
    payload = {"items": [_rule_dict(row, counts.get(str(row.id))) for row in rows]}
    db.commit()
    return payload


@router.post("/rules/ensure-defaults")
def ensure_default_rules(
    ctx: TenantContext = Depends(require_quality_write_permission("qms.authorization.policy.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    rows = ensure_default_quality_privilege_rules(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id)
    db.commit()
    return {"items": [_rule_dict(row) for row in rows]}


@router.post("/rules", status_code=status.HTTP_201_CREATED)
def create_rule(
    payload: PrivilegeRuleCreate,
    ctx: TenantContext = Depends(require_quality_write_permission("qms.authorization.policy.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    code = payload.privilege_code.strip().upper()
    if db.query(QualityPrivilegeRule.id).filter(
        QualityPrivilegeRule.amo_id == ctx.amo_id,
        QualityPrivilegeRule.privilege_code == code,
    ).first():
        raise HTTPException(status_code=409, detail="A Quality authorization type with this code already exists.")
    row = QualityPrivilegeRule(
        amo_id=ctx.amo_id,
        privilege_code=code,
        title=payload.title.strip(),
        privilege_type=payload.privilege_type,
        description=payload.description,
        required_training_course_codes=sorted({
            value.strip().upper()
            for value in payload.required_training_course_codes
            if value.strip()
        }),
        independence_required=payload.independence_required,
        max_concurrent_assignments=payload.max_concurrent_assignments,
        scope_schema=payload.scope_schema,
        created_by_user_id=ctx.user_id,
        updated_by_user_id=ctx.user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _rule_dict(row)


@router.patch("/rules/{rule_id}")
def update_rule(
    rule_id: str,
    payload: PrivilegeRuleUpdate,
    ctx: TenantContext = Depends(require_quality_write_permission("qms.authorization.policy.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    row = db.query(QualityPrivilegeRule).filter(
        QualityPrivilegeRule.amo_id == ctx.amo_id,
        QualityPrivilegeRule.id == rule_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Quality authorization type not found.")
    updates = payload.model_dump(exclude_unset=True)
    if "title" in updates:
        row.title = str(updates["title"]).strip()
    if "description" in updates:
        row.description = updates["description"]
    if "required_training_course_codes" in updates:
        row.required_training_course_codes = sorted({
            value.strip().upper()
            for value in (updates["required_training_course_codes"] or [])
            if value.strip()
        })
    if "independence_required" in updates:
        row.independence_required = bool(updates["independence_required"])
    if "max_concurrent_assignments" in updates:
        row.max_concurrent_assignments = updates["max_concurrent_assignments"]
    if "scope_schema" in updates:
        row.scope_schema = updates["scope_schema"] or {}
    if "is_active" in updates:
        if updates["is_active"] is False:
            live = db.query(QualityPrivilege.id).filter(
                QualityPrivilege.amo_id == ctx.amo_id,
                QualityPrivilege.rule_id == row.id,
                QualityPrivilege.status.in_(["ACTIVE", "SUSPENDED", "DRAFT"]),
            ).first()
            if live:
                raise HTTPException(
                    status_code=409,
                    detail="This authorization type still has live authorizations. Resolve them before deactivating the policy.",
                )
        row.is_active = bool(updates["is_active"])
    row.updated_by_user_id = ctx.user_id
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    counts = _holder_counts(db, amo_id=ctx.amo_id, rule_ids=[str(row.id)])
    return _rule_dict(row, counts.get(str(row.id)))


@router.get("/independence/policy")
def independence_policy(
    ctx: TenantContext = Depends(require_quality_permission("qms.people.view")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return get_independence_policy(db, amo_id=ctx.amo_id)


@router.patch("/independence/policy")
def update_independence_policy(
    payload: IndependencePolicyUpdate,
    ctx: TenantContext = Depends(write_tenant_context),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    # Independence enforcement is a platform safety control, not an ordinary
    # tenant authorization setting. AMO roles may view it but cannot turn it off.
    if not ctx.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Only an active platform support administrator may change tenant independence enforcement.",
        )
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    try:
        policy = set_independence_policy(
            db,
            amo_id=ctx.amo_id,
            enforced=payload.enforced,
            allow_impartiality_form=payload.allow_impartiality_form,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return policy
