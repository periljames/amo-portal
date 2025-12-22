"""add import reconciliation tables

Revision ID: e1b2c3d4e5f6
Revises: 70a4e360dd80
Create Date: 2025-01-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "70a4e360dd80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "aircraft_import_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("import_type", sa.String(length=32), nullable=False, server_default="aircraft"),
        sa.Column("diff_map", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_import_snapshot_batch",
        "aircraft_import_snapshots",
        ["batch_id", "created_at"],
    )
    op.create_index(
        "ix_import_snapshot_type",
        "aircraft_import_snapshots",
        ["import_type", "created_at"],
    )

    op.create_table(
        "aircraft_import_reconciliation_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("import_type", sa.String(length=32), nullable=False, server_default="aircraft"),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(length=50), nullable=True),
        sa.Column("original_value", sa.JSON(), nullable=True),
        sa.Column("proposed_value", sa.JSON(), nullable=True),
        sa.Column("final_value", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["aircraft_import_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_import_recon_batch",
        "aircraft_import_reconciliation_logs",
        ["batch_id", "created_at"],
    )
    op.create_index(
        "ix_import_recon_snapshot",
        "aircraft_import_reconciliation_logs",
        ["snapshot_id", "created_at"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_import_recon_snapshot", table_name="aircraft_import_reconciliation_logs")
    op.drop_index("ix_import_recon_batch", table_name="aircraft_import_reconciliation_logs")
    op.drop_table("aircraft_import_reconciliation_logs")

    op.drop_index("ix_import_snapshot_type", table_name="aircraft_import_snapshots")
    op.drop_index("ix_import_snapshot_batch", table_name="aircraft_import_snapshots")
    op.drop_table("aircraft_import_snapshots")
