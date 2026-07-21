"""add aircraft import templates table

Revision ID: ab12cd34ef56
Revises: 70a4e360dd80
Create Date: 2025-01-15 12:30:00.000000

This migration is deliberately idempotent because several development
and restored AMO databases already contain aircraft_import_templates even
when Alembic has not recorded this revision.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ab12cd34ef56"
down_revision: Union[str, Sequence[str], None] = "70a4e360dd80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "aircraft_import_templates"


def _table_exists(conn) -> bool:
    return bool(
        conn.execute(
            sa.text("""
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = :table_name
                LIMIT 1
            """),
            {"table_name": _TABLE},
        ).scalar()
    )


def _constraint_exists(conn, constraint_name: str) -> bool:
    return bool(
        conn.execute(
            sa.text("""
                SELECT 1
                FROM information_schema.table_constraints
                WHERE table_schema = current_schema()
                  AND table_name = :table_name
                  AND constraint_name = :constraint_name
                LIMIT 1
            """),
            {"table_name": _TABLE, "constraint_name": constraint_name},
        ).scalar()
    )


def _column_exists(conn, column_name: str) -> bool:
    return bool(
        conn.execute(
            sa.text("""
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = :table_name
                  AND column_name = :column_name
                LIMIT 1
            """),
            {"table_name": _TABLE, "column_name": column_name},
        ).scalar()
    )


def _create_table_if_missing(conn) -> None:
    if _table_exists(conn):
        return

    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("aircraft_template", sa.String(length=50), nullable=True),
        sa.Column("model_code", sa.String(length=32), nullable=True),
        sa.Column("operator_code", sa.String(length=5), nullable=True),
        sa.Column("column_mapping", sa.JSON(), nullable=True),
        sa.Column("default_values", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_aircraft_import_template_name"),
    )


def _ensure_columns(conn) -> None:
    column_defs = {
        "id": "ALTER TABLE aircraft_import_templates ADD COLUMN id SERIAL",
        "name": "ALTER TABLE aircraft_import_templates ADD COLUMN name varchar(120)",
        "aircraft_template": "ALTER TABLE aircraft_import_templates ADD COLUMN aircraft_template varchar(50)",
        "model_code": "ALTER TABLE aircraft_import_templates ADD COLUMN model_code varchar(32)",
        "operator_code": "ALTER TABLE aircraft_import_templates ADD COLUMN operator_code varchar(5)",
        "column_mapping": "ALTER TABLE aircraft_import_templates ADD COLUMN column_mapping json",
        "default_values": "ALTER TABLE aircraft_import_templates ADD COLUMN default_values json",
        "created_at": "ALTER TABLE aircraft_import_templates ADD COLUMN created_at timestamptz",
        "updated_at": "ALTER TABLE aircraft_import_templates ADD COLUMN updated_at timestamptz",
    }
    for column_name, ddl in column_defs.items():
        if not _column_exists(conn, column_name):
            conn.execute(sa.text(ddl))

    conn.execute(
        sa.text("""
            UPDATE aircraft_import_templates
            SET created_at = COALESCE(created_at, NOW()),
                updated_at = COALESCE(updated_at, NOW())
            WHERE created_at IS NULL OR updated_at IS NULL
        """)
    )

    conn.execute(sa.text("ALTER TABLE aircraft_import_templates ALTER COLUMN name SET NOT NULL"))
    conn.execute(sa.text("ALTER TABLE aircraft_import_templates ALTER COLUMN created_at SET NOT NULL"))
    conn.execute(sa.text("ALTER TABLE aircraft_import_templates ALTER COLUMN updated_at SET NOT NULL"))

    if not _constraint_exists(conn, "pk_aircraft_import_templates"):
        conn.execute(
            sa.text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_constraint c
                        JOIN pg_class t ON t.oid = c.conrelid
                        JOIN pg_namespace n ON n.oid = t.relnamespace
                        WHERE n.nspname = current_schema()
                          AND t.relname = 'aircraft_import_templates'
                          AND c.contype = 'p'
                    ) THEN
                        ALTER TABLE aircraft_import_templates
                        ADD CONSTRAINT pk_aircraft_import_templates PRIMARY KEY (id);
                    END IF;
                END $$;
            """)
        )

    if not _constraint_exists(conn, "uq_aircraft_import_template_name"):
        conn.execute(
            sa.text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_constraint c
                        JOIN pg_class t ON t.oid = c.conrelid
                        JOIN pg_namespace n ON n.oid = t.relnamespace
                        WHERE n.nspname = current_schema()
                          AND t.relname = 'aircraft_import_templates'
                          AND c.conname = 'uq_aircraft_import_template_name'
                    ) THEN
                        ALTER TABLE aircraft_import_templates
                        ADD CONSTRAINT uq_aircraft_import_template_name UNIQUE (name);
                    END IF;
                END $$;
            """)
        )


def _ensure_indexes(conn) -> None:
    conn.execute(
        sa.text("""
            CREATE INDEX IF NOT EXISTS ix_aircraft_import_template_aircraft_template
            ON aircraft_import_templates (aircraft_template)
        """)
    )
    conn.execute(
        sa.text("""
            CREATE INDEX IF NOT EXISTS ix_aircraft_import_template_model_code
            ON aircraft_import_templates (model_code)
        """)
    )
    conn.execute(
        sa.text("""
            CREATE INDEX IF NOT EXISTS ix_aircraft_import_template_operator_code
            ON aircraft_import_templates (operator_code)
        """)
    )
    conn.execute(
        sa.text("""
            CREATE INDEX IF NOT EXISTS ix_aircraft_import_templates_name
            ON aircraft_import_templates (name)
        """)
    )


def upgrade() -> None:
    """Upgrade schema idempotently."""
    conn = op.get_bind()
    _create_table_if_missing(conn)
    _ensure_columns(conn)
    _ensure_indexes(conn)


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    if not _table_exists(conn):
        return
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_aircraft_import_templates_name"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_aircraft_import_template_operator_code"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_aircraft_import_template_model_code"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_aircraft_import_template_aircraft_template"))
    op.drop_table(_TABLE)
