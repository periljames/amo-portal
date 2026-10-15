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


def _authorized_manual_tenant(
    db: Session, *, user: accounts.User, tenant_slug: str,
) -> manuals.Tenant:
    """Resolve the tenant only after the current actor's AMO is established."""
    amo_id = (
        getattr(user, "active_amo_id", None)
        if bool(getattr(user, "is_superuser", False))
        else getattr(user, "amo_id", None)
    )
    if not amo_id:
        raise HTTPException(status_code=404, detail="Tenant not found")
    amo = db.get(accounts.AMO, str(amo_id))
    if amo is None or amo.is_active is not True:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tenant = db.query(manuals.Tenant).filter(manuals.Tenant.amo_id == str(amo_id)).first()
    # No implicit tenant creation in access-control dependencies.
    if tenant is None or str(tenant_slug).strip().lower() not in {
        str(tenant.slug).lower(), str(amo.login_slug).lower(), str(amo.amo_code).lower(),
    }:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


def require_manuals_record_access(
    request: Request,
    db: Session = Depends(get_db),
    user: accounts.User = Depends(get_current_active_user),
) -> None:
    """Bind path document/revision identifiers to the authenticated tenant."""
    params = request.path_params
    tenant = _authorized_manual_tenant(
        db, user=user, tenant_slug=str(params.get("tenant_slug") or ""),
    )
    manual_id = str(params.get("manual_id") or "")
    rev_id = str(params.get("rev_id") or "")
    if not manual_id:
        raise HTTPException(status_code=404, detail="Manual not found")
    query = db.query(manuals.Manual).filter(
        manuals.Manual.id == manual_id,
        manuals.Manual.tenant_id == tenant.id,
    )
    if rev_id:
        query = query.join(
            manuals.ManualRevision,
            manuals.ManualRevision.manual_id == manuals.Manual.id,
        ).filter(manuals.ManualRevision.id == rev_id)
    if query.first() is None:
        raise HTTPException(status_code=404, detail="Manual or revision not found")


def require_manuals_export_access(
    request: Request,
    db: Session = Depends(get_db),
    user: accounts.User = Depends(get_current_active_user),
) -> None:
    """Exports without a tenant slug must never permit cross-tenant writes."""
    export_id = str(request.path_params.get("export_id") or "")
    expected = (
        getattr(user, "active_amo_id", None)
        if bool(getattr(user, "is_superuser", False))
        else getattr(user, "amo_id", None)
    )
    if not expected:
        raise HTTPException(status_code=404, detail="Export not found")
    export = (
        db.query(manuals.PrintExport)
        .join(manuals.ManualRevision, manuals.ManualRevision.id == manuals.PrintExport.revision_id)
        .join(manuals.Manual, manuals.Manual.id == manuals.ManualRevision.manual_id)
        .join(manuals.Tenant, manuals.Tenant.id == manuals.Manual.tenant_id)
        .join(accounts.AMO, accounts.AMO.id == manuals.Tenant.amo_id)
        .filter(
            manuals.PrintExport.id == export_id,
            accounts.AMO.id == str(expected),
            accounts.AMO.is_active.is_(True),
        )
        .first()
    )
    if export is None:
        raise HTTPException(status_code=404, detail="Export not found")
