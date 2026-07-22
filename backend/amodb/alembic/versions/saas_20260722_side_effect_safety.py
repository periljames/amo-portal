"""Add durable source references for non-repeatable side effects.

Revision ID: saas_20260722_side_effect_safe
Revises: saas_20260722_runtime_fence
Create Date: 2026-07-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "saas_20260722_side_effect_safe"
down_revision = "saas_20260722_runtime_fence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("saas_support_ticket_messages"):
        raise RuntimeError("Side-effect safety requires SaaS support messages")
    columns = {str(column["name"]) for column in inspector.get_columns("saas_support_ticket_messages")}
    if "source_job_id" not in columns:
        op.add_column(
            "saas_support_ticket_messages",
            sa.Column("source_job_id", sa.String(length=36), nullable=True),
        )
        op.create_foreign_key(
            "fk_saas_support_message_source_job",
            "saas_support_ticket_messages",
            "saas_jobs",
            ["source_job_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_saas_support_message_source_job "
            "ON saas_support_ticket_messages (source_job_id) WHERE source_job_id IS NOT NULL"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_saas_support_message_source_job"))
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("saas_support_ticket_messages"):
        columns = {str(column["name"]) for column in inspector.get_columns("saas_support_ticket_messages")}
        if "source_job_id" in columns:
            foreign_keys = inspector.get_foreign_keys("saas_support_ticket_messages")
            if any(key.get("name") == "fk_saas_support_message_source_job" for key in foreign_keys):
                op.drop_constraint(
                    "fk_saas_support_message_source_job",
                    "saas_support_ticket_messages",
                    type_="foreignkey",
                )
            op.drop_column("saas_support_ticket_messages", "source_job_id")
