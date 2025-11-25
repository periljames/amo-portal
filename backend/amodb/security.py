from datetime import datetime, timedelta
import os
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .database import get_db  # write DB for auth flows
from amodb.apps.accounts import models as account_models
from amodb.apps.accounts.models import AccountRole

# Used by FastAPI’s OAuth2 flow docs / OpenAPI
# This is the endpoint that issues tokens now.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    default="pbkdf2_sha256",
    deprecated="auto",
)

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))


# -------------------------------------------------------------------
# PASSWORD UTILITIES
# -------------------------------------------------------------------

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


# -------------------------------------------------------------------
# TOKEN CREATION
# -------------------------------------------------------------------

def create_access_token(
    *,
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT with arbitrary payload.

    Common fields in `data`:
    - sub: user.id (string)
    - amo_id: AMO id (string or None)
    - department_id: Department id (string or None)
    - role: user's role (e.g. 'CERTIFYING_ENGINEER')
    - is_superuser / is_amo_admin: boolean flags for admin logic
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# -------------------------------------------------------------------
# LOOKUPS
# -------------------------------------------------------------------

def get_user_by_id(db: Session, user_id: str) -> Optional[account_models.User]:
    return (
        db.query(account_models.User)
        .filter(account_models.User.id == user_id)
        .first()
    )


# -------------------------------------------------------------------
# CURRENT USER DEPENDENCIES
# -------------------------------------------------------------------

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> account_models.User:
    """
    Decode JWT, load accounts.User from DB, and fail hard if anything is wrong.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            raise credentials_exception
        user_id = str(sub)
    except (JWTError, ValueError):
        raise credentials_exception

    user = get_user_by_id(db, user_id=user_id)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: account_models.User = Depends(get_current_user),
) -> account_models.User:
    """
    Reject inactive accounts early.
    """
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def require_superuser(
    current_user: account_models.User = Depends(get_current_active_user),
) -> account_models.User:
    """
    Global platform owner gate.

    Use this for operations that must only be done by the root/system owner,
    such as environment-wide configuration, AI system setup, etc.
    """
    if current_user.is_superuser:
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Superuser privileges required",
    )


def require_admin(
    current_user: account_models.User = Depends(get_current_active_user),
) -> account_models.User:
    """
    Admin gate:

    - Global superuser (platform owner), OR
    - AMO admin (per-organisation admin), OR
    - Quality/Safety managers where appropriate.

    This is what accounts_admin router depends on.
    """
    if current_user.is_superuser or current_user.is_amo_admin:
        return current_user

    # Allow Quality Manager (and optionally Safety Manager) as admin-level
    if current_user.role in {
        AccountRole.QUALITY_MANAGER,
        AccountRole.SAFETY_MANAGER,
    }:
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient privileges",
    )
