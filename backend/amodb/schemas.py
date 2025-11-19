from datetime import datetime
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, EmailStr


# ---------------- USER SCHEMAS ----------------

class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: Optional[str] = "user"


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class UserRead(UserBase):
    id: int
    user_code: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------------- AUTH SCHEMAS ----------------

class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: Optional[EmailStr] = None


# ---------------- RETENTION / ARCHIVE SCHEMAS ----------------

class ArchivedUserSummary(BaseModel):
    id: int
    user_code: str
    email: EmailStr
    full_name: str
    role: str
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
    archived_at: datetime
    delete_after: datetime
    snapshot: Dict[str, Any]
