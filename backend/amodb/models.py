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
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_code = Column(String(64), unique=True, index=True, nullable=False)

    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)

    role = Column(String(50), nullable=False, default="user", index=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    hashed_password = Column(String(255), nullable=False)

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


class ArchivedUser(Base):
    """
    Holds compressed snapshots of deleted users for 36 months.
    """

    __tablename__ = "archived_users"

    id = Column(Integer, primary_key=True, index=True)

    original_user_id = Column(Integer, index=True, nullable=True)
    user_code = Column(String(64), index=True, nullable=False)
    email = Column(String(255), index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)

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
