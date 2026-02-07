"""add car attachments

Revision ID: c9f1b2a3d4e5
Revises: m1b2c3d4e5f8
Create Date: 2025-02-14 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "c9f1b2a3d4e5"
down_revision = "m1b2c3d4e5f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not op.get_bind().dialect.has_table(op.get_bind(), "quality_cars"):
        return
    op.create_table(
        "quality_car_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("car_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_ref", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["car_id"], ["quality_cars.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_quality_car_attachments_car_id",
        "quality_car_attachments",
        ["car_id"],
        unique=False,
    )


def downgrade() -> None:
    if not op.get_bind().dialect.has_table(op.get_bind(), "quality_car_attachments"):
        return
    op.drop_index("ix_quality_car_attachments_car_id", table_name="quality_car_attachments")
    op.drop_table("quality_car_attachments")
