from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import module_commerce


_INSTALLED = False


def _metadata(row: account_models.ModuleSubscription) -> dict[str, Any]:
    if not row.metadata_json:
        return {}
    try:
        value = json.loads(row.metadata_json)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def install_module_offer_policy() -> None:
    """Mark price-only placeholder rows so they never revoke legacy access."""
    global _INSTALLED
    if _INSTALLED:
        return

    original = module_commerce.set_tenant_offer

    def set_tenant_offer(
        db: Session,
        *,
        tenant_id: str,
        module_code: str,
        payload: dict[str, Any],
        actor_user_id: str,
    ) -> dict[str, Any]:
        code = module_commerce.normalize_code(module_code)
        existing = (
            db.query(account_models.ModuleSubscription)
            .filter(
                account_models.ModuleSubscription.amo_id == tenant_id,
                account_models.ModuleSubscription.module_code == code,
            )
            .first()
        )
        result = original(
            db,
            tenant_id=tenant_id,
            module_code=code,
            payload=payload,
            actor_user_id=actor_user_id,
        )
        if existing is None:
            row = (
                db.query(account_models.ModuleSubscription)
                .filter(
                    account_models.ModuleSubscription.amo_id == tenant_id,
                    account_models.ModuleSubscription.module_code == code,
                )
                .first()
            )
            if row is not None:
                metadata = _metadata(row)
                metadata["commercial_offer_only"] = True
                row.metadata_json = json.dumps(metadata, separators=(",", ":"))
                db.commit()
                result = dict(result)
                result["commercial_offer_only"] = True
        return result

    module_commerce.set_tenant_offer = set_tenant_offer
    _INSTALLED = True
