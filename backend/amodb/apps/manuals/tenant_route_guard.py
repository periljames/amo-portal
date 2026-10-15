"""Fail-closed tenant ownership boundary for every tenant-addressed Manuals route.

This is deliberately applied to the final composed router, including legacy
aliases and extension routers, before FastAPI mounts/copies the routes.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as accounts
from amodb.database import get_db
from amodb.security import get_current_active_user
from . import models as manuals


def require_manuals_tenant_access(
    request: Request,
    db: Session = Depends(get_db),
    user: accounts.User = Depends(get_current_active_user),
) -> None:
    """Authorize the requested AMO, not merely the user or URL's manual slug.

    Platform staff must first select an active support tenant. A platform
    superuser without that explicit context cannot enumerate other companies'
    Manuals using the URL. All denials are 404 to avoid tenant enumeration.
    """
    slug = str(request.path_params.get("tenant_slug") or "").strip().lower()
    if not slug:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant = db.query(manuals.Tenant).filter(func.lower(manuals.Tenant.slug) == slug).first()
    amo = db.get(accounts.AMO, tenant.amo_id) if tenant and tenant.amo_id else None
    if amo is None:
        amo = (
            db.query(accounts.AMO)
            .filter(
                (func.lower(accounts.AMO.login_slug) == slug)
                | (func.lower(accounts.AMO.amo_code) == slug)
            )
            .first()
        )
    if amo is None or amo.is_active is not True:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # No cross-tenant implicit access, including for platform administrators.
    expected_amo_id = (
        getattr(user, "active_amo_id", None)
        if bool(getattr(user, "is_superuser", False))
        else getattr(user, "amo_id", None)
    )
    if not expected_amo_id or str(expected_amo_id) != str(amo.id):
        raise HTTPException(status_code=404, detail="Tenant not found")
