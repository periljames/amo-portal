# backend/amodb/security.py

"""
Security helpers for AMOdb.

Responsibilities:
- Password hashing and verification
- JWT access token creation and decoding
- FastAPI dependencies for current user / admin checks
- Role-based access helpers for router dependencies

This module is intentionally focused and aligned with the new accounts app:
`amodb.apps.accounts.models.User` and its AccountRole enum.
"""

from __future__ import annotations

from amodb.apps.accounts.tenant_authority import is_tenant_admin, tenant_member

import hashlib
import os
from contextvars import ContextVar, Token
from datetime import datetime, timedelta, timezone
from typing import Optional, Callable, Union, Set, Sequence
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.dependencies.utils import get_parameterless_sub_dependant
from fastapi.routing import APIRoute
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHash
import bcrypt

from .database import get_db
from amodb.apps.accounts import models as account_models
from amodb.apps.accounts.models import AccountRole

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

# In production, ALWAYS override these via environment variables.
SECRET_KEY = (os.getenv("SECRET_KEY") or "").strip()
_APP_ENV = (os.getenv("APP_ENV") or os.getenv("ENV") or "development").strip().lower()
_is_production = _APP_ENV in {"prod", "production"}
if _is_production and (not SECRET_KEY or SECRET_KEY == "CHANGE_ME_IN_PRODUCTION"):
    raise RuntimeError(
        "SECRET_KEY must be provided via environment variable and cannot use the default placeholder in production."
    )
if not SECRET_KEY:
    SECRET_KEY = "CHANGE_ME_IN_PRODUCTION"

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

try:
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    )
except ValueError:
    ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Used by FastAPI’s OAuth2 docs / OpenAPI
# This is the logical endpoint that issues tokens.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Current actor id for request-scoped access in routers.
CURRENT_ACTOR_ID: ContextVar[Optional[str]] = ContextVar(
    "current_actor_id",
    default=None,
)

# Authentication-session identity copied into refreshed JWTs. This differs from
# the user id: concurrent browsers for the same account receive independent
# values, so an elevated Admin Profile cannot leak between those sessions.
CURRENT_AUTH_SESSION_ID: ContextVar[Optional[str]] = ContextVar(
    "current_auth_session_id",
    default=None,
)


# ---------------------------------------------------------------------------
# PASSWORD HASHING
# ---------------------------------------------------------------------------

# Argon2id (argon2-cffi) password hasher.
# You can tune these via env vars if needed.
_pwd_hasher = PasswordHasher(
    time_cost=int(os.getenv("ARGON2_TIME_COST", "3")),
    memory_cost=int(os.getenv("ARGON2_MEMORY_COST", "65536")),  # KiB (64MB)
    parallelism=int(os.getenv("ARGON2_PARALLELISM", "2")),
    hash_len=int(os.getenv("ARGON2_HASH_LEN", "32")),
    salt_len=int(os.getenv("ARGON2_SALT_LEN", "16")),
)


def _is_argon2_hash(hashed_password: str) -> bool:
    return isinstance(hashed_password, str) and hashed_password.startswith("$argon2")


def _is_bcrypt_hash(hashed_password: str) -> bool:
    return isinstance(hashed_password, str) and hashed_password.startswith(("$2a$", "$2b$", "$2y$"))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if the plain password matches the hash."""
    if not plain_password or not hashed_password:
        return False

    # Prefer Argon2 for new hashes
    if _is_argon2_hash(hashed_password):
        try:
            return _pwd_hasher.verify(hashed_password, plain_password)
        except (VerifyMismatchError, VerificationError, InvalidHash):
            return False

    # Backward compatibility: support existing bcrypt hashes (if any)
    if _is_bcrypt_hash(hashed_password):
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8"),
            )
        except Exception:
            return False

    # Unknown hash format
    return False


def get_password_hash(password: str) -> str:
    """Hash a password for storing in the database (Argon2id)."""
    return _pwd_hasher.hash(password)


# ---------------------------------------------------------------------------
# JWT TOKENS
# ---------------------------------------------------------------------------


def _normalise_auth_session_id(value: object) -> Optional[str]:
    candidate = str(value or "").strip()
    if not candidate or len(candidate) > 64:
        return None
    return candidate


def _auth_session_id_from_token(token: str, payload: dict) -> str:
    """Resolve a stable server-session id from a JWT.

    New tokens carry an explicit UUID. A deterministic token hash keeps older
    tokens isolated from one another during a rolling deployment without ever
    treating the account id itself as the authentication session.
    """
    explicit = _normalise_auth_session_id(payload.get("auth_session_id"))
    if explicit:
        return explicit
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def bind_current_auth_session_id(value: str) -> Token:
    normalised = _normalise_auth_session_id(value)
    if not normalised:
        raise ValueError("A valid authentication-session id is required.")
    return CURRENT_AUTH_SESSION_ID.set(normalised)


def reset_current_auth_session_id(token: Token) -> None:
    CURRENT_AUTH_SESSION_ID.reset(token)


def get_current_auth_session_id() -> Optional[str]:
    return CURRENT_AUTH_SESSION_ID.get()


def create_access_token(
    *,
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a signed JWT.

    The `data` dict should already include the subject, e.g.:
        {"sub": user.id, "amo_id": user.amo_id}

    A fresh authentication-session id is created for a new login. The explicit
    refresh dependency binds the current id into CURRENT_AUTH_SESSION_ID so a
    token refresh stays within the same browser/device session.
    """
    to_encode = data.copy()

    auth_session_id = (
        _normalise_auth_session_id(to_encode.get("auth_session_id"))
        or _normalise_auth_session_id(CURRENT_AUTH_SESSION_ID.get())
        or str(uuid4())
    )
    to_encode["auth_session_id"] = auth_session_id

    expire = datetime.utcnow() + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    now = datetime.utcnow()
    to_encode.update({"exp": expire, "iat": now})

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


# ---------------------------------------------------------------------------
# USER LOOKUP HELPERS
# ---------------------------------------------------------------------------


def get_user_by_id(
    db: Session,
    user_id: Union[str, int],
) -> Optional[account_models.User]:
    """
    Minimal helper to load a user by ID.

    Services inside the accounts app may use richer helpers with joinedload;
    this is intentionally simple to avoid circular imports.
    """
    # Your User.id is String(36); do not coerce to int.
    if user_id is None:
        return None

    normalised_id = str(user_id).strip()

    user = db.get(account_models.User, normalised_id)
    if user is not None:
        return user
    return (
        db.query(account_models.User)
        .filter(account_models.User.id == normalised_id)
        .first()
    )


# ---------------------------------------------------------------------------
# FASTAPI DEPENDENCIES
# ---------------------------------------------------------------------------


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> account_models.User:
    """Decode the JWT and load identity from the strongly consistent writer.

    Authentication, token revocation, tenant membership and role decisions must
    never trust a potentially lagging read replica. Read sessions remain suitable
    only after this writer-side identity has authorized the requested operation.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id: Optional[Union[str, int]] = payload.get("sub")
        if user_id is None:
            raise _credentials_exception()
        auth_session_id = _auth_session_id_from_token(token, payload)
    except JWTError:
        raise _credentials_exception()

    user = get_user_by_id(db, user_id)
    if user is None:
        raise _credentials_exception()

    # New sessions are independently revocable. Tokens issued before this
    # migration remain valid through the legacy user-level revocation check
    # below, which permits a zero-downtime deployment after migrations run.
    try:
        auth_session = db.get(account_models.PortalAuthSession, auth_session_id)
    except (OperationalError, ProgrammingError):
        # Unmanaged tokens predate server-side auth sessions and remain valid
        # during the documented rolling migration. Managed tokens must never
        # bypass a missing revocation store.
        db.rollback()
        if payload.get("auth_session_managed") is True:
            raise _credentials_exception()
        auth_session = None
    if payload.get("auth_session_managed") is True and auth_session is None:
        raise _credentials_exception()
    if auth_session is not None:
        session_expiry = auth_session.expires_at
        if session_expiry is not None and session_expiry.tzinfo is None:
            session_expiry = session_expiry.replace(tzinfo=timezone.utc)
        if (
            str(auth_session.user_id) != str(user.id)
            or auth_session.revoked_at is not None
            or session_expiry is None
            or session_expiry <= datetime.now(timezone.utc)
        ):
            raise _credentials_exception()

    token_issued_at = payload.get("iat")
    revoked_at = getattr(user, "token_revoked_at", None)
    if revoked_at is not None:
        if isinstance(token_issued_at, (int, float)):
            issued_at_dt = datetime.fromtimestamp(token_issued_at, tz=timezone.utc)
        elif isinstance(token_issued_at, datetime):
            issued_at_dt = token_issued_at if token_issued_at.tzinfo else token_issued_at.replace(tzinfo=timezone.utc)
        else:
            issued_at_dt = None
        revoked_dt = revoked_at if revoked_at.tzinfo else revoked_at.replace(tzinfo=timezone.utc)
        # JWT libraries commonly serialise iat to whole seconds while the
        # database stores token_revoked_at with microsecond precision. Without a
        # small leeway, a token issued immediately after login can be rejected
        # when a previous logout happened in the same second. Successful login
        # also clears token_revoked_at, but the leeway protects concurrent tabs
        # and legacy rows.
        if issued_at_dt is None or issued_at_dt + timedelta(seconds=2) <= revoked_dt:
            raise _credentials_exception()

    setattr(user, "auth_session_id", auth_session_id)
    setattr(user, "_auth_session_id", auth_session_id)
    return user


def get_current_active_user(
    current_user: account_models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> account_models.User:
    """Ensure the writer-side user is active and attach tenant context.

    Superusers remain platform actors, but their selected support AMO is exposed
    through ``active_amo_id``/``effective_amo_id`` so admin/support screens can
    be tenant-aware without silently converting the superuser into an AMO user.
    """
    if not getattr(current_user, "is_active", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user account",
        )
    CURRENT_ACTOR_ID.set(str(current_user.id))
    active_amo_id = current_user.amo_id
    effective_amo_id = current_user.amo_id

    if getattr(current_user, "is_superuser", False):
        active_amo_id = None
        effective_amo_id = None
        try:
            context = (
                db.query(account_models.UserActiveContext)
                .filter(account_models.UserActiveContext.user_id == str(current_user.id))
                .first()
            )
            if context and context.active_amo_id:
                amo = (
                    db.query(account_models.AMO)
                    .filter(
                        account_models.AMO.id == context.active_amo_id,
                        account_models.AMO.is_active.is_(True),
                    )
                    .first()
                )
                if amo:
                    active_amo_id = str(amo.id)
                    effective_amo_id = str(amo.id)
                    set_committed_value(current_user, "amo", amo)
        except Exception:
            active_amo_id = None
            effective_amo_id = None

        # Keep the persisted user unchanged. Attribute assignment here only sets
        # the request-scoped ORM instance for dependencies that still read amo_id.
        set_committed_value(current_user, "amo_id", active_amo_id)
        if active_amo_id is None:
            set_committed_value(current_user, "amo", None)
        setattr(current_user, "is_platform_context", True)

    setattr(current_user, "active_amo_id", active_amo_id)
    setattr(current_user, "effective_amo_id", effective_amo_id)
    from amodb.apps.accounts.tenant_authority import is_standing_admin, tenant_member
    from amodb.apps.accounts.tenant_authority import active_admin_profile_session
    from types import SimpleNamespace
    setattr(current_user, "_admin_profile_elevated", False)
    if tenant_member(current_user) and not is_standing_admin(current_user):
        setattr(current_user, "_admin_profile_elevated", active_admin_profile_session(
            db, current_user, SimpleNamespace(id=current_user.amo_id)
        ))
    from amodb.apps.accounts import access_control
    access_control.attach_user_access(db, current_user)
    return current_user


def require_admin(
    current_user: account_models.User = Depends(get_current_active_user),
) -> account_models.User:
    """
    Dependency that enforces an admin-level role.

    This is account/configuration administration, not regulatory management.
    Only SUPERUSER and AMO_ADMIN pass. KCAR management roles receive their
    workflow permissions through the relevant module guards and never inherit
    tenant-administrator access merely because they are managers.
    """
    if getattr(current_user, "is_superuser", False) or is_tenant_admin(current_user):
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient privileges",
    )


def get_current_actor_id() -> Optional[str]:
    return CURRENT_ACTOR_ID.get()


def require_capability(
    capability_code: str,
) -> Callable[[account_models.User, Session], account_models.User]:
    """Fail-closed capability gate against the writer-side authorization state."""

    def dependency(
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_db),
    ) -> account_models.User:
        try:
            from amodb.apps.accounts import access_control
            allowed = access_control.user_has_capability(
                db, user=current_user, capability_code=capability_code
            )
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authorization capability service unavailable",
            )

        if allowed:
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Capability '{capability_code}' is required",
        )

    return dependency


def require_module_access(
    module_code: str,
    level: str = "view",
) -> Callable[[account_models.User, Session], account_models.User]:
    """Enforce the tenant profile's module boundary before route logic.

    Module grants may narrow a compatibility persona. Existing operation-level
    role, scope, segregation-of-duties and personal-authorization checks remain
    authoritative inside each module and cannot be bypassed by this gate.
    """
    normalized_module = str(module_code or "").strip().lower()
    normalized_level = str(level or "view").strip().lower()
    if normalized_level not in {"view", "manage"}:
        raise ValueError("Module access level must be 'view' or 'manage'")

    def dependency(
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_db),
    ) -> account_models.User:
        # Standing AMO administrators are a tenant privilege assigned by the
        # platform superuser. Their module administration is broad by default;
        # module-specific regulated decision gates still apply downstream.
        if is_tenant_admin(current_user):
            return current_user
        if getattr(current_user, "is_superuser", False):
            if normalized_level == "view":
                return current_user
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Platform support identity cannot perform tenant operational mutations",
            )
        from amodb.apps.accounts import access_control
        if normalized_module not in access_control.MODULE_CODES:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unknown portal module access boundary",
            )
        required = f"portal.{normalized_module}.{normalized_level}"
        if access_control.user_has_capability(db, user=current_user, capability_code=required):
            return current_user
        if normalized_level == "view" and access_control.user_has_capability(
            db,
            user=current_user,
            capability_code=f"portal.{normalized_module}.manage",
        ):
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your tenant access profile does not include {normalized_module.replace('_', ' ')} access",
        )

    return dependency


def require_any_module_access(
    *module_codes: str,
    level: str = "view",
) -> Callable[[account_models.User, Session], account_models.User]:
    """Allow a shared router when any one of its owning modules is granted."""
    normalized_modules = tuple(
        dict.fromkeys(str(code or "").strip().lower() for code in module_codes if str(code or "").strip())
    )
    normalized_level = str(level or "view").strip().lower()
    if not normalized_modules:
        raise ValueError("At least one module access boundary is required")
    if normalized_level not in {"view", "manage"}:
        raise ValueError("Module access level must be 'view' or 'manage'")

    def dependency(
        current_user: account_models.User = Depends(get_current_active_user),
        db: Session = Depends(get_db),
    ) -> account_models.User:
        # Match require_module_access: standing tenant administrators can view
        # and configure every licensed tenant module until the platform
        # superuser removes their standing overlay. Operational decision gates
        # inside each module remain authoritative.
        if is_tenant_admin(current_user):
            return current_user
        if getattr(current_user, "is_superuser", False):
            if normalized_level == "view":
                return current_user
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Platform support identity cannot perform tenant operational mutations",
            )
        from amodb.apps.accounts import access_control
        unknown = [code for code in normalized_modules if code not in access_control.MODULE_CODES]
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unknown portal module access boundary",
            )
        for module_code in normalized_modules:
            if access_control.user_has_capability(
                db, user=current_user, capability_code=f"portal.{module_code}.{normalized_level}"
            ):
                return current_user
            if normalized_level == "view" and access_control.user_has_capability(
                db, user=current_user, capability_code=f"portal.{module_code}.manage"
            ):
                return current_user
        labels = ", ".join(code.replace("_", " ") for code in normalized_modules)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your tenant access profile does not include any of: {labels}",
        )

    return dependency


_MUTATING_HTTP_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def apply_module_access_boundary(
    router: APIRouter,
    *module_codes: str,
    path_prefixes: Sequence[str] | None = None,
) -> None:
    """Enforce profile ``view``/``manage`` grants on an existing router.

    FastAPI copies routes when routers are composed, so this is called after
    module composition and before application mounting.  Operation-level role,
    assignment, authorization and segregation checks remain authoritative.
    ``path_prefixes`` lets a shared aggregate (currently Stores/Procurement)
    retain separate module ownership instead of granting cross-module access.
    """
    normalized_modules = tuple(
        dict.fromkeys(
            str(code or "").strip().lower()
            for code in module_codes
            if str(code or "").strip()
        )
    )
    if not normalized_modules:
        raise ValueError("At least one module access boundary is required")
    normalized_prefixes = tuple(
        prefix for prefix in (path_prefixes or ()) if str(prefix or "").strip()
    )
    view_dependency = (
        require_module_access(normalized_modules[0], "view")
        if len(normalized_modules) == 1
        else require_any_module_access(*normalized_modules, level="view")
    )
    manage_dependency = (
        require_module_access(normalized_modules[0], "manage")
        if len(normalized_modules) == 1
        else require_any_module_access(*normalized_modules, level="manage")
    )
    boundary_key = (normalized_modules, normalized_prefixes)

    def attach(route: APIRoute, dependency: Callable) -> None:
        depends = Depends(dependency)
        route.dependencies.append(depends)
        route.dependant.dependencies.insert(
            0,
            get_parameterless_sub_dependant(
                depends=depends,
                path=route.path_format,
            ),
        )

    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        if normalized_prefixes and not any(
            str(route.path).startswith(prefix) for prefix in normalized_prefixes
        ):
            continue
        applied = set(getattr(route, "_portal_module_boundaries", set()))
        if boundary_key in applied:
            continue
        attach(route, view_dependency)
        if bool((route.methods or set()) & _MUTATING_HTTP_METHODS):
            attach(route, manage_dependency)
        applied.add(boundary_key)
        setattr(route, "_portal_module_boundaries", applied)


# ---------------------------------------------------------------------------
# ROLE-BASED ACCESS HELPER
# ---------------------------------------------------------------------------


def require_roles(
    *allowed_roles: Union[AccountRole, str],
) -> Callable[[account_models.User], account_models.User]:
    """
    Dependency factory to enforce that the current user has one of the given roles.

    Behaviour:
    - Platform SUPERUSER passes only when explicitly listed in `allowed_roles`.
    - The user's writer-side operational role must otherwise be in the set.
    - Tenant administrators inherit all tenant roles, never platform-only authority.
    - Administrator appointment/revocation uses its separate governance policy.
    """
    normalised_roles: Set[AccountRole] = set()
    for r in allowed_roles:
        if isinstance(r, AccountRole):
            normalised_roles.add(r)
        else:
            try:
                normalised_roles.add(AccountRole(r))
            except ValueError:
                raise ValueError(f"Unknown role {r!r} passed to require_roles()")

    def dependency(
        current_user: account_models.User = Depends(get_current_active_user),
    ) -> account_models.User:
        if getattr(current_user, "is_superuser", False):
            if AccountRole.SUPERUSER in normalised_roles:
                return current_user
            raise HTTPException(status_code=403, detail="Platform identity has no tenant operational role.")
        if not tenant_member(current_user):
            raise HTTPException(status_code=403, detail="A tenant identity is required for this operation.")
        if is_tenant_admin(current_user) and normalised_roles - {AccountRole.SUPERUSER}:
            return current_user

        if current_user.role not in normalised_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this operation",
            )
        return current_user

    return dependency
