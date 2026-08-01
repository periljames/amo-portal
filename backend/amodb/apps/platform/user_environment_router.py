from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_read_db

from .commercial_services import normalize_data_mode
from .router import require_platform_superuser


def scoped_users(
    q: str | None = None,
    tenant_id: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    data_mode: str = Query("REAL"),
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_read_db),
    user=Depends(require_platform_superuser),
):
    mode = normalize_data_mode(data_mode)
    query = db.query(account_models.User).outerjoin(
        account_models.AMO,
        account_models.AMO.id == account_models.User.amo_id,
    ).filter(
        or_(
            account_models.User.amo_id.is_(None),
            account_models.AMO.is_demo.is_(mode == "DEMO"),
        )
    )
    if tenant_id:
        tenant = db.get(account_models.AMO, tenant_id)
        if not tenant or bool(tenant.is_demo) != (mode == "DEMO"):
            raise HTTPException(status_code=422, detail="Tenant does not belong to the selected REAL or DEMO environment")
        query = query.filter(account_models.User.amo_id == tenant_id)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            account_models.User.email.ilike(like)
            | account_models.User.full_name.ilike(like)
        )
    if status_filter == "active":
        query = query.filter(account_models.User.is_active.is_(True))
    if status_filter == "disabled":
        query = query.filter(account_models.User.is_active.is_(False))

    total = query.count()
    rows = query.order_by(account_models.User.updated_at.desc()).offset(offset).limit(min(limit, 200)).all()
    return {
        "items": [
            {
                "id": row.id,
                "email": row.email,
                "full_name": row.full_name,
                "role": getattr(row.role, "value", str(row.role)),
                "amo_id": row.amo_id,
                "tenant_name": getattr(row.amo, "name", None),
                "is_active": row.is_active,
                "is_superuser": row.is_superuser,
                "is_amo_admin": row.is_amo_admin,
                "webauthn_registered": row.webauthn_registered,
                "last_login_at": row.last_login_at,
                "locked_until": row.locked_until,
                "failed_login_count": row.login_attempts,
            }
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
        "data_mode": mode,
    }


def install_environment_scoped_user_route(platform_router: APIRouter) -> None:
    platform_router.routes[:] = [
        route_item
        for route_item in platform_router.routes
        if not (
            str(getattr(route_item, "path", "")).endswith("/users")
            and "GET" in set(getattr(route_item, "methods", None) or ())
        )
    ]
    platform_router.add_api_route(
        "/users",
        scoped_users,
        methods=["GET"],
        tags=["platform-control-plane"],
        name="environment_scoped_platform_users",
    )


__all__ = ["install_environment_scoped_user_route", "scoped_users"]
