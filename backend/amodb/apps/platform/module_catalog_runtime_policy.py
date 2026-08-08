from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import module_commerce


_INSTALLED = False
_ORIGINAL_SELF_SERVICE_CATALOG = module_commerce.self_service_catalog


def _metadata(row: account_models.ModuleSubscription | None) -> dict[str, Any]:
    if row is None or not row.metadata_json:
        return {}
    try:
        parsed = json.loads(row.metadata_json)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def enriched_self_service_catalog(db: Session, *, tenant_id: str) -> dict[str, Any]:
    result = _ORIGINAL_SELF_SERVICE_CATALOG(db, tenant_id=tenant_id)
    rows = {
        module_commerce.normalize_code(row.module_code): row
        for row in db.query(account_models.ModuleSubscription)
        .filter(account_models.ModuleSubscription.amo_id == tenant_id)
        .all()
    }
    now = datetime.now(timezone.utc)
    for item in result.get("items") or []:
        code = module_commerce.normalize_code(str(item.get("code") or ""))
        row = rows.get(code)
        metadata = _metadata(row)
        commercial_terms = metadata.get("commercial_terms") if isinstance(metadata.get("commercial_terms"), dict) else {}
        valid_until = commercial_terms.get("valid_until") if commercial_terms else None
        offer_expired = False
        if valid_until:
            try:
                parsed = datetime.fromisoformat(str(valid_until).replace("Z", "+00:00"))
                parsed = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
                offer_expired = parsed < now
            except ValueError:
                offer_expired = True

        item.update(
            {
                "effective_from": _aware(row.effective_from).isoformat() if row and row.effective_from else None,
                "effective_to": _aware(row.effective_to).isoformat() if row and row.effective_to else None,
                "plan_code": row.plan_code if row else None,
                "contract_module_code": metadata.get("contract_module_code"),
                "bundle_parent": metadata.get("bundle_parent"),
                "auto_renew": bool(metadata.get("auto_renew", False)),
                "cancel_at_period_end": bool(metadata.get("cancel_at_period_end", False)),
                "is_root_contract": bool(
                    row
                    and not metadata.get("commercial_offer_only")
                    and not metadata.get("bundle_parent")
                    and str(metadata.get("contract_module_code") or row.module_code) == str(row.module_code)
                ),
                "tenant_offer_valid_until": valid_until,
                "tenant_offer_expired": offer_expired,
            }
        )
        if offer_expired and commercial_terms:
            # An expired negotiated offer must never remain purchasable at its old
            # negotiated amount. Superuser can issue a new offer or the tenant can
            # use a separately configured global price after the override is reset.
            item["prices"] = []
            item["can_subscribe"] = False
    return result


def install_module_catalog_runtime_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    module_commerce.self_service_catalog = enriched_self_service_catalog
    _INSTALLED = True
