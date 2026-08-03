from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import services as account_services
from amodb.security import get_password_hash

from . import models as platform_models
from .commercial_models import (
    CommercialModule,
    EntitlementOverride,
    InvoiceLineItem,
    PaymentTransaction,
    PriceBook,
    PriceBookEntry,
    ProductPlan,
    ProductPlanModule,
    SubscriptionEvent,
    SubscriptionItem,
    TenantSubscription,
)

VALID_DATA_MODES = {"REAL", "DEMO"}
VALID_PLAN_STATUSES = {"DRAFT", "ACTIVE", "ARCHIVED"}
VALID_MODULE_STATUSES = {"ACTIVE", "DEPRECATED", "DEVELOPMENT", "ARCHIVED"}
VALID_PRICE_STATUSES = {"DRAFT", "ACTIVE", "RETIRED"}
VALID_SUBSCRIPTION_STATUSES = {"DRAFT", "TRIALING", "ACTIVE", "PAST_DUE", "PAUSED", "CANCELLED", "EXPIRED"}
ACTIVE_SUBSCRIPTION_STATUSES = {"TRIALING", "ACTIVE", "PAST_DUE"}
VALID_BILLING_TERMS = {"MONTHLY", "BI_ANNUAL", "ANNUAL", "ONE_TIME"}
VALID_MODULE_ACCESS = {"ENABLED", "TRIAL", "SUSPENDED", "DISABLED"}

DEFAULT_MODULES: tuple[dict[str, Any], ...] = (
    {"code": "quality", "name": "Quality Management", "category": "QUALITY", "route_prefix": "/quality"},
    {"code": "training", "name": "Training & Competence", "category": "WORKFORCE", "route_prefix": "/training"},
    {"code": "manuals", "name": "Controlled Manuals", "category": "DOCUMENTS", "route_prefix": "/document-control"},
    {"code": "aerodoc_hybrid_dms", "name": "AeroDoc Hybrid DMS", "category": "DOCUMENTS", "route_prefix": "/document-control"},
    {"code": "maintenance_program", "name": "Maintenance Programme", "category": "MAINTENANCE", "route_prefix": "/planning"},
    {"code": "work", "name": "Work Orders", "category": "MAINTENANCE", "route_prefix": "/work"},
    {"code": "fleet", "name": "Fleet", "category": "MAINTENANCE", "route_prefix": "/aircraft"},
    {"code": "reliability", "name": "Reliability", "category": "AIRWORTHINESS", "route_prefix": "/reliability"},
    {"code": "finance_inventory", "name": "Finance & Inventory", "category": "COMMERCIAL", "route_prefix": "/inventory"},
    {"code": "production", "name": "Production", "category": "MAINTENANCE", "route_prefix": "/production"},
    {"code": "planning", "name": "Planning", "category": "MAINTENANCE", "route_prefix": "/planning"},
    {"code": "technical_records", "name": "Technical Records", "category": "RECORDS", "route_prefix": "/technical-records"},
    {"code": "equipment_calibration", "name": "Equipment & Calibration", "category": "QUALITY", "route_prefix": "/calibration"},
    {"code": "suppliers", "name": "Suppliers", "category": "QUALITY", "route_prefix": "/suppliers"},
    {"code": "management_review", "name": "Management Review", "category": "QUALITY", "route_prefix": "/management-review"},
    {"code": "rostering", "name": "Rostering", "category": "WORKFORCE", "route_prefix": "/rostering"},
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_data_mode(value: str | None, *, default: str = "REAL") -> str:
    mode = (value or default).strip().upper()
    if mode == "LIVE":
        mode = "REAL"
    if mode not in VALID_DATA_MODES:
        raise ValueError("data_mode must be REAL or DEMO. ALL is intentionally unsupported.")
    return mode


def normalize_code(value: str, *, label: str = "code") -> str:
    code = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not code or len(code) > 64 or not all(ch.isalnum() or ch == "_" for ch in code):
        raise ValueError(f"{label} must contain only letters, numbers and underscores")
    return code


def plan_code(value: str) -> str:
    return normalize_code(value, label="plan code").upper()


def enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def audit(
    db: Session,
    *,
    actor_user_id: str | None,
    action: str,
    tenant_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(platform_models.PlatformAuditLog(
        actor_user_id=actor_user_id,
        tenant_id=tenant_id,
        action=action,
        module="commercial",
        entity_type=entity_type,
        entity_id=entity_id,
        reason=(reason or "")[:1000] or None,
        details_json=details or {},
    ))


def ensure_catalog(db: Session, *, actor_user_id: str | None = None) -> None:
    existing = {row.code for row in db.query(CommercialModule).all()}
    changed = False
    for definition in DEFAULT_MODULES:
        if definition["code"] in existing:
            continue
        db.add(CommercialModule(
            code=definition["code"], name=definition["name"], category=definition["category"],
            route_prefix=definition["route_prefix"], status="ACTIVE", sellable=True,
            trial_eligible=True, created_by=actor_user_id, updated_by=actor_user_id,
        ))
        changed = True
    if changed:
        db.flush()

    if db.query(ProductPlan).count() == 0:
        starter = ProductPlan(code="STARTER", name="Starter", description="Core controlled operations for a small AMO.", status="ACTIVE", is_public=True, trial_days=14, default_billing_term="MONTHLY", created_by=actor_user_id, updated_by=actor_user_id)
        professional = ProductPlan(code="PROFESSIONAL", name="Professional", description="Expanded operational, workforce and assurance modules.", status="ACTIVE", is_public=True, trial_days=14, default_billing_term="MONTHLY", created_by=actor_user_id, updated_by=actor_user_id)
        enterprise = ProductPlan(code="ENTERPRISE", name="Enterprise", description="Full platform access with negotiated limits and provider integration.", status="ACTIVE", is_public=False, trial_days=0, default_billing_term="ANNUAL", created_by=actor_user_id, updated_by=actor_user_id)
        db.add_all([starter, professional, enterprise]); db.flush()
        module_by_code = {row.code: row for row in db.query(CommercialModule).all()}
        starter_codes = {"quality", "training", "manuals", "work", "fleet"}
        professional_codes = starter_codes | {"planning", "production", "technical_records", "suppliers", "equipment_calibration", "rostering"}
        for code, module in module_by_code.items():
            if code in starter_codes:
                db.add(ProductPlanModule(plan_id=starter.id, module_id=module.id, included=True))
            if code in professional_codes:
                db.add(ProductPlanModule(plan_id=professional.id, module_id=module.id, included=True))
            db.add(ProductPlanModule(plan_id=enterprise.id, module_id=module.id, included=True))
        changed = True

    if db.query(PriceBook).count() == 0:
        db.add_all([
            PriceBook(code="REAL_USD", name="Real tenants · USD", currency="USD", data_mode="REAL", status="ACTIVE", created_by=actor_user_id, updated_by=actor_user_id),
            PriceBook(code="REAL_KES", name="Real tenants · KES", currency="KES", data_mode="REAL", status="ACTIVE", created_by=actor_user_id, updated_by=actor_user_id),
            PriceBook(code="DEMO_USD", name="Demo tenants · USD", currency="USD", data_mode="DEMO", status="ACTIVE", created_by=actor_user_id, updated_by=actor_user_id),
        ])
        changed = True
    if changed:
        db.commit()


def module_payload(row: CommercialModule) -> dict[str, Any]:
    return {
        "id": row.id, "code": row.code, "name": row.name, "description": row.description,
        "category": row.category, "status": row.status, "sellable": row.sellable,
        "trial_eligible": row.trial_eligible, "route_prefix": row.route_prefix,
        "dependencies": row.dependencies_json or [], "features": row.features_json or [],
        "default_limits": row.default_limits_json or {}, "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def plan_payload(db: Session, row: ProductPlan) -> dict[str, Any]:
    links = db.query(ProductPlanModule, CommercialModule).join(CommercialModule, CommercialModule.id == ProductPlanModule.module_id).filter(ProductPlanModule.plan_id == row.id).order_by(ProductPlanModule.sort_order.asc(), CommercialModule.name.asc()).all()
    return {
        "id": row.id, "code": row.code, "name": row.name, "description": row.description,
        "status": row.status, "is_public": row.is_public, "trial_days": row.trial_days,
        "default_billing_term": row.default_billing_term, "metadata": row.metadata_json or {},
        "modules": [{"id": link.id, "module_id": module.id, "module_code": module.code, "module_name": module.name, "included": link.included, "limits": link.limits_json or {}, "feature_overrides": link.feature_overrides_json or {}, "sort_order": link.sort_order} for link, module in links],
        "created_at": row.created_at, "updated_at": row.updated_at,
    }


def price_book_payload(row: PriceBook) -> dict[str, Any]:
    return {"id": row.id, "code": row.code, "name": row.name, "currency": row.currency, "market": row.market, "data_mode": row.data_mode, "status": row.status, "tax_inclusive": row.tax_inclusive, "metadata": row.metadata_json or {}, "created_at": row.created_at, "updated_at": row.updated_at}


def price_payload(db: Session, row: PriceBookEntry) -> dict[str, Any]:
    book = db.get(PriceBook, row.price_book_id)
    plan = db.get(ProductPlan, row.plan_id) if row.plan_id else None
    module = db.get(CommercialModule, row.module_id) if row.module_id else None
    return {
        "id": row.id, "price_book_id": row.price_book_id, "price_book_code": book.code if book else None,
        "currency": book.currency if book else None, "data_mode": book.data_mode if book else None,
        "plan_id": row.plan_id, "plan_code": plan.code if plan else None, "plan_name": plan.name if plan else None,
        "module_id": row.module_id, "module_code": module.code if module else None, "module_name": module.name if module else None,
        "billing_term": row.billing_term, "unit_amount_cents": row.unit_amount_cents,
        "included_quantity": row.included_quantity, "overage_amount_cents": row.overage_amount_cents,
        "trial_days": row.trial_days, "tax_rate_bps": row.tax_rate_bps, "status": row.status,
        "effective_from": row.effective_from, "effective_to": row.effective_to,
        "external_product_ref": row.external_product_ref, "external_price_ref": row.external_price_ref,
        "metadata": row.metadata_json or {}, "created_at": row.created_at, "updated_at": row.updated_at,
    }


def list_modules(db: Session, *, include_archived: bool = False) -> list[dict[str, Any]]:
    ensure_catalog(db)
    query = db.query(CommercialModule)
    if not include_archived:
        query = query.filter(CommercialModule.status != "ARCHIVED")
    return [module_payload(row) for row in query.order_by(CommercialModule.category, CommercialModule.name).all()]


def upsert_module(db: Session, *, payload: dict[str, Any], actor_user_id: str, module_id: str | None = None) -> dict[str, Any]:
    row = db.get(CommercialModule, module_id) if module_id else None
    if module_id and not row:
        raise ValueError("Module not found")
    code = normalize_code(str(payload.get("code") or getattr(row, "code", "")), label="module code")
    duplicate = db.query(CommercialModule).filter(CommercialModule.code == code)
    if row:
        duplicate = duplicate.filter(CommercialModule.id != row.id)
    if duplicate.first():
        raise ValueError("A module with this code already exists")
    state = str(payload.get("status") or getattr(row, "status", "ACTIVE")).strip().upper()
    if state not in VALID_MODULE_STATUSES:
        raise ValueError("Unsupported module status")
    if not row:
        row = CommercialModule(code=code, name=str(payload.get("name") or code.replace("_", " ").title()), created_by=actor_user_id)
        db.add(row)
    row.code = code; row.name = str(payload.get("name") or row.name).strip(); row.description = payload.get("description", row.description)
    row.category = str(payload.get("category") or row.category or "GENERAL").strip().upper(); row.status = state
    row.sellable = bool(payload.get("sellable", row.sellable if row.id else True)); row.trial_eligible = bool(payload.get("trial_eligible", row.trial_eligible if row.id else True))
    row.route_prefix = payload.get("route_prefix", row.route_prefix); row.dependencies_json = list(payload.get("dependencies", row.dependencies_json or []))
    row.features_json = list(payload.get("features", row.features_json or [])); row.default_limits_json = dict(payload.get("default_limits", row.default_limits_json or {})); row.updated_by = actor_user_id
    db.flush(); audit(db, actor_user_id=actor_user_id, action="commercial.module.upserted", entity_type="commercial_module", entity_id=row.id, reason=payload.get("reason"), details=module_payload(row)); db.commit(); db.refresh(row)
    return module_payload(row)


def list_plans(db: Session, *, include_archived: bool = False) -> list[dict[str, Any]]:
    ensure_catalog(db)
    query = db.query(ProductPlan)
    if not include_archived:
        query = query.filter(ProductPlan.status != "ARCHIVED")
    return [plan_payload(db, row) for row in query.order_by(ProductPlan.name).all()]


def upsert_plan(db: Session, *, payload: dict[str, Any], actor_user_id: str, plan_id: str | None = None) -> dict[str, Any]:
    row = db.get(ProductPlan, plan_id) if plan_id else None
    if plan_id and not row:
        raise ValueError("Plan not found")
    code = plan_code(str(payload.get("code") or getattr(row, "code", "")))
    duplicate = db.query(ProductPlan).filter(ProductPlan.code == code)
    if row:
        duplicate = duplicate.filter(ProductPlan.id != row.id)
    if duplicate.first():
        raise ValueError("A plan with this code already exists")
    state = str(payload.get("status") or getattr(row, "status", "DRAFT")).strip().upper()
    if state not in VALID_PLAN_STATUSES:
        raise ValueError("Unsupported plan status")
    term = str(payload.get("default_billing_term") or getattr(row, "default_billing_term", "MONTHLY")).strip().upper()
    if term not in VALID_BILLING_TERMS:
        raise ValueError("Unsupported billing term")
    if not row:
        row = ProductPlan(code=code, name=str(payload.get("name") or code.title()), created_by=actor_user_id)
        db.add(row)
    row.code = code; row.name = str(payload.get("name") or row.name).strip(); row.description = payload.get("description", row.description); row.status = state
    row.is_public = bool(payload.get("is_public", row.is_public if row.id else False)); row.trial_days = max(0, min(int(payload.get("trial_days", row.trial_days or 0)), 365)); row.default_billing_term = term
    row.metadata_json = dict(payload.get("metadata", row.metadata_json or {})); row.updated_by = actor_user_id; db.flush()
    if "modules" in payload:
        module_rows = {module.id: module for module in db.query(CommercialModule).all()}
        db.query(ProductPlanModule).filter(ProductPlanModule.plan_id == row.id).delete(synchronize_session=False)
        for index, item in enumerate(payload.get("modules") or []):
            module_id_value = str(item.get("module_id") or "")
            if module_id_value not in module_rows:
                raise ValueError(f"Unknown module in plan: {module_id_value}")
            db.add(ProductPlanModule(plan_id=row.id, module_id=module_id_value, included=bool(item.get("included", True)), limits_json=dict(item.get("limits") or {}), feature_overrides_json=dict(item.get("feature_overrides") or {}), sort_order=int(item.get("sort_order") or (index + 1) * 10)))
    audit(db, actor_user_id=actor_user_id, action="commercial.plan.upserted", entity_type="product_plan", entity_id=row.id, reason=payload.get("reason"), details={"code": code, "status": state}); db.commit(); db.refresh(row)
    return plan_payload(db, row)


def list_price_books(db: Session, *, data_mode: str | None = None) -> list[dict[str, Any]]:
    ensure_catalog(db)
    query = db.query(PriceBook)
    if data_mode:
        query = query.filter(PriceBook.data_mode == normalize_data_mode(data_mode))
    return [price_book_payload(row) for row in query.order_by(PriceBook.data_mode, PriceBook.currency, PriceBook.name).all()]


def upsert_price_book(db: Session, *, payload: dict[str, Any], actor_user_id: str, book_id: str | None = None) -> dict[str, Any]:
    row = db.get(PriceBook, book_id) if book_id else None
    if book_id and not row:
        raise ValueError("Price book not found")
    code = plan_code(str(payload.get("code") or getattr(row, "code", "")))
    duplicate = db.query(PriceBook).filter(PriceBook.code == code)
    if row:
        duplicate = duplicate.filter(PriceBook.id != row.id)
    if duplicate.first():
        raise ValueError("A price book with this code already exists")
    mode = normalize_data_mode(str(payload.get("data_mode") or getattr(row, "data_mode", "REAL")))
    if not row:
        row = PriceBook(code=code, name=str(payload.get("name") or code.title()), created_by=actor_user_id)
        db.add(row)
    row.code = code; row.name = str(payload.get("name") or row.name).strip(); row.currency = str(payload.get("currency") or row.currency or "USD").strip().upper(); row.market = payload.get("market", row.market)
    row.data_mode = mode; row.status = str(payload.get("status") or row.status or "ACTIVE").strip().upper(); row.tax_inclusive = bool(payload.get("tax_inclusive", row.tax_inclusive if row.id else False)); row.metadata_json = dict(payload.get("metadata", row.metadata_json or {})); row.updated_by = actor_user_id
    db.flush(); audit(db, actor_user_id=actor_user_id, action="commercial.price_book.upserted", entity_type="price_book", entity_id=row.id, reason=payload.get("reason"), details=price_book_payload(row)); db.commit(); db.refresh(row)
    return price_book_payload(row)


def list_prices(db: Session, *, data_mode: str | None = None, include_retired: bool = False) -> list[dict[str, Any]]:
    ensure_catalog(db)
    query = db.query(PriceBookEntry).join(PriceBook, PriceBook.id == PriceBookEntry.price_book_id)
    if data_mode:
        query = query.filter(PriceBook.data_mode == normalize_data_mode(data_mode))
    if not include_retired:
        query = query.filter(PriceBookEntry.status != "RETIRED")
    return [price_payload(db, row) for row in query.order_by(PriceBook.code, PriceBookEntry.effective_from.desc()).all()]


def upsert_price(db: Session, *, payload: dict[str, Any], actor_user_id: str, price_id: str | None = None) -> dict[str, Any]:
    row = db.get(PriceBookEntry, price_id) if price_id else None
    if price_id and not row:
        raise ValueError("Price not found")
    book_id = str(payload.get("price_book_id") or getattr(row, "price_book_id", "")); plan_id_value = str(payload.get("plan_id") or getattr(row, "plan_id", "")) or None; module_id_value = str(payload.get("module_id") or getattr(row, "module_id", "")) or None
    book = db.get(PriceBook, book_id)
    if not book or book.status != "ACTIVE":
        raise ValueError("An active price book is required")
    if not plan_id_value and not module_id_value:
        raise ValueError("A price must target a plan or module")
    if plan_id_value and not db.get(ProductPlan, plan_id_value):
        raise ValueError("Plan not found")
    if module_id_value and not db.get(CommercialModule, module_id_value):
        raise ValueError("Module not found")
    term = str(payload.get("billing_term") or getattr(row, "billing_term", "MONTHLY")).strip().upper()
    if term not in VALID_BILLING_TERMS:
        raise ValueError("Unsupported billing term")
    amount = int(payload.get("unit_amount_cents", getattr(row, "unit_amount_cents", -1)))
    if amount < 0:
        raise ValueError("unit_amount_cents cannot be negative")
    state = str(payload.get("status") or getattr(row, "status", "ACTIVE")).strip().upper()
    if state not in VALID_PRICE_STATUSES:
        raise ValueError("Unsupported price status")
    effective_from = payload.get("effective_from") or getattr(row, "effective_from", None) or utcnow()
    if isinstance(effective_from, str):
        effective_from = datetime.fromisoformat(effective_from.replace("Z", "+00:00"))
    effective_to = payload.get("effective_to", getattr(row, "effective_to", None))
    if isinstance(effective_to, str) and effective_to:
        effective_to = datetime.fromisoformat(effective_to.replace("Z", "+00:00"))
    if effective_to and effective_to <= effective_from:
        raise ValueError("effective_to must be after effective_from")
    if not row:
        row = PriceBookEntry(price_book_id=book_id, billing_term=term, unit_amount_cents=amount, created_by=actor_user_id); db.add(row)
    row.price_book_id = book_id; row.plan_id = plan_id_value; row.module_id = module_id_value; row.billing_term = term; row.unit_amount_cents = amount
    row.included_quantity = max(1, int(payload.get("included_quantity", row.included_quantity or 1))); row.overage_amount_cents = payload.get("overage_amount_cents", row.overage_amount_cents)
    row.trial_days = max(0, min(int(payload.get("trial_days", row.trial_days or 0)), 365)); row.tax_rate_bps = max(0, min(int(payload.get("tax_rate_bps", row.tax_rate_bps or 0)), 10000)); row.status = state
    row.effective_from = effective_from; row.effective_to = effective_to; row.external_product_ref = payload.get("external_product_ref", row.external_product_ref); row.external_price_ref = payload.get("external_price_ref", row.external_price_ref); row.metadata_json = dict(payload.get("metadata", row.metadata_json or {})); row.updated_by = actor_user_id
    db.flush(); audit(db, actor_user_id=actor_user_id, action="commercial.price.upserted", entity_type="price_book_entry", entity_id=row.id, reason=payload.get("reason"), details=price_payload(db, row)); db.commit(); db.refresh(row)
    return price_payload(db, row)


def period_end(start: datetime, term: str) -> datetime | None:
    if term == "ONE_TIME":
        return None
    return start + timedelta(days={"MONTHLY": 30, "BI_ANNUAL": 182, "ANNUAL": 365}.get(term, 30))


def subscription_snapshot(row: TenantSubscription) -> dict[str, Any]:
    return {"id": row.id, "tenant_id": row.tenant_id, "plan_id": row.plan_id, "price_book_id": row.price_book_id, "status": row.status, "billing_term": row.billing_term, "quantity": row.quantity, "currency": row.currency, "provider": row.provider, "external_customer_ref": row.external_customer_ref, "external_subscription_ref": row.external_subscription_ref, "auto_collection": row.auto_collection, "cancel_at_period_end": row.cancel_at_period_end, "current_period_start": row.current_period_start, "current_period_end": row.current_period_end, "trial_ends_at": row.trial_ends_at, "cancelled_at": row.cancelled_at, "metadata": row.metadata_json or {}}


def subscription_payload(db: Session, row: TenantSubscription, *, include_events: bool = False) -> dict[str, Any]:
    tenant = db.get(account_models.AMO, row.tenant_id); plan = db.get(ProductPlan, row.plan_id); book = db.get(PriceBook, row.price_book_id) if row.price_book_id else None
    items = db.query(SubscriptionItem, CommercialModule).join(CommercialModule, CommercialModule.id == SubscriptionItem.module_id).filter(SubscriptionItem.subscription_id == row.id).order_by(CommercialModule.name).all()
    result = {**subscription_snapshot(row), "tenant_name": tenant.name if tenant else None, "tenant_code": tenant.amo_code if tenant else None, "data_mode": "DEMO" if tenant and tenant.is_demo else "REAL", "plan_code": plan.code if plan else None, "plan_name": plan.name if plan else None, "price_book_code": book.code if book else None, "items": [{"id": item.id, "module_id": module.id, "module_code": module.code, "module_name": module.name, "price_entry_id": item.price_entry_id, "status": item.status, "quantity": item.quantity, "unit_amount_cents": item.unit_amount_cents, "limits": item.limits_json or {}, "effective_from": item.effective_from, "effective_to": item.effective_to} for item, module in items]}
    if include_events:
        result["events"] = [{"id": event.id, "event_type": event.event_type, "actor_user_id": event.actor_user_id, "reason": event.reason, "before": event.before_json or {}, "after": event.after_json or {}, "created_at": event.created_at} for event in db.query(SubscriptionEvent).filter(SubscriptionEvent.subscription_id == row.id).order_by(SubscriptionEvent.created_at.desc()).limit(100).all()]
    return result


def list_subscriptions(db: Session, *, data_mode: str, tenant_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    mode = normalize_data_mode(data_mode)
    query = db.query(TenantSubscription).join(account_models.AMO, account_models.AMO.id == TenantSubscription.tenant_id).filter(account_models.AMO.is_demo.is_(mode == "DEMO"))
    if tenant_id:
        query = query.filter(TenantSubscription.tenant_id == tenant_id)
    if status:
        query = query.filter(TenantSubscription.status == status.strip().upper())
    return [subscription_payload(db, row) for row in query.order_by(TenantSubscription.updated_at.desc()).all()]


def active_price_for(db: Session, *, price_book_id: str | None, plan_id: str | None, module_id: str | None, billing_term: str, at: datetime) -> PriceBookEntry | None:
    if not price_book_id:
        return None
    query = db.query(PriceBookEntry).filter(PriceBookEntry.price_book_id == price_book_id, PriceBookEntry.billing_term == billing_term, PriceBookEntry.status == "ACTIVE", PriceBookEntry.effective_from <= at, or_(PriceBookEntry.effective_to.is_(None), PriceBookEntry.effective_to > at))
    if module_id:
        query = query.filter(PriceBookEntry.module_id == module_id)
    else:
        query = query.filter(PriceBookEntry.module_id.is_(None), PriceBookEntry.plan_id == plan_id)
    return query.order_by(PriceBookEntry.effective_from.desc()).first()


def plan_module_links(db: Session, plan_id: str) -> list[ProductPlanModule]:
    return db.query(ProductPlanModule).filter(ProductPlanModule.plan_id == plan_id, ProductPlanModule.included.is_(True)).order_by(ProductPlanModule.sort_order).all()


def create_subscription(db: Session, *, payload: dict[str, Any], actor_user_id: str) -> dict[str, Any]:
    tenant_id = str(payload.get("tenant_id") or ""); tenant = db.get(account_models.AMO, tenant_id)
    if not tenant:
        raise ValueError("Tenant not found")
    plan = db.get(ProductPlan, str(payload.get("plan_id") or ""))
    if not plan or plan.status != "ACTIVE":
        raise ValueError("An active product plan is required")
    mode = "DEMO" if tenant.is_demo else "REAL"; book = db.get(PriceBook, str(payload.get("price_book_id") or "")) if payload.get("price_book_id") else None
    if book and (book.status != "ACTIVE" or book.data_mode != mode):
        raise ValueError("Price book does not match the tenant environment")
    existing = db.query(TenantSubscription).filter(TenantSubscription.tenant_id == tenant_id, TenantSubscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES | {"DRAFT", "PAUSED"})).first()
    if existing:
        raise ValueError("Tenant already has a current subscription")
    term = str(payload.get("billing_term") or plan.default_billing_term or "MONTHLY").strip().upper()
    if term not in VALID_BILLING_TERMS:
        raise ValueError("Unsupported billing term")
    state = str(payload.get("status") or ("TRIALING" if plan.trial_days > 0 else "ACTIVE")).strip().upper()
    if state not in VALID_SUBSCRIPTION_STATUSES:
        raise ValueError("Unsupported subscription status")
    now = utcnow(); trial_days = max(0, int(payload.get("trial_days", plan.trial_days or 0)))
    if state == "TRIALING" and trial_days <= 0:
        raise ValueError("This plan has no trial period")
    row = TenantSubscription(tenant_id=tenant_id, plan_id=plan.id, price_book_id=book.id if book else None, status=state, billing_term=term, quantity=max(1, int(payload.get("quantity") or 1)), currency=book.currency if book else str(payload.get("currency") or "USD").upper(), provider=str(payload.get("provider") or "").strip().lower() or None, external_customer_ref=payload.get("external_customer_ref"), external_subscription_ref=payload.get("external_subscription_ref"), auto_collection=bool(payload.get("auto_collection", False)), current_period_start=now if state in ACTIVE_SUBSCRIPTION_STATUSES else None, current_period_end=period_end(now, term) if state in ACTIVE_SUBSCRIPTION_STATUSES else None, trial_ends_at=now + timedelta(days=trial_days) if state == "TRIALING" else None, metadata_json=dict(payload.get("metadata") or {}), created_by=actor_user_id, updated_by=actor_user_id)
    db.add(row); db.flush()
    for link in plan_module_links(db, plan.id):
        module = db.get(CommercialModule, link.module_id); price = active_price_for(db, price_book_id=row.price_book_id, plan_id=plan.id, module_id=link.module_id, billing_term=term, at=now)
        db.add(SubscriptionItem(subscription_id=row.id, module_id=link.module_id, price_entry_id=price.id if price else None, status="ACTIVE", quantity=row.quantity, unit_amount_cents=price.unit_amount_cents if price else 0, limits_json={**(module.default_limits_json or {}), **(link.limits_json or {})} if module else (link.limits_json or {}), effective_from=now))
    db.add(SubscriptionEvent(subscription_id=row.id, event_type="CREATED", actor_user_id=actor_user_id, reason=str(payload.get("reason") or "Subscription created"), before_json={}, after_json=subscription_snapshot(row)))
    audit(db, actor_user_id=actor_user_id, action="commercial.subscription.created", tenant_id=tenant_id, entity_type="tenant_subscription", entity_id=row.id, reason=payload.get("reason"), details=subscription_snapshot(row)); db.flush()
    reconcile_subscription(db, row=row, actor_user_id=actor_user_id, reason="Canonical subscription projection", commit=False); db.commit(); db.refresh(row)
    return subscription_payload(db, row, include_events=True)


def update_subscription(db: Session, *, subscription_id: str, payload: dict[str, Any], actor_user_id: str) -> dict[str, Any]:
    row = db.get(TenantSubscription, subscription_id)
    if not row:
        raise ValueError("Subscription not found")
    before = subscription_snapshot(row)
    if "plan_id" in payload:
        plan = db.get(ProductPlan, str(payload.get("plan_id") or ""))
        if not plan or plan.status != "ACTIVE":
            raise ValueError("An active plan is required")
        row.plan_id = plan.id
    if "price_book_id" in payload:
        book = db.get(PriceBook, str(payload.get("price_book_id") or "")); tenant = db.get(account_models.AMO, row.tenant_id); expected_mode = "DEMO" if tenant and tenant.is_demo else "REAL"
        if not book or book.status != "ACTIVE" or book.data_mode != expected_mode:
            raise ValueError("Price book does not match the tenant environment")
        row.price_book_id = book.id; row.currency = book.currency
    if "billing_term" in payload:
        term = str(payload.get("billing_term") or "").strip().upper()
        if term not in VALID_BILLING_TERMS:
            raise ValueError("Unsupported billing term")
        row.billing_term = term
        if row.status in ACTIVE_SUBSCRIPTION_STATUSES:
            start = row.current_period_start or utcnow(); row.current_period_start = start; row.current_period_end = period_end(start, term)
    for field in ("quantity", "external_customer_ref", "external_subscription_ref", "provider", "auto_collection", "cancel_at_period_end"):
        if field in payload:
            setattr(row, field, payload[field])
    row.quantity = max(1, int(row.quantity or 1))
    if "metadata" in payload:
        row.metadata_json = dict(payload.get("metadata") or {})
    row.updated_by = actor_user_id; db.flush()
    db.add(SubscriptionEvent(subscription_id=row.id, event_type="UPDATED", actor_user_id=actor_user_id, reason=str(payload.get("reason") or "Subscription updated"), before_json=before, after_json=subscription_snapshot(row)))
    audit(db, actor_user_id=actor_user_id, action="commercial.subscription.updated", tenant_id=row.tenant_id, entity_type="tenant_subscription", entity_id=row.id, reason=payload.get("reason"), details={"before": before, "after": subscription_snapshot(row)})
    reconcile_subscription(db, row=row, actor_user_id=actor_user_id, reason="Canonical subscription updated", commit=False); db.commit(); db.refresh(row)
    return subscription_payload(db, row, include_events=True)


def transition_subscription(db: Session, *, subscription_id: str, target_status: str, actor_user_id: str, reason: str, at_period_end: bool = False) -> dict[str, Any]:
    row = db.get(TenantSubscription, subscription_id)
    if not row:
        raise ValueError("Subscription not found")
    target = target_status.strip().upper()
    if target not in VALID_SUBSCRIPTION_STATUSES:
        raise ValueError("Unsupported subscription status")
    if not reason.strip():
        raise ValueError("A reason is required")
    before = subscription_snapshot(row); now = utcnow()
    if target == "CANCELLED" and at_period_end:
        row.cancel_at_period_end = True
    else:
        row.status = target; row.cancel_at_period_end = False
        if target in {"ACTIVE", "TRIALING", "PAST_DUE"}:
            row.current_period_start = now; row.current_period_end = period_end(now, row.billing_term)
            if target == "TRIALING":
                plan = db.get(ProductPlan, row.plan_id); days = int(plan.trial_days if plan else 0)
                if days <= 0:
                    raise ValueError("This plan is not trial eligible")
                row.trial_ends_at = now + timedelta(days=days)
        if target == "CANCELLED":
            row.cancelled_at = now
        if target == "EXPIRED":
            row.current_period_end = now
    row.updated_by = actor_user_id; db.flush()
    db.add(SubscriptionEvent(subscription_id=row.id, event_type=f"STATUS_{target}", actor_user_id=actor_user_id, reason=reason, before_json=before, after_json=subscription_snapshot(row)))
    audit(db, actor_user_id=actor_user_id, action="commercial.subscription.transitioned", tenant_id=row.tenant_id, entity_type="tenant_subscription", entity_id=row.id, reason=reason, details={"target_status": target, "at_period_end": at_period_end})
    reconcile_subscription(db, row=row, actor_user_id=actor_user_id, reason=reason, commit=False); db.commit(); db.refresh(row)
    return subscription_payload(db, row, include_events=True)


def upsert_subscription_item(db: Session, *, subscription_id: str, payload: dict[str, Any], actor_user_id: str) -> dict[str, Any]:
    subscription = db.get(TenantSubscription, subscription_id)
    if not subscription:
        raise ValueError("Subscription not found")
    module = db.get(CommercialModule, str(payload.get("module_id") or ""))
    if not module or module.status not in {"ACTIVE", "DEVELOPMENT"}:
        raise ValueError("Module not found or not available")
    row = db.query(SubscriptionItem).filter(SubscriptionItem.subscription_id == subscription.id, SubscriptionItem.module_id == module.id).first()
    if not row:
        row = SubscriptionItem(subscription_id=subscription.id, module_id=module.id, effective_from=utcnow()); db.add(row)
    price = active_price_for(db, price_book_id=subscription.price_book_id, plan_id=subscription.plan_id, module_id=module.id, billing_term=subscription.billing_term, at=utcnow())
    row.price_entry_id = str(payload.get("price_entry_id") or (price.id if price else row.price_entry_id or "")) or None; row.status = str(payload.get("status") or row.status or "ACTIVE").strip().upper(); row.quantity = max(1, int(payload.get("quantity", row.quantity or subscription.quantity)))
    row.unit_amount_cents = int(payload.get("unit_amount_cents", price.unit_amount_cents if price else row.unit_amount_cents or 0)); row.limits_json = dict(payload.get("limits", row.limits_json or module.default_limits_json or {}))
    if payload.get("effective_to"):
        value = payload["effective_to"]; row.effective_to = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    db.flush(); db.add(SubscriptionEvent(subscription_id=subscription.id, event_type="ITEM_UPSERTED", actor_user_id=actor_user_id, reason=str(payload.get("reason") or "Subscription item updated"), before_json={}, after_json={"module_code": module.code, "status": row.status, "quantity": row.quantity}))
    audit(db, actor_user_id=actor_user_id, action="commercial.subscription.item_upserted", tenant_id=subscription.tenant_id, entity_type="subscription_item", entity_id=row.id, reason=payload.get("reason"), details={"module_code": module.code, "status": row.status})
    reconcile_subscription(db, row=subscription, actor_user_id=actor_user_id, reason="Subscription item updated", commit=False); db.commit(); db.refresh(subscription)
    return subscription_payload(db, subscription, include_events=True)


def create_override(db: Session, *, tenant_id: str, payload: dict[str, Any], actor_user_id: str) -> dict[str, Any]:
    tenant = db.get(account_models.AMO, tenant_id); module = db.get(CommercialModule, str(payload.get("module_id") or ""))
    if not tenant or not module:
        raise ValueError("Tenant or module not found")
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise ValueError("A reason is required")
    access_state = str(payload.get("access_state") or "ENABLED").strip().upper()
    if access_state not in VALID_MODULE_ACCESS:
        raise ValueError("Unsupported access state")
    expires_at = payload.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    if not expires_at:
        expires_at = utcnow() + timedelta(days=max(1, min(int(payload.get("expires_in_days") or 7), 90)))
    if expires_at <= utcnow():
        raise ValueError("Override expiry must be in the future")
    overlapping = db.query(EntitlementOverride).filter(EntitlementOverride.tenant_id == tenant_id, EntitlementOverride.module_id == module.id, EntitlementOverride.status == "ACTIVE", EntitlementOverride.expires_at > utcnow()).first()
    if overlapping:
        overlapping.status = "SUPERSEDED"
    row = EntitlementOverride(tenant_id=tenant_id, module_id=module.id, access_state=access_state, limits_json=dict(payload.get("limits") or {}), reason=reason, expires_at=expires_at, approved_by=actor_user_id, created_by=actor_user_id)
    db.add(row); db.flush(); audit(db, actor_user_id=actor_user_id, action="commercial.entitlement.override_created", tenant_id=tenant_id, entity_type="entitlement_override", entity_id=row.id, reason=reason, details={"module_code": module.code, "access_state": access_state, "expires_at": expires_at.isoformat()}); db.commit(); db.refresh(row)
    return {"id": row.id, "tenant_id": row.tenant_id, "module_id": row.module_id, "module_code": module.code, "module_name": module.name, "status": row.status, "access_state": row.access_state, "limits": row.limits_json or {}, "reason": row.reason, "starts_at": row.starts_at, "expires_at": row.expires_at, "approved_by": row.approved_by}


def resolved_entitlements(db: Session, *, tenant_id: str) -> list[dict[str, Any]]:
    now = utcnow(); subscription = db.query(TenantSubscription).filter(TenantSubscription.tenant_id == tenant_id, TenantSubscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES | {"PAUSED"})).order_by(TenantSubscription.updated_at.desc()).first(); resolved: dict[str, dict[str, Any]] = {}
    if subscription:
        plan = db.get(ProductPlan, subscription.plan_id)
        for item, module in db.query(SubscriptionItem, CommercialModule).join(CommercialModule, CommercialModule.id == SubscriptionItem.module_id).filter(SubscriptionItem.subscription_id == subscription.id).all():
            state = "DISABLED" if subscription.status in {"PAUSED", "PAST_DUE"} or item.status != "ACTIVE" else ("TRIAL" if subscription.status == "TRIALING" else "ENABLED")
            resolved[module.code] = {"module_id": module.id, "module_code": module.code, "module_name": module.name, "access_state": state, "source": "SUBSCRIPTION", "subscription_id": subscription.id, "subscription_item_id": item.id, "plan_code": plan.code if plan else None, "limits": item.limits_json or {}, "effective_from": item.effective_from, "effective_to": item.effective_to}
    overrides = db.query(EntitlementOverride, CommercialModule).join(CommercialModule, CommercialModule.id == EntitlementOverride.module_id).filter(EntitlementOverride.tenant_id == tenant_id, EntitlementOverride.status == "ACTIVE", EntitlementOverride.starts_at <= now, EntitlementOverride.expires_at > now).all()
    for override, module in overrides:
        resolved[module.code] = {"module_id": module.id, "module_code": module.code, "module_name": module.name, "access_state": override.access_state, "source": "OVERRIDE", "override_id": override.id, "reason": override.reason, "limits": override.limits_json or {}, "effective_from": override.starts_at, "effective_to": override.expires_at}
    return sorted(resolved.values(), key=lambda item: str(item["module_name"]))


def legacy_status(status: str):
    return {"TRIALING": account_models.LicenseStatus.TRIALING, "ACTIVE": account_models.LicenseStatus.ACTIVE, "PAST_DUE": account_models.LicenseStatus.EXPIRED, "PAUSED": account_models.LicenseStatus.EXPIRED, "CANCELLED": account_models.LicenseStatus.CANCELLED, "EXPIRED": account_models.LicenseStatus.EXPIRED, "DRAFT": account_models.LicenseStatus.TRIALING}.get(status, account_models.LicenseStatus.EXPIRED)


def legacy_term(term: str):
    if term == "ANNUAL": return account_models.BillingTerm.ANNUAL
    if term == "BI_ANNUAL": return account_models.BillingTerm.BI_ANNUAL
    return account_models.BillingTerm.MONTHLY


def reconcile_subscription(db: Session, *, row: TenantSubscription, actor_user_id: str, reason: str, commit: bool = True) -> dict[str, Any]:
    plan = db.get(ProductPlan, row.plan_id)
    if not plan:
        raise ValueError("Subscription plan not found")
    plan_price = active_price_for(db, price_book_id=row.price_book_id, plan_id=plan.id, module_id=None, billing_term=row.billing_term, at=utcnow())
    item_total = sum(item.unit_amount_cents * max(1, item.quantity) for item in db.query(SubscriptionItem).filter(SubscriptionItem.subscription_id == row.id, SubscriptionItem.status == "ACTIVE").all()); amount = plan_price.unit_amount_cents if plan_price else item_total
    sku_code = f"CANONICAL_{plan.code}_{row.billing_term}_{row.currency}"[:64]; sku = db.query(account_models.CatalogSKU).filter(account_models.CatalogSKU.code == sku_code).first()
    if not sku:
        sku = account_models.CatalogSKU(code=sku_code, name=f"{plan.name} {row.billing_term.title()}", description=f"Projection of canonical plan {plan.code}", term=legacy_term(row.billing_term), trial_days=plan.trial_days, amount_cents=amount, currency=row.currency, is_active=True); db.add(sku); db.flush()
    else:
        sku.name = f"{plan.name} {row.billing_term.title()}"; sku.amount_cents = amount; sku.currency = row.currency; sku.trial_days = plan.trial_days; sku.term = legacy_term(row.billing_term); sku.is_active = plan.status == "ACTIVE"
    license_row = account_services.get_latest_subscription(db, amo_id=row.tenant_id)
    if not license_row:
        license_row = account_models.TenantLicense(amo_id=row.tenant_id, sku_id=sku.id, term=legacy_term(row.billing_term), status=legacy_status(row.status), current_period_start=row.current_period_start or utcnow(), current_period_end=row.current_period_end); db.add(license_row)
    license_row.sku_id = sku.id; license_row.term = legacy_term(row.billing_term); license_row.status = legacy_status(row.status); license_row.trial_started_at = row.current_period_start if row.status == "TRIALING" else license_row.trial_started_at; license_row.trial_ends_at = row.trial_ends_at
    license_row.current_period_start = row.current_period_start or license_row.current_period_start or utcnow(); license_row.current_period_end = row.current_period_end; license_row.canceled_at = row.cancelled_at; license_row.is_read_only = row.status in {"PAST_DUE", "PAUSED", "EXPIRED", "CANCELLED"}; db.flush()
    entitlements = resolved_entitlements(db, tenant_id=row.tenant_id)
    for item in entitlements:
        legacy = db.query(account_models.ModuleSubscription).filter(account_models.ModuleSubscription.amo_id == row.tenant_id, account_models.ModuleSubscription.module_code == item["module_code"]).first()
        if not legacy:
            legacy = account_models.ModuleSubscription(amo_id=row.tenant_id, module_code=item["module_code"]); db.add(legacy)
        legacy.status = account_models.ModuleSubscriptionStatus(item["access_state"]); legacy.plan_code = plan.code; legacy.effective_from = item.get("effective_from"); legacy.effective_to = item.get("effective_to"); legacy.metadata_json = json.dumps({"source": item.get("source"), "canonical_subscription_id": row.id, "limits": item.get("limits") or {}}, separators=(",", ":"))
    audit(db, actor_user_id=actor_user_id, action="commercial.subscription.reconciled", tenant_id=row.tenant_id, entity_type="tenant_subscription", entity_id=row.id, reason=reason, details={"legacy_sku": sku.code, "legacy_license_id": license_row.id, "entitlement_count": len(entitlements)})
    if commit: db.commit()
    return {"subscription_id": row.id, "legacy_sku": sku.code, "legacy_license_id": license_row.id, "entitlements": entitlements}


def update_tenant_profile(db: Session, *, tenant_id: str, payload: dict[str, Any], actor_user_id: str) -> dict[str, Any]:
    tenant = db.get(account_models.AMO, tenant_id)
    if not tenant: raise ValueError("Tenant not found")
    editable = {"name", "icao_code", "country", "contact_email", "contact_phone", "time_zone"}; before = {field: getattr(tenant, field) for field in editable}
    for field in editable:
        if field in payload: setattr(tenant, field, payload[field] if payload[field] not in {""} else None)
    if "is_active" in payload: tenant.is_active = bool(payload["is_active"])
    if "is_demo" in payload and bool(payload["is_demo"]) != bool(tenant.is_demo):
        current = db.query(TenantSubscription).filter(TenantSubscription.tenant_id == tenant_id, TenantSubscription.status.in_(ACTIVE_SUBSCRIPTION_STATUSES)).first()
        if current: raise ValueError("End or migrate the active subscription before changing tenant environment")
        tenant.is_demo = bool(payload["is_demo"])
    audit(db, actor_user_id=actor_user_id, action="commercial.tenant.profile_updated", tenant_id=tenant_id, entity_type="tenant", entity_id=tenant_id, reason=payload.get("reason"), details={"before": before, "after": {field: getattr(tenant, field) for field in editable}}); db.commit(); db.refresh(tenant)
    return tenant_control_plane(db, tenant_id=tenant_id)


def provision_tenant(db: Session, *, payload: dict[str, Any], actor_user_id: str) -> dict[str, Any]:
    required = ["name", "amo_code", "login_slug", "owner_email", "owner_first_name", "owner_last_name", "plan_id"]; missing = [field for field in required if not str(payload.get(field) or "").strip()]
    if missing: raise ValueError(f"Missing required fields: {', '.join(missing)}")
    mode = normalize_data_mode(str(payload.get("data_mode") or "REAL")); amo_code = str(payload["amo_code"]).strip().upper(); login_slug = str(payload["login_slug"]).strip().lower()
    if db.query(account_models.AMO).filter(or_(account_models.AMO.amo_code == amo_code, account_models.AMO.login_slug == login_slug)).first(): raise ValueError("AMO code or login slug already exists")
    plan = db.get(ProductPlan, str(payload["plan_id"]))
    if not plan or plan.status != "ACTIVE": raise ValueError("An active product plan is required")
    book = db.get(PriceBook, str(payload.get("price_book_id") or "")) if payload.get("price_book_id") else None
    if book and (book.data_mode != mode or book.status != "ACTIVE"): raise ValueError("Price book does not match the tenant environment")
    tenant = account_models.AMO(amo_code=amo_code, name=str(payload["name"]).strip(), icao_code=str(payload.get("icao_code") or "").strip().upper() or None, country=str(payload.get("country") or "").strip() or None, login_slug=login_slug, contact_email=str(payload["owner_email"]).strip().lower(), contact_phone=str(payload.get("contact_phone") or "").strip() or None, time_zone=str(payload.get("time_zone") or "Africa/Nairobi").strip(), is_demo=mode == "DEMO", is_active=True)
    db.add(tenant); db.flush()
    departments = payload.get("departments") or [{"code": "ADMIN", "name": "Administration", "default_route": f"/maintenance/{login_slug}/admin/overview", "sort_order": 10}, {"code": "QUALITY", "name": "Quality", "default_route": f"/maintenance/{login_slug}/quality", "sort_order": 20}, {"code": "ENGINEERING", "name": "Engineering", "default_route": f"/maintenance/{login_slug}/dashboard", "sort_order": 30}]
    department_by_code: dict[str, account_models.Department] = {}
    for definition in departments:
        code = str(definition.get("code") or "").strip().upper()
        if not code: continue
        department = account_models.Department(amo_id=tenant.id, code=code, name=str(definition.get("name") or code.title()), default_route=definition.get("default_route"), sort_order=int(definition.get("sort_order") or 100), is_active=True); db.add(department); department_by_code[code] = department
    db.flush(); temporary_password = secrets.token_urlsafe(24) + "A1"
    owner = account_models.User(amo_id=tenant.id, department_id=(department_by_code.get("ADMIN") or next(iter(department_by_code.values()), None)).id if department_by_code else None, staff_code=str(payload.get("owner_staff_code") or "AMO-OWNER").strip().upper(), email=str(payload["owner_email"]).strip().lower(), first_name=str(payload["owner_first_name"]).strip(), last_name=str(payload["owner_last_name"]).strip(), full_name=f"{str(payload['owner_first_name']).strip()} {str(payload['owner_last_name']).strip()}".strip(), role=account_models.AccountRole.AMO_ADMIN, position_title=str(payload.get("owner_position_title") or "AMO Administrator"), phone=str(payload.get("owner_phone") or "").strip() or None, hashed_password=get_password_hash(temporary_password), is_active=True, is_amo_admin=True, must_change_password=True)
    db.add(owner); db.flush(); state = str(payload.get("subscription_status") or ("TRIALING" if plan.trial_days else "ACTIVE")).strip().upper(); term = str(payload.get("billing_term") or plan.default_billing_term).strip().upper()
    subscription = TenantSubscription(tenant_id=tenant.id, plan_id=plan.id, price_book_id=book.id if book else None, status=state, billing_term=term, quantity=max(1, int(payload.get("quantity") or 1)), currency=book.currency if book else str(payload.get("currency") or "USD").upper(), current_period_start=utcnow(), trial_ends_at=utcnow() + timedelta(days=plan.trial_days) if state == "TRIALING" and plan.trial_days else None, created_by=actor_user_id, updated_by=actor_user_id)
    subscription.current_period_end = period_end(subscription.current_period_start, subscription.billing_term); db.add(subscription); db.flush()
    for link in plan_module_links(db, plan.id):
        price = active_price_for(db, price_book_id=subscription.price_book_id, plan_id=plan.id, module_id=link.module_id, billing_term=subscription.billing_term, at=utcnow()); module = db.get(CommercialModule, link.module_id)
        db.add(SubscriptionItem(subscription_id=subscription.id, module_id=link.module_id, price_entry_id=price.id if price else None, status="ACTIVE", quantity=subscription.quantity, unit_amount_cents=price.unit_amount_cents if price else 0, limits_json={**(module.default_limits_json or {}), **(link.limits_json or {})} if module else (link.limits_json or {}), effective_from=utcnow()))
    db.flush(); db.add(SubscriptionEvent(subscription_id=subscription.id, event_type="PROVISIONED", actor_user_id=actor_user_id, reason=str(payload.get("reason") or "Tenant provisioned"), before_json={}, after_json=subscription_snapshot(subscription)))
    audit(db, actor_user_id=actor_user_id, action="commercial.tenant.provisioned", tenant_id=tenant.id, entity_type="tenant", entity_id=tenant.id, reason=payload.get("reason"), details={"owner_user_id": owner.id, "plan_code": plan.code, "data_mode": mode})
    reconcile_subscription(db, row=subscription, actor_user_id=actor_user_id, reason="Tenant provisioning projection", commit=False); db.commit(); db.refresh(tenant); db.refresh(owner); db.refresh(subscription)
    reset_token = account_services.create_password_reset_token(db, owner)
    return {"tenant": {"id": tenant.id, "amo_code": tenant.amo_code, "name": tenant.name, "login_slug": tenant.login_slug, "data_mode": mode}, "owner": {"id": owner.id, "email": owner.email, "full_name": owner.full_name, "must_change_password": owner.must_change_password}, "subscription": subscription_payload(db, subscription), "owner_password_setup_token": reset_token, "warning": "The password setup token is returned once. Deliver it through an approved secure channel."}


def tenant_control_plane(db: Session, *, tenant_id: str) -> dict[str, Any]:
    tenant = db.get(account_models.AMO, tenant_id)
    if not tenant: raise ValueError("Tenant not found")
    subscription = db.query(TenantSubscription).filter(TenantSubscription.tenant_id == tenant_id).order_by(TenantSubscription.updated_at.desc()).first(); users = db.query(account_models.User).filter(account_models.User.amo_id == tenant_id).order_by(account_models.User.full_name).all(); invoices = db.query(account_models.BillingInvoice).filter(account_models.BillingInvoice.amo_id == tenant_id).order_by(account_models.BillingInvoice.created_at.desc()).limit(50).all(); payments = db.query(PaymentTransaction).filter(PaymentTransaction.tenant_id == tenant_id).order_by(PaymentTransaction.recorded_at.desc()).limit(50).all(); usage = db.query(account_models.UsageMeter).filter(account_models.UsageMeter.amo_id == tenant_id).order_by(account_models.UsageMeter.meter_key).all(); support = db.query(platform_models.PlatformSupportTicket).filter(platform_models.PlatformSupportTicket.tenant_id == tenant_id).order_by(platform_models.PlatformSupportTicket.updated_at.desc()).limit(25).all(); audit_rows = db.query(platform_models.PlatformAuditLog).filter(platform_models.PlatformAuditLog.tenant_id == tenant_id).order_by(platform_models.PlatformAuditLog.created_at.desc()).limit(50).all()
    return {"tenant": {"id": tenant.id, "amo_code": tenant.amo_code, "name": tenant.name, "icao_code": tenant.icao_code, "country": tenant.country, "login_slug": tenant.login_slug, "contact_email": tenant.contact_email, "contact_phone": tenant.contact_phone, "time_zone": tenant.time_zone, "is_demo": tenant.is_demo, "data_mode": "DEMO" if tenant.is_demo else "REAL", "is_active": tenant.is_active, "created_at": tenant.created_at, "updated_at": tenant.updated_at}, "subscription": subscription_payload(db, subscription, include_events=True) if subscription else None, "entitlements": resolved_entitlements(db, tenant_id=tenant_id), "users": [{"id": user.id, "email": user.email, "full_name": user.full_name, "role": enum_value(user.role), "is_active": user.is_active, "is_amo_admin": user.is_amo_admin, "must_change_password": user.must_change_password, "last_login_at": user.last_login_at} for user in users], "usage": [{"id": meter.id, "meter_key": meter.meter_key, "used_units": meter.used_units, "last_recorded_at": meter.last_recorded_at} for meter in usage], "invoices": [invoice_payload(db, invoice) for invoice in invoices], "payments": [payment_payload(payment) for payment in payments], "support": [{"id": ticket.id, "title": ticket.title, "status": ticket.status, "priority": ticket.priority, "updated_at": ticket.updated_at} for ticket in support], "audit": [{"id": event.id, "action": event.action, "reason": event.reason, "details": event.details_json or {}, "actor_user_id": event.actor_user_id, "created_at": event.created_at} for event in audit_rows]}


def invoice_payload(db: Session, row: account_models.BillingInvoice) -> dict[str, Any]:
    tenant = db.get(account_models.AMO, row.amo_id); lines = db.query(InvoiceLineItem).filter(InvoiceLineItem.invoice_id == row.id).order_by(InvoiceLineItem.sort_order).all(); payments = db.query(PaymentTransaction).filter(PaymentTransaction.invoice_id == row.id, PaymentTransaction.status == "SUCCEEDED").all(); paid_cents = sum(int(payment.amount_cents or 0) for payment in payments)
    return {"id": row.id, "invoice_number": account_services.format_invoice_number(row), "tenant_id": row.amo_id, "tenant_name": tenant.name if tenant else None, "tenant_code": tenant.amo_code if tenant else None, "amount_cents": row.amount_cents, "paid_cents": paid_cents, "balance_cents": max(0, int(row.amount_cents or 0) - paid_cents), "currency": row.currency, "status": enum_value(row.status), "description": row.description, "issued_at": row.issued_at, "due_at": row.due_at, "paid_at": row.paid_at, "created_at": row.created_at, "lines": [{"id": line.id, "module_id": line.module_id, "description": line.description, "quantity": line.quantity, "unit_amount_cents": line.unit_amount_cents, "subtotal_cents": line.subtotal_cents, "tax_rate_bps": line.tax_rate_bps, "tax_amount_cents": line.tax_amount_cents, "total_cents": line.total_cents} for line in lines]}


def list_invoices(db: Session, *, data_mode: str, status: str | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    mode = normalize_data_mode(data_mode); query = db.query(account_models.BillingInvoice).join(account_models.AMO, account_models.AMO.id == account_models.BillingInvoice.amo_id).filter(account_models.AMO.is_demo.is_(mode == "DEMO"))
    if status: query = query.filter(account_models.BillingInvoice.status == account_models.InvoiceStatus(status.strip().upper()))
    total = query.count(); rows = query.order_by(account_models.BillingInvoice.created_at.desc()).offset(offset).limit(min(max(limit, 1), 200)).all()
    return {"items": [invoice_payload(db, row) for row in rows], "total": total, "limit": limit, "offset": offset, "data_mode": mode}


def create_invoice(db: Session, *, tenant_id: str, payload: dict[str, Any], actor_user_id: str) -> dict[str, Any]:
    tenant = db.get(account_models.AMO, tenant_id)
    if not tenant: raise ValueError("Tenant not found")
    lines = payload.get("lines") or []
    if not isinstance(lines, list) or not lines: raise ValueError("At least one invoice line is required")
    idempotency_key = str(payload.get("idempotency_key") or "").strip()
    if not idempotency_key: raise ValueError("idempotency_key is required")
    existing = db.query(account_models.BillingInvoice).filter(account_models.BillingInvoice.amo_id == tenant_id, account_models.BillingInvoice.idempotency_key == idempotency_key).first()
    if existing: return invoice_payload(db, existing)
    currency = str(payload.get("currency") or "USD").strip().upper(); calculated: list[dict[str, Any]] = []; total = 0
    for index, raw in enumerate(lines):
        quantity = max(1, int(raw.get("quantity") or 1)); unit = int(raw.get("unit_amount_cents") or 0)
        if unit < 0: raise ValueError("Invoice line amount cannot be negative")
        tax_rate = max(0, min(int(raw.get("tax_rate_bps") or 0), 10000)); subtotal = quantity * unit; tax = round(subtotal * tax_rate / 10000); line_total = subtotal + tax; total += line_total
        calculated.append({**raw, "quantity": quantity, "unit_amount_cents": unit, "tax_rate_bps": tax_rate, "subtotal_cents": subtotal, "tax_amount_cents": tax, "total_cents": line_total, "sort_order": int(raw.get("sort_order") or (index + 1) * 10)})
    ledger = account_models.LedgerEntry(amo_id=tenant_id, amount_cents=total, currency=currency, entry_type=account_models.LedgerEntryType.CHARGE, description=str(payload.get("description") or "Platform invoice"), idempotency_key=idempotency_key, recorded_at=utcnow()); db.add(ledger); db.flush()
    due_days = max(0, min(int(payload.get("due_days") or 14), 365)); invoice = account_models.BillingInvoice(amo_id=tenant_id, ledger_entry_id=ledger.id, amount_cents=total, currency=currency, status=account_models.InvoiceStatus.PENDING, description=str(payload.get("description") or "Platform invoice"), idempotency_key=idempotency_key, issued_at=utcnow(), due_at=utcnow() + timedelta(days=due_days)); db.add(invoice); db.flush()
    for line in calculated:
        module_id_value = str(line.get("module_id") or "") or None
        if module_id_value and not db.get(CommercialModule, module_id_value): raise ValueError("Invoice line references an unknown module")
        db.add(InvoiceLineItem(invoice_id=invoice.id, module_id=module_id_value, subscription_item_id=str(line.get("subscription_item_id") or "") or None, description=str(line.get("description") or "Commercial service"), quantity=line["quantity"], unit_amount_cents=line["unit_amount_cents"], subtotal_cents=line["subtotal_cents"], tax_rate_bps=line["tax_rate_bps"], tax_amount_cents=line["tax_amount_cents"], total_cents=line["total_cents"], sort_order=line["sort_order"], metadata_json=dict(line.get("metadata") or {})))
    audit(db, actor_user_id=actor_user_id, action="commercial.invoice.created", tenant_id=tenant_id, entity_type="billing_invoice", entity_id=invoice.id, reason=payload.get("reason"), details={"amount_cents": total, "currency": currency, "line_count": len(calculated)}); db.commit(); db.refresh(invoice)
    return invoice_payload(db, invoice)


def payment_payload(row: PaymentTransaction) -> dict[str, Any]:
    return {"id": row.id, "tenant_id": row.tenant_id, "invoice_id": row.invoice_id, "provider": row.provider, "external_reference": row.external_reference, "status": row.status, "amount_cents": row.amount_cents, "currency": row.currency, "payment_method": row.payment_method, "notes": row.notes, "recorded_by": row.recorded_by, "recorded_at": row.recorded_at}


def record_payment(db: Session, *, invoice_id: str, payload: dict[str, Any], actor_user_id: str) -> dict[str, Any]:
    invoice = db.get(account_models.BillingInvoice, invoice_id)
    if not invoice: raise ValueError("Invoice not found")
    amount = int(payload.get("amount_cents") or 0)
    if amount <= 0: raise ValueError("Payment amount must be greater than zero")
    provider = str(payload.get("provider") or "MANUAL").strip().upper(); external_reference = str(payload.get("external_reference") or "").strip() or None
    if provider != "MANUAL" and not external_reference: raise ValueError("External reference is required for provider payments")
    payment = PaymentTransaction(tenant_id=invoice.amo_id, invoice_id=invoice.id, provider=provider, external_reference=external_reference, status="SUCCEEDED", amount_cents=amount, currency=invoice.currency, payment_method=str(payload.get("payment_method") or "").strip() or None, notes=str(payload.get("notes") or "").strip() or None, metadata_json=dict(payload.get("metadata") or {}), recorded_by=actor_user_id); db.add(payment); db.flush()
    total_paid = sum(int(row.amount_cents or 0) for row in db.query(PaymentTransaction).filter(PaymentTransaction.invoice_id == invoice.id, PaymentTransaction.status == "SUCCEEDED").all())
    if total_paid >= int(invoice.amount_cents or 0): invoice.status = account_models.InvoiceStatus.PAID; invoice.paid_at = utcnow()
    db.add(account_models.LedgerEntry(amo_id=invoice.amo_id, license_id=invoice.license_id, amount_cents=-amount, currency=invoice.currency, entry_type=account_models.LedgerEntryType.PAYMENT, description=f"Payment for invoice {account_services.format_invoice_number(invoice)}", idempotency_key=f"payment:{payment.id}", recorded_at=utcnow()))
    audit(db, actor_user_id=actor_user_id, action="commercial.payment.recorded", tenant_id=invoice.amo_id, entity_type="payment_transaction", entity_id=payment.id, reason=payload.get("reason"), details={"invoice_id": invoice.id, "amount_cents": amount, "provider": provider, "external_reference": external_reference}); db.commit(); db.refresh(payment); db.refresh(invoice)
    return {"payment": payment_payload(payment), "invoice": invoice_payload(db, invoice)}


def force_password_reset(db: Session, *, user_id: str, actor_user_id: str, reason: str) -> dict[str, Any]:
    user = db.get(account_models.User, user_id)
    if not user: raise ValueError("User not found")
    if not reason.strip(): raise ValueError("A reason is required")
    user.must_change_password = True; user.token_revoked_at = utcnow(); user.password_changed_at = None
    audit(db, actor_user_id=actor_user_id, action="commercial.user.password_reset_forced", tenant_id=user.amo_id, entity_type="user", entity_id=user.id, reason=reason, details={"email": user.email}); db.commit(); db.refresh(user)
    return {"id": user.id, "email": user.email, "must_change_password": user.must_change_password, "token_revoked_at": user.token_revoked_at}


def commercial_summary(db: Session, *, data_mode: str) -> dict[str, Any]:
    mode = normalize_data_mode(data_mode); tenant_filter = account_models.AMO.is_demo.is_(mode == "DEMO"); subscription_rows = db.query(TenantSubscription).join(account_models.AMO, account_models.AMO.id == TenantSubscription.tenant_id).filter(tenant_filter).all(); subscriptions = {state: 0 for state in VALID_SUBSCRIPTION_STATUSES}; revenue_by_currency: dict[str, dict[str, int]] = {}; now = utcnow()
    for subscription in subscription_rows:
        subscriptions[subscription.status] = subscriptions.get(subscription.status, 0) + 1
        if subscription.status not in ACTIVE_SUBSCRIPTION_STATUSES: continue
        amount = sum(item.unit_amount_cents * max(1, item.quantity) for item in db.query(SubscriptionItem).filter(SubscriptionItem.subscription_id == subscription.id, SubscriptionItem.status == "ACTIVE").all()); monthly = amount if subscription.billing_term == "MONTHLY" else (round(amount / 6) if subscription.billing_term == "BI_ANNUAL" else round(amount / 12) if subscription.billing_term == "ANNUAL" else 0)
        bucket = revenue_by_currency.setdefault(subscription.currency, {"mrr_cents": 0, "arr_cents": 0, "at_risk_cents": 0, "trial_pipeline_cents": 0}); bucket["mrr_cents"] += monthly; bucket["arr_cents"] += monthly * 12
        if subscription.status == "PAST_DUE": bucket["at_risk_cents"] += monthly
        if subscription.status == "TRIALING": bucket["trial_pipeline_cents"] += monthly
    invoice_query = db.query(account_models.BillingInvoice).join(account_models.AMO, account_models.AMO.id == account_models.BillingInvoice.amo_id).filter(tenant_filter); overdue = invoice_query.filter(account_models.BillingInvoice.status == account_models.InvoiceStatus.PENDING, account_models.BillingInvoice.due_at.isnot(None), account_models.BillingInvoice.due_at < now).count(); outstanding_by_currency: dict[str, int] = {}
    for invoice in invoice_query.filter(account_models.BillingInvoice.status == account_models.InvoiceStatus.PENDING).all():
        paid = sum(int(row.amount_cents or 0) for row in db.query(PaymentTransaction).filter(PaymentTransaction.invoice_id == invoice.id, PaymentTransaction.status == "SUCCEEDED").all()); outstanding_by_currency[invoice.currency] = outstanding_by_currency.get(invoice.currency, 0) + max(0, int(invoice.amount_cents or 0) - paid)
    return {"data_mode": mode, "subscriptions": subscriptions, "revenue_by_currency": revenue_by_currency, "outstanding_by_currency": outstanding_by_currency, "overdue_invoices": overdue, "module_count": db.query(CommercialModule).filter(CommercialModule.status != "ARCHIVED").count(), "plan_count": db.query(ProductPlan).filter(ProductPlan.status != "ARCHIVED").count(), "active_price_books": db.query(PriceBook).filter(PriceBook.data_mode == mode, PriceBook.status == "ACTIVE").count(), "generated_at": now}
