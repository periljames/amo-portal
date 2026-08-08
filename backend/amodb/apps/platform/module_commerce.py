from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.user_id import generate_user_id

from . import models as platform_models
from . import saas_models, saas_services


MODULE_SCOPE = "COMMERCIAL_MODULE"
DEPENDENCY_SCOPE = "COMMERCIAL_MODULE_DEP"
BUNDLE_MEMBER_SCOPE = "COMMERCIAL_BUNDLE_MEMBER"
ALLOWED_KINDS = {"STANDALONE", "ADD_ON", "BUNDLE", "PLATFORM_INCLUDED", "CATALOG_ONLY"}

# These are commercial capability boundaries, not individual pages. Embedded
# capabilities are listed so the UI explains what the tenant actually receives.
FIRST_PARTY_MODULES: dict[str, dict[str, Any]] = {
    "quality": {
        "name": "Quality & Compliance",
        "description": "QMS audits, findings/CAR, assurance planning, quality evidence and governed quality workflows.",
        "kind": "STANDALONE",
        "hard_requires": [],
        "embedded_capabilities": ["audits", "corrective_actions", "quality_planner", "quality_tasks", "quality_notifications", "document_control_legacy"],
        "customer_selectable": True,
        "implemented": True,
    },
    "training": {
        "name": "Training & Competence",
        "description": "Training records, competence, currency, course planning and evidence.",
        "kind": "STANDALONE",
        "hard_requires": [],
        "embedded_capabilities": ["training_records", "competence", "currency", "training_planning"],
        "customer_selectable": True,
        "implemented": True,
    },
    "fleet": {
        "name": "Fleet & Aircraft",
        "description": "Aircraft, components, utilisation, aircraft documents and fleet master data.",
        "kind": "STANDALONE",
        "hard_requires": [],
        "embedded_capabilities": ["aircraft", "components", "utilisation", "aircraft_documents"],
        "customer_selectable": True,
        "implemented": True,
    },
    "work": {
        "name": "Maintenance Operations",
        "description": "Planning, production execution, work orders, technical records and maintenance release workflow.",
        "kind": "ADD_ON",
        "hard_requires": ["fleet"],
        "embedded_capabilities": ["planning", "production", "work_orders", "technical_records", "maintenance_program", "crs_workflow"],
        "customer_selectable": True,
        "implemented": True,
    },
    "reliability": {
        "name": "Reliability & EHM",
        "description": "Reliability programme, FRACAS, event/health monitoring and reliability reporting.",
        "kind": "ADD_ON",
        "hard_requires": ["fleet", "work"],
        "embedded_capabilities": ["reliability_programme", "fracas", "ehm", "reliability_reporting"],
        "customer_selectable": True,
        "implemented": True,
    },
    "finance": {
        "name": "Finance",
        "description": "Tenant operational finance, invoices, credit notes, vendors and finance controls.",
        "kind": "STANDALONE",
        "hard_requires": [],
        "embedded_capabilities": ["operational_finance", "vendors", "credit_notes"],
        "customer_selectable": True,
        "implemented": True,
    },
    "inventory": {
        "name": "Stores & Inventory",
        "description": "Parts, stores locations, receiving, stock ledger, quarantine and inventory traceability.",
        "kind": "STANDALONE",
        "hard_requires": [],
        "embedded_capabilities": ["stores", "parts", "receiving", "inventory_ledger", "quarantine"],
        "customer_selectable": True,
        "implemented": True,
    },
    "procurement": {
        "name": "Procurement",
        "description": "Requests, vendor purchasing, approvals, receiving and procurement documentation.",
        "kind": "ADD_ON",
        "hard_requires": ["finance", "inventory"],
        "embedded_capabilities": ["purchase_requests", "purchase_orders", "vendor_workflow", "procurement_receiving"],
        "customer_selectable": True,
        "implemented": True,
    },
    # Compatibility bundle for tenants licensed before finance/inventory/procurement
    # were separated. New buyers may still choose it as a suite.
    "finance_inventory": {
        "name": "Supply Chain & Finance Suite",
        "description": "Finance, stores/inventory and procurement as one commercial suite.",
        "kind": "BUNDLE",
        "hard_requires": [],
        "included_modules": ["finance", "inventory", "procurement"],
        "embedded_capabilities": [],
        "customer_selectable": True,
        "implemented": True,
        "legacy_compatibility": True,
    },
    "maintenance_suite": {
        "name": "Maintenance Operations Suite",
        "description": "Fleet, maintenance operations and reliability in one integrated package.",
        "kind": "BUNDLE",
        "hard_requires": [],
        "included_modules": ["fleet", "work", "reliability"],
        "embedded_capabilities": [],
        "customer_selectable": True,
        "implemented": True,
    },
    "quality_suite": {
        "name": "Quality & Competence Suite",
        "description": "Quality/compliance and training/competence in one governance package.",
        "kind": "BUNDLE",
        "hard_requires": [],
        "included_modules": ["quality", "training"],
        "embedded_capabilities": [],
        "customer_selectable": True,
        "implemented": True,
    },
    "rostering": {
        "name": "Rostering & Workforce Planning",
        "description": "Roster planning, manpower boards, training impact and workforce scheduling.",
        "kind": "PLATFORM_INCLUDED",
        "hard_requires": [],
        "embedded_capabilities": ["rostering", "manpower_planning"],
        "customer_selectable": False,
        "implemented": True,
        "commercial_note": "Implemented but not yet independently entitlement-gated; keep platform-included until that boundary is migrated safely.",
    },
}


def normalize_code(value: str) -> str:
    return saas_services.normalize_module_code(str(value or ""))


def _flag_key(code: str) -> str:
    return f"commercial.module.{normalize_code(code)}"


def _dependency_key(code: str, dependency: str) -> str:
    return f"commercial.module.{normalize_code(code)}.requires.{normalize_code(dependency)}"


def _member_key(bundle: str, member: str) -> str:
    return f"commercial.bundle.{normalize_code(bundle)}.includes.{normalize_code(member)}"


def _load_catalog_flags(db: Session) -> tuple[dict[str, platform_models.PlatformFeatureFlag], list[platform_models.PlatformFeatureFlag], list[platform_models.PlatformFeatureFlag]]:
    rows = (
        db.query(platform_models.PlatformFeatureFlag)
        .filter(platform_models.PlatformFeatureFlag.scope.in_([MODULE_SCOPE, DEPENDENCY_SCOPE, BUNDLE_MEMBER_SCOPE]))
        .all()
    )
    definitions: dict[str, platform_models.PlatformFeatureFlag] = {}
    dependencies: list[platform_models.PlatformFeatureFlag] = []
    members: list[platform_models.PlatformFeatureFlag] = []
    for row in rows:
        scope = str(row.scope or "").upper()
        if scope == MODULE_SCOPE:
            code = str(row.key or "").removeprefix("commercial.module.")
            if code:
                definitions[normalize_code(code)] = row
        elif scope == DEPENDENCY_SCOPE and row.enabled:
            dependencies.append(row)
        elif scope == BUNDLE_MEMBER_SCOPE and row.enabled:
            members.append(row)
    return definitions, dependencies, members


def _parse_dependency_flag(row: platform_models.PlatformFeatureFlag) -> tuple[str, str] | None:
    key = str(row.key or "")
    prefix = "commercial.module."
    marker = ".requires."
    if not key.startswith(prefix) or marker not in key:
        return None
    left, right = key[len(prefix):].split(marker, 1)
    if not left or not right:
        return None
    return normalize_code(left), normalize_code(right)


def _parse_member_flag(row: platform_models.PlatformFeatureFlag) -> tuple[str, str] | None:
    key = str(row.key or "")
    prefix = "commercial.bundle."
    marker = ".includes."
    if not key.startswith(prefix) or marker not in key:
        return None
    left, right = key[len(prefix):].split(marker, 1)
    if not left or not right:
        return None
    return normalize_code(left), normalize_code(right)


def list_module_catalog(db: Session, *, include_inactive: bool = True) -> list[dict[str, Any]]:
    definition_flags, dependency_flags, member_flags = _load_catalog_flags(db)
    dependency_overrides: dict[str, set[str]] = {}
    member_overrides: dict[str, set[str]] = {}
    for row in dependency_flags:
        parsed = _parse_dependency_flag(row)
        if parsed:
            dependency_overrides.setdefault(parsed[0], set()).add(parsed[1])
    for row in member_flags:
        parsed = _parse_member_flag(row)
        if parsed:
            member_overrides.setdefault(parsed[0], set()).add(parsed[1])

    price_codes = {
        normalize_code(code)
        for (code,) in db.query(saas_models.SaaSModulePrice.module_code).distinct().all()
        if code
    }
    subscription_codes = {
        normalize_code(code)
        for (code,) in db.query(account_models.ModuleSubscription.module_code).distinct().all()
        if code
    }
    codes = set(FIRST_PARTY_MODULES) | set(definition_flags) | price_codes | subscription_codes
    result: list[dict[str, Any]] = []

    for code in sorted(codes):
        base = dict(FIRST_PARTY_MODULES.get(code) or {})
        flag = definition_flags.get(code)
        if flag:
            kind = str(flag.plan_code or base.get("kind") or "CATALOG_ONLY").upper()
            if kind not in ALLOWED_KINDS:
                kind = "CATALOG_ONLY"
            base.update(
                {
                    "name": flag.name or base.get("name") or code.replace("_", " ").title(),
                    "description": flag.description or base.get("description"),
                    "kind": kind,
                    "customer_selectable": bool(flag.enabled),
                    "catalog_record_id": flag.id,
                }
            )
        else:
            base.setdefault("name", code.replace("_", " ").title())
            base.setdefault("description", "Custom commercial capability.")
            base.setdefault("kind", "CATALOG_ONLY" if code not in FIRST_PARTY_MODULES else "STANDALONE")
            base.setdefault("customer_selectable", bool(base.get("customer_selectable", False)))

        hard = set(base.get("hard_requires") or [])
        hard.update(dependency_overrides.get(code, set()))
        included = set(base.get("included_modules") or [])
        if code in member_overrides:
            included = set(member_overrides[code])
        implemented = bool(base.get("implemented", code in FIRST_PARTY_MODULES))
        if code not in FIRST_PARTY_MODULES:
            implemented = False
            base["kind"] = "CATALOG_ONLY"
            base["customer_selectable"] = False
        row = {
            "code": code,
            "name": base.get("name"),
            "description": base.get("description"),
            "kind": str(base.get("kind") or "CATALOG_ONLY").upper(),
            "implemented": implemented,
            "customer_selectable": bool(base.get("customer_selectable", False) and implemented),
            "hard_requires": sorted(normalize_code(value) for value in hard if value),
            "included_modules": sorted(normalize_code(value) for value in included if value),
            "embedded_capabilities": list(base.get("embedded_capabilities") or []),
            "legacy_compatibility": bool(base.get("legacy_compatibility", False)),
            "commercial_note": base.get("commercial_note"),
            "has_price": code in price_codes,
            "catalog_record_id": base.get("catalog_record_id"),
        }
        if include_inactive or row["customer_selectable"] or row["has_price"]:
            result.append(row)
    return result


def catalog_by_code(db: Session) -> dict[str, dict[str, Any]]:
    return {row["code"]: row for row in list_module_catalog(db, include_inactive=True)}


def upsert_module_definition(
    db: Session,
    *,
    payload: dict[str, Any],
    actor_user_id: str,
) -> dict[str, Any]:
    code = normalize_code(str(payload.get("code") or ""))
    if not code:
        raise ValueError("Module code is required")
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("Module name is required")
    kind = str(payload.get("kind") or "STANDALONE").strip().upper()
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"Unsupported module kind: {kind}")

    first_party = FIRST_PARTY_MODULES.get(code)
    requested_selectable = bool(payload.get("customer_selectable", True))
    if first_party is None:
        kind = "CATALOG_ONLY"
        requested_selectable = False

    row = (
        db.query(platform_models.PlatformFeatureFlag)
        .filter(
            platform_models.PlatformFeatureFlag.scope == MODULE_SCOPE,
            platform_models.PlatformFeatureFlag.key == _flag_key(code),
            platform_models.PlatformFeatureFlag.tenant_id.is_(None),
        )
        .first()
    )
    if row is None:
        row = platform_models.PlatformFeatureFlag(
            key=_flag_key(code),
            scope=MODULE_SCOPE,
            tenant_id=None,
            plan_code=kind,
            name=name,
            created_by=actor_user_id,
        )
        db.add(row)
    row.name = name
    row.description = str(payload.get("description") or "").strip() or None
    row.plan_code = kind
    row.enabled = requested_selectable
    row.updated_by = actor_user_id
    db.flush()

    requested_dependencies = {normalize_code(v) for v in (payload.get("hard_requires") or []) if str(v).strip()}
    minimum_dependencies = {normalize_code(v) for v in ((first_party or {}).get("hard_requires") or [])}
    requested_dependencies |= minimum_dependencies

    requested_members = {normalize_code(v) for v in (payload.get("included_modules") or []) if str(v).strip()}
    if kind != "BUNDLE" and requested_members:
        raise ValueError("Only a BUNDLE may include other modules")
    if first_party and first_party.get("kind") == "BUNDLE" and not requested_members:
        requested_members = {normalize_code(v) for v in first_party.get("included_modules") or []}

    prefix_dep = f"commercial.module.{code}.requires."
    prefix_member = f"commercial.bundle.{code}.includes."
    existing_rules = (
        db.query(platform_models.PlatformFeatureFlag)
        .filter(
            platform_models.PlatformFeatureFlag.scope.in_([DEPENDENCY_SCOPE, BUNDLE_MEMBER_SCOPE]),
            platform_models.PlatformFeatureFlag.tenant_id.is_(None),
        )
        .all()
    )
    for rule in existing_rules:
        key = str(rule.key or "")
        if key.startswith(prefix_dep) or key.startswith(prefix_member):
            rule.enabled = False
            rule.updated_by = actor_user_id

    for dependency in sorted(requested_dependencies):
        dep_key = _dependency_key(code, dependency)
        dep = (
            db.query(platform_models.PlatformFeatureFlag)
            .filter(platform_models.PlatformFeatureFlag.scope == DEPENDENCY_SCOPE, platform_models.PlatformFeatureFlag.key == dep_key)
            .first()
        )
        if dep is None:
            dep = platform_models.PlatformFeatureFlag(
                key=dep_key,
                name=f"{code} requires {dependency}",
                description="Commercial dependency rule",
                scope=DEPENDENCY_SCOPE,
                enabled=True,
                created_by=actor_user_id,
            )
            db.add(dep)
        dep.enabled = True
        dep.updated_by = actor_user_id

    for member in sorted(requested_members):
        member_key = _member_key(code, member)
        member_row = (
            db.query(platform_models.PlatformFeatureFlag)
            .filter(platform_models.PlatformFeatureFlag.scope == BUNDLE_MEMBER_SCOPE, platform_models.PlatformFeatureFlag.key == member_key)
            .first()
        )
        if member_row is None:
            member_row = platform_models.PlatformFeatureFlag(
                key=member_key,
                name=f"{code} includes {member}",
                description="Commercial bundle membership",
                scope=BUNDLE_MEMBER_SCOPE,
                enabled=True,
                created_by=actor_user_id,
            )
            db.add(member_row)
        member_row.enabled = True
        member_row.updated_by = actor_user_id

    db.add(
        platform_models.PlatformAuditLog(
            actor_user_id=actor_user_id,
            tenant_id=None,
            action="saas.module_catalog.upserted",
            module="billing",
            entity_type="commercial_module",
            entity_id=code,
            reason=str(payload.get("reason") or "Module catalog administration")[:1000],
            details_json={
                "code": code,
                "name": name,
                "kind": kind,
                "customer_selectable": requested_selectable,
                "hard_requires": sorted(requested_dependencies),
                "included_modules": sorted(requested_members),
                "implemented": first_party is not None,
            },
        )
    )
    db.commit()
    return catalog_by_code(db)[code]


def expand_activation_codes(catalog: dict[str, dict[str, Any]], module_code: str) -> list[str]:
    code = normalize_code(module_code)
    module = catalog.get(code)
    if module is None:
        return [code]
    if module.get("kind") != "BUNDLE":
        return [code]
    result: list[str] = []
    visiting: set[str] = set()

    def visit(value: str) -> None:
        normalized = normalize_code(value)
        if normalized in visiting:
            raise ValueError("Bundle membership contains a cycle")
        definition = catalog.get(normalized)
        if definition and definition.get("kind") == "BUNDLE":
            visiting.add(normalized)
            for member in definition.get("included_modules") or []:
                visit(str(member))
            visiting.remove(normalized)
        elif normalized not in result:
            result.append(normalized)

    visit(code)
    return result


def active_module_codes(db: Session, *, tenant_id: str) -> set[str]:
    now = datetime.now(timezone.utc)
    rows = (
        db.query(account_models.ModuleSubscription)
        .filter(
            account_models.ModuleSubscription.amo_id == tenant_id,
            account_models.ModuleSubscription.status.in_([
                account_models.ModuleSubscriptionStatus.ENABLED,
                account_models.ModuleSubscriptionStatus.TRIAL,
            ]),
        )
        .all()
    )
    result: set[str] = set()
    for row in rows:
        start = row.effective_from
        end = row.effective_to
        if start and start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end and end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        if start and start > now:
            continue
        if end and end < now:
            continue
        result.add(normalize_code(row.module_code))
        if row.module_code == "finance_inventory":
            result.update({"finance", "inventory", "procurement"})
    return result


def validate_dependencies(db: Session, *, tenant_id: str, module_code: str) -> list[str]:
    catalog = catalog_by_code(db)
    definition = catalog.get(normalize_code(module_code))
    if definition is None:
        raise ValueError("Unknown module")
    active = active_module_codes(db, tenant_id=tenant_id)
    if definition.get("kind") == "BUNDLE":
        purchased = set(expand_activation_codes(catalog, module_code))
        active |= purchased
        missing: set[str] = set()
        for included in purchased:
            included_def = catalog.get(included) or {}
            for dependency in included_def.get("hard_requires") or []:
                if dependency not in active:
                    missing.add(str(dependency))
        return sorted(missing)
    return sorted(str(dep) for dep in definition.get("hard_requires") or [] if str(dep) not in active)


def _decode_metadata(row: account_models.ModuleSubscription | None) -> dict[str, Any]:
    if row is None or not row.metadata_json:
        return {}
    try:
        parsed = json.loads(row.metadata_json)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_offer_expiry(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("valid_until must be an ISO-8601 timestamp") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _offer_is_current(terms: dict[str, Any], *, now: datetime | None = None) -> bool:
    if not bool(terms.get("customer_selectable", True)):
        return False
    expiry = _parse_offer_expiry(terms.get("valid_until"))
    return expiry is None or expiry >= (now or datetime.now(timezone.utc))


def tenant_offer_overrides(db: Session, *, tenant_id: str) -> dict[str, dict[str, Any]]:
    rows = db.query(account_models.ModuleSubscription).filter(account_models.ModuleSubscription.amo_id == tenant_id).all()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        metadata = _decode_metadata(row)
        terms = metadata.get("commercial_terms")
        if isinstance(terms, dict):
            result[normalize_code(row.module_code)] = dict(terms)
    return result


def set_tenant_offer(
    db: Session,
    *,
    tenant_id: str,
    module_code: str,
    payload: dict[str, Any],
    actor_user_id: str,
) -> dict[str, Any]:
    code = normalize_code(module_code)
    if code not in catalog_by_code(db):
        raise ValueError("Unknown module")
    price_id = str(payload.get("base_price_id") or "").strip()
    price = db.get(saas_models.SaaSModulePrice, price_id) if price_id else None
    if price_id and (price is None or normalize_code(price.module_code) != code):
        raise ValueError("Base price does not belong to this module")
    amount = payload.get("amount_cents")
    if amount is not None and int(amount) < 0:
        raise ValueError("amount_cents cannot be negative")
    currency = str(payload.get("currency") or (price.currency if price else "USD")).strip().upper()
    if len(currency) < 3 or len(currency) > 8:
        raise ValueError("Invalid currency")
    term = str(payload.get("billing_term") or (price.billing_term if price else "MONTHLY")).strip().upper()
    if term not in {"MONTHLY", "BI_ANNUAL", "ANNUAL"}:
        raise ValueError("Unsupported billing term")
    tax_rate_bps = int(payload.get("tax_rate_bps") if payload.get("tax_rate_bps") is not None else (price.tax_rate_bps if price else 0))
    if tax_rate_bps < 0 or tax_rate_bps > 10000:
        raise ValueError("tax_rate_bps must be between 0 and 10000")
    trial_days = int(payload.get("trial_days") if payload.get("trial_days") is not None else (price.trial_days if price else 0))
    if trial_days < 0 or trial_days > 365:
        raise ValueError("trial_days must be between 0 and 365")
    valid_until = payload.get("valid_until")
    expiry = _parse_offer_expiry(valid_until)
    if expiry is not None and expiry <= datetime.now(timezone.utc):
        raise ValueError("valid_until must be in the future when creating or updating an offer")

    row = (
        db.query(account_models.ModuleSubscription)
        .filter(account_models.ModuleSubscription.amo_id == tenant_id, account_models.ModuleSubscription.module_code == code)
        .first()
    )
    if row is None:
        row = account_models.ModuleSubscription(
            amo_id=tenant_id,
            module_code=code,
            status=account_models.ModuleSubscriptionStatus.DISABLED,
        )
        db.add(row)
    metadata = _decode_metadata(row)
    terms = {
        "base_price_id": price.id if price else None,
        "amount_cents": int(amount if amount is not None else (price.amount_cents if price else 0)),
        "currency": currency,
        "billing_term": term,
        "tax_rate_bps": tax_rate_bps,
        "trial_days": trial_days,
        "customer_selectable": bool(payload.get("customer_selectable", True)),
        "valid_until": expiry.isoformat() if expiry is not None else None,
        "reason": str(payload.get("reason") or "Tenant commercial terms")[:1000],
        "updated_by": actor_user_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    metadata["commercial_terms"] = terms
    row.metadata_json = json.dumps(metadata, separators=(",", ":"))
    db.add(
        platform_models.PlatformAuditLog(
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            action="saas.tenant_module_offer.updated",
            module="billing",
            entity_type="module_subscription",
            entity_id=code,
            reason=terms["reason"],
            details_json={key: value for key, value in terms.items() if key not in {"reason"}},
        )
    )
    db.commit()
    return {"module_code": code, "commercial_terms": terms, "subscription_status": getattr(row.status, "value", str(row.status))}


def _price_payload(price: saas_models.SaaSModulePrice) -> dict[str, Any]:
    return {
        "id": price.id,
        "module_code": normalize_code(price.module_code),
        "plan_code": str(price.plan_code or "STANDARD").upper(),
        "billing_term": str(price.billing_term or "MONTHLY").upper(),
        "amount_cents": int(price.amount_cents or 0),
        "currency": str(price.currency or "USD").upper(),
        "trial_days": int(price.trial_days or 0),
        "tax_rate_bps": int(price.tax_rate_bps or 0),
        "is_active": bool(price.is_active),
    }


def self_service_catalog(db: Session, *, tenant_id: str) -> dict[str, Any]:
    catalog = list_module_catalog(db, include_inactive=False)
    definitions = {row["code"]: row for row in catalog}
    prices = (
        db.query(saas_models.SaaSModulePrice)
        .filter(saas_models.SaaSModulePrice.is_active.is_(True))
        .order_by(saas_models.SaaSModulePrice.module_code.asc(), saas_models.SaaSModulePrice.amount_cents.asc())
        .all()
    )
    price_by_module: dict[str, list[dict[str, Any]]] = {}
    for row in prices:
        code = normalize_code(row.module_code)
        if code in definitions:
            price_by_module.setdefault(code, []).append(_price_payload(row))
    overrides = tenant_offer_overrides(db, tenant_id=tenant_id)
    active = active_module_codes(db, tenant_id=tenant_id)
    subscriptions = {
        normalize_code(row.module_code): row
        for row in db.query(account_models.ModuleSubscription).filter(account_models.ModuleSubscription.amo_id == tenant_id).all()
    }
    items: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for code, definition in definitions.items():
        if not definition.get("customer_selectable"):
            continue
        module_prices = list(price_by_module.get(code) or [])
        override = overrides.get(code)
        if override is not None:
            if not _offer_is_current(override, now=now):
                # A tenant-specific commercial record is authoritative. Hidden or
                # expired negotiated terms must not silently fall back to a global
                # public price that the commercial team intentionally overrode.
                module_prices = []
            else:
                base_id = str(override.get("base_price_id") or "")
                base = next((row for row in module_prices if row["id"] == base_id), module_prices[0] if module_prices else None)
                if base:
                    effective = dict(base)
                    effective.update({
                        "amount_cents": int(override.get("amount_cents", base["amount_cents"])),
                        "currency": str(override.get("currency") or base["currency"]).upper(),
                        "billing_term": str(override.get("billing_term") or base["billing_term"]).upper(),
                        "tax_rate_bps": int(override.get("tax_rate_bps", base["tax_rate_bps"])),
                        "trial_days": int(override.get("trial_days", base["trial_days"])),
                        "tenant_override": True,
                        "offer_valid_until": override.get("valid_until"),
                    })
                    module_prices = [effective]
                else:
                    # Negotiated terms require an enforceable server price identity.
                    # Do not create a purchasable offer from free-form metadata alone.
                    module_prices = []
        subscription = subscriptions.get(code)
        missing = validate_dependencies(db, tenant_id=tenant_id, module_code=code)
        items.append({
            **definition,
            "prices": module_prices,
            "subscription_status": getattr(subscription.status, "value", None) if subscription else None,
            "is_active_for_tenant": code in active,
            "missing_dependencies": missing,
            "can_subscribe": bool(module_prices and not missing and code not in active),
        })
    return {"items": items, "active_modules": sorted(active)}


def _tax_cents(subtotal_cents: int, rate_bps: int) -> int:
    value = (Decimal(int(subtotal_cents)) * Decimal(int(rate_bps))) / Decimal(10000)
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def create_self_service_invoice(
    db: Session,
    *,
    tenant_id: str,
    module_code: str,
    price_id: str,
    expected_amount_cents: int,
    expected_currency: str,
    actor_user_id: str,
    idempotency_key: str,
    terms_version: str,
    auto_renew_accepted: bool,
) -> dict[str, Any]:
    code = normalize_code(module_code)
    key = str(idempotency_key or "").strip()
    if not key:
        raise ValueError("idempotency_key is required")
    catalog = catalog_by_code(db)
    definition = catalog.get(code)
    if not definition or not definition.get("implemented") or not definition.get("customer_selectable"):
        raise ValueError("Module is not available for self-service purchase")
    missing = validate_dependencies(db, tenant_id=tenant_id, module_code=code)
    if missing:
        raise ValueError(f"Required modules must be active first: {', '.join(missing)}")
    if code in active_module_codes(db, tenant_id=tenant_id):
        raise ValueError("Module is already active")

    available = self_service_catalog(db, tenant_id=tenant_id)
    offer = next((item for item in available["items"] if item["code"] == code), None)
    if not offer or not offer.get("can_subscribe"):
        raise ValueError("Module offer is not currently available for this tenant")
    selected = next((row for row in offer.get("prices") or [] if str(row.get("id")) == str(price_id)), None)
    if selected is None:
        raise ValueError("Price is not available for this tenant")
    if normalize_code(str(selected.get("module_code") or code)) != code:
        raise ValueError("Selected price does not belong to this module")
    if int(selected["amount_cents"]) != int(expected_amount_cents):
        raise ValueError("Displayed price changed; refresh the billing page before accepting")
    currency = str(selected["currency"]).upper()
    if currency != str(expected_currency or "").upper():
        raise ValueError("Displayed currency changed; refresh the billing page before accepting")
    if not str(terms_version or "").strip():
        raise ValueError("terms_version is required")
    if not auto_renew_accepted:
        raise ValueError("Explicit recurring billing acceptance is required")

    existing = (
        db.query(account_models.BillingInvoice)
        .filter(account_models.BillingInvoice.amo_id == tenant_id, account_models.BillingInvoice.idempotency_key == key)
        .first()
    )
    if existing:
        details = _safe_invoice_details(existing.description)
        expected_total = int(selected["amount_cents"]) + _tax_cents(int(selected["amount_cents"]), int(selected.get("tax_rate_bps") or 0))
        if (
            str(details.get("module_code") or "") != code
            or str(details.get("price_id") or "") != str(selected.get("id") or "")
            or str(existing.currency or "").upper() != currency
            or int(existing.amount_cents or 0) != expected_total
            or str(details.get("terms_version") or "") != str(terms_version)
        ):
            raise ValueError("idempotency_key is already bound to a different checkout")
        return _invoice_view(existing)

    subtotal = int(selected["amount_cents"])
    tax_rate_bps = int(selected.get("tax_rate_bps") or 0)
    tax_amount = _tax_cents(subtotal, tax_rate_bps)
    total = subtotal + tax_amount
    now = datetime.now(timezone.utc)
    activation_codes = expand_activation_codes(catalog, code)
    ledger = account_models.LedgerEntry(
        amo_id=tenant_id,
        amount_cents=total,
        currency=currency,
        entry_type=account_models.LedgerEntryType.CHARGE,
        description=json.dumps({"event": "MODULE_SELF_SERVICE_ORDER", "module_code": code, "price_id": selected.get("id"), "activation_codes": activation_codes, "subtotal_cents": subtotal, "tax_amount_cents": tax_amount, "total_cents": total}, separators=(",", ":")),
        idempotency_key=key,
        recorded_at=now,
    )
    db.add(ledger)
    db.flush()
    description = json.dumps(
        {
            "module_code": code,
            "module_name": definition.get("name"),
            "price_id": selected.get("id"),
            "tenant_override": bool(selected.get("tenant_override")),
            "offer_valid_until": selected.get("offer_valid_until"),
            "activation_codes": activation_codes,
            "plan_code": selected.get("plan_code") or "STANDARD",
            "billing_term": selected.get("billing_term") or "MONTHLY",
            "quantity": 1,
            "unit_amount_cents": subtotal,
            "subtotal_cents": subtotal,
            "tax_rate_bps": tax_rate_bps,
            "tax_amount_cents": tax_amount,
            "tax_mode": "EXCLUSIVE",
            "total_cents": total,
            "lock_scope": "MODULE",
            "terms_version": str(terms_version),
            "auto_renew_accepted": True,
            "accepted_by_user_id": actor_user_id,
            "accepted_at": now.isoformat(),
            "source": "TENANT_SELF_SERVICE",
        },
        separators=(",", ":"),
    )
    invoice = account_models.BillingInvoice(
        amo_id=tenant_id,
        ledger_entry_id=ledger.id,
        amount_cents=total,
        currency=currency,
        status=account_models.InvoiceStatus.PENDING,
        description=description,
        idempotency_key=key,
        issued_at=now,
        due_at=None,
    )
    db.add(invoice)
    db.flush()
    db.add(
        platform_models.PlatformAuditLog(
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            action="saas.module_checkout.created",
            module="billing",
            entity_type="billing_invoice",
            entity_id=invoice.id,
            reason="Tenant self-service module subscription",
            details_json={
                "module_code": code,
                "activation_codes": activation_codes,
                "price_id": selected.get("id"),
                "subtotal_cents": subtotal,
                "tax_amount_cents": tax_amount,
                "total_cents": total,
                "currency": currency,
                "billing_term": selected.get("billing_term"),
                "terms_version": str(terms_version),
                "auto_renew_accepted": True,
            },
        )
    )
    db.commit()
    db.refresh(invoice)
    return _invoice_view(invoice)


def _safe_invoice_details(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _invoice_view(invoice: account_models.BillingInvoice) -> dict[str, Any]:
    return {
        "id": invoice.id,
        "invoice_number": saas_services.account_services.format_invoice_number(invoice) if hasattr(saas_services, "account_services") else invoice.id,
        "amo_id": invoice.amo_id,
        "amount_cents": int(invoice.amount_cents or 0),
        "currency": str(invoice.currency or "USD").upper(),
        "status": getattr(invoice.status, "value", str(invoice.status)),
        "issued_at": invoice.issued_at,
        "due_at": invoice.due_at,
        "paid_at": invoice.paid_at,
        "commercial": _safe_invoice_details(invoice.description),
    }


def resolve_access_aliases(module_key: str) -> tuple[str, ...]:
    key = normalize_code(module_key)
    aliases: dict[str, tuple[str, ...]] = {
        "finance": ("finance", "finance_inventory"),
        "inventory": ("inventory", "finance_inventory"),
        "procurement": ("procurement", "finance_inventory"),
    }
    return aliases.get(key, (key,))
