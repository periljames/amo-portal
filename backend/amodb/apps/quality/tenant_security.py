from __future__ import annotations

from amodb.apps.accounts.tenant_authority import is_tenant_admin, tenant_member

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy import event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, lazyload

from amodb.database import get_read_db, get_write_db
from amodb.security import get_current_active_user
from amodb.apps.accounts import access_control, models as account_models
from amodb.apps.platform import models as platform_models


_TENANT_CONTEXT_KEY = "quality_tenant_context"


@event.listens_for(Session, "after_begin")
def _restore_postgres_tenant_context(session: Session, transaction, connection) -> None:  # noqa: ARG001
    """Restore transaction-local RLS settings after a commit opens a new transaction."""
    context = session.info.get(_TENANT_CONTEXT_KEY)
    if not context or connection.dialect.name != "postgresql":
        return
    amo_id, user_id = context
    connection.execute(text("SELECT set_config('app.tenant_id', :amo_id, true)"), {"amo_id": amo_id})
    connection.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": user_id})


@dataclass(frozen=True)
class TenantContext:
    amo_code: str
    amo_id: str
    user_id: str
    is_superuser: bool
    support_session_id: str | None = None
    support_access_level: str | None = None
    admin_authority: bool = False


_READ_ONLY_SUPPORT_PERMISSIONS = {
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
    "qms.evidence.download",
    "qms.settings.view",
    "qms.people.view",
}


def _normalise(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip()


def _is_platform_superuser(user: account_models.User) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_platform_context", False))



def _support_level_allows(level: str | None, permission: str) -> bool:
    if permission not in access_control.WORKFLOW_CAPABILITIES or permission in access_control.PROTECTED_DECISION_CAPABILITIES:
        return False
    access_level = str(level or "").upper()
    if access_level == "ADMIN":
        return True
    if access_level == "READ_ONLY":
        return permission in _READ_ONLY_SUPPORT_PERMISSIONS
    return False


def _has_capability_permission(
    db: Session, *, amo_id: str, user_id: str, permission: str,
    department_id: str | None = None,
) -> bool:
    """Use the canonical access evaluator on every database, without role fallback."""
    try:
        user = db.query(account_models.User).options(lazyload("*")).filter(
            account_models.User.id == user_id,
            account_models.User.amo_id == amo_id,
            account_models.User.is_active.is_(True),
            account_models.User.is_system_account.is_(False),
        ).first()
        if user is None:
            return False
        return access_control.evaluate_capability(
            db, user=user, capability_code=permission, department_id=department_id,
        ).allowed
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Quality authorization could not be verified.",
        ) from exc


def _assert_quality_module_available(db: Session, *, amo_id: str) -> None:
    """Honor an explicit tenant Quality subscription disable at the API boundary.

    Some older installations predate module-subscription rows, so absence remains
    backward-compatible. Once a Quality subscription exists, disabled, suspended,
    not-yet-effective and expired states must not be bypassable through a direct
    Quality deep link or API call.
    """
    subscription = (
        db.query(account_models.ModuleSubscription).options(lazyload("*"))
        .filter(
            account_models.ModuleSubscription.amo_id == str(amo_id),
            account_models.ModuleSubscription.module_code == "quality",
        )
        .first()
    )
    if subscription is None or not isinstance(subscription, account_models.ModuleSubscription):
        return
    state = _normalise(subscription.status).upper()
    if state not in {
        account_models.ModuleSubscriptionStatus.ENABLED.value,
        account_models.ModuleSubscriptionStatus.TRIAL.value,
    }:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="The Quality module is not enabled for this AMO tenant.")
    now = datetime.now(timezone.utc)
    effective_from = subscription.effective_from
    effective_to = subscription.effective_to
    if effective_from is not None:
        effective_from = effective_from if effective_from.tzinfo else effective_from.replace(tzinfo=timezone.utc)
        if effective_from > now:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="The Quality module subscription is not effective yet.")
    if effective_to is not None:
        effective_to = effective_to if effective_to.tzinfo else effective_to.replace(tzinfo=timezone.utc)
        if effective_to <= now:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="The Quality module subscription has expired.")


def set_postgres_tenant_context(db: Session, *, amo_id: str, user_id: str) -> None:
    """Set and remember request-local PostgreSQL context used by RLS policies."""
    db.info[_TENANT_CONTEXT_KEY] = (str(amo_id), str(user_id))
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    db.execute(text("SELECT set_config('app.tenant_id', :amo_id, true)"), {"amo_id": str(amo_id)})
    db.execute(text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": str(user_id)})


def _resolve_amo(db: Session, amo_code: str) -> account_models.AMO:
    amo = (
        db.query(account_models.AMO).options(lazyload("*"))
        .filter(
            account_models.AMO.is_active.is_(True),
            (account_models.AMO.amo_code == amo_code) | (account_models.AMO.login_slug == amo_code),
        )
        .first()
    )
    if not amo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AMO tenant was not found.")
    return amo


def _active_support_session(db: Session, *, amo_id: str, platform_user_id: str) -> platform_models.PlatformTenantSupportSession | None:
    now = datetime.now(timezone.utc)
    row = (
        db.query(platform_models.PlatformTenantSupportSession)
        .filter(
            platform_models.PlatformTenantSupportSession.tenant_id == str(amo_id),
            platform_models.PlatformTenantSupportSession.platform_user_id == str(platform_user_id),
            platform_models.PlatformTenantSupportSession.status == "ACTIVE",
            platform_models.PlatformTenantSupportSession.expires_at > now,
            platform_models.PlatformTenantSupportSession.ended_at.is_(None),
        )
        .order_by(platform_models.PlatformTenantSupportSession.created_at.desc())
        .first()
    )
    return row


def _resolve_tenant_context_impl(*, amo_code: str, current_user: account_models.User, db: Session) -> TenantContext:
    amo = _resolve_amo(db, amo_code)
    if _is_platform_superuser(current_user):
        session = _active_support_session(db, amo_id=str(amo.id), platform_user_id=str(current_user.id))
        if not session:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Start an active platform support session for this tenant before opening Quality tenant routes.",
            )
        _assert_quality_module_available(db, amo_id=str(amo.id))
        set_postgres_tenant_context(db, amo_id=str(amo.id), user_id=str(current_user.id))
        return TenantContext(
            amo_code=amo_code,
            amo_id=str(amo.id),
            user_id=str(current_user.id),
            is_superuser=True,
            support_session_id=str(session.id),
            support_access_level=str(session.access_level),
        )

    effective_amo_id = getattr(current_user, "effective_amo_id", None) or current_user.amo_id
    if not effective_amo_id or str(effective_amo_id) != str(amo.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not a member of this AMO tenant.")

    _assert_quality_module_available(db, amo_id=str(amo.id))
    set_postgres_tenant_context(db, amo_id=str(amo.id), user_id=str(current_user.id))
    return TenantContext(amo_code=amo_code, amo_id=str(amo.id), user_id=str(current_user.id), is_superuser=False, admin_authority=is_tenant_admin(current_user, amo.id))


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


def require_quality_permission(permission: str) -> Callable[[TenantContext, account_models.User, Session], TenantContext]:
    """Gate a Quality route on a permission using the shared read tenant session.

    Prefer this for GET/list routes. Mutation routes should use
    ``require_quality_write_permission`` so authz and the handler share the
    writer session (one pool checkout when engines are split).
    """

    def dependency(
        ctx: TenantContext = Depends(resolve_tenant_context),
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_read_db),
    ) -> TenantContext:
        return _enforce_quality_permission(ctx=ctx, current_user=current_user, db=db, permission=permission)

    return dependency


def require_quality_write_permission(permission: str) -> Callable[[TenantContext, account_models.User, Session], TenantContext]:
    """Gate a Quality mutation on a permission using the writer tenant session."""

    def dependency(
        ctx: TenantContext = Depends(write_tenant_context),
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_write_db),
    ) -> TenantContext:
        return _enforce_quality_permission(ctx=ctx, current_user=current_user, db=db, permission=permission)

    return dependency


def _enforce_quality_permission(
    *, ctx: TenantContext, current_user: account_models.User,
    db: Session, permission: str,
) -> TenantContext:
    if str(current_user.id) != ctx.user_id:
        raise HTTPException(status_code=403, detail="Quality identity does not match the tenant context.")
    if has_quality_permission(db, ctx, permission):
        return ctx
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission '{permission}' is required.")


def has_quality_permission(
    db: Session, ctx: TenantContext, permission: str, *, department_id: str | None = None,
) -> bool:
    """Evaluate effective scoped grants, never an administrative approval overlay."""
    if ctx.is_superuser:
        if permission in access_control.PROTECTED_DECISION_CAPABILITIES:
            return False
        return _support_level_allows(ctx.support_access_level, permission)
    return _has_capability_permission(
        db, amo_id=ctx.amo_id, user_id=ctx.user_id,
        permission=permission, department_id=department_id,
    )


def assert_quality_permission(db: Session, ctx: TenantContext, permission: str) -> None:
    """Imperative permission check for canonical Quality routes."""
    if has_quality_permission(db, ctx, permission):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission '{permission}' is required.")


def assert_quality_permission_any(db: Session, ctx: TenantContext, *permissions: str) -> None:
    """Require at least one Quality capability without bypassing tenant authorization."""
    if not permissions:
        raise ValueError("At least one Quality permission is required.")
    if any(has_quality_permission(db, ctx, permission) for permission in permissions):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Permission '{permissions[0]}' is required.",
    )
