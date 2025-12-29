from __future__ import annotations

from datetime import datetime, timedelta, date, timezone
from typing import Dict, List, Optional, Tuple

import secrets
import string

from jose import JWTError, jwt  # noqa: F401  (imported for future token use)

from sqlalchemy import or_, func
from sqlalchemy.orm import Session, joinedload, noload

from amodb.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    get_password_hash,
    verify_password,
)
from . import models, schemas
from .models import (
    MaintenanceScope,
    RegulatoryAuthority,
    BillingTerm,
    LedgerEntryType,
    LicenseStatus,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PASSWORD_RESET_TOKEN_TTL_MINUTES = 60 * 24  # 24 hours
MAX_LOGIN_ATTEMPTS = 3
LOCKOUT_SCHEDULE_SECONDS = (30, 90, 900)
MIN_PASSWORD_LENGTH = 12


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
    if license.status in {LicenseStatus.CANCELLED, LicenseStatus.EXPIRED}:
        return False
    if license.current_period_start and license.current_period_start > at:
        return False
    if license.current_period_end and license.current_period_end < at:
        return False
    if license.trial_ends_at and license.status == LicenseStatus.TRIALING:
        return license.trial_ends_at >= at
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
) -> models.UsageMeter:
    """
    Increment usage for a meter, creating it if needed.
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

    meter.used_units += quantity
    meter.last_recorded_at = at

    db.add(meter)
    db.commit()
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
