"""global superuser tenant safety and QMS phase 3 hardening

Revision ID: qms_p3_20260501
Revises: qms_p2_20260426
Create Date: 2026-05-01

This migration separates platform superusers from AMO tenants and adds a
minimal safety layer required by the canonical QMS route model.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "qms_p3_20260501"
down_revision = "qms_p2_20260426"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _pg_table_exists(table_name: str) -> bool:
    if not _is_postgresql():
        return False
    return bool(
        op.get_bind()
        .execute(sa.text("SELECT to_regclass(:table_name)"), {"table_name": f"public.{table_name}"})
        .scalar()
    )


def _pg_column_exists(table_name: str, column_name: str) -> bool:
    if not _pg_table_exists(table_name):
        return False
    return bool(
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                  AND column_name = :column_name
                """
            ),
            {"table_name": table_name, "column_name": column_name},
        )
        .first()
    )


def _clear_superuser_active_context_postgres() -> None:
    # The live model/table name is user_active_context. Older experimental
    # patches used user_active_contexts; never assume either table exists.
    for table_name in ("user_active_context", "user_active_contexts"):
        if _pg_table_exists(table_name) and _pg_column_exists(table_name, "active_amo_id"):
            op.execute(
                sa.text(
                    f"""
                    UPDATE {table_name}
                    SET active_amo_id = NULL
                    WHERE user_id IN (
                        SELECT id FROM users WHERE is_superuser IS TRUE
                    )
                    """
                )
            )


def upgrade() -> None:
    bind = op.get_bind()

    if _is_postgresql():
        op.execute("ALTER TABLE users ALTER COLUMN amo_id DROP NOT NULL")
        if _pg_column_exists("users", "staff_code"):
            op.execute("ALTER TABLE users ALTER COLUMN staff_code DROP NOT NULL")
        if _pg_column_exists("users", "department_id"):
            op.execute("UPDATE users SET amo_id = NULL, department_id = NULL WHERE is_superuser IS TRUE")
        else:
            op.execute("UPDATE users SET amo_id = NULL WHERE is_superuser IS TRUE")
        _clear_superuser_active_context_postgres()
        op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_global_superuser_email ON users (lower(email)) WHERE is_superuser IS TRUE AND amo_id IS NULL")
        op.execute("CREATE INDEX IF NOT EXISTS ix_users_platform_superuser ON users (is_superuser, amo_id) WHERE is_superuser IS TRUE")
    else:
        with op.batch_alter_table("users") as batch:
            batch.alter_column("amo_id", existing_type=sa.String(length=36), nullable=True)
            batch.alter_column("staff_code", existing_type=sa.String(length=32), nullable=True)
        bind.execute(sa.text("UPDATE users SET amo_id = NULL, department_id = NULL WHERE is_superuser = 1"))


def downgrade() -> None:
    # Do not reattach platform superusers to arbitrary tenants on downgrade.
    if _is_postgresql():
        op.execute("DROP INDEX IF EXISTS ix_users_platform_superuser")
        op.execute("DROP INDEX IF EXISTS uq_users_global_superuser_email")
