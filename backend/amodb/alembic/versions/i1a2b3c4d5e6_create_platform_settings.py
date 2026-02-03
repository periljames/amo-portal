"""create platform settings table

Revision ID: i1a2b3c4d5e6
Revises: f8a1b2c3d4e6
Create Date: 2026-02-05 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "i1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "f8a1b2c3d4e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("api_base_url", sa.String(length=255), nullable=True),
        sa.Column("platform_name", sa.String(length=255), nullable=True),
        sa.Column("platform_tagline", sa.String(length=255), nullable=True),
        sa.Column("brand_accent", sa.String(length=32), nullable=True),
        sa.Column("brand_accent_soft", sa.String(length=64), nullable=True),
        sa.Column("brand_accent_secondary", sa.String(length=32), nullable=True),
        sa.Column("platform_logo_path", sa.String(length=512), nullable=True),
        sa.Column("platform_logo_filename", sa.String(length=255), nullable=True),
        sa.Column("platform_logo_content_type", sa.String(length=128), nullable=True),
        sa.Column("platform_logo_uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acme_directory_url", sa.String(length=255), nullable=True),
        sa.Column("acme_client", sa.String(length=128), nullable=True),
        sa.Column("certificate_status", sa.String(length=64), nullable=True),
        sa.Column("certificate_issuer", sa.String(length=255), nullable=True),
        sa.Column("certificate_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_renewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("platform_settings")
