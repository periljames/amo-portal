from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models

from . import models as platform_models


def active_platform_support_session(
    db: Session,
    *,
    tenant_id: str,
    platform_user_id: str,
    session_id: str | None = None,
) -> platform_models.PlatformTenantSupportSession | None:
    """Return an exact active support session for a platform actor and tenant."""
    now = datetime.now(timezone.utc)
    query = db.query(platform_models.PlatformTenantSupportSession).filter(
        platform_models.PlatformTenantSupportSession.tenant_id == str(tenant_id),
        platform_models.PlatformTenantSupportSession.platform_user_id == str(platform_user_id),
        platform_models.PlatformTenantSupportSession.status == "ACTIVE",
        platform_models.PlatformTenantSupportSession.expires_at > now,
        platform_models.PlatformTenantSupportSession.ended_at.is_(None),
    )
    if session_id:
        query = query.filter(platform_models.PlatformTenantSupportSession.id == str(session_id))
    return query.order_by(platform_models.PlatformTenantSupportSession.created_at.desc()).first()


def require_tenant_data_access(
    db: Session,
    *,
    tenant_id: str,
    actor_user_id: str,
    support_session_id: str | None = None,
) -> str | None:
    """Authorize one actor to send data from one tenant to an external AI.

    Tenant users may send only data from their own AMO. Platform users are not
    tenant identities and therefore require a current governed support session
    for the exact AMO. A tenant-bound account marked superuser is deliberately
    rejected as a platform support identity.

    Returns the support-session id for platform access, otherwise ``None``.
    """
    actor = db.get(account_models.User, str(actor_user_id))
    if actor is None or not bool(getattr(actor, "is_active", False)):
        raise PermissionError("AI tenant-data access requires an active authenticated actor")

    actor_tenant_id = str(getattr(actor, "amo_id", "") or "")
    is_superuser = bool(getattr(actor, "is_superuser", False))
    if not is_superuser:
        if actor_tenant_id != str(tenant_id):
            raise PermissionError("AI tenant-data scope does not match the authenticated AMO context")
        return None

    if actor_tenant_id:
        raise PermissionError("Tenant-bound superuser accounts cannot use platform AI access for another AMO")

    session = active_platform_support_session(
        db,
        tenant_id=str(tenant_id),
        platform_user_id=str(actor_user_id),
        session_id=support_session_id,
    )
    if session is None:
        raise PermissionError(
            "Cross-tenant AI data access requires an active governed platform support session for this AMO"
        )
    return str(session.id)
