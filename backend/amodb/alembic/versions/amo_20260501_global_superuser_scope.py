"""make superusers global platform identities

Revision ID: amo_20260501_gsu_scope
Revises: 2c4d7e9f0a1b, 9c6a7d2e8f10, a1b2c3d4e5f6, a5c1d2e3f4b6, b2c3d4e5f6g7, c1d2e3f4a5b7, d9e2f3a4b5c6, e4b7d1a2c3f4, g1b2c3d4e5f6, l1b2c3d4e5f7, m4a5n6u7a8l9, qms_p2_20260426, s9t8u7v6w5x4, v0a1b2c3d4e5
Create Date: 2026-05-01
"""

from alembic import op
import sqlalchemy as sa

revision = "amo_20260501_gsu_scope"
down_revision = (
    "2c4d7e9f0a1b",
    "9c6a7d2e8f10",
    "a1b2c3d4e5f6",
    "a5c1d2e3f4b6",
    "b2c3d4e5f6g7",
    "c1d2e3f4a5b7",
    "d9e2f3a4b5c6",
    "e4b7d1a2c3f4",
    "g1b2c3d4e5f6",
    "l1b2c3d4e5f7",
    "m4a5n6u7a8l9",
    "qms_p2_20260426",
    "s9t8u7v6w5x4",
    "v0a1b2c3d4e5",
)
branch_labels = None
depends_on = None


def _drop_users_amo_fk_if_exists() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for fk in inspector.get_foreign_keys("users"):
        if fk.get("constrained_columns") == ["amo_id"] and fk.get("name"):
            op.drop_constraint(fk["name"], "users", type_="foreignkey")
            return


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return bool(
            bind.execute(sa.text("SELECT to_regclass(:table_name)"), {"table_name": f"public.{table_name}"})
            .scalar()
        )
    return table_name in sa.inspect(bind).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return bool(
            bind.execute(
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
            ).first()
        )
    return any(col["name"] == column_name for col in sa.inspect(bind).get_columns(table_name))


def _clear_superuser_active_context() -> None:
    for table_name in ("user_active_context", "user_active_contexts"):
        if _table_exists(table_name) and _column_exists(table_name, "active_amo_id"):
            assignments = ["active_amo_id = NULL"]
            if _column_exists(table_name, "last_real_amo_id"):
                assignments.append("last_real_amo_id = NULL")
            if _column_exists(table_name, "data_mode"):
                assignments.append("data_mode = 'REAL'")
            op.execute(
                sa.text(
                    f"""
                    UPDATE {table_name}
                    SET {', '.join(assignments)}
                    WHERE user_id IN (SELECT id FROM users WHERE is_superuser = TRUE)
                    """
                )
            )


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        _drop_users_amo_fk_if_exists()
        op.alter_column(
            "users",
            "amo_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
        op.create_foreign_key(
            "users_amo_id_fkey",
            "users",
            "amos",
            ["amo_id"],
            ["id"],
            ondelete="SET NULL",
        )
    else:
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column(
                "amo_id",
                existing_type=sa.String(length=36),
                nullable=True,
            )

    op.execute(
        sa.text(
            """
            UPDATE users
            SET amo_id = NULL,
                department_id = NULL,
                is_amo_admin = FALSE,
                role = 'SUPERUSER'
            WHERE is_superuser = TRUE
            """
        )
    )
    _clear_superuser_active_context()


def downgrade() -> None:
    # Downgrade cannot safely infer which tenant owned each former platform user.
    # Operators must assign amo_id manually before enforcing NOT NULL again.
    pass
