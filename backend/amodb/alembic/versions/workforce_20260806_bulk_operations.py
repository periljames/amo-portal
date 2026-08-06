"""Add durable Workforce bulk operations and scale indexes.

Revision ID: workforce_20260806_bulk_ops
Revises: rel_20260805_workpack_merge
Create Date: 2026-08-06
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "workforce_20260806_bulk_ops"
down_revision: Union[str, Sequence[str], None] = "rel_20260805_workpack_merge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workforce_bulk_operations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=False),
        sa.Column("operation_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="QUEUED"),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("selection_token", sa.String(length=64), nullable=False),
        sa.Column("selection_snapshot", sa.JSON(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("retry_of_operation_id", sa.String(length=36), nullable=True),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("succeeded_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("total_count >= 0", name="ck_workforce_bulk_operation_total"),
        sa.CheckConstraint("processed_count >= 0", name="ck_workforce_bulk_operation_processed"),
        sa.CheckConstraint("succeeded_count >= 0", name="ck_workforce_bulk_operation_succeeded"),
        sa.CheckConstraint("skipped_count >= 0", name="ck_workforce_bulk_operation_skipped"),
        sa.CheckConstraint("failed_count >= 0", name="ck_workforce_bulk_operation_failed"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["retry_of_operation_id"], ["workforce_bulk_operations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "amo_id",
            "actor_user_id",
            "operation_type",
            "idempotency_key",
            name="uq_workforce_bulk_operation_idempotency",
        ),
    )
    op.create_index("ix_workforce_bulk_operation_tenant_status", "workforce_bulk_operations", ["amo_id", "status", "created_at"])
    op.create_index("ix_workforce_bulk_operation_actor", "workforce_bulk_operations", ["amo_id", "actor_user_id", "created_at"])
    op.create_index("ix_workforce_bulk_operation_retry", "workforce_bulk_operations", ["retry_of_operation_id"])
    op.create_index("ix_workforce_bulk_operations_amo_id", "workforce_bulk_operations", ["amo_id"])
    op.create_index("ix_workforce_bulk_operations_actor_user_id", "workforce_bulk_operations", ["actor_user_id"])
    op.create_index("ix_workforce_bulk_operations_operation_type", "workforce_bulk_operations", ["operation_type"])
    op.create_index("ix_workforce_bulk_operations_status", "workforce_bulk_operations", ["status"])

    op.create_table(
        "workforce_bulk_operation_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("operation_id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("outcome_code", sa.String(length=96), nullable=True),
        sa.Column("outcome_message", sa.Text(), nullable=True),
        sa.Column("input_json", sa.JSON(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("sequence >= 0", name="ck_workforce_bulk_item_sequence"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_workforce_bulk_item_attempts"),
        sa.ForeignKeyConstraint(["operation_id"], ["workforce_bulk_operations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_id", "user_id", name="uq_workforce_bulk_operation_item_user"),
    )
    op.create_index("ix_workforce_bulk_item_status", "workforce_bulk_operation_items", ["operation_id", "status", "sequence"])
    op.create_index("ix_workforce_bulk_item_tenant_user", "workforce_bulk_operation_items", ["amo_id", "user_id", "created_at"])
    op.create_index("ix_workforce_bulk_operation_items_operation_id", "workforce_bulk_operation_items", ["operation_id"])
    op.create_index("ix_workforce_bulk_operation_items_amo_id", "workforce_bulk_operation_items", ["amo_id"])
    op.create_index("ix_workforce_bulk_operation_items_user_id", "workforce_bulk_operation_items", ["user_id"])
    op.create_index("ix_workforce_bulk_operation_items_status", "workforce_bulk_operation_items", ["status"])

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_employment_contracts_amo_type_effective "
        "ON employment_contracts (amo_id, contract_type, effective_from, effective_to)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_employment_contracts_amo_base_status "
        "ON employment_contracts (amo_id, primary_base_station_id, employment_status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_employment_contracts_amo_supervisor_status "
        "ON employment_contracts (amo_id, supervisor_user_id, employment_status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_employment_contracts_amo_payroll "
        "ON employment_contracts (amo_id, payroll_number)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_users_amo_department_active "
        "ON users (amo_id, department_id, is_active, is_system_account)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_users_amo_position_title "
        "ON users (amo_id, position_title)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_employee_pattern_amo_user_effective_range "
        "ON employee_work_pattern_assignments (amo_id, user_id, effective_from, effective_to)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_employee_pattern_amo_user_effective_range")
    op.execute("DROP INDEX IF EXISTS ix_users_amo_position_title")
    op.execute("DROP INDEX IF EXISTS ix_users_amo_department_active")
    op.execute("DROP INDEX IF EXISTS ix_employment_contracts_amo_payroll")
    op.execute("DROP INDEX IF EXISTS ix_employment_contracts_amo_supervisor_status")
    op.execute("DROP INDEX IF EXISTS ix_employment_contracts_amo_base_status")
    op.execute("DROP INDEX IF EXISTS ix_employment_contracts_amo_type_effective")

    op.drop_index("ix_workforce_bulk_operation_items_status", table_name="workforce_bulk_operation_items")
    op.drop_index("ix_workforce_bulk_operation_items_user_id", table_name="workforce_bulk_operation_items")
    op.drop_index("ix_workforce_bulk_operation_items_amo_id", table_name="workforce_bulk_operation_items")
    op.drop_index("ix_workforce_bulk_operation_items_operation_id", table_name="workforce_bulk_operation_items")
    op.drop_index("ix_workforce_bulk_item_tenant_user", table_name="workforce_bulk_operation_items")
    op.drop_index("ix_workforce_bulk_item_status", table_name="workforce_bulk_operation_items")
    op.drop_table("workforce_bulk_operation_items")

    op.drop_index("ix_workforce_bulk_operations_status", table_name="workforce_bulk_operations")
    op.drop_index("ix_workforce_bulk_operations_operation_type", table_name="workforce_bulk_operations")
    op.drop_index("ix_workforce_bulk_operations_actor_user_id", table_name="workforce_bulk_operations")
    op.drop_index("ix_workforce_bulk_operations_amo_id", table_name="workforce_bulk_operations")
    op.drop_index("ix_workforce_bulk_operation_retry", table_name="workforce_bulk_operations")
    op.drop_index("ix_workforce_bulk_operation_actor", table_name="workforce_bulk_operations")
    op.drop_index("ix_workforce_bulk_operation_tenant_status", table_name="workforce_bulk_operations")
    op.drop_table("workforce_bulk_operations")
