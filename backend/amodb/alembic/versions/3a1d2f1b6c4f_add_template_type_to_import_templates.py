"""Add template_type to aircraft import templates.

Revision ID: 3a1d2f1b6c4f
Revises: ab12cd34ef56
Create Date: 2025-01-12 00:00:00.000000

This migration is idempotent because restored/local databases may already
contain aircraft_import_templates.template_type while Alembic has not recorded
this revision.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3a1d2f1b6c4f"
down_revision: Union[str, Sequence[str], None] = "ab12cd34ef56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "aircraft_import_templates"


def _table_exists(conn) -> bool:
    return bool(
        conn.execute(
            sa.text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = :table_name
                LIMIT 1
                """
            ),
            {"table_name": _TABLE},
        ).scalar()
    )


def _column_exists(conn, column_name: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = :table_name
                  AND column_name = :column_name
                LIMIT 1
                """
            ),
            {"table_name": _TABLE, "column_name": column_name},
        ).scalar()
    )


def _constraint_exists(conn, constraint_name: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                """
                SELECT 1
                FROM information_schema.table_constraints
                WHERE table_schema = current_schema()
                  AND table_name = :table_name
                  AND constraint_name = :constraint_name
                LIMIT 1
                """
            ),
            {"table_name": _TABLE, "constraint_name": constraint_name},
        ).scalar()
    )


def _index_exists(conn, index_name: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                """
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND tablename = :table_name
                  AND indexname = :index_name
                LIMIT 1
                """
            ),
            {"table_name": _TABLE, "index_name": index_name},
        ).scalar()
    )


def _has_duplicate_type_name_pairs(conn) -> bool:
    if not (_column_exists(conn, "template_type") and _column_exists(conn, "name")):
        return True
    return bool(
        conn.execute(
            sa.text(
                """
                SELECT 1
                FROM aircraft_import_templates
                GROUP BY template_type, name
                HAVING COUNT(*) > 1
                LIMIT 1
                """
            )
        ).scalar()
    )


def _ensure_template_type_column(conn) -> None:
    if not _column_exists(conn, "template_type"):
        conn.execute(
            sa.text(
                """
                ALTER TABLE aircraft_import_templates
                ADD COLUMN template_type varchar(32)
                """
            )
        )

    conn.execute(
        sa.text(
            """
            UPDATE aircraft_import_templates
            SET template_type = COALESCE(NULLIF(template_type, ''), 'aircraft')
            WHERE template_type IS NULL OR template_type = ''
            """
        )
    )
    conn.execute(
        sa.text(
            """
            ALTER TABLE aircraft_import_templates
            ALTER COLUMN template_type SET DEFAULT 'aircraft'
            """
        )
    )
    conn.execute(
        sa.text(
            """
            ALTER TABLE aircraft_import_templates
            ALTER COLUMN template_type SET NOT NULL
            """
        )
    )


def _drop_old_name_unique_if_present(conn) -> None:
    if _constraint_exists(conn, "uq_aircraft_import_template_name"):
        conn.execute(
            sa.text(
                """
                ALTER TABLE aircraft_import_templates
                DROP CONSTRAINT uq_aircraft_import_template_name
                """
            )
        )


def _ensure_type_name_unique_if_safe(conn) -> None:
    if _constraint_exists(conn, "uq_aircraft_import_template_type_name"):
        return
    if _has_duplicate_type_name_pairs(conn):
        # Do not delete or alter data in a migration. The application can still
        # run; an operator can clean duplicates later and add the constraint.
        return
    conn.execute(
        sa.text(
            """
            ALTER TABLE aircraft_import_templates
            ADD CONSTRAINT uq_aircraft_import_template_type_name
            UNIQUE (template_type, name)
            """
        )
    )


def _ensure_type_index(conn) -> None:
    if not _index_exists(conn, "ix_aircraft_import_template_type"):
        conn.execute(
            sa.text(
                """
                CREATE INDEX ix_aircraft_import_template_type
                ON aircraft_import_templates (template_type)
                """
            )
        )


def upgrade() -> None:
    conn = op.get_bind()
    if not _table_exists(conn):
        # The down_revision should normally create this table. This guard keeps
        # the revision safe if an operator runs branches in an unusual order.
        conn.execute(
            sa.text(
                """
                CREATE TABLE aircraft_import_templates (
                    id SERIAL PRIMARY KEY,
                    name varchar(120) NOT NULL,
                    aircraft_template varchar(50),
                    model_code varchar(32),
                    operator_code varchar(5),
                    column_mapping json,
                    default_values json,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
        )
    _ensure_template_type_column(conn)
    _drop_old_name_unique_if_present(conn)
    _ensure_type_name_unique_if_safe(conn)
    _ensure_type_index(conn)


def downgrade() -> None:
    conn = op.get_bind()
    if not _table_exists(conn):
        return
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_aircraft_import_template_type"))
    if _constraint_exists(conn, "uq_aircraft_import_template_type_name"):
        conn.execute(
            sa.text(
                """
                ALTER TABLE aircraft_import_templates
                DROP CONSTRAINT uq_aircraft_import_template_type_name
                """
            )
        )
    if not _constraint_exists(conn, "uq_aircraft_import_template_name") and not _has_duplicate_type_name_pairs(conn):
        # Recreate the legacy name-only uniqueness only when safe.
        conn.execute(
            sa.text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM (
                            SELECT name FROM aircraft_import_templates
                            GROUP BY name
                            HAVING COUNT(*) > 1
                        ) d
                    ) THEN
                        ALTER TABLE aircraft_import_templates
                        ADD CONSTRAINT uq_aircraft_import_template_name UNIQUE (name);
                    END IF;
                END $$;
                """
            )
        )
    if _column_exists(conn, "template_type"):
        conn.execute(sa.text("ALTER TABLE aircraft_import_templates DROP COLUMN template_type"))
