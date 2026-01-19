# backend/amodb/apps/accounts/schemas.py

from __future__ import annotations

from datetime import datetime, date
from typing import Any, Optional, Literal

from pydantic import BaseModel, EmailStr, Field

from .models import (
    RegulatoryAuthority,
    AccountRole,
    MaintenanceScope,
    AMOAssetKind,
    BillingTerm,
    LicenseStatus,
    LedgerEntryType,
    PaymentProvider,
    InvoiceStatus,
)

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
# AMO ASSETS
# ---------------------------------------------------------------------------


class AMOAssetBase(BaseModel):
    kind: AMOAssetKind
    name: Optional[str] = None
    description: Optional[str] = None
    original_filename: str
    storage_path: str
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None
    sha256: Optional[str] = None


class AMOAssetCreate(AMOAssetBase):
    amo_id: str
    is_active: Optional[bool] = True


class AMOAssetUpdate(BaseModel):
    kind: Optional[AMOAssetKind] = None
    name: Optional[str] = None
    description: Optional[str] = None
    original_filename: Optional[str] = None
    storage_path: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None
    sha256: Optional[str] = None
    is_active: Optional[bool] = None


class AMOAssetRead(AMOAssetBase):
    id: str
    amo_id: str
    is_active: bool
    uploaded_by_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AMOAssetSummary(BaseModel):
    amo_id: str
    crs_logo_filename: Optional[str] = None
    crs_logo_content_type: Optional[str] = None
    crs_logo_uploaded_at: Optional[datetime] = None
    crs_template_filename: Optional[str] = None
    crs_template_content_type: Optional[str] = None
    crs_template_uploaded_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# USER SCHEMAS
# ---------------------------------------------------------------------------


class UserBase(BaseModel):
    email: EmailStr

    # split names + optional full_name for convenience
    first_name: str
    last_name: str
    full_name: Optional[str] = None

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
    first_name: Optional[str] = None
    last_name: Optional[str] = None
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

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    position_title: Optional[str] = None
    phone: Optional[str] = None


class UserRead(UserBase):
    id: str
    amo_id: str
    department_id: Optional[str] = None
    staff_code: str

    # For reads we guarantee full_name is present
    full_name: str

    is_active: bool
    is_superuser: bool
    is_amo_admin: bool
    must_change_password: bool
    last_login_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# BOOTSTRAP: FIRST SUPERUSER PAYLOAD
# ---------------------------------------------------------------------------


class FirstSuperuserCreate(BaseModel):
    """
    Payload for /auth/first-superuser.

    NOTE:
    - No role
    - No amo_id
    - No licence fields

    The endpoint will:
    - create (or reuse) a ROOT AMO
    - force role = SUPERUSER
    - set is_superuser = True, is_amo_admin = True
    """
    email: EmailStr
    first_name: str
    last_name: str
    full_name: Optional[str] = None
    staff_code: str
    password: str
    position_title: Optional[str] = None
    phone: Optional[str] = None


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


class LoginContextResponse(BaseModel):
    login_slug: str
    amo_code: Optional[str] = None
    amo_name: Optional[str] = None
    is_platform: bool = False


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


# ---------------------------------------------------------------------------
# PASSWORD RESET
# ---------------------------------------------------------------------------


class PasswordResetRequest(BaseModel):
    amo_slug: str
    email: EmailStr
    delivery_method: Literal["email", "whatsapp", "both"] = "email"


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


# ---------------------------------------------------------------------------
# BILLING / LICENSING
# ---------------------------------------------------------------------------


class CatalogSKUBase(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    term: BillingTerm
    trial_days: int = Field(0, ge=0)
    amount_cents: int = Field(..., ge=0, description="Price in the smallest currency unit.")
    currency: str = "USD"
    is_active: bool = True


class CatalogSKUCreate(CatalogSKUBase):
    pass


class CatalogSKURead(CatalogSKUBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TenantLicenseCreate(BaseModel):
    amo_id: str
    sku_id: str
    term: BillingTerm
    status: LicenseStatus = LicenseStatus.TRIALING
    trial_started_at: Optional[datetime] = None
    trial_ends_at: Optional[datetime] = None
    trial_grace_expires_at: Optional[datetime] = None
    is_read_only: bool = False
    current_period_start: datetime
    current_period_end: Optional[datetime] = None
    notes: Optional[str] = None


class TenantLicenseRead(TenantLicenseCreate):
    id: str
    canceled_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LicenseEntitlementCreate(BaseModel):
    license_id: str
    key: str
    limit: Optional[int] = Field(None, ge=0)
    is_unlimited: bool = False
    description: Optional[str] = None


class LicenseEntitlementRead(LicenseEntitlementCreate):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True


class UsageMeterRead(BaseModel):
    id: str
    amo_id: str
    license_id: Optional[str] = None
    meter_key: str
    used_units: int
    last_recorded_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LedgerEntryCreate(BaseModel):
    amo_id: str
    license_id: Optional[str] = None
    amount_cents: int
    currency: str = "USD"
    entry_type: LedgerEntryType
    description: Optional[str] = None
    idempotency_key: str
    recorded_at: datetime


class LedgerEntryRead(LedgerEntryCreate):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True


class PaymentMethodCreate(BaseModel):
    amo_id: str
    provider: PaymentProvider
    external_ref: str
    display_name: Optional[str] = None
    card_last4: Optional[str] = None
    card_exp_month: Optional[int] = None
    card_exp_year: Optional[int] = None
    is_default: bool = False


class PaymentMethodRead(PaymentMethodCreate):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaymentMethodUpsertRequest(PaymentMethodCreate):
    idempotency_key: str


class ResolvedEntitlement(BaseModel):
    key: str
    is_unlimited: bool
    limit: Optional[int] = None
    source_license_id: str
    license_term: BillingTerm
    license_status: LicenseStatus


class SubscriptionRead(BaseModel):
    id: str
    amo_id: str
    sku_id: str
    term: BillingTerm
    status: LicenseStatus
    trial_started_at: Optional[datetime]
    trial_ends_at: Optional[datetime]
    trial_grace_expires_at: Optional[datetime]
    is_read_only: bool
    current_period_start: datetime
    current_period_end: Optional[datetime]
    canceled_at: Optional[datetime]

    class Config:
        from_attributes = True


class InvoiceRead(BaseModel):
    id: str
    amo_id: str
    license_id: Optional[str]
    ledger_entry_id: Optional[str]
    amount_cents: int
    currency: str
    status: InvoiceStatus
    description: Optional[str]
    issued_at: datetime
    due_at: Optional[datetime]
    paid_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TrialStartRequest(BaseModel):
    sku_code: str
    idempotency_key: str


class PurchaseRequest(BaseModel):
    sku_code: str
    idempotency_key: str
    purchase_kind: str = "PURCHASE"
    expected_amount_cents: Optional[int] = None
    currency: Optional[str] = None


class CancelSubscriptionRequest(BaseModel):
    effective_date: datetime
    idempotency_key: str


class AuditEventCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=128)
    details: Optional[dict[str, Any]] = None


class PaymentMethodMutationRequest(BaseModel):
    idempotency_key: str


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


# ---------------------------------------------------------------------------
# PLATFORM SETTINGS (SUPERUSER)
# ---------------------------------------------------------------------------


class PlatformSettingsBase(BaseModel):
    api_base_url: Optional[str] = None
    acme_directory_url: Optional[str] = None
    acme_client: Optional[str] = None
    certificate_status: Optional[str] = None
    certificate_issuer: Optional[str] = None
    certificate_expires_at: Optional[datetime] = None
    last_renewed_at: Optional[datetime] = None
    notes: Optional[str] = None


class PlatformSettingsUpdate(PlatformSettingsBase):
    pass


class PlatformSettingsRead(PlatformSettingsBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
