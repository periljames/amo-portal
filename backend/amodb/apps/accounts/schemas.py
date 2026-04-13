# backend/amodb/apps/accounts/schemas.py

from __future__ import annotations

from datetime import datetime, date
from typing import Any, Optional, Literal, List

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
    ModuleSubscriptionStatus,
    DataMode,
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
    is_demo: Optional[bool] = None


class AMOCreate(AMOBase):
    pass


class AMOUpdate(BaseModel):
    name: Optional[str] = None
    icao_code: Optional[str] = None
    country: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    time_zone: Optional[str] = None
    is_demo: Optional[bool] = None
    is_active: Optional[bool] = None


class TrialExtendRequest(BaseModel):
    extend_days: int = Field(..., ge=1, le=3650)


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


class StaffCodeSuggestions(BaseModel):
    suggestions: List[str]



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
    secondary_phone: Optional[str] = None

    regulatory_authority: Optional[RegulatoryAuthority] = None
    licence_number: Optional[str] = None
    licence_state_or_country: Optional[str] = None
    licence_expires_on: Optional[date] = None


class UserCreate(UserBase):
    amo_id: str
    department_id: Optional[str] = None
    staff_code: str
    password: str
    is_auditor: Optional[bool] = None


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None

    role: Optional[AccountRole] = None
    position_title: Optional[str] = None
    phone: Optional[str] = None
    secondary_phone: Optional[str] = None
    department_id: Optional[str] = None

    regulatory_authority: Optional[RegulatoryAuthority] = None
    licence_number: Optional[str] = None
    licence_state_or_country: Optional[str] = None
    licence_expires_on: Optional[date] = None

    is_active: Optional[bool] = None
    is_amo_admin: Optional[bool] = None
    is_auditor: Optional[bool] = None


class UserSelfUpdate(BaseModel):
    """
    Fields that a normal user is allowed to change about themselves.
    """

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    position_title: Optional[str] = None
    phone: Optional[str] = None
    secondary_phone: Optional[str] = None


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
    is_auditor: bool
    must_change_password: bool
    password_changed_at: Optional[datetime] = None
    token_revoked_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True




class UserCommandNotifyPayload(BaseModel):
    subject: str = Field(min_length=3, max_length=160)
    message: str = Field(min_length=3, max_length=5000)


class UserCommandSchedulePayload(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    description: Optional[str] = Field(default=None, max_length=5000)
    due_at: Optional[datetime] = None
    priority: int = Field(default=2, ge=1, le=5)


class UserCommandResult(BaseModel):
    user_id: str
    command: str
    status: str
    effective_at: datetime
    task_id: Optional[str] = None

class OnboardingStatusRead(BaseModel):
    is_complete: bool
    missing: list[str] = Field(default_factory=list)


class PersonnelImportRowIssue(BaseModel):
    row_number: int
    person_id: Optional[str] = None
    reason: str


class PersonnelImportSummary(BaseModel):
    dry_run: bool
    rows_processed: int
    created_personnel: int
    updated_personnel: int
    created_accounts: int
    updated_accounts: int
    skipped_accounts: int
    rejected_rows: int
    skipped_rows: int
    issues: list[PersonnelImportRowIssue] = Field(default_factory=list)
    conflicts: list[PersonnelImportConflict] = Field(default_factory=list)


class PersonnelImportConflict(BaseModel):
    row_number: int
    person_id: Optional[str] = None
    existing_email: Optional[str] = None
    imported_email: Optional[str] = None
    reason: str
    options: list[str] = Field(default_factory=list)


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
    identifier: Optional[str] = None
    email: Optional[EmailStr] = None
    staff_code: Optional[str] = None
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
    min_usage_limit: Optional[int] = Field(None, ge=0)
    max_usage_limit: Optional[int] = Field(None, ge=0)
    is_active: bool = True


class CatalogSKUCreate(CatalogSKUBase):
    pass


class CatalogSKUUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    term: Optional[BillingTerm] = None
    trial_days: Optional[int] = Field(None, ge=0)
    amount_cents: Optional[int] = Field(None, ge=0)
    currency: Optional[str] = None
    min_usage_limit: Optional[int] = Field(None, ge=0)
    max_usage_limit: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None


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


class ModuleSubscriptionBase(BaseModel):
    module_code: str
    status: ModuleSubscriptionStatus
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    plan_code: Optional[str] = None
    metadata_json: Optional[str] = None


class ModuleSubscriptionCreate(ModuleSubscriptionBase):
    amo_id: Optional[str] = None


class ModuleSubscriptionRead(ModuleSubscriptionBase):
    id: str
    amo_id: str
    created_at: datetime
    updated_at: datetime

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


class UserActiveContextRead(BaseModel):
    user_id: str
    active_amo_id: Optional[str] = None
    data_mode: DataMode
    last_real_amo_id: Optional[str] = None
    updated_at: datetime

    class Config:
        from_attributes = True


class UserActiveContextUpdate(BaseModel):
    active_amo_id: Optional[str] = None
    data_mode: Optional[DataMode] = None


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


class BillingAuditLogRead(BaseModel):
    id: str
    amo_id: Optional[str]
    event_type: str
    details: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class InvoiceDetailRead(InvoiceRead):
    ledger_entry: Optional[LedgerEntryRead] = None


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
    platform_name: Optional[str] = None
    platform_tagline: Optional[str] = None
    brand_accent: Optional[str] = None
    brand_accent_soft: Optional[str] = None
    brand_accent_secondary: Optional[str] = None
    platform_logo_filename: Optional[str] = None
    platform_logo_content_type: Optional[str] = None
    platform_logo_uploaded_at: Optional[datetime] = None
    gzip_minimum_size: Optional[int] = None
    gzip_compresslevel: Optional[int] = None
    max_request_body_bytes: Optional[int] = None
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


# ---------------------------------------------------------------------------
# ADMIN OVERVIEW SUMMARY
# ---------------------------------------------------------------------------


class OverviewSystemStatus(BaseModel):
    status: str
    last_checked_at: datetime
    refresh_paused: bool = False
    errors: List[str] = Field(default_factory=list)


class OverviewBadge(BaseModel):
    count: Optional[int] = None
    severity: str = "info"
    route: str
    available: bool = True


class OverviewIssue(BaseModel):
    key: str
    label: str
    count: Optional[int] = None
    severity: str
    route: str


class OverviewActivity(BaseModel):
    occurred_at: Optional[datetime] = None
    action: str
    entity_type: str
    actor_user_id: Optional[str] = None


class OverviewSummary(BaseModel):
    system: OverviewSystemStatus
    badges: dict[str, OverviewBadge]
    issues: List[OverviewIssue]
    recent_activity: List[OverviewActivity] = []
    recent_activity_available: bool = True


# ---------------------------------------------------------------------------
# USER DIRECTORY / WORKSPACE (ADMIN USER MANAGEMENT)
# ---------------------------------------------------------------------------


class UserPresenceRead(BaseModel):
    state: str = "offline"
    is_online: bool = False
    last_seen_at: Optional[datetime] = None
    source: Optional[str] = None


class UserPresenceDisplayRead(BaseModel):
    status_label: str = "Offline"
    last_seen_label: str = "Never seen"
    last_seen_at: Optional[datetime] = None
    last_seen_at_display: Optional[str] = None


class AdminUserDirectoryItem(BaseModel):
    id: str
    amo_id: str
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    staff_code: str
    email: EmailStr
    first_name: str
    last_name: str
    full_name: str
    role: AccountRole
    position_title: Optional[str] = None
    is_active: bool
    is_superuser: bool
    is_amo_admin: bool
    display_title: str
    availability_status: Optional[str] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    presence: UserPresenceRead
    presence_display: UserPresenceDisplayRead


class AdminUserDirectoryMetrics(BaseModel):
    total_users: int = 0
    active_users: int = 0
    inactive_users: int = 0
    online_users: int = 0
    away_users: int = 0
    on_leave_users: int = 0
    recently_active_users: int = 0
    departmentless_users: int = 0
    managers: int = 0


class AdminUserDirectoryRead(BaseModel):
    items: List[AdminUserDirectoryItem] = Field(default_factory=list)
    metrics: AdminUserDirectoryMetrics = Field(default_factory=AdminUserDirectoryMetrics)


class UserWorkspaceMetricRead(BaseModel):
    key: str
    label: str
    value: int


class UserTaskSummaryRead(BaseModel):
    id: str
    title: str
    status: str
    priority: int
    due_at: Optional[datetime] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    updated_at: datetime


class UserPermissionSummaryRead(BaseModel):
    id: str
    code: str
    label: str
    maintenance_scope: Optional[str] = None
    scope_text: Optional[str] = None
    effective_from: date
    expires_at: Optional[date] = None
    is_currently_valid: bool


class UserActivitySummaryRead(BaseModel):
    id: str
    occurred_at: datetime
    action: str
    entity_type: str
    entity_id: str


class UserLoginRecordRead(BaseModel):
    last_login_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    last_login_user_agent: Optional[str] = None
    must_change_password: bool
    password_changed_at: Optional[datetime] = None
    token_revoked_at: Optional[datetime] = None


class UserGroupChipRead(BaseModel):
    kind: str
    label: str
    value: Optional[str] = None


class PersonnelProfileSummaryRead(BaseModel):
    id: str
    person_id: str
    employment_status: Optional[str] = None
    status: Optional[str] = None
    hire_date: Optional[date] = None
    department: Optional[str] = None
    position_title: Optional[str] = None


class UserAvailabilitySummaryRead(BaseModel):
    id: str
    status: str
    effective_from: datetime
    effective_to: Optional[datetime] = None
    note: Optional[str] = None
    updated_at: datetime


class UserGroupRead(BaseModel):
    id: str
    amo_id: str
    owner_user_id: Optional[str] = None
    code: str
    name: str
    description: Optional[str] = None
    group_type: str
    is_system_managed: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    member_count: int = 0

    class Config:
        from_attributes = True


class UserGroupCreate(BaseModel):
    amo_id: str
    code: str
    name: str
    description: Optional[str] = None
    group_type: Literal["POST_HOLDERS", "DEPARTMENT", "CUSTOM", "PERSONAL"] = "CUSTOM"
    is_active: bool = True


class UserGroupUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class UserGroupMemberCreate(BaseModel):
    user_id: str
    member_role: str = Field(default="member", max_length=32)


class UserGroupMemberRead(BaseModel):
    id: str
    group_id: str
    user_id: str
    full_name: str
    email: EmailStr
    staff_code: str
    member_role: str
    added_at: datetime


class BulkUserActionRequest(BaseModel):
    user_ids: List[str] = Field(default_factory=list)
    action: Literal[
        "enable",
        "disable",
        "delete",
        "assign_department",
        "clear_department",
        "change_role",
        "add_group",
        "remove_group",
        "schedule_leave",
        "return_from_leave",
    ]
    department_id: Optional[str] = None
    role: Optional[AccountRole] = None
    group_id: Optional[str] = None
    note: Optional[str] = None
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None


class BulkUserActionResult(BaseModel):
    action: str
    processed: int
    affected_user_ids: List[str] = Field(default_factory=list)
    detail: str


class UserEmploymentActionRequest(BaseModel):
    action: Literal[
        "new_hire",
        "promote",
        "demote",
        "transfer",
        "resign",
        "reinstate",
        "schedule_leave",
        "return_from_leave",
    ]
    role: Optional[AccountRole] = None
    department_id: Optional[str] = None
    position_title: Optional[str] = None
    note: Optional[str] = None
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    employment_status: Optional[str] = None


class UserEmploymentActionResult(BaseModel):
    user_id: str
    action: str
    effective_at: datetime
    status: str
    note: Optional[str] = None


class AdminUserWorkspaceRead(BaseModel):
    user: UserRead
    department_name: Optional[str] = None
    display_title: str
    presence: UserPresenceRead
    presence_display: UserPresenceDisplayRead
    metrics: List[UserWorkspaceMetricRead] = Field(default_factory=list)
    tasks: List[UserTaskSummaryRead] = Field(default_factory=list)
    permissions: List[UserPermissionSummaryRead] = Field(default_factory=list)
    activity_log: List[UserActivitySummaryRead] = Field(default_factory=list)
    login_record: UserLoginRecordRead
    groups: List[UserGroupChipRead] = Field(default_factory=list)
    profile: Optional[PersonnelProfileSummaryRead] = None
    availability: List[UserAvailabilitySummaryRead] = Field(default_factory=list)
    group_memberships: List[UserGroupRead] = Field(default_factory=list)
