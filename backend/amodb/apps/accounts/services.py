# backend/amodb/apps/accounts/services.py

from __future__ import annotations

from datetime import datetime, timedelta, date
from typing import List, Optional, Sequence, Tuple

import secrets
import string

from jose import JWTError, jwt  # noqa: F401  (imported for future token use)

from sqlalchemy import and_, or_, func, select  # noqa: F401
from sqlalchemy.orm import Session, joinedload

from amodb.security import (
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    get_password_hash,
    verify_password,
)
from . import models, schemas
from .models import MaintenanceScope, RegulatoryAuthority

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PASSWORD_RESET_TOKEN_TTL_MINUTES = 60 * 24  # 24 hours
MAX_LOGIN_ATTEMPTS = 5
ACCOUNT_LOCKOUT_MINUTES = 15


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class AuthenticationError(Exception):
    """Raised when login credentials are invalid or account is locked."""


class AuthorisationError(Exception):
    """Raised when a user tries to perform an action they are not authorised for."""


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _normalise_email(value: str) -> str:
    return value.strip().lower()


def _normalise_username(value: str) -> str:
    return value.strip().lower()


def _normalise_staff_code(value: str) -> str:
    # Staff codes are often formatted, but it's safer to force uppercase and strip.
    return value.strip().upper()


# ---------------------------------------------------------------------------
# User fetch helpers
# ---------------------------------------------------------------------------

def get_user_by_id(db: Session, user_id: str) -> Optional[models.User]:
    return (
        db.query(models.User)
        .options(joinedload(models.User.organisation))
        .filter(models.User.id == user_id)
        .first()
    )


def get_active_user_by_email(db: Session, email: str) -> Optional[models.User]:
    email = _normalise_email(email)
    return (
        db.query(models.User)
        .filter(
            models.User.email == email,
            models.User.is_active.is_(True),
            models.User.deleted_at.is_(None),
        )
        .first()
    )


def get_active_user_by_username(db: Session, username: str) -> Optional[models.User]:
    username = _normalise_username(username)
    return (
        db.query(models.User)
        .filter(
            models.User.username == username,
            models.User.is_active.is_(True),
            models.User.deleted_at.is_(None),
        )
        .first()
    )


def get_active_user_by_staff_code(
    db: Session, organisation_id: str, staff_code: str
) -> Optional[models.User]:
    staff_code = _normalise_staff_code(staff_code)
    return (
        db.query(models.User)
        .filter(
            models.User.organisation_id == organisation_id,
            models.User.staff_code == staff_code,
            models.User.is_active.is_(True),
            models.User.deleted_at.is_(None),
        )
        .first()
    )


# ---------------------------------------------------------------------------
# User lifecycle
# ---------------------------------------------------------------------------

def create_user(db: Session, data: schemas.UserCreate) -> models.User:
    email = _normalise_email(data.email)
    username = _normalise_username(data.username)
    staff_code = _normalise_staff_code(data.staff_code)

    # Enforce uniqueness within organisation
    if (
        db.query(models.User)
        .filter(
            models.User.organisation_id == data.organisation_id,
            or_(
                models.User.email == email,
                models.User.username == username,
                models.User.staff_code == staff_code,
            ),
        )
        .first()
        is not None
    ):
        raise ValueError("A user with this email, username or staff code already exists.")

    hashed = get_password_hash(data.password)

    user = models.User(
        organisation_id=data.organisation_id,
        staff_code=staff_code,
        username=username,
        email=email,
        full_name=data.full_name.strip(),
        role=data.role,
        department=data.department,
        is_active=True,
        is_superuser=data.is_superuser or False,
        is_certifying_staff=data.is_certifying_staff or False,
        regulatory_authority=data.regulatory_authority,
        licence_number=(data.licence_number or "").strip() or None,
        licence_expires_on=data.licence_expires_on,
        password_hash=hashed,
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
    if data.email is not None:
        email = _normalise_email(data.email)
        existing = (
            db.query(models.User)
            .filter(
                models.User.organisation_id == user.organisation_id,
                models.User.email == email,
                models.User.id != user.id,
            )
            .first()
        )
        if existing:
            raise ValueError("Another user with this email already exists.")
        user.email = email

    if data.username is not None:
        username = _normalise_username(data.username)
        existing = (
            db.query(models.User)
            .filter(
                models.User.organisation_id == user.organisation_id,
                models.User.username == username,
                models.User.id != user.id,
            )
            .first()
        )
        if existing:
            raise ValueError("Another user with this username already exists.")
        user.username = username

    if data.staff_code is not None:
        staff_code = _normalise_staff_code(data.staff_code)
        existing = (
            db.query(models.User)
            .filter(
                models.User.organisation_id == user.organisation_id,
                models.User.staff_code == staff_code,
                models.User.id != user.id,
            )
            .first()
        )
        if existing:
            raise ValueError("Another user with this staff code already exists.")
        user.staff_code = staff_code

    # Other mutable fields
    if data.full_name is not None:
        user.full_name = data.full_name.strip()

    if data.role is not None:
        user.role = data.role

    if data.department is not None:
        user.department = data.department

    if data.is_active is not None:
        user.is_active = data.is_active

    if data.is_superuser is not None:
        user.is_superuser = data.is_superuser

    if data.is_certifying_staff is not None:
        user.is_certifying_staff = data.is_certifying_staff

    if data.regulatory_authority is not None:
        user.regulatory_authority = data.regulatory_authority

    if data.licence_number is not None:
        user.licence_number = (data.licence_number or "").strip() or None

    if data.licence_expires_on is not None:
        user.licence_expires_on = data.licence_expires_on

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def soft_delete_user(db: Session, user: models.User) -> models.User:
    user.is_active = False
    user.deleted_at = datetime.utcnow()
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Authentication and access tokens
# ---------------------------------------------------------------------------

def _is_account_locked(user: models.User) -> bool:
    if user.locked_until and user.locked_until > datetime.utcnow():
        return True
    return False


def _register_failed_login(db: Session, user: models.User) -> None:
    user.failed_login_attempts += 1
    if user.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
        user.locked_until = datetime.utcnow() + timedelta(minutes=ACCOUNT_LOCKOUT_MINUTES)
    db.add(user)
    db.commit()


def _reset_failed_logins(db: Session, user: models.User) -> None:
    user.failed_login_attempts = 0
    user.locked_until = None
    db.add(user)
    db.commit()


def authenticate_user(
    db: Session,
    *,
    login: str,
    password: str,
) -> models.User:
    """
    Authenticate using either email or username.

    Raises AuthenticationError instead of returning None so that callers
    don't accidentally forget to handle failures.
    """
    login_norm = login.strip()
    user = None

    # Try email first
    if "@" in login_norm:
        user = get_active_user_by_email(db, login_norm)
    if user is None:
        # Fall back to username
        user = get_active_user_by_username(db, login_norm)

    if user is None or not user.is_active or user.deleted_at is not None:
        raise AuthenticationError("Invalid credentials.")

    if _is_account_locked(user):
        raise AuthenticationError("Account is temporarily locked due to failed logins.")

    if not verify_password(password, user.password_hash):
        _register_failed_login(db, user)
        raise AuthenticationError("Invalid credentials.")

    _reset_failed_logins(db, user)
    return user


def issue_access_token_for_user(user: models.User) -> schemas.Token:
    expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": user.id,
            "organisation_id": user.organisation_id,
            "role": user.role.value if hasattr(user.role, "value") else user.role,
            "is_superuser": user.is_superuser,
        },
        expires_delta=expires_delta,
    )
    return schemas.Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


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
    request_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Tuple[models.PasswordResetToken, str]:
    """
    Create a one-time password reset token.

    Returns (token_row, raw_token string). Only the raw token should be sent
    to the user; it is never stored in clear in the database.
    """
    raw_token = _generate_reset_token_raw()
    token_hash = get_password_hash(raw_token)
    expires_at = datetime.utcnow() + timedelta(minutes=PASSWORD_RESET_TOKEN_TTL_MINUTES)

    token_row = models.PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        request_ip=request_ip,
        request_user_agent=user_agent,
    )
    db.add(token_row)
    db.commit()
    db.refresh(token_row)
    return token_row, raw_token


def consume_password_reset_token(
    db: Session,
    raw_token: str,
) -> models.PasswordResetToken:
    """
    Find and mark a password reset token as used.

    Raises ValueError if the token is invalid or expired.
    """
    candidate_tokens: Sequence[models.PasswordResetToken] = (
        db.query(models.PasswordResetToken)
        .filter(models.PasswordResetToken.consumed_at.is_(None))
        .order_by(models.PasswordResetToken.created_at.desc())
        .all()
    )

    now = datetime.utcnow()
    for token in candidate_tokens:
        if token.expires_at and token.expires_at < now:
            continue
        if verify_password(raw_token, token.token_hash):
            token.consumed_at = now
            db.add(token)
            db.commit()
            db.refresh(token)
            return token

    raise ValueError("Invalid or expired reset token.")


def reset_password(
    db: Session,
    raw_token: str,
    new_password: str,
) -> models.User:
    token = consume_password_reset_token(db, raw_token)
    user = get_user_by_id(db, token.user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise ValueError("Account is not active.")

    user.password_hash = get_password_hash(new_password)
    db.add(user)
    db.commit()
    db.refresh(user)
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
    Return all current, non-suspended authorisations for the given user.

    This follows aviation practice:
    - Authorisation must be active and not revoked/suspended.
    - Valid_from/valid_until window must include 'at_date' (or today).
    - If crs_only=True => only authorisations whose AuthorisationType
      is flagged as 'can_issue_crs'.
    - Optional filters by maintenance scope and regulatory authority.
    """
    if at_date is None:
        at_date = date.today()

    q = (
        db.query(models.UserAuthorisation)
        .options(joinedload(models.UserAuthorisation.authorisation_type))
        .join(models.AuthorisationType)
        .filter(
            models.UserAuthorisation.user_id == user.id,
            models.UserAuthorisation.is_active.is_(True),
            models.UserAuthorisation.is_revoked.is_(False),
            models.UserAuthorisation.valid_from <= at_date,
            or_(
                models.UserAuthorisation.valid_until.is_(None),
                models.UserAuthorisation.valid_until >= at_date,
            ),
            models.AuthorisationType.is_active.is_(True),
        )
    )

    if crs_only:
        q = q.filter(models.AuthorisationType.can_issue_crs.is_(True))

    if maintenance_scope is not None:
        q = q.filter(models.AuthorisationType.maintenance_scope == maintenance_scope)

    if regulatory_authority is not None:
        # Allow types that either explicitly match or are generic (NULL)
        q = q.filter(
            or_(
                models.AuthorisationType.default_reg_authority == regulatory_authority,
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
            # If licence is missing or expired, this authorisation cannot be used.
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
    if not user.is_active or user.deleted_at is not None:
        return False
    if not user.is_certifying_staff:
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
    if not user.is_active or user.deleted_at is not None:
        raise AuthorisationError("User account is not active.")

    if not user.is_certifying_staff:
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
    organisation_id: str,
    aircraft_type: Optional[str],
    maintenance_scope: Optional[MaintenanceScope],
    regulatory_authority: Optional[RegulatoryAuthority],
    as_of_date: date,
) -> List[Tuple[models.User, models.UserAuthorisation]]:
    """
    Helper for the CRS app:
    Given a WO context (organisation, aircraft type, scope, authority),
    return all (User, UserAuthorisation) pairs that are currently allowed
    to issue a CRS.

    Intended use: suggest signatories in the UI, or validate selection.
    """
    # First, pull all active certifying staff in the organisation.
    staff: List[models.User] = (
        db.query(models.User)
        .filter(
            models.User.organisation_id == organisation_id,
            models.User.is_active.is_(True),
            models.User.deleted_at.is_(None),
            models.User.is_certifying_staff.is_(True),
        )
        .all()
    )

    results: List[Tuple[models.User, models.UserAuthorisation]] = []

    for user in staff:
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
