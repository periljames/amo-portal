"""add composite audit_events replay index

Revision ID: z1y2x3w4v5u6
Revises: y3z4a5b6c7d8
Create Date: 2026-02-10 00:00:01.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "z1y2x3w4v5u6"
down_revision = "y3z4a5b6c7d8"
branch_labels = None
depends_on = None


def _index_exists(bind, name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(idx.get("name") == name for idx in inspector.get_indexes("audit_events"))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "audit_events" not in inspector.get_table_names():
        return
    if not _index_exists(bind, "ix_audit_events_amo_time_id_desc"):
        op.create_index(
            "ix_audit_events_amo_time_id_desc",
            "audit_events",
            ["amo_id", sa.text("occurred_at DESC"), sa.text("id DESC")],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "audit_events" not in inspector.get_table_names():
        return
    if _index_exists(bind, "ix_audit_events_amo_time_id_desc"):
        op.drop_index("ix_audit_events_amo_time_id_desc", table_name="audit_events")
