"""add tasks table

Revision ID: r1s2t3u4v5w6
Revises: q1w2e3r4t5u7
Create Date: 2026-03-05 00:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "r1s2t3u4v5w6"
down_revision = "q1w2e3r4t5u7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    task_status_enum = sa.Enum(
        "OPEN",
        "IN_PROGRESS",
        "DONE",
        "CANCELLED",
        name="task_status_enum",
        native_enum=False,
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("status", task_status_enum, nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("supervisor_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tasks_amo_status", "tasks", ["amo_id", "status"], unique=False)
    op.create_index("ix_tasks_owner_status", "tasks", ["owner_user_id", "status"], unique=False)
    op.create_index("ix_tasks_due", "tasks", ["amo_id", "due_at"], unique=False)


def downgrade() -> None:
    task_status_enum = sa.Enum(
        "OPEN",
        "IN_PROGRESS",
        "DONE",
        "CANCELLED",
        name="task_status_enum",
        native_enum=False,
    )
    op.drop_index("ix_tasks_due", table_name="tasks")
    op.drop_index("ix_tasks_owner_status", table_name="tasks")
    op.drop_index("ix_tasks_amo_status", table_name="tasks")
    op.drop_table("tasks")
    task_status_enum.drop(op.get_bind(), checkfirst=True)
