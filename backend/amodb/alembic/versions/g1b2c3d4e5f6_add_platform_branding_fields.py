"""Add platform branding fields.

Revision ID: g1b2c3d4e5f6
Revises: f8a1b2c3d4e6
Create Date: 2026-01-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "g1b2c3d4e5f6"
down_revision = "i1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = {col["name"] for col in inspector.get_columns("platform_settings")}

    columns = [
        ("platform_name", sa.String(length=255)),
        ("platform_tagline", sa.String(length=255)),
        ("brand_accent", sa.String(length=32)),
        ("brand_accent_soft", sa.String(length=64)),
        ("brand_accent_secondary", sa.String(length=32)),
        ("platform_logo_path", sa.String(length=512)),
        ("platform_logo_filename", sa.String(length=255)),
        ("platform_logo_content_type", sa.String(length=128)),
        ("platform_logo_uploaded_at", sa.DateTime(timezone=True)),
    ]

    for name, col_type in columns:
        if name in existing:
            continue
        op.add_column("platform_settings", sa.Column(name, col_type, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = {col["name"] for col in inspector.get_columns("platform_settings")}
    to_drop = [
        "platform_logo_uploaded_at",
        "platform_logo_content_type",
        "platform_logo_filename",
        "platform_logo_path",
        "brand_accent_secondary",
        "brand_accent_soft",
        "brand_accent",
        "platform_tagline",
        "platform_name",
    ]
    for name in to_drop:
        if name in existing:
            op.drop_column("platform_settings", name)
