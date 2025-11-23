# backend/amodb/security.py

from datetime import datetime, timedelta
import os
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from . import models
from .database import get_db  # write DB for auth flows

# Used by FastAPI’s OAuth2 flow docs
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

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
    user: models.User,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT for the given user.

    - sub: stringified user.id (not email)
    - embeds role / AMO / department for quick routing on frontend.
    """
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    to_encode = {
        "sub": str(user.id),
        "exp": expire,
        "role": user.role,
        "amo_code": user.amo_code,
        "department_code": user.department_code,
        "is_superuser": user.is_superuser,
        "is_amo_admin": user.is_amo_admin,
    }

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# -------------------------------------------------------------------
# LOOKUPS
# -------------------------------------------------------------------

def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.email == email).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.id == user_id).first()


def authenticate_user(db: Session, email: str, password: str) -> Optional[models.User]:
    """
    Email + password login. Returns the user or None.
    """
    user = get_user_by_email(db, email=email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


# -------------------------------------------------------------------
# CURRENT USER DEPENDENCIES
# -------------------------------------------------------------------

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    """
    Decode JWT, load user from DB, and fail hard if anything is wrong.
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
        user_id = int(sub)
    except (JWTError, ValueError):
        raise credentials_exception

    user = get_user_by_id(db, user_id=user_id)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    """
    Reject inactive accounts early.
    """
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def require_admin(
    current_user: models.User = Depends(get_current_active_user),
) -> models.User:
    """
    Admin gate:

    - Global superuser (platform owner), OR
    - AMO admin (per-organisation admin), OR
    - Certain high-privilege roles for backwards compatibility.
    """
    if current_user.is_superuser or current_user.is_amo_admin:
        return current_user

    # Backwards compatibility with role-driven access
    if current_user.role and current_user.role.lower() in {
        "admin",
        "quality_manager",
        "hr_manager",
    }:
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient privileges",
    )
