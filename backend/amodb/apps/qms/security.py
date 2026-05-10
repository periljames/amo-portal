from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.database import get_read_db, get_write_db
from amodb.security import get_current_active_user
from amodb.apps.accounts import models as account_models


@dataclass(frozen=True)
class TenantContext:
    amo_code: str
    amo_id: str
    user_id: str
    is_superuser: bool


_QMS_ROLE_PERMISSIONS: dict[str, set[str]] = {
    # Platform superusers are intentionally absent. They are global operators,
    # not members of an AMO tenant QMS. Use /platform/control for platform work.
    "AMO_ADMIN": {"qms.*"},
    "QUALITY_MANAGER": {"qms.*"},
    "QUALITY_INSPECTOR": {
        "qms.dashboard.view",
        "qms.inbox.view",
        "qms.calendar.view",
        "qms.audit.view",
        "qms.audit.execute",
        "qms.finding.view",
        "qms.finding.create",
        "qms.car.view",
        "qms.document.view",
        "qms.evidence.view",
        "qms.evidence.download",
    },
    "AUDITOR": {
        "qms.dashboard.view",
        "qms.inbox.view",
        "qms.calendar.view",
        "qms.audit.view",
        "qms.audit.execute",
        "qms.finding.view",
        "qms.finding.create",
        "qms.car.view",
        "qms.document.view",
        "qms.evidence.view",
        "qms.evidence.download",
    },
    "VIEW_ONLY": {
        "qms.dashboard.view",
        "qms.inbox.view",
        "qms.calendar.view",
        "qms.audit.view",
        "qms.finding.view",
        "qms.car.view",
        "qms.document.view",
        "qms.training.view",
        "qms.supplier.view",
        "qms.equipment.view",
        "qms.risk.view",
        "qms.change.view",
        "qms.management_review.view",
        "qms.reports.view",
        "qms.evidence.view",
    },
}


def _normalise(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip()


def _permission_matches(grant: str, permission: str) -> bool:
    if grant == "*":
        return True
    if grant.endswith(".*"):
        return permission.startswith(grant[:-1])
    return grant == permission


def _is_platform_superuser(user: account_models.User) -> bool:
    return bool(getattr(user, "is_superuser", False))


def _deny_platform_superuser() -> None:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Platform superuser is global and cannot enter tenant QMS routes. Use Platform Control or create a tenant membership account.",
    )


def _has_role_permission(user: account_models.User, permission: str) -> bool:
    if _is_platform_superuser(user):
        return False
    role_name = _normalise(getattr(user, "role", ""))
    grants = _QMS_ROLE_PERMISSIONS.get(role_name, set())
    return any(_permission_matches(grant, permission) for grant in grants)


def _has_capability_permission(db: Session, *, amo_id: str, user_id: str, permission: str) -> Optional[bool]:
    """Return True/False when authz tables are usable, or None when not configured."""
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return None
    try:
        capability_exists = db.execute(
            text("""
                SELECT to_regclass('public.auth_capability_definitions') IS NOT NULL
                   AND to_regclass('public.auth_user_role_assignments') IS NOT NULL
                   AND to_regclass('public.auth_role_capability_bindings') IS NOT NULL
            """)
        ).scalar()
        if not capability_exists:
            return None
        capability_defined = db.execute(
            text("SELECT 1 FROM auth_capability_definitions WHERE code = :permission LIMIT 1"),
            {"permission": permission},
        ).first()
        if not capability_defined:
            return None
        allowed = db.execute(
            text("""
                SELECT 1
                FROM auth_user_role_assignments ura
                JOIN auth_role_capability_bindings rcb ON rcb.role_id = ura.role_id
                JOIN auth_capability_definitions cd ON cd.id = rcb.capability_id
                WHERE ura.amo_id = :amo_id
                  AND ura.user_id = :user_id
                  AND cd.code = :permission
                  AND (ura.valid_from IS NULL OR ura.valid_from <= NOW())
                  AND (ura.valid_to IS NULL OR ura.valid_to >= NOW())
                LIMIT 1
            """),
            {"amo_id": amo_id, "user_id": user_id, "permission": permission},
        ).first()
        return bool(allowed)
    except Exception:
        return None


def set_postgres_tenant_context(db: Session, *, amo_id: str, user_id: str) -> None:
    """Set request-local PostgreSQL context used by RLS policies."""
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    db.execute(text("SELECT set_config('app.tenant_id', :amo_id, true)"), {"amo_id": str(amo_id)})
    db.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": str(user_id)})


def _resolve_amo(db: Session, amo_code: str) -> account_models.AMO:
    amo = (
        db.query(account_models.AMO)
        .filter(
            account_models.AMO.is_active.is_(True),
            (account_models.AMO.amo_code == amo_code) | (account_models.AMO.login_slug == amo_code),
        )
        .first()
    )
    if not amo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AMO tenant was not found.")
    return amo


def _resolve_tenant_context_impl(*, amo_code: str, current_user: account_models.User, db: Session) -> TenantContext:
    if _is_platform_superuser(current_user):
        _deny_platform_superuser()

    amo = _resolve_amo(db, amo_code)
    effective_amo_id = getattr(current_user, "effective_amo_id", None) or current_user.amo_id
    if not effective_amo_id or str(effective_amo_id) != str(amo.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not a member of this AMO tenant.")

    set_postgres_tenant_context(db, amo_id=str(amo.id), user_id=str(current_user.id))
    return TenantContext(amo_code=amo_code, amo_id=str(amo.id), user_id=str(current_user.id), is_superuser=False)


def resolve_tenant_context(
    amo_code: str = Path(..., alias="amo_code"),
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_read_db),
) -> TenantContext:
    return _resolve_tenant_context_impl(amo_code=amo_code, current_user=current_user, db=db)


def write_tenant_context(
    amo_code: str = Path(..., alias="amo_code"),
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
) -> TenantContext:
    return _resolve_tenant_context_impl(amo_code=amo_code, current_user=current_user, db=db)


def require_qms_permission(permission: str) -> Callable[[TenantContext, account_models.User, Session], TenantContext]:
    def dependency(
        ctx: TenantContext = Depends(resolve_tenant_context),
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_read_db),
    ) -> TenantContext:
        if _is_platform_superuser(current_user):
            _deny_platform_superuser()
        capability_result = _has_capability_permission(db, amo_id=ctx.amo_id, user_id=ctx.user_id, permission=permission)
        if capability_result is True:
            return ctx
        if capability_result is False:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission '{permission}' is required.")
        if _has_role_permission(current_user, permission):
            return ctx
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission '{permission}' is required.")

    return dependency


def has_qms_permission(db: Session, ctx: TenantContext, permission: str) -> bool:
    """Return whether the resolved tenant user has a QMS permission."""
    user = db.query(account_models.User).filter(account_models.User.id == ctx.user_id).first()
    if not user or _is_platform_superuser(user):
        return False
    capability_result = _has_capability_permission(db, amo_id=ctx.amo_id, user_id=ctx.user_id, permission=permission)
    if capability_result is not None:
        return bool(capability_result)
    return _has_role_permission(user, permission)


def assert_qms_permission(db: Session, ctx: TenantContext, permission: str) -> None:
    """Imperative permission check for generic canonical QMS routes."""
    user = db.query(account_models.User).filter(account_models.User.id == ctx.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authenticated user was not found.")
    if _is_platform_superuser(user):
        _deny_platform_superuser()
    if has_qms_permission(db, ctx, permission):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission '{permission}' is required.")
