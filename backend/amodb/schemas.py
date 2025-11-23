# backend/amodb/schemas.py

from datetime import datetime
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, EmailStr


# -------------------------------------------------------------------
# USER SCHEMAS
# -------------------------------------------------------------------

class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: Optional[str] = "user"

    # Context for routing, permissions, dashboards
    amo_code: Optional[str] = None
    department_code: Optional[str] = None


class UserCreate(UserBase):
    """
    Used when creating a user (including the very first admin).

    Admin flags (`is_superuser`, `is_amo_admin`) are not exposed here
    by default to avoid casual misuse. The bootstrap endpoint will
    set them server-side.
    """
    password: str


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None

    amo_code: Optional[str] = None
    department_code: Optional[str] = None

    # Optional privilege changes – only certain roles may use these
    is_superuser: Optional[bool] = None
    is_amo_admin: Optional[bool] = None


class UserRead(UserBase):
    id: int
    user_code: str
    is_active: bool
    is_superuser: bool
    is_amo_admin: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# -------------------------------------------------------------------
# AUTH SCHEMAS
# -------------------------------------------------------------------

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    """
    Decoded token payload we care about.
    """
    user_id: Optional[int] = None
    role: Optional[str] = None
    amo_code: Optional[str] = None
    department_code: Optional[str] = None
    is_superuser: Optional[bool] = None
    is_amo_admin: Optional[bool] = None


# -------------------------------------------------------------------
# RETENTION / ARCHIVE SCHEMAS
# -------------------------------------------------------------------

class ArchivedUserSummary(BaseModel):
    id: int
    user_code: str
    email: EmailStr
    full_name: str
    role: str
    amo_code: Optional[str] = None
    department_code: Optional[str] = None
    archived_at: datetime
    delete_after: datetime

    class Config:
        from_attributes = True


class ArchivedUserDetail(BaseModel):
    id: int
    user_code: str
    email: EmailStr
    full_name: str
    role: str
    amo_code: Optional[str] = None
    department_code: Optional[str] = None
    archived_at: datetime
    delete_after: datetime
    snapshot: Dict[str, Any]
