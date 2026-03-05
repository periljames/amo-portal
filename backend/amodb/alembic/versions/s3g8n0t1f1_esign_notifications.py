"""esign notifications phase38

Revision ID: s3g8n0t1f1
Revises: r4n1m3p7k2
Create Date: 2026-03-05
"""

from alembic import op
import sqlalchemy as sa


revision = "s3g8n0t1f1"
down_revision = "r4n1m3p7k2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "esign_notifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=48), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("link_path", sa.Text(), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["request_id"], ["esign_signature_requests.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_esign_notifications_tenant_user_read", "esign_notifications", ["tenant_id", "user_id", "read_at"])
    op.create_index("ix_esign_notifications_tenant_user_created", "esign_notifications", ["tenant_id", "user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_esign_notifications_tenant_user_created", table_name="esign_notifications")
    op.drop_index("ix_esign_notifications_tenant_user_read", table_name="esign_notifications")
    op.drop_table("esign_notifications")
