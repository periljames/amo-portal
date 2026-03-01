"""enable ltree and index physical copy location paths

Revision ID: b1a2e3r4o5d6
Revises: aerodoc_hybrid_dms
Create Date: 2026-03-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "b1a2e3r4o5d6"
down_revision = "aerodoc_hybrid_dms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS ltree")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'physical_controlled_copies'
                  AND column_name = 'storage_location_path'
                  AND data_type <> 'USER-DEFINED'
            ) THEN
                ALTER TABLE physical_controlled_copies
                ALTER COLUMN storage_location_path TYPE ltree
                USING NULLIF(replace(storage_location_path, '.', '.'), '')::ltree;
            END IF;
        END $$;
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_physical_copy_location_gist ON physical_controlled_copies USING GIST (storage_location_path)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_physical_copy_location_gist")
    # Keep ltree extension and column type to avoid destructive downgrade.
