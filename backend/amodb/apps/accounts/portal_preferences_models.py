from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)

from amodb.database import Base
from amodb.user_id import generate_user_id


class UserPortalPreference(Base):
    """User-scoped accessibility and appearance settings.

    These preferences are intentionally separate from the regulated user identity
    record. They can change freely without modifying employment, licensing or
    authorisation evidence.
    """

    __tablename__ = "user_portal_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_portal_preferences_user"),
        CheckConstraint(
            "text_scale IN ('standard', 'large', 'extra-large')",
            name="ck_user_portal_preferences_text_scale",
        ),
        CheckConstraint(
            "density IN ('comfortable', 'compact')",
            name="ck_user_portal_preferences_density",
        ),
        CheckConstraint(
            "motion IN ('system', 'full', 'reduced')",
            name="ck_user_portal_preferences_motion",
        ),
        CheckConstraint(
            "color_scheme IN ('system', 'light', 'dark')",
            name="ck_user_portal_preferences_color_scheme",
        ),
        CheckConstraint(
            "accent IN ('tenant', 'blue', 'teal', 'green', 'amber', 'violet')",
            name="ck_user_portal_preferences_accent",
        ),
        Index("ix_user_portal_preferences_amo_user", "amo_id", "user_id"),
    )

    id = Column(String(36), primary_key=True, default=generate_user_id)
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    amo_id = Column(
        String(36),
        ForeignKey("amos.id", ondelete="CASCADE"),
        nullable=True,
    )
    text_scale = Column(String(24), nullable=False, default="standard", server_default="standard")
    density = Column(String(24), nullable=False, default="comfortable", server_default="comfortable")
    motion = Column(String(24), nullable=False, default="system", server_default="system")
    color_scheme = Column(String(24), nullable=False, default="system", server_default="system")
    accent = Column(String(24), nullable=False, default="tenant", server_default="tenant")
    version = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
