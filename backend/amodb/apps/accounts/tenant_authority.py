"""Shared tenant administrator policy. Platform authority is never inherited."""
from __future__ import annotations

from .role_registry import canonical_role_key


def tenant_member(user: object, amo_id: object | None = None) -> bool:
    if user is None or getattr(user, "is_superuser", False):
        return False
    if canonical_role_key(getattr(user, "role", None)) == "SUPERUSER":
        return False
    if getattr(user, "is_active", True) is False or getattr(user, "is_system_account", False):
        return False
    own = getattr(user, "amo_id", None)
    effective = getattr(user, "effective_amo_id", None) or own
    return bool(own and str(own) == str(effective) and (amo_id is None or str(own) == str(amo_id)))


def is_tenant_admin(user: object, amo_id: object | None = None) -> bool:
    return tenant_member(user, amo_id) and bool(
        getattr(user, "is_amo_admin", False)
        or canonical_role_key(getattr(user, "role", None)) == "AMO_ADMIN"
        or getattr(user, "_admin_profile_elevated", False)
    )


def is_standing_admin(user: object, amo_id: object | None = None) -> bool:
    return is_tenant_admin(user, amo_id) and not getattr(user, "_admin_profile_elevated", False)


def can_revoke_administrator(user: object, amo_id: object) -> bool:
    """This governance exception deliberately does not inherit admin rights."""
    return bool(getattr(user, "is_superuser", False)) or (
        tenant_member(user, amo_id)
        and canonical_role_key(getattr(user, "role", None)) == "ACCOUNTABLE_EXECUTIVE"
    )


def has_admin_appointment(db, user: object) -> bool:
    """Include future and active delegated appointments when protecting removals."""
    if not getattr(user, "amo_id", None) or getattr(user, "is_superuser", False):
        return False
    if getattr(user, "is_amo_admin", False) or canonical_role_key(getattr(user, "role", None)) == "AMO_ADMIN":
        return True
    from datetime import datetime, timezone
    from sqlalchemy import inspect, text
    # Isolated SQLite tests may omit the optional governance schema.
    if db.get_bind().dialect.name == "sqlite" and not inspect(db.get_bind()).has_table("admin_access_grants"):
        return False
    return db.execute(text("""
        SELECT 1 FROM admin_access_grants
        WHERE amo_id = :amo_id AND user_id = :user_id AND status = 'ACTIVE'
          AND (valid_until IS NULL OR valid_until > :now)
        LIMIT 1
    """), {"amo_id": str(user.amo_id), "user_id": str(user.id), "now": datetime.now(timezone.utc)}).first() is not None


def assert_administrator_removal_allowed(db, *, actor: object, user: object) -> None:
    from fastapi import HTTPException
    if has_admin_appointment(db, user) and not can_revoke_administrator(actor, user.amo_id):
        raise HTTPException(status_code=403, detail="Only the platform superuser or this tenant's Accountable Executive may deactivate or remove an administrator.")


def active_admin_profile_session(db, user, amo) -> bool:
    """Return whether the user has standing or session-scoped admin authority.

    Standing AMO administrators are appointed and revoked by the platform
    superuser, so their authority does not depend on a temporary activation
    row. Approved delegates use rows linked to a currently active grant;
    concurrent logins for the same delegated account never share elevation.
    """
    from datetime import datetime, timezone
    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError

    if not tenant_member(user, amo.id):
        return False
    if is_standing_admin(user):
        return True

    auth_session_id = str(
        getattr(user, "auth_session_id", None)
        or getattr(user, "_auth_session_id", None)
        or ""
    ).strip()
    if not auth_session_id:
        return False

    try:
        with db.begin_nested():
            return db.execute(
                text(
                    """
                    SELECT 1
                    FROM admin_profile_sessions s
                    LEFT JOIN admin_access_grants g ON g.id = s.grant_id
                    WHERE s.amo_id = :amo_id
                      AND s.user_id = :user_id
                      AND s.auth_session_id = :auth_session_id
                      AND s.revoked_at IS NULL
                      AND s.expires_at > :now
                      AND (
                        (
                          :implicit_admin = TRUE
                          AND s.grant_id IS NULL
                        )
                        OR (
                          s.grant_id IS NOT NULL
                          AND g.amo_id = s.amo_id
                          AND g.user_id = s.user_id
                          AND g.status = 'ACTIVE'
                          AND (g.valid_from IS NULL OR g.valid_from <= :now)
                          AND (g.valid_until IS NULL OR g.valid_until > :now)
                        )
                      )
                    LIMIT 1
                    """
                ),
                {
                    "amo_id": str(amo.id),
                    "user_id": str(user.id),
                    "auth_session_id": auth_session_id,
                    "implicit_admin": False,
                    "now": datetime.now(timezone.utc),
                },
            ).first() is not None
    except SQLAlchemyError:
        return False
