# backend/amodb/models.py
"""
Core models (accounts + audit).

This stays deliberately small and stable:
- User
- ArchivedUser
- UserActivity

Other domain models live in amodb.apps.<app>.models
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    Index,
)
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    """
    Global user record.

    Design goals:
    - Safe for a global multi-AMO deployment.
    - Can support SSO, MFA, and per-department dashboards.
    - Minimal but explicit privilege flags.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    # Human-friendly internal code (e.g. MUIY01, AVED02)
    user_code = Column(String(64), unique=True, index=True, nullable=False)

    # Login identity
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)

    # AMO and department context (for routing dashboards, permissions, etc.)
    amo_code = Column(String(32), index=True, nullable=True)          # e.g. "SAFA03"
    department_code = Column(String(64), index=True, nullable=True)   # e.g. "QUALITY"

    # Primary role label (still useful for UI / policies)
    role = Column(String(50), nullable=False, default="user", index=True)

    # Privilege flags
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    is_superuser = Column(Boolean, nullable=False, default=False, index=True)
    is_amo_admin = Column(Boolean, nullable=False, default=False, index=True)

    # Authentication
    hashed_password = Column(String(255), nullable=False)

    # Timeline
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # Activity relationships (not loaded unless needed)
    activities_as_actor = relationship(
        "UserActivity",
        foreign_keys="UserActivity.actor_id",
        back_populates="actor",
        lazy="noload",
    )
    activities_as_target = relationship(
        "UserActivity",
        foreign_keys="UserActivity.target_user_id",
        back_populates="target_user",
        lazy="noload",
    )


# Optional: composite indexes to speed up tenant-scoped queries
Index("idx_users_amo_email", User.amo_code, User.email)
Index("idx_users_amo_dept", User.amo_code, User.department_code)


class ArchivedUser(Base):
    """
    Holds compressed snapshots of deleted users for 36 months (retention).

    We keep AMO + department so historical investigations know
    which organisation and department the user belonged to.
    """

    __tablename__ = "archived_users"

    id = Column(Integer, primary_key=True, index=True)

    original_user_id = Column(Integer, index=True, nullable=True)
    user_code = Column(String(64), index=True, nullable=False)
    email = Column(String(255), index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)

    amo_code = Column(String(32), index=True, nullable=True)
    department_code = Column(String(64), index=True, nullable=True)

    archived_at = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        server_default=func.now(),
    )
    delete_after = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # Base64-encoded compressed JSON snapshot
    compressed_snapshot_b64 = Column(Text, nullable=False)


Index("idx_archived_users_email_role", ArchivedUser.email, ArchivedUser.role)


class UserActivity(Base):
    """
    Lightweight activity log. Used for audits and investigations.

    We intentionally keep this small: who did what to whom and when.
    If you ever need full payloads, you can add a JSON column later.
    """

    __tablename__ = "user_activities"

    id = Column(Integer, primary_key=True, index=True)

    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    action = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    actor = relationship(
        "User",
        foreign_keys=[actor_id],
        back_populates="activities_as_actor",
        lazy="joined",
    )
    target_user = relationship(
        "User",
        foreign_keys=[target_user_id],
        back_populates="activities_as_target",
        lazy="joined",
    )


Index(
    "idx_user_activities_actor_target_created",
    UserActivity.actor_id,
    UserActivity.target_user_id,
    UserActivity.created_at,
)
