# backend/amodb/apps/accounts/schemas.py

from __future__ import annotations

from datetime import datetime, date
from typing import Optional, List

from pydantic import BaseModel, EmailStr, Field

from .models import RegulatoryAuthority, AccountRole, MaintenanceScope


# ---------------------------------------------------------------------------
# BASE SHARED OBJECTS
# ---------------------------------------------------------------------------


class AMOBase(BaseModel):
    amo_code: str
    name: str
    icao_code: Optional[str] = None
    country: Optional[str] = None
    login_slug: str
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    time_zone: Optional[str] = None


class AMOCreate(AMOBase):
    pass


class AMOUpdate(BaseModel):
    name: Optional[str] = None
    icao_code: Optional[str] = None
    country: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    time_zone: Optional[str] = None
    is_active: Optional[bool] = None


class AMORead(AMOBase):
    id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True



class DepartmentBase(BaseModel):
    code: str = Field(..., description="Short code, e.g. 'PLANNING'")
    name: str
    default_route: Optional[str] = None
    sort_order: int = 100


class DepartmentCreate(DepartmentBase):
    amo_id: str


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    default_route: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class DepartmentRead(DepartmentBase):
    id: str
    amo_id: str
    is_active: bool

    class Config:
        from_attributes = True



# ---------------------------------------------------------------------------
# USER SCHEMAS
# ---------------------------------------------------------------------------


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: AccountRole
    position_title: Optional[str] = None
    phone: Optional[str] = None

    regulatory_authority: Optional[RegulatoryAuthority] = None
    licence_number: Optional[str] = None
    licence_state_or_country: Optional[str] = None
    licence_expires_on: Optional[date] = None


class UserCreate(UserBase):
    amo_id: str
    department_id: Optional[str] = None
    staff_code: str
    password: str


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[AccountRole] = None
    position_title: Optional[str] = None
    phone: Optional[str] = None
    department_id: Optional[str] = None

    regulatory_authority: Optional[RegulatoryAuthority] = None
    licence_number: Optional[str] = None
    licence_state_or_country: Optional[str] = None
    licence_expires_on: Optional[date] = None

    is_active: Optional[bool] = None
    is_amo_admin: Optional[bool] = None


class UserSelfUpdate(BaseModel):
    """
    Fields that a normal user is allowed to change about themselves.
    """

    full_name: Optional[str] = None
    position_title: Optional[str] = None
    phone: Optional[str] = None


class UserRead(UserBase):
    id: str
    amo_id: str
    department_id: Optional[str] = None
    staff_code: str
    is_active: bool
    is_superuser: bool
    is_amo_admin: bool
    last_login_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True



# ---------------------------------------------------------------------------
# AUTHORISATIONS
# ---------------------------------------------------------------------------


class AuthorisationTypeBase(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    maintenance_scope: MaintenanceScope = MaintenanceScope.LINE
    regulation_reference: Optional[str] = None
    can_issue_crs: bool = False
    requires_dual_sign: bool = False
    requires_valid_licence: bool = True


class AuthorisationTypeCreate(AuthorisationTypeBase):
    amo_id: str


class AuthorisationTypeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    maintenance_scope: Optional[MaintenanceScope] = None
    regulation_reference: Optional[str] = None
    can_issue_crs: Optional[bool] = None
    requires_dual_sign: Optional[bool] = None
    requires_valid_licence: Optional[bool] = None
    is_active: Optional[bool] = None


class AuthorisationTypeRead(AuthorisationTypeBase):
    id: str
    amo_id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True



class UserAuthorisationBase(BaseModel):
    authorisation_type_id: str
    scope_text: Optional[str] = None
    effective_from: date
    expires_at: Optional[date] = None


class UserAuthorisationCreate(UserAuthorisationBase):
    user_id: str
    granted_by_user_id: Optional[str] = None


class UserAuthorisationUpdate(BaseModel):
    scope_text: Optional[str] = None
    effective_from: Optional[date] = None
    expires_at: Optional[date] = None
    revoked_at: Optional[datetime] = None
    revoked_reason: Optional[str] = None


class UserAuthorisationRead(UserAuthorisationBase):
    id: str
    user_id: str
    granted_by_user_id: Optional[str] = None
    revoked_at: Optional[datetime] = None
    revoked_reason: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True



# ---------------------------------------------------------------------------
# AUTH / TOKENS
# ---------------------------------------------------------------------------


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead
    amo: AMORead
    department: Optional[DepartmentRead] = None


class TokenData(BaseModel):
    sub: str
    amo_id: Optional[str] = None
    department_id: Optional[str] = None
    role: Optional[AccountRole] = None
    exp: Optional[int] = None


class LoginRequest(BaseModel):
    amo_slug: str = Field(..., description="AMO login slug, e.g. 'maintenance.safa03'")
    email: EmailStr
    password: str


# ---------------------------------------------------------------------------
# PASSWORD RESET
# ---------------------------------------------------------------------------


class PasswordResetRequest(BaseModel):
    amo_slug: str
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


# ---------------------------------------------------------------------------
# SECURITY EVENTS
# ---------------------------------------------------------------------------


class SecurityEventRead(BaseModel):
    id: str
    user_id: Optional[str]
    amo_id: Optional[str]
    event_type: str
    description: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
