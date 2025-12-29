from __future__ import annotations

from datetime import datetime, timedelta, date, timezone
from typing import Dict, List, Optional, Tuple, Set
import math

import hashlib
import hmac
import json
import os
import secrets
import string

from jose import JWTError, jwt  # noqa: F401  (imported for future token use)

from fastapi import HTTPException
from sqlalchemy import or_, func
from sqlalchemy.orm import Session, joinedload, noload

from amodb.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    get_password_hash,
    verify_password,
)
from . import audit, models, schemas
from .models import (
    MaintenanceScope,
    RegulatoryAuthority,
    BillingTerm,
    LedgerEntryType,
    LicenseStatus,
    PaymentProvider,
    InvoiceStatus,
    WebhookStatus,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PASSWORD_RESET_TOKEN_TTL_MINUTES = 60 * 24  # 24 hours
MAX_LOGIN_ATTEMPTS = 3
LOCKOUT_SCHEDULE_SECONDS = (30, 90, 900)
MIN_PASSWORD_LENGTH = 12
DEFAULT_USAGE_WARN_THRESHOLD = float(os.getenv("USAGE_WARN_THRESHOLD", "0.8"))
METER_KEY_STORAGE_MB = "storage_mb"
METER_KEY_AUTOMATION_RUNS = "automation_runs"
METER_KEY_SCHEDULED_JOBS = "scheduled_jobs"
METER_KEY_NOTIFICATIONS = "notifications_sent"
METER_KEY_API_CALLS = "api_calls"
# Map meter keys to entitlement keys when limits are defined in different units
METER_LIMIT_KEY_MAP = {
    METER_KEY_STORAGE_MB: ("storage_gb", 1024),
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AuthenticationError(Exception):
    """Raised when login credentials are invalid or account is locked."""

    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class AuthorisationError(Exception):
    """Raised when a user tries to perform an action they are not authorised for."""


class IdempotencyError(Exception):
    """Raised when an idempotency key is reused with conflicting payload."""


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------


def _normalise_email(value: str) -> str:
    return value.strip().lower()


def _normalise_staff_code(value: str) -> str:
    # Staff codes are often formatted, but it's safer to force uppercase and strip.
    return value.strip().upper()


# ---------------------------------------------------------------------------
# Password policy
# ---------------------------------------------------------------------------


def _validate_password_strength(password: str) -> None:
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
        )

    has_upper = any(ch.isupper() for ch in password)
    has_lower = any(ch.islower() for ch in password)
    has_digit = any(ch.isdigit() for ch in password)
    has_symbol = any(not ch.isalnum() for ch in password)

    if not (has_upper and has_lower and has_digit and has_symbol):
        raise ValueError(
            "Password must include upper and lower case letters, a number, and a symbol."
        )


# ---------------------------------------------------------------------------
# Usage metering helpers
# ---------------------------------------------------------------------------


def megabytes_from_bytes(size_bytes: int) -> int:
    """
    Convert a byte count to whole megabytes (rounded up, minimum 1).
    """
    if size_bytes <= 0:
        return 0
    return max(1, math.ceil(size_bytes / (1024 * 1024)))


def _resolve_meter_limit_for_key(
    meter_key: str, entitlements: Dict[str, schemas.ResolvedEntitlement]
) -> tuple[Optional[int], bool]:
    """
    Resolve a numeric limit and unlimited flag for a given meter key.

    Supports explicit matches, plus any cross-unit mappings in METER_LIMIT_KEY_MAP
    (e.g., usage tracked in MB while entitlement is expressed in GB).
    """
    ent = entitlements.get(meter_key)
    if ent:
        return ent.limit, ent.is_unlimited

    mapped = METER_LIMIT_KEY_MAP.get(meter_key)
    if mapped:
        ent_key, multiplier = mapped
        mapped_ent = entitlements.get(ent_key)
        if mapped_ent:
            limit = None if mapped_ent.limit is None else mapped_ent.limit * multiplier
            return limit, mapped_ent.is_unlimited

    return None, False


# ---------------------------------------------------------------------------
# Security event helper
# ---------------------------------------------------------------------------


def _log_security_event(
    db: Session,
    *,
    user: Optional[models.User],
    amo: Optional[models.AMO],
    event_type: str,
    description: Optional[str],
    ip: Optional[str],
    user_agent: Optional[str],
) -> None:
    event = models.AccountSecurityEvent(
        user_id=user.id if user else None,
        amo_id=amo.id if amo else None,
        event_type=event_type,
        description=description,
        ip_address=ip,
        user_agent=user_agent,
    )
    db.add(event)
    db.commit()


# ---------------------------------------------------------------------------
# User fetch helpers
# ---------------------------------------------------------------------------


def get_user_by_id(db: Session, user_id: str) -> Optional[models.User]:
    return (
        db.query(models.User)
        .options(
            joinedload(models.User.amo),
            joinedload(models.User.department),
        )
        .filter(models.User.id == user_id)
        .first()
    )


def get_active_user_by_email(
    db: Session,
    amo_id: str,
    email: str,
) -> Optional[models.User]:
    email = _normalise_email(email)
    return (
        db.query(models.User)
        .filter(
            models.User.amo_id == amo_id,
            models.User.email == email,
            models.User.is_active.is_(True),
        )
        .first()
    )


def get_active_user_by_staff_code(
    db: Session,
    amo_id: str,
    staff_code: str,
) -> Optional[models.User]:
    staff_code = _normalise_staff_code(staff_code)
    return (
        db.query(models.User)
        .filter(
            models.User.amo_id == amo_id,
            models.User.staff_code == staff_code,
            models.User.is_active.is_(True),
        )
        .first()
    )


def get_global_superuser_by_email(
    db: Session,
    email: str,
) -> Optional[models.User]:
    """
    Look up a GLOBAL superuser (no AMO restriction) by email.

    Used for the root system owner who may not have amo_id set yet.
    """
    email = _normalise_email(email)
    return (
        db.query(models.User)
        .options(
            joinedload(models.User.amo),
            joinedload(models.User.department),
        )
        .filter(
            models.User.email == email,
            models.User.is_active.is_(True),
            models.User.is_superuser.is_(True),
        )
        .first()
    )


# ---------------------------------------------------------------------------
# User lifecycle
# ---------------------------------------------------------------------------


def create_user(db: Session, data: schemas.UserCreate) -> models.User:
    email = _normalise_email(data.email)
    staff_code = _normalise_staff_code(data.staff_code)

    # Ensure AMO exists
    amo = db.query(models.AMO).filter(models.AMO.id == data.amo_id).first()
    if not amo:
        raise ValueError("Invalid AMO id.")

    # Enforce uniqueness within AMO
    dup = (
        db.query(models.User)
        .filter(
            models.User.amo_id == data.amo_id,
            or_(
                models.User.email == email,
                models.User.staff_code == staff_code,
            ),
        )
        .first()
    )
    if dup:
        raise ValueError(
            "A user with this email or staff code already exists in this AMO."
        )

    first_name = data.first_name.strip()
    last_name = data.last_name.strip()
    full_name = (
        (data.full_name or "").strip()
        or f"{first_name} {last_name}".strip()
    )

    _validate_password_strength(data.password)
    hashed = get_password_hash(data.password)

    user = models.User(
        amo_id=data.amo_id,
        department_id=data.department_id,
        staff_code=staff_code,
        email=email,
        first_name=first_name,
        last_name=last_name,
        full_name=full_name,
        role=data.role,
        position_title=data.position_title,
        phone=data.phone,
        regulatory_authority=data.regulatory_authority,
        licence_number=(data.licence_number or "").strip() or None,
        licence_state_or_country=(data.licence_state_or_country or "").strip()
        or None,
        licence_expires_on=data.licence_expires_on,
        hashed_password=hashed,
        is_active=True,
        is_amo_admin=data.role == models.AccountRole.AMO_ADMIN,
        # is_system_account defaults to False in the model – human by default.
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session,
    user: models.User,
    data: schemas.UserUpdate,
) -> models.User:
    # Names
    name_changed = False
    if data.first_name is not None:
        user.first_name = data.first_name.strip()
        name_changed = True
    if data.last_name is not None:
        user.last_name = data.last_name.strip()
        name_changed = True
    if data.full_name is not None:
        user.full_name = data.full_name.strip()
    elif name_changed:
        user.full_name = f"{user.first_name} {user.last_name}".strip()

    # Role / org placement
    if data.role is not None:
        user.role = data.role
        if data.is_amo_admin is None:
            user.is_amo_admin = data.role == models.AccountRole.AMO_ADMIN
    if data.position_title is not None:
        user.position_title = data.position_title
    if data.phone is not None:
        user.phone = data.phone
    if data.department_id is not None:
        user.department_id = data.department_id

    # Regulatory
    if data.regulatory_authority is not None:
        user.regulatory_authority = data.regulatory_authority
    if data.licence_number is not None:
        user.licence_number = (data.licence_number or "").strip() or None
    if data.licence_state_or_country is not None:
        user.licence_state_or_country = (
            data.licence_state_or_country or ""
        ).strip() or None
    if data.licence_expires_on is not None:
        user.licence_expires_on = data.licence_expires_on

    # Flags
    if data.is_active is not None:
        # Simple deactivation timestamp to support off-boarding audit
        if user.is_active and not data.is_active and user.deactivated_at is None:
            user.deactivated_at = datetime.now(timezone.utc)
        user.is_active = data.is_active

    if data.is_amo_admin is not None:
        user.is_amo_admin = data.is_amo_admin

    # Optional: allow marking system/service accounts via API if schema supports it
    if hasattr(data, "is_system_account") and getattr(
        data, "is_system_account"
    ) is not None:
        user.is_system_account = bool(getattr(data, "is_system_account"))

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Authentication and access tokens
# ---------------------------------------------------------------------------


def _is_account_locked(user: models.User) -> bool:
    """
    Return True if the account is currently locked.

    Handles both naive and timezone-aware datetimes safely.
    """
    locked_until = user.locked_until
    if not locked_until:
        return False

    # Normalise to timezone-aware UTC
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    return locked_until > now


def _seconds_until_unlock(user: models.User) -> Optional[int]:
    locked_until = user.locked_until
    if not locked_until:
        return None
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    remaining = locked_until - now
    return max(0, int(remaining.total_seconds()))


def _notify_amo_admins_of_lockout(
    db: Session,
    *,
    user: models.User,
    amo: Optional[models.AMO],
    ip: Optional[str],
    user_agent: Optional[str],
) -> None:
    if not amo:
        return

    try:
        from amodb.apps.training import models as training_models
        from amodb.apps.training.models import TrainingNotificationSeverity
    except Exception:
        return

    admins = (
        db.query(models.User)
        .filter(
            models.User.amo_id == amo.id,
            models.User.is_active.is_(True),
            or_(
                models.User.is_amo_admin.is_(True),
                models.User.is_superuser.is_(True),
            ),
        )
        .all()
    )

    if not admins:
        return

    title = "Security alert: account lockout"
    body = (
        f"User {user.email} was locked out after repeated failed login attempts."
        f"\nIP: {ip or 'unknown'}"
        f"\nUser agent: {user_agent or 'unknown'}"
    )

    for admin in admins:
        note = training_models.TrainingNotification(
            amo_id=amo.id,
            user_id=admin.id,
            title=title,
            body=body,
            severity=TrainingNotificationSeverity.WARNING,
            dedupe_key=f"account-lockout:{user.id}:{user.lockout_count}",
        )
        db.add(note)

    db.commit()


def _register_failed_login(
    db: Session,
    user: models.User,
    amo: Optional[models.AMO],
    ip: Optional[str],
    user_agent: Optional[str],
) -> None:
    user.login_attempts = (user.login_attempts or 0) + 1

    _log_security_event(
        db,
        user=user,
        amo=amo,
        event_type="LOGIN_FAILED",
        description="Invalid password.",
        ip=ip,
        user_agent=user_agent,
    )

    if user.login_attempts < MAX_LOGIN_ATTEMPTS:
        db.add(user)
        db.commit()
        return

    user.login_attempts = 0
    user.lockout_count = (user.lockout_count or 0) + 1
    lockout_index = min(user.lockout_count - 1, len(LOCKOUT_SCHEDULE_SECONDS) - 1)
    lockout_seconds = LOCKOUT_SCHEDULE_SECONDS[lockout_index]
    user.locked_until = datetime.now(timezone.utc) + timedelta(
        seconds=lockout_seconds
    )
    db.add(user)
    db.commit()

    _log_security_event(
        db,
        user=user,
        amo=amo,
        event_type="LOCKOUT",
        description=(
            f"Account locked for {lockout_seconds} seconds after repeated failures."
        ),
        ip=ip,
        user_agent=user_agent,
    )

    if user.lockout_count >= 3:
        _log_security_event(
            db,
            user=user,
            amo=amo,
            event_type="LOCKOUT_ESCALATED",
            description="Lockout escalation threshold reached; notify AMO admin.",
            ip=ip,
            user_agent=user_agent,
        )
        _notify_amo_admins_of_lockout(db, user=user, amo=amo, ip=ip, user_agent=user_agent)


def _reset_failed_logins(
    db: Session,
    user: models.User,
    amo: Optional[models.AMO],
    ip: Optional[str],
    user_agent: Optional[str],
) -> None:
    user.login_attempts = 0
    user.locked_until = None
    user.lockout_count = 0
    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = ip
    user.last_login_user_agent = user_agent
    db.add(user)
    db.commit()

    _log_security_event(
        db,
        user=user,
        amo=amo,
        event_type="LOGIN_SUCCESS",
        description=None,
        ip=ip,
        user_agent=user_agent,
    )


def _find_amo_by_slug_or_code(db: Session, amo_slug: str) -> Optional[models.AMO]:
    amo_slug_norm = (amo_slug or "").strip().lower()
    if not amo_slug_norm:
        return None

    amo = (
        db.query(models.AMO)
        .filter(
            func.lower(models.AMO.login_slug) == amo_slug_norm,
            models.AMO.is_active.is_(True),
        )
        .first()
    )
    if amo:
        return amo

    return (
        db.query(models.AMO)
        .filter(
            func.lower(models.AMO.amo_code) == amo_slug_norm,
            models.AMO.is_active.is_(True),
        )
        .first()
    )


def get_user_for_login(
    db: Session,
    *,
    amo_slug: str,
    email: str,
) -> Optional[models.User]:
    email = _normalise_email(email)

    # Look up AMO case-insensitively on login_slug or amo_code
    amo = _find_amo_by_slug_or_code(db, amo_slug)
    if not amo:
        return None

    # Now fetch the user in that AMO
    user = (
        db.query(models.User)
        .options(
            joinedload(models.User.amo),
            joinedload(models.User.department),
        )
        .filter(
            models.User.amo_id == amo.id,
            models.User.email == email,
        )
        .first()
    )
    if not user or not user.is_active:
        return None

    return user


def authenticate_user(
    db: Session,
    *,
    login_req: schemas.LoginRequest,
    ip: Optional[str],
    user_agent: Optional[str],
) -> Optional[models.User]:
    """
    Password-based login using AMO slug + email + password.

    Normal path:
    - AMO slug is provided and we look up a user scoped to that AMO.

    Special path:
    - If amo_slug is blank / "system" / "root", allow a GLOBAL SUPERUSER
      (is_superuser=True, possibly amo_id=None) to log in by email.

    Returns a user on success, or None on failure (lockout, bad credentials).
    System/service accounts are not allowed to authenticate via this flow.
    """
    email = _normalise_email(login_req.email)
    amo_slug_raw = (login_req.amo_slug or "").strip()
    amo_slug = amo_slug_raw.lower()

    user: Optional[models.User] = None
    amo: Optional[models.AMO] = None

    # -----------------------------------------------------------------------
    # Global superuser login (system owner)
    # -----------------------------------------------------------------------
    if amo_slug in {"", "system", "root"}:
        user = get_global_superuser_by_email(db, email=email)

        if not user:
            _log_security_event(
                db,
                user=None,
                amo=None,
                event_type="LOGIN_FAILED",
                description="Unknown superuser or inactive account.",
                ip=ip,
                user_agent=user_agent,
            )
            return None
        # For global superuser, amo stays None
    else:
        # -------------------------------------------------------------------
        # Normal AMO-scoped login
        # -------------------------------------------------------------------
        user = get_user_for_login(
            db=db,
            amo_slug=amo_slug_raw,
            email=email,
        )

        if user:
            amo = user.amo
        else:
            # If AMO exists, log a generic failed login.
            amo = _find_amo_by_slug_or_code(db, amo_slug_raw)
            _log_security_event(
                db,
                user=None,
                amo=amo,
                event_type="LOGIN_FAILED",
                description="Unknown user or inactive account.",
                ip=ip,
                user_agent=user_agent,
            )
            return None

    # Block system/AI/service accounts from using human login flows.
    if getattr(user, "is_system_account", False):
        _log_security_event(
            db,
            user=user,
            amo=amo,
            event_type="LOGIN_FAILED",
            description="System/service account attempted password login.",
            ip=ip,
            user_agent=user_agent,
        )
        return None

    if _is_account_locked(user):
        retry_after = _seconds_until_unlock(user)
        _log_security_event(
            db,
            user=user,
            amo=amo,
            event_type="LOCKOUT",
            description="Account locked due to repeated failed logins.",
            ip=ip,
            user_agent=user_agent,
        )
        raise AuthenticationError(
            "Account locked due to repeated failed attempts.",
            retry_after_seconds=retry_after,
        )

    if not verify_password(login_req.password, user.hashed_password):
        _register_failed_login(db, user, amo, ip, user_agent)
        raise AuthenticationError("Invalid credentials.")

    _reset_failed_logins(db, user, amo, ip, user_agent)
    return user


def issue_access_token_for_user(user: models.User) -> Tuple[str, int]:
    """
    Create a JWT access token for the user.

    Returns (token_string, expires_in_seconds).

    Note: token payload includes user id, AMO, department, role and key flags.
    """
    expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(user.id),
        "amo_id": user.amo_id,
        "department_id": user.department_id,
        "role": (
            user.role.value if hasattr(user.role, "value") else str(user.role)
        ),
        "is_superuser": bool(getattr(user, "is_superuser", False)),
        "is_amo_admin": bool(getattr(user, "is_amo_admin", False)),
        "is_system_account": bool(getattr(user, "is_system_account", False)),
    }

    access_token = create_access_token(
        data=payload,
        expires_delta=expires_delta,
    )
    return access_token, int(ACCESS_TOKEN_EXPIRE_MINUTES * 60)


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------


def _generate_reset_token_raw(length: int = 32) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def create_password_reset_token(
    db: Session,
    user: models.User,
    *,

    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> str:
    """
    Create a one-time password reset token.

    Returns the raw token string (only this should be sent to the user).
    """
    raw_token = _generate_reset_token_raw()
    token_hash = get_password_hash(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=PASSWORD_RESET_TOKEN_TTL_MINUTES
    )

    token_row = models.PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        request_ip=ip,
        request_user_agent=user_agent,
    )
    db.add(token_row)
    db.commit()
    db.refresh(token_row)

    _log_security_event(
        db,
        user=user,
        amo=user.amo,
        event_type="PASSWORD_RESET_REQUEST",
        description="Password reset requested.",
        ip=ip,
        user_agent=user_agent,
    )

    return raw_token


def _find_matching_reset_token(
    db: Session,
    raw_token: str,
) -> Optional[models.PasswordResetToken]:
    now = datetime.now(timezone.utc)
    candidate_tokens: List[models.PasswordResetToken] = (
        db.query(models.PasswordResetToken)
        .filter(models.PasswordResetToken.used_at.is_(None))
        .order_by(models.PasswordResetToken.issued_at.desc())
        .all()
    )

    for token in candidate_tokens:
        if token.expires_at and token.expires_at < now:
            continue
        if verify_password(raw_token, token.token_hash):
            return token

    return None


def redeem_password_reset_token(
    db: Session,
    *,
    raw_token: str,
    new_password: str,
) -> Optional[models.User]:
    """
    Redeem a password reset token and set a new password.

    Returns the user on success, or None if the token is invalid/expired.
    """
    token = _find_matching_reset_token(db, raw_token)
    if not token:
        return None

    token.used_at = datetime.now(timezone.utc)
    db.add(token)

    user = token.user
    if not user or not user.is_active:
        db.commit()
        return None

    _validate_password_strength(new_password)
    user.hashed_password = get_password_hash(new_password)
    db.add(user)
    db.commit()
    db.refresh(user)

    _log_security_event(
        db,
        user=user,
        amo=user.amo,
        event_type="PASSWORD_RESET",
        description="Password reset via token.",
        ip=token.request_ip,
        user_agent=token.request_user_agent,
    )

    return user


# ---------------------------------------------------------------------------
# CRS-related authorisation helpers
# ---------------------------------------------------------------------------


def get_active_authorisations_for_user(
    db: Session,
    *,
    user: models.User,
    at_date: Optional[date] = None,
    maintenance_scope: Optional[MaintenanceScope] = None,
    regulatory_authority: Optional[RegulatoryAuthority] = None,
    crs_only: bool = False,
) -> List[models.UserAuthorisation]:
    """
    Return all current, non-revoked authorisations for the given user.

    This follows aviation practice:
    - Authorisation must be active on 'at_date' (or today if None).
    - Not revoked.
    - Optional filters by maintenance scope and regulatory authority.
    - If crs_only=True, only types marked can_issue_crs.
    """
    if at_date is None:
        at_date = date.today()

    q = (
        db.query(models.UserAuthorisation)
        .options(joinedload(models.UserAuthorisation.authorisation_type))
        .join(models.AuthorisationType)
        .filter(
            models.UserAuthorisation.user_id == user.id,
            models.UserAuthorisation.revoked_at.is_(None),
            models.UserAuthorisation.effective_from <= at_date,
            or_(
                models.UserAuthorisation.expires_at.is_(None),
                models.UserAuthorisation.expires_at >= at_date,
            ),
            models.AuthorisationType.is_active.is_(True),
        )
    )

    if crs_only:
        q = q.filter(models.AuthorisationType.can_issue_crs.is_(True))

    if maintenance_scope is not None:
        q = q.filter(
            models.AuthorisationType.maintenance_scope == maintenance_scope
        )

    if regulatory_authority is not None:
        q = q.filter(
            or_(
                models.AuthorisationType.default_reg_authority
                == regulatory_authority,
                models.AuthorisationType.default_reg_authority.is_(None),
            )
        )

    auths: List[models.UserAuthorisation] = q.all()

    # Enforce "requires_valid_licence" at the business logic level.
    filtered: List[models.UserAuthorisation] = []
    for ua in auths:
        atype = ua.authorisation_type
        if atype is None:
            continue

        if atype.requires_valid_licence:
            if not user.licence_expires_on or user.licence_expires_on < at_date:
                continue

        filtered.append(ua)

    return filtered


def can_user_issue_crs(
    db: Session,
    *,
    user: models.User,
    at_date: Optional[date] = None,
    maintenance_scope: Optional[MaintenanceScope] = None,
    regulatory_authority: Optional[RegulatoryAuthority] = None,
) -> bool:
    if not user.is_active:
        return False
    if not user.is_certifying_staff():
        return False

    auths = get_active_authorisations_for_user(
        db,
        user=user,
        at_date=at_date,
        maintenance_scope=maintenance_scope,
        regulatory_authority=regulatory_authority,
        crs_only=True,
    )
    return len(auths) > 0


def require_user_can_issue_crs(
    db: Session,
    *,
    user: models.User,
    at_date: Optional[date] = None,
    maintenance_scope: Optional[MaintenanceScope] = None,
    regulatory_authority: Optional[RegulatoryAuthority] = None,
) -> models.UserAuthorisation:
    """
    Return one active CRS-signing authorisation for this user or raise AuthorisationError.
    """
    if not user.is_active:
        raise AuthorisationError("User account is not active.")

    if not user.is_certifying_staff():
        raise AuthorisationError("User is not marked as certifying staff.")

    auths = get_active_authorisations_for_user(
        db,
        user=user,
        at_date=at_date,
        maintenance_scope=maintenance_scope,
        regulatory_authority=regulatory_authority,
        crs_only=True,
    )

    if not auths:
        raise AuthorisationError(
            "User has no current CRS-signing authorisation for this scope/authority."
        )

    # If there are multiple, just pick the first; front-end could later allow
    # the user to explicitly select one.
    return auths[0]


def get_current_certifying_staff_for_wo(
    db: Session,
    *,
    organisation_id: str,  # interpreted as amo_id in this context
    aircraft_type: Optional[str],
    maintenance_scope: Optional[MaintenanceScope],
    regulatory_authority: Optional[RegulatoryAuthority],
    as_of_date: date,
) -> List[Tuple[models.User, models.UserAuthorisation]]:
    """
    Helper for the CRS app:
    Given a WO context (AMO, aircraft type, scope, authority),
    return all (User, UserAuthorisation) pairs that are currently allowed
    to issue a CRS.
    """
    staff: List[models.User] = (
        db.query(models.User)
        .filter(
            models.User.amo_id == organisation_id,
            models.User.is_active.is_(True),
        )
        .all()
    )

    results: List[Tuple[models.User, models.UserAuthorisation]] = []

    for user in staff:
        if not user.is_certifying_staff():
            continue

        auths = get_active_authorisations_for_user(
            db,
            user=user,
            at_date=as_of_date,
            maintenance_scope=maintenance_scope,
            regulatory_authority=regulatory_authority,
            crs_only=True,
        )
        for ua in auths:
            results.append((user, ua))

    return results


# ---------------------------------------------------------------------------
# BILLING / LICENSING
# ---------------------------------------------------------------------------


def _license_is_active(license: models.TenantLicense, at: datetime) -> bool:
    if license.status == LicenseStatus.EXPIRED:
        if (
            license.trial_grace_expires_at
            and at <= license.trial_grace_expires_at
            and not license.is_read_only
        ):
            return True
        return False
    if license.status == LicenseStatus.CANCELLED:
        return False
    if license.current_period_start and license.current_period_start > at:
        return False
    if license.current_period_end and license.current_period_end < at:
        return False
    if license.trial_ends_at and license.status == LicenseStatus.TRIALING:
        return license.trial_ends_at >= at
    return True


def grant_entitlement(
    db: Session,
    *,
    license_id: str,
    key: str,
    limit: Optional[int] = None,
    is_unlimited: bool = False,
    description: Optional[str] = None,
) -> models.LicenseEntitlement:
    """
    Create or update a license entitlement and emit an audit entry.
    """
    license = (
        db.query(models.TenantLicense)
        .filter(models.TenantLicense.id == license_id)
        .first()
    )
    if not license:
        raise ValueError("License not found.")

    entitlement = (
        db.query(models.LicenseEntitlement)
        .filter(
            models.LicenseEntitlement.license_id == license_id,
            models.LicenseEntitlement.key == key,
        )
        .first()
    )
    event = "ENTITLEMENT_GRANTED"
    if entitlement:
        entitlement.limit = limit
        entitlement.is_unlimited = is_unlimited
        entitlement.description = description
        event = "ENTITLEMENT_UPDATED"
    else:
        entitlement = models.LicenseEntitlement(
            license_id=license_id,
            key=key,
            limit=limit,
            is_unlimited=is_unlimited,
            description=description,
        )
    db.add(entitlement)
    db.commit()
    _log_billing_audit(
        db,
        amo_id=license.amo_id,
        event=event,
        details={
            "license_id": license_id,
            "key": key,
            "limit": limit,
            "is_unlimited": is_unlimited,
        },
    )
    return entitlement


def revoke_entitlement(
    db: Session,
    *,
    license_id: str,
    key: str,
) -> bool:
    """
    Remove a license entitlement (no-op if not present) and log the change.
    """
    entitlement = (
        db.query(models.LicenseEntitlement)
        .filter(
            models.LicenseEntitlement.license_id == license_id,
            models.LicenseEntitlement.key == key,
        )
        .first()
    )
    if not entitlement:
        return False

    license = (
        db.query(models.TenantLicense)
        .filter(models.TenantLicense.id == license_id)
        .first()
    )
    db.delete(entitlement)
    db.commit()
    _log_billing_audit(
        db,
        amo_id=license.amo_id if license else None,
        event="ENTITLEMENT_REVOKED",
        details={"license_id": license_id, "key": key},
    )
    return True


def resolve_entitlements(
    db: Session,
    *,
    amo_id: str,
    as_of: Optional[datetime] = None,
) -> Dict[str, schemas.ResolvedEntitlement]:
    """
    Return the strongest entitlement per key for the AMO.

    - Only active/trialing licenses with current coverage are considered.
    - Unlimited entitlements always win over numeric limits.
    - For numeric entitlements, the highest limit wins.
    """
    as_of = as_of or datetime.now(timezone.utc)
    resolved: Dict[str, schemas.ResolvedEntitlement] = {}

    licenses = (
        db.query(models.TenantLicense)
        .options(
            joinedload(models.TenantLicense.entitlements),
            noload(models.TenantLicense.amo),
            noload(models.TenantLicense.catalog_sku),
            noload(models.TenantLicense.ledger_entries),
            noload(models.TenantLicense.usage_meters),
        )
        .filter(models.TenantLicense.amo_id == amo_id)
        .all()
    )

    for license in licenses:
        if not _license_is_active(license, as_of):
            continue

        for entitlement in license.entitlements:
            if entitlement.is_unlimited:
                resolved[entitlement.key] = schemas.ResolvedEntitlement(
                    key=entitlement.key,
                    is_unlimited=True,
                    limit=None,
                    source_license_id=license.id,
                    license_term=license.term,
                    license_status=license.status,
                )
                continue

            candidate_limit = entitlement.limit if entitlement.limit is not None else 0
            existing = resolved.get(entitlement.key)

            if existing is None or (
                existing.limit is not None and candidate_limit > existing.limit
            ):
                resolved[entitlement.key] = schemas.ResolvedEntitlement(
                    key=entitlement.key,
                    is_unlimited=False,
                    limit=candidate_limit,
                    source_license_id=license.id,
                    license_term=license.term,
                    license_status=license.status,
                )

    return resolved


def record_usage(
    db: Session,
    *,
    amo_id: str,
    meter_key: str,
    quantity: int,
    license_id: Optional[str] = None,
    at: Optional[datetime] = None,
    attach_license: bool = True,
    commit: bool = True,
) -> models.UsageMeter:
    """
    Increment usage for a meter, creating it if needed.

    attach_license:
        When True, link the meter to the current active/trialing subscription if no
        license_id is supplied.

    commit:
        When False, the caller is responsible for committing the session (useful when
        recording usage inside a broader transaction).
    """
    if quantity < 0:
        raise ValueError("Quantity must be non-negative.")

    at = at or datetime.now(timezone.utc)
    meter = (
        db.query(models.UsageMeter)
        .filter(
            models.UsageMeter.amo_id == amo_id,
            models.UsageMeter.meter_key == meter_key,
        )
        .first()
    )

    if meter is None:
        meter = models.UsageMeter(
            amo_id=amo_id,
            meter_key=meter_key,
            license_id=license_id,
            used_units=0,
        )

    # Preserve any existing license link but allow initial association
    if license_id and meter.license_id is None:
        meter.license_id = license_id
    elif attach_license and meter.license_id is None:
        current_license = get_current_subscription(db, amo_id=amo_id)
        if current_license:
            meter.license_id = current_license.id

    meter.used_units += quantity
    meter.last_recorded_at = at

    db.add(meter)
    if commit:
        db.commit()
        db.refresh(meter)
    else:
        db.flush()
    return meter


def _assert_ledger_idempotency(
    existing: models.LedgerEntry,
    *,
    amount_cents: int,
    currency: str,
    entry_type: LedgerEntryType,
    license_id: Optional[str],
) -> None:
    if (
        existing.amount_cents != amount_cents
        or existing.currency != currency
        or existing.entry_type != entry_type
        or existing.license_id != license_id
    ):
        raise IdempotencyError(
            "Idempotency key reuse with a different ledger payload is not allowed."
        )


def append_ledger_entry(
    db: Session,
    *,
    amo_id: str,
    amount_cents: int,
    currency: str,
    entry_type: LedgerEntryType,
    description: Optional[str],
    idempotency_key: str,
    license_id: Optional[str] = None,
    recorded_at: Optional[datetime] = None,
) -> models.LedgerEntry:
    """
    Append a ledger entry, enforcing idempotency per AMO + key.
    """
    if not idempotency_key:
        raise ValueError("idempotency_key is required.")

    existing = (
        db.query(models.LedgerEntry)
        .options(
            noload(models.LedgerEntry.amo),
            noload(models.LedgerEntry.license),
        )
        .filter(
            models.LedgerEntry.amo_id == amo_id,
            models.LedgerEntry.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing:
        _assert_ledger_idempotency(
            existing,
            amount_cents=amount_cents,
            currency=currency,
            entry_type=entry_type,
            license_id=license_id,
        )
        return existing

    entry = models.LedgerEntry(
        amo_id=amo_id,
        license_id=license_id,
        amount_cents=amount_cents,
        currency=currency,
        entry_type=entry_type,
        description=description,
        idempotency_key=idempotency_key,
        recorded_at=recorded_at or datetime.now(timezone.utc),
    )
    db.add(entry)
    db.commit()
    return entry


# ---------------------------------------------------------------------------
# BILLING OPERATIONS / IDEMPOTENCY
# ---------------------------------------------------------------------------


def _hash_payload(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def register_idempotency_key(
    db: Session,
    *,
    scope: str,
    key: str,
    payload: dict,
) -> models.IdempotencyKey:
    if not key:
        raise ValueError("idempotency key is required")

    payload_hash = _hash_payload(payload)
    existing = (
        db.query(models.IdempotencyKey)
        .filter(
            models.IdempotencyKey.scope == scope,
            models.IdempotencyKey.key == key,
        )
        .first()
    )
    if existing:
        if existing.payload_hash != payload_hash:
            raise IdempotencyError("Idempotency key reuse with different payload.")
        return existing

    idem = models.IdempotencyKey(
        scope=scope,
        key=key,
        payload_hash=payload_hash,
    )
    db.add(idem)
    db.commit()
    return idem


def _log_billing_audit(db: Session, *, amo_id: Optional[str], event: str, details: object) -> Optional[models.BillingAuditLog]:
    """
    Best-effort audit logger shared by billing workflows.
    """
    return audit.safe_record_audit_event(db, amo_id=amo_id, event=event, details=details)


def add_payment_method(
    db: Session,
    *,
    amo_id: str,
    data: schemas.PaymentMethodCreate,
    idempotency_key: str,
) -> models.PaymentMethod:
    register_idempotency_key(
        db,
        scope=f"payment_method:{amo_id}",
        key=idempotency_key,
        payload=data.model_dump(),
    )

    method = (
        db.query(models.PaymentMethod)
        .filter(
            models.PaymentMethod.amo_id == amo_id,
            models.PaymentMethod.provider == data.provider,
            models.PaymentMethod.external_ref == data.external_ref,
        )
        .first()
    )
    if method:
        return method

    if data.is_default:
        db.query(models.PaymentMethod).filter(
            models.PaymentMethod.amo_id == amo_id,
            models.PaymentMethod.is_default.is_(True),
        ).update({"is_default": False})

    method = models.PaymentMethod(
        amo_id=amo_id,
        provider=data.provider,
        external_ref=data.external_ref,
        display_name=data.display_name,
        card_last4=data.card_last4,
        card_exp_month=data.card_exp_month,
        card_exp_year=data.card_exp_year,
        is_default=data.is_default,
    )
    db.add(method)
    db.commit()
    _log_billing_audit(
        db,
        amo_id=amo_id,
        event="PAYMENT_METHOD_ADDED",
        details=f"Provider={data.provider} ref={data.external_ref}",
    )
    return method


def remove_payment_method(
    db: Session,
    *,
    amo_id: str,
    payment_method_id: str,
    idempotency_key: str,
) -> None:
    register_idempotency_key(
        db,
        scope=f"payment_method_delete:{amo_id}",
        key=idempotency_key,
        payload={"payment_method_id": payment_method_id},
    )
    method = (
        db.query(models.PaymentMethod)
        .filter(
            models.PaymentMethod.id == payment_method_id,
            models.PaymentMethod.amo_id == amo_id,
        )
        .first()
    )
    if method:
        db.delete(method)
        db.commit()
        _log_billing_audit(
            db,
            amo_id=amo_id,
            event="PAYMENT_METHOD_REMOVED",
            details=f"id={payment_method_id}",
        )


def list_payment_methods(
    db: Session,
    *,
    amo_id: str,
) -> List[models.PaymentMethod]:
    """
    Return payment methods for the AMO, newest first.
    """
    return (
        db.query(models.PaymentMethod)
        .options(
            noload(models.PaymentMethod.amo),
        )
        .filter(models.PaymentMethod.amo_id == amo_id)
        .order_by(models.PaymentMethod.created_at.desc())
        .all()
    )


def list_catalog_skus(
    db: Session,
    *,
    include_inactive: bool = False,
) -> List[models.CatalogSKU]:
    query = db.query(models.CatalogSKU)
    if not include_inactive:
        query = query.filter(models.CatalogSKU.is_active.is_(True))
    return query.order_by(models.CatalogSKU.amount_cents.asc()).all()


def _price_for_sku(db: Session, sku_code: str) -> models.CatalogSKU:
    sku = (
        db.query(models.CatalogSKU)
        .filter(
            models.CatalogSKU.code == sku_code,
            models.CatalogSKU.is_active.is_(True),
        )
        .first()
    )
    if not sku:
        raise ValueError("Unknown or inactive SKU.")
    return sku


def start_trial(
    db: Session,
    *,
    amo_id: str,
    sku_code: str,
    idempotency_key: str,
) -> models.TenantLicense:
    sku = _price_for_sku(db, sku_code)
    register_idempotency_key(
        db,
        scope=f"trial:{amo_id}",
        key=idempotency_key,
        payload={"sku": sku_code},
    )

    # Enforce a single trial per tenant per SKU (evergreen)
    prior_trial = (
        db.query(models.TenantLicense)
        .filter(
            models.TenantLicense.amo_id == amo_id,
            models.TenantLicense.sku_id == sku.id,
            models.TenantLicense.trial_started_at.isnot(None),
        )
        .first()
    )
    if prior_trial:
        raise ValueError("Trial for this SKU already consumed for this tenant.")

    now = datetime.now(timezone.utc)
    trial_end = now + timedelta(days=sku.trial_days or 0)
    license = models.TenantLicense(
        amo_id=amo_id,
        sku_id=sku.id,
        term=sku.term,
        status=LicenseStatus.TRIALING,
        trial_started_at=now,
        trial_ends_at=trial_end,
        trial_grace_expires_at=None,
        is_read_only=False,
        current_period_start=now,
        current_period_end=trial_end,
    )
    db.add(license)
        db.commit()

    _log_billing_audit(
        db,
        amo_id=amo_id,
        event="TRIAL_STARTED",
        details={
            "sku": sku.code,
            "license_id": license.id,
            "trial_ends_at": trial_end.isoformat(),
        },
    )
    return license


def purchase_sku(
    db: Session,
    *,
    amo_id: str,
    sku_code: str,
    idempotency_key: str,
    purchase_kind: str = "PURCHASE",
    expected_amount_cents: Optional[int] = None,
    expected_currency: Optional[str] = None,
) -> Tuple[models.TenantLicense, models.LedgerEntry, models.BillingInvoice]:
    sku = _price_for_sku(db, sku_code)
    if expected_amount_cents is not None and expected_amount_cents != sku.amount_cents:
        raise ValueError("Client price does not match server SKU pricing.")
    if expected_currency is not None and expected_currency != sku.currency:
        raise ValueError("Client currency does not match server SKU pricing.")
    register_idempotency_key(
        db,
        scope=f"purchase:{amo_id}",
        key=idempotency_key,
        payload={"sku": sku_code, "purchase_kind": purchase_kind},
    )

    _log_billing_audit(
        db,
        amo_id=amo_id,
        event="PAYMENT_ATTEMPT",
        details={
            "sku": sku.code,
            "purchase_kind": purchase_kind,
            "amount_cents": sku.amount_cents,
            "currency": sku.currency,
            "idempotency_key": idempotency_key,
        },
    )

    now = datetime.now(timezone.utc)
    existing = (
        db.query(models.TenantLicense)
        .filter(
            models.TenantLicense.amo_id == amo_id,
            models.TenantLicense.status.in_(
                [LicenseStatus.ACTIVE, LicenseStatus.TRIALING]
            ),
        )
        .all()
    )
    for lic in existing:
        lic.status = LicenseStatus.CANCELLED
        lic.canceled_at = now

    license = models.TenantLicense(
        amo_id=amo_id,
        sku_id=sku.id,
        term=sku.term,
        status=LicenseStatus.ACTIVE,
        is_read_only=False,
        current_period_start=now,
        current_period_end=now + timedelta(days=30 if sku.term == BillingTerm.MONTHLY else 365),
    )
    db.add(license)
    db.commit()

    ledger = append_ledger_entry(
        db,
        amo_id=amo_id,
        amount_cents=sku.amount_cents,
        currency=sku.currency,
        entry_type=LedgerEntryType.CHARGE,
        description=f"{purchase_kind}:{sku.code}",
        idempotency_key=idempotency_key,
        license_id=license.id,
    )

    invoice = models.BillingInvoice(
        amo_id=amo_id,
        license_id=license.id,
        ledger_entry_id=ledger.id,
        amount_cents=sku.amount_cents,
        currency=sku.currency,
        status=InvoiceStatus.PAID if sku.amount_cents == 0 else InvoiceStatus.PENDING,
        description=f"Invoice for {sku.code}",
        idempotency_key=idempotency_key,
        issued_at=now,
        due_at=now if sku.amount_cents == 0 else now + timedelta(days=7),
        paid_at=now if sku.amount_cents == 0 else None,
    )
    db.add(invoice)
    db.commit()

    _log_billing_audit(
        db,
        amo_id=amo_id,
        event=purchase_kind,
        details={
            "sku": sku.code,
            "license_id": license.id,
            "amount_cents": sku.amount_cents,
            "currency": sku.currency,
            "invoice_id": invoice.id,
        },
    )
    return license, ledger, invoice


def cancel_subscription(
    db: Session,
    *,
    amo_id: str,
    effective_date: datetime,
    idempotency_key: str,
) -> Optional[models.TenantLicense]:
    register_idempotency_key(
        db,
        scope=f"cancel:{amo_id}",
        key=idempotency_key,
        payload={"effective_date": effective_date.isoformat()},
    )
    license = (
        db.query(models.TenantLicense)
        .filter(
            models.TenantLicense.amo_id == amo_id,
            models.TenantLicense.status.in_(
                [LicenseStatus.ACTIVE, LicenseStatus.TRIALING]
            ),
        )
        .order_by(models.TenantLicense.created_at.desc())
        .first()
    )
    if license:
        license.status = LicenseStatus.CANCELLED
        license.canceled_at = effective_date
        license.current_period_end = effective_date
        db.add(license)
        db.commit()
        _log_billing_audit(
            db,
            amo_id=amo_id,
            event="CANCELLED",
            details={
                "license_id": license.id,
                "effective": effective_date.isoformat(),
            },
        )
    return license


def list_invoices(db: Session, *, amo_id: str) -> List[models.BillingInvoice]:
    return (
        db.query(models.BillingInvoice)
        .filter(models.BillingInvoice.amo_id == amo_id)
        .order_by(models.BillingInvoice.issued_at.desc())
        .all()
    )


def get_current_subscription(db: Session, *, amo_id: str) -> Optional[models.TenantLicense]:
    active_or_trialing = (
        db.query(models.TenantLicense)
        .filter(
            models.TenantLicense.amo_id == amo_id,
            models.TenantLicense.status.in_(
                [LicenseStatus.ACTIVE, LicenseStatus.TRIALING]
            ),
        )
        .order_by(models.TenantLicense.current_period_end.desc())
        .first()
    )
    if active_or_trialing:
        return active_or_trialing

    now = datetime.now(timezone.utc)
    return (
        db.query(models.TenantLicense)
        .filter(
            models.TenantLicense.amo_id == amo_id,
            models.TenantLicense.status == LicenseStatus.EXPIRED,
            models.TenantLicense.trial_grace_expires_at.isnot(None),
            models.TenantLicense.trial_grace_expires_at >= now,
        )
        .order_by(models.TenantLicense.trial_grace_expires_at.desc())
        .first()
    )


def list_usage_meters(db: Session, *, amo_id: str) -> List[models.UsageMeter]:
    return (
        db.query(models.UsageMeter)
        .filter(models.UsageMeter.amo_id == amo_id)
        .order_by(models.UsageMeter.meter_key)
        .all()
    )


def roll_billing_periods_and_alert(
    db: Session,
    *,
    as_of: Optional[datetime] = None,
    warn_threshold: float = DEFAULT_USAGE_WARN_THRESHOLD,
) -> dict:
    """
    Rolls subscription periods that have ended and logs alerts for meters nearing limits.

    Returns a summary dict for logging/cron visibility.
    """
    now = as_of or datetime.now(timezone.utc)
    rolled: List[str] = []
    expired: List[str] = []
    warned: List[str] = []

    # 1) Roll or expire licenses where needed
    delta_by_term = {
        BillingTerm.MONTHLY: timedelta(days=30),
        BillingTerm.BI_ANNUAL: timedelta(days=182),
        BillingTerm.ANNUAL: timedelta(days=365),
    }
    grace_period = timedelta(days=7)
    has_payment_method = {
        row[0]: True
        for row in db.query(models.PaymentMethod.amo_id).distinct().all()
        if row[0]
    }
    licenses = (
        db.query(models.TenantLicense)
        .filter(
            models.TenantLicense.status.in_([LicenseStatus.ACTIVE, LicenseStatus.TRIALING])
        )
        .all()
    )
    for license in licenses:
        if (
            license.status == LicenseStatus.TRIALING
            and license.trial_ends_at
            and license.trial_ends_at <= now
        ):
            # Auto-convert to paid if a payment method is available
            if has_payment_method.get(license.amo_id):
                delta = delta_by_term.get(license.term, timedelta(days=30))
                license.status = LicenseStatus.ACTIVE
                license.current_period_start = license.trial_ends_at
                license.current_period_end = license.trial_ends_at + delta
                license.trial_grace_expires_at = None
                license.is_read_only = False
                db.add(license)
                _log_billing_audit(
                    db,
                    amo_id=license.amo_id,
                    event="TRIAL_CONVERTED",
                    details={
                        "license_id": license.id,
                        "converted_at": now.isoformat(),
                        "next_period_end": license.current_period_end.isoformat(),
                    },
                )
            else:
                license.status = LicenseStatus.EXPIRED
                license.current_period_end = license.trial_ends_at
                if not license.trial_grace_expires_at:
                    license.trial_grace_expires_at = license.trial_ends_at + grace_period
                    _log_billing_audit(
                        db,
                        amo_id=license.amo_id,
                        event="TRIAL_GRACE_STARTED",
                        details={
                            "license_id": license.id,
                            "grace_until": license.trial_grace_expires_at.isoformat(),
                        },
                    )
                license.is_read_only = now >= (license.trial_grace_expires_at or now)
                db.add(license)
                _log_billing_audit(
                    db,
                    amo_id=license.amo_id,
                    event="TRIAL_EXPIRED",
                    details={
                        "license_id": license.id,
                        "trial_ended": license.trial_ends_at.isoformat(),
                    },
                )
                expired.append(license.id)
            continue

        if license.current_period_end and license.current_period_end <= now:
            delta = delta_by_term.get(license.term, timedelta(days=30))
            prev_end = license.current_period_end
            license.current_period_start = prev_end
            license.current_period_end = prev_end + delta
            if license.status != LicenseStatus.ACTIVE:
                license.status = LicenseStatus.ACTIVE
            db.add(license)
            _log_billing_audit(
                db,
                amo_id=license.amo_id,
                event="PERIOD_ROLLED",
                details={
                    "license_id": license.id,
                    "next_period_end": license.current_period_end.isoformat(),
                },
            )
            rolled.append(license.id)

    # 1b) Flip read-only after grace for expired trials
    expired_grace = (
        db.query(models.TenantLicense)
        .filter(
            models.TenantLicense.status == LicenseStatus.EXPIRED,
            models.TenantLicense.trial_grace_expires_at.isnot(None),
        )
        .all()
    )
    for license in expired_grace:
        if license.trial_grace_expires_at and license.trial_grace_expires_at <= now:
            if not license.is_read_only:
                license.is_read_only = True
                db.add(license)
                _log_billing_audit(
                    db,
                    amo_id=license.amo_id,
                    event="TRIAL_LOCKED",
                    details={
                        "license_id": license.id,
                        "locked_at": now.isoformat(),
                        "grace_until": license.trial_grace_expires_at.isoformat(),
                    },
                )

    db.commit()

    # 2) Emit alerts for usage meters approaching limits
    warn_pct = int(warn_threshold * 100)
    amo_ids: Set[str] = {
        row[0]
        for row in db.query(models.UsageMeter.amo_id).distinct().all()
        if row[0]
    }
    for amo_id in amo_ids:
        entitlements = resolve_entitlements(db, amo_id=amo_id, as_of=now)
        for meter in list_usage_meters(db, amo_id=amo_id):
            limit, is_unlimited = _resolve_meter_limit_for_key(meter.meter_key, entitlements)
            if is_unlimited or limit in (None, 0):
                continue
            percent = int(min(100, round((meter.used_units / limit) * 100)))
            if percent >= warn_pct:
                _log_billing_audit(
                    db,
                    amo_id=amo_id,
                    event="USAGE_THRESHOLD",
                    details={
                        "meter": meter.meter_key,
                        "used_units": meter.used_units,
                        "limit": limit,
                        "percent": percent,
                    },
                )
                warned.append(f"{amo_id}:{meter.meter_key}")

    return {
        "rolled_licenses": rolled,
        "expired_licenses": expired,
        "warned_meters": warned,
    }


def _compute_backoff_seconds(attempt_count: int, *, base: int = 5, cap: int = 3600) -> int:
    delay = base * (2 ** max(attempt_count - 1, 0))
    return min(delay, cap)


def handle_webhook(
    db: Session,
    *,
    provider: PaymentProvider,
    payload: dict,
    signature: str,
    external_event_id: str,
    event_type: Optional[str] = None,
    should_fail: bool = False,
) -> models.WebhookEvent:
    secret = (
        os.getenv("PSP_WEBHOOK_SECRET") or ""
    )
    if not secret:
        raise HTTPException(status_code=500, detail="Webhook secret not configured.")

    computed = hmac.new(
        secret.encode("utf-8"),
        msg=json.dumps(payload, sort_keys=True).encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(computed, signature or ""):
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")

    register_idempotency_key(
        db,
        scope=f"webhook:{provider.value}",
        key=external_event_id,
        payload=payload,
    )

    log = _log_billing_audit(
        db,
        amo_id=None,
        event="WEBHOOK_RECEIVED",
        details={
            "provider": provider.value,
            "external_event_id": external_event_id,
            "event_type": event_type,
        },
    )

    event = models.WebhookEvent(
        provider=provider,
        external_event_id=external_event_id,
        signature=signature,
        event_type=event_type,
        payload=json.dumps(payload, sort_keys=True),
        status=WebhookStatus.PROCESSED if not should_fail else WebhookStatus.FAILED,
        attempt_count=1,
        processed_at=datetime.now(timezone.utc) if not should_fail else None,
        audit_log_id=log.id if log else None,
    )
    if should_fail:
        event.status = WebhookStatus.FAILED
        event.last_error = "Processing failed"
        event.next_retry_at = datetime.now(timezone.utc) + timedelta(
            seconds=_compute_backoff_seconds(event.attempt_count)
        )
    db.add(event)
    db.commit()
    return event
