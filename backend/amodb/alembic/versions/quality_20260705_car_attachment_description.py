"""Add CAR attachment descriptions.

Revision ID: quality_20260705_car_attachment_description
Revises: qual_20260704_schedfix
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa

revision = "quality_20260705_car_attachment_description"
down_revision = "qual_20260704_schedfix"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return False
    return any(col["name"] == column for col in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table("quality_car_attachments"):
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS quality_car_attachments (
                id UUID NOT NULL,
                car_id UUID NOT NULL,
                filename VARCHAR(255) NOT NULL,
                description VARCHAR(500),
                file_ref VARCHAR(512) NOT NULL,
                content_type VARCHAR(128),
                size_bytes INTEGER,
                sha256 VARCHAR(64),
                uploaded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    elif not _has_column("quality_car_attachments", "description"):
        op.add_column("quality_car_attachments", sa.Column("description", sa.String(length=500), nullable=True))
    op.execute("CREATE INDEX IF NOT EXISTS ix_quality_car_attachments_car_description_runtime ON quality_car_attachments (car_id)")


def downgrade() -> None:
    if _has_column("quality_car_attachments", "description"):
        op.drop_column("quality_car_attachments", "description")
