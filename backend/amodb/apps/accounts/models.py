# backend/amodb/apps/accounts/models.py

from __future__ import annotations

import enum
from datetime import datetime, date

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship

from amodb.database import Base
# GUID-like IDs for portability and multi-tenant separation
from amodb.user_id import generate_user_id


# ---------------------------------------------------------------------------
# ENUMS
# ---------------------------------------------------------------------------


class RegulatoryAuthority(str, enum.Enum):
    FAA = "FAA"
    EASA = "EASA"
    KCAA = "KCAA"
    CAA_UK = "CAA_UK"
    OTHER = "OTHER"


class AccountRole(str, enum.Enum):
    """High-level roles used across the portal.

    Fine-grained privileges for maintenance / CRS are defined via
    AuthorisationType + UserAuthorisation.
    """

    SUPERUSER = "SUPERUSER"           # Platform owner
    AMO_ADMIN = "AMO_ADMIN"           # AMO specific admin
    QUALITY_MANAGER = "QUALITY_MANAGER"
    SAFETY_MANAGER = "SAFETY_MANAGER"
    PLANNING_ENGINEER = "PLANNING_ENGINEER"
    PRODUCTION_ENGINEER = "PRODUCTION_ENGINEER"
    CERTIFYING_ENGINEER = "CERTIFYING_ENGINEER"
    CERTIFYING_TECHNICIAN = "CERTIFYING_TECHNICIAN"
    TECHNICIAN = "TECHNICIAN"
    STORES = "STORES"
    VIEW_ONLY = "VIEW_ONLY"


class MaintenanceScope(str, enum.Enum):
    """Rough mapping to Part-145 / Part-66 style scopes."""

    LINE = "LINE"
    BASE = "BASE"
    COMPONENT = "COMPONENT"
    STRUCTURES = "STRUCTURES"
    AVIONICS = "AVIONICS"
    POWERPLANT = "POWERPLANT"
    OTHER = "OTHER"


# ---------------------------------------------------------------------------
# AMO + DEPARTMENT
# ---------------------------------------------------------------------------


class AMO(Base):
    """
    Approved Maintenance Organisation (or equivalent).

    This lets you support multiple AMOs on the same platform later.
    Records like authorisations and users are always scoped to an AMO.
    """

    __tablename__ = "amos"

    id = Column(
        String(36),
        primary_key=True,
        default=generate_user_id,
    )
    amo_code = Column(String(32), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    icao_code = Column(String(8), nullable=True, index=True)
    country = Column(String(64), nullable=True)
    login_slug = Column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        doc="Short slug for URLs, e.g. 'maintenance.safa03'",
    )
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(64), nullable=True)
    time_zone = Column(String(64), nullable=True)

    is_active = Column(Boolean, nullable=False, default=True, index=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    departments = relationship(
        "Department",
        back_populates="amo",
        lazy="selectin",
    )
    users = relationship(
        "User",
        back_populates="amo",
        lazy="selectin",
    )
    assets = relationship(
        "AMOAsset",
        back_populates="amo",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<AMO {self.amo_code} {self.name}>"


class AMOAsset(Base):
    """
    Files associated with an AMO (branding + CRS assets).

    Stored as a 1:1 table keyed by amo_id for easier expansion.
    """

    __tablename__ = "amo_assets"

    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        primary_key=True,
    )

    crs_logo_path = Column(Text, nullable=True)
    crs_logo_filename = Column(String(255), nullable=True)
    crs_logo_content_type = Column(String(100), nullable=True)
    crs_logo_uploaded_at = Column(DateTime(timezone=True), nullable=True)

    crs_template_path = Column(Text, nullable=True)
    crs_template_filename = Column(String(255), nullable=True)
    crs_template_content_type = Column(String(100), nullable=True)
    crs_template_uploaded_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    amo = relationship("AMO", back_populates="assets")

    def __repr__(self) -> str:
        return f"<AMOAsset amo_id={self.amo_id}>"


class Department(Base):
    """
    Logical department within an AMO (Planning, Production, Quality, etc.).

    Used for:
    - Landing dashboard routing
    - Data partitioning / filtering
    - Access control for specific modules
    """

    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_departments_amo_code"),
    )

    id = Column(
        String(36),
        primary_key=True,
        default=generate_user_id,
    )
    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    code = Column(
        String(32),
        nullable=False,
        doc="Short code, e.g. 'PLANNING', 'PRODUCTION', 'QUALITY'",
    )
    name = Column(String(255), nullable=False)
    default_route = Column(
        String(255),
        nullable=True,
        doc="Frontend route for this department, e.g. '/maintenance/planning'",
    )

    is_active = Column(Boolean, nullable=False, default=True, index=True)
    sort_order = Column(Integer, nullable=False, default=100)

    amo = relationship("AMO", back_populates="departments")
    users = relationship(
        "User",
        back_populates="department",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Department {self.amo.amo_code if self.amo else '?'}:{self.code}>"


# ---------------------------------------------------------------------------
# USER & SECURITY
# ---------------------------------------------------------------------------


class User(Base):
    """
    User account, including regulatory licence metadata.

    Designed to satisfy expectations that maintenance organisations:
    - keep records of certifying staff, licences and scope
    - control who can issue maintenance releases / CRS

    NOTE ON AI / SYSTEM ACCOUNTS:
    - is_system_account = True marks a non-human/service/AI account.
    - System accounts must NOT be used as certifying staff and must not
      issue CRS; business logic should enforce this.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("amo_id", "email", name="uq_users_amo_email"),
        UniqueConstraint("amo_id", "staff_code", name="uq_users_amo_staff_code"),
        Index("idx_users_role_active", "role", "is_active"),
    )

    id = Column(
        String(36),
        primary_key=True,
        default=generate_user_id,
    )

    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    department_id = Column(
        String(36),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    staff_code = Column(
        String(32),
        nullable=False,
        doc="Internal HR/Staff code (not same as login code).",
    )

    email = Column(String(255), nullable=False, index=True)

    # Split name fields + keep full_name for display/search
    first_name = Column(String(128), nullable=False)
    last_name = Column(String(128), nullable=False)
    full_name = Column(String(255), nullable=False)

    role = Column(
        Enum(AccountRole, name="account_role_enum"),
        nullable=False,
        default=AccountRole.TECHNICIAN,
        index=True,
    )

    # Flags and status
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    is_superuser = Column(Boolean, nullable=False, default=False, index=True)
    is_amo_admin = Column(Boolean, nullable=False, default=False, index=True)

    # Marks non-human/system/AI accounts
    is_system_account = Column(
        Boolean,
        nullable=False,
        default=False,
        doc="True for system/AI/service accounts, never used as certifying staff.",
    )

    position_title = Column(String(255), nullable=True)
    phone = Column(String(64), nullable=True)

    # Regulatory/licence metadata to back CRS signatories etc.
    regulatory_authority = Column(
        Enum(RegulatoryAuthority, name="regulatory_authority_enum"),
        nullable=True,
    )
    licence_number = Column(String(64), nullable=True)
    licence_state_or_country = Column(String(64), nullable=True)
    licence_expires_on = Column(Date, nullable=True)

    # On-boarding / approval trail
    approved_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        doc="User who approved this account (e.g. QM / AMO Admin).",
    )
    approved_at = Column(
        DateTime(timezone=True),
        nullable=True,
        doc="Date/time when the account was formally approved for use.",
    )
    approval_notes = Column(
        Text,
        nullable=True,
        doc="Optional notes on basis for approval (scope, references, etc.).",
    )

    # Off-boarding / deactivation trail
    deactivated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        doc="When this user was deactivated (if applicable).",
    )
    deactivated_reason = Column(
        Text,
        nullable=True,
        doc="Reason for deactivation (left company, licence withdrawn, etc.).",
    )

    # Security: password + lockout + login tracking
    hashed_password = Column(String(255), nullable=False)
    login_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    last_login_ip = Column(String(64), nullable=True)
    last_login_user_agent = Column(Text, nullable=True)

    # Future: mark if user has registered WebAuthn / passkeys (MFA hook)
    webauthn_registered = Column(Boolean, nullable=False, default=False)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    amo = relationship("AMO", back_populates="users")
    department = relationship("Department", back_populates="users")

    # who approved this user (self-referential)
    approved_by = relationship(
        "User",
        remote_side=[id],
        lazy="joined",
        doc="Relationship to the user who approved this account.",
    )

    # FIXED: specify which FK to use so SQLAlchemy doesn't get confused
    authorisations = relationship(
        "UserAuthorisation",
        back_populates="user",
        lazy="selectin",
        foreign_keys="UserAuthorisation.user_id",
        primaryjoin="User.id == UserAuthorisation.user_id",
    )

    security_events = relationship(
        "AccountSecurityEvent",
        back_populates="user",
        lazy="selectin",
    )

    def is_certifying_staff(self) -> bool:
        """
        Helper used by business logic to decide if this user can ever act as
        certifying staff. System/AI accounts must not be certifying staff.
        """
        if self.is_system_account:
            return False
        return self.role in {
            AccountRole.CERTIFYING_ENGINEER,
            AccountRole.CERTIFYING_TECHNICIAN,
        }

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"


# ---------------------------------------------------------------------------
# AUTHORISATIONS (WHO CAN SIGN WHAT)
# ---------------------------------------------------------------------------


class AuthorisationType(Base):
    """
    Defines a type of authorisation, e.g.:

    - "CRS Line Maintenance Dash 8"
    - "Engine Run-up"
    - "Night shift shift-lead"

    Each UserAuthorisation instance ties a specific user to one of these,
    with validity dates and scope text.
    """

    __tablename__ = "authorisation_types"
    __table_args__ = (
        UniqueConstraint("amo_id", "code", name="uq_auth_types_amo_code"),
    )

    id = Column(
        String(36),
        primary_key=True,
        default=generate_user_id,
    )
    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    code = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    maintenance_scope = Column(
        Enum(MaintenanceScope, name="maintenance_scope_enum"),
        nullable=False,
        default=MaintenanceScope.LINE,
    )

    regulation_reference = Column(
        String(128),
        nullable=True,
        doc="e.g. 'EASA Part-145.A.35(e)' or '14 CFR Part 145.157'",
    )

    # Optional default authority for this authorisation type
    default_reg_authority = Column(
        Enum(RegulatoryAuthority, name="regulatory_authority_enum"),
        nullable=True,
        doc="If set, default regulatory authority for this authorisation type.",
    )

    # Flags controlling CRS / sign-off behaviour
    can_issue_crs = Column(Boolean, nullable=False, default=False)
    requires_dual_sign = Column(Boolean, nullable=False, default=False)
    requires_valid_licence = Column(Boolean, nullable=False, default=True)

    is_active = Column(Boolean, nullable=False, default=True, index=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    user_links = relationship(
        "UserAuthorisation",
        back_populates="authorisation_type",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<AuthorisationType {self.code} ({self.maintenance_scope})>"


class UserAuthorisation(Base):
    """
    Grants a specific user a specific AuthorisationType, with a clear scope.

    This aligns with regulatory expectations that certifying staff
    authorisations are:
    - formally documented,
    - specify the scope and limitations,
    - and have defined validity periods.
    """

    __tablename__ = "user_authorisations"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "authorisation_type_id",
            "effective_from",
            name="uq_user_auth_unique",
        ),
        Index("idx_user_auth_validity", "user_id", "effective_from", "expires_at"),
    )

    id = Column(
        String(36),
        primary_key=True,
        default=generate_user_id,
    )
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    authorisation_type_id = Column(
        String(36),
        ForeignKey("authorisation_types.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    scope_text = Column(
        Text,
        nullable=True,
        doc="Free-text scope/limitations, e.g. aircraft types, stations.",
    )

    effective_from = Column(Date, nullable=False)
    expires_at = Column(Date, nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_reason = Column(Text, nullable=True)

    granted_by_user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        doc="User who granted/approved this authorisation record.",
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    user = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="authorisations",
    )
    authorisation_type = relationship(
        "AuthorisationType",
        back_populates="user_links",
    )
    granted_by = relationship(
        "User",
        foreign_keys=[granted_by_user_id],
        lazy="joined",
    )

    def is_currently_valid(self, today: date | None = None) -> bool:
        today = today or date.today()
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at < today:
            return False
        return self.effective_from <= today

    def __repr__(self) -> str:
        return f"<UserAuthorisation user={self.user_id} type={self.authorisation_type_id}>"


# ---------------------------------------------------------------------------
# PASSWORD RESET TOKENS
# ---------------------------------------------------------------------------


class PasswordResetToken(Base):
    """
    One-time password reset token.

    - We store only a hash of the token (raw token is emailed to user).
    - Tokens expire and are marked used once redeemed.
    """

    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        Index("idx_reset_tokens_user_expires", "user_id", "expires_at"),
    )

    id = Column(
        String(36),
        primary_key=True,
        default=generate_user_id,
    )
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Store a hash, not the raw token
    token_hash = Column(String(255), nullable=False, index=True)
    issued_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
    )
    used_at = Column(DateTime(timezone=True), nullable=True)

    request_ip = Column(String(64), nullable=True)
    request_user_agent = Column(Text, nullable=True)

    user = relationship("User", lazy="joined")

    def is_active(self, now: datetime | None = None) -> bool:
        now = now or datetime.utcnow()
        if self.used_at is not None:
            return False
        return self.expires_at >= now


# ---------------------------------------------------------------------------
# SECURITY EVENTS (AUDIT TRAIL)
# ---------------------------------------------------------------------------


class AccountSecurityEvent(Base):
    """
    Focused security audit trail (authentication, password changes, etc.).

    Keep separate from general audit logs to make security reviews easier.
    """

    __tablename__ = "account_security_events"
    __table_args__ = (
        Index(
            "idx_security_events_user_created",
            "user_id",
            "event_type",
            "created_at",
        ),
    )

    id = Column(
        String(36),
        primary_key=True,
        default=generate_user_id,
    )
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    event_type = Column(
        String(64),
        nullable=False,
        doc="e.g. 'LOGIN_SUCCESS', 'LOGIN_FAILED', 'LOCKOUT', 'PASSWORD_RESET'",
    )
    description = Column(Text, nullable=True)

    ip_address = Column(String(64), nullable=True)
    user_agent = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    user = relationship("User", back_populates="security_events", lazy="joined")
    amo = relationship("AMO", lazy="joined")

    def __repr__(self) -> str:
        return f"<SecurityEvent {self.event_type} user={self.user_id}>"
