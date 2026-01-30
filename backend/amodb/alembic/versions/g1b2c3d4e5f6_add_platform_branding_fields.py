"""Add platform branding fields.

Revision ID: g1b2c3d4e5f6
Revises: f8a1b2c3d4e6
Create Date: 2026-01-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "g1b2c3d4e5f6"
down_revision = "f8a1b2c3d4e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("platform_settings", sa.Column("platform_name", sa.String(length=255), nullable=True))
    op.add_column("platform_settings", sa.Column("platform_tagline", sa.String(length=255), nullable=True))
    op.add_column("platform_settings", sa.Column("brand_accent", sa.String(length=32), nullable=True))
    op.add_column("platform_settings", sa.Column("brand_accent_soft", sa.String(length=64), nullable=True))
    op.add_column("platform_settings", sa.Column("brand_accent_secondary", sa.String(length=32), nullable=True))
    op.add_column("platform_settings", sa.Column("platform_logo_path", sa.String(length=512), nullable=True))
    op.add_column("platform_settings", sa.Column("platform_logo_filename", sa.String(length=255), nullable=True))
    op.add_column("platform_settings", sa.Column("platform_logo_content_type", sa.String(length=128), nullable=True))
    op.add_column("platform_settings", sa.Column("platform_logo_uploaded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("platform_settings", "platform_logo_uploaded_at")
    op.drop_column("platform_settings", "platform_logo_content_type")
    op.drop_column("platform_settings", "platform_logo_filename")
    op.drop_column("platform_settings", "platform_logo_path")
    op.drop_column("platform_settings", "brand_accent_secondary")
    op.drop_column("platform_settings", "brand_accent_soft")
    op.drop_column("platform_settings", "brand_accent")
    op.drop_column("platform_settings", "platform_tagline")
    op.drop_column("platform_settings", "platform_name")
