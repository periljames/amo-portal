"""Add actionable QMS notification links.

Revision ID: quality_20260705_notification_action_links
Revises: qual_20260704_schedfix
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa

revision = "quality_20260705_notification_action_links"
down_revision = "qual_20260704_schedfix"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return False
    return any(col["name"] == column for col in inspector.get_columns(table))


def upgrade() -> None:
    if not _has_table("qms_notifications"):
        return
    if not _has_column("qms_notifications", "action_url"):
        op.add_column("qms_notifications", sa.Column("action_url", sa.String(length=1024), nullable=True))
    if not _has_column("qms_notifications", "action_label"):
        op.add_column("qms_notifications", sa.Column("action_label", sa.String(length=80), nullable=True))
    if not _has_column("qms_notifications", "entity_type"):
        op.add_column("qms_notifications", sa.Column("entity_type", sa.String(length=64), nullable=True))
    if not _has_column("qms_notifications", "entity_id"):
        op.add_column("qms_notifications", sa.Column("entity_id", sa.String(length=64), nullable=True))
    op.execute("CREATE INDEX IF NOT EXISTS ix_qms_notifications_entity_runtime ON qms_notifications (entity_type, entity_id)")


def downgrade() -> None:
    if not _has_table("qms_notifications"):
        return
    op.execute("DROP INDEX IF EXISTS ix_qms_notifications_entity_runtime")
    for column_name in ("entity_id", "entity_type", "action_label", "action_url"):
        if _has_column("qms_notifications", column_name):
            op.drop_column("qms_notifications", column_name)
