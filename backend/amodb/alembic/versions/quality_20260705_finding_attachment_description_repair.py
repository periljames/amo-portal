"""Repair finding evidence attachment description column.

Revision ID: quality_20260705_finding_attachment_description_repair
Revises: qual_20260704_schedfix
Create Date: 2026-07-05
"""

from alembic import op
import sqlalchemy as sa

revision = "quality_20260705_finding_attachment_description_repair"
down_revision = "qual_20260704_schedfix"
branch_labels = None
depends_on = None


def _has_table(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return inspector.has_table(table_name)


def _has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "qms_finding_attachments"):
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS qms_finding_attachments (
                id UUID NOT NULL,
                finding_id UUID NOT NULL,
                filename VARCHAR(255) NOT NULL,
                description VARCHAR(500),
                file_ref VARCHAR(512) NOT NULL,
                content_type VARCHAR(128),
                size_bytes INTEGER,
                sha256 VARCHAR(64),
                uploaded_by_user_id VARCHAR(36),
                uploaded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    elif not _has_column(bind, "qms_finding_attachments", "description"):
        op.add_column("qms_finding_attachments", sa.Column("description", sa.String(length=500), nullable=True))

    op.execute("CREATE INDEX IF NOT EXISTS ix_qms_finding_attachments_id_repair ON qms_finding_attachments (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_qms_finding_attachments_finding_repair ON qms_finding_attachments (finding_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_qms_finding_attachments_uploaded_repair ON qms_finding_attachments (uploaded_at)")


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "qms_finding_attachments", "description"):
        op.drop_column("qms_finding_attachments", "description")
