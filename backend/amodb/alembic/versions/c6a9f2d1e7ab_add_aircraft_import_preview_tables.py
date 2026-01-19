"""add aircraft import preview tables

Revision ID: c6a9f2d1e7ab
Revises: a1b2c3d4e5f7
Create Date: 2025-03-27 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c6a9f2d1e7ab"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "aircraft_import_preview_sessions",
        sa.Column("preview_id", sa.String(length=36), primary_key=True),
        sa.Column("import_type", sa.String(length=32), nullable=False, server_default="aircraft"),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("column_mapping", sa.JSON(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("ocr_info", sa.JSON(), nullable=True),
        sa.Column("formula_discrepancies", sa.JSON(), nullable=True),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_aircraft_import_preview_session_created",
        "aircraft_import_preview_sessions",
        ["created_at"],
    )
    op.create_index(
        "ix_aircraft_import_preview_session_type",
        "aircraft_import_preview_sessions",
        ["import_type"],
    )

    op.create_table(
        "aircraft_import_preview_rows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("preview_id", sa.String(length=36), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("suggested_template", sa.JSON(), nullable=True),
        sa.Column("formula_proposals", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["preview_id"],
            ["aircraft_import_preview_sessions.preview_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_aircraft_import_preview_row_preview",
        "aircraft_import_preview_rows",
        ["preview_id", "row_number"],
    )
    op.create_index(
        "ix_aircraft_import_preview_row_preview_action",
        "aircraft_import_preview_rows",
        ["preview_id", "action"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_aircraft_import_preview_row_preview_action",
        table_name="aircraft_import_preview_rows",
    )
    op.drop_index(
        "ix_aircraft_import_preview_row_preview",
        table_name="aircraft_import_preview_rows",
    )
    op.drop_table("aircraft_import_preview_rows")

    op.drop_index(
        "ix_aircraft_import_preview_session_type",
        table_name="aircraft_import_preview_sessions",
    )
    op.drop_index(
        "ix_aircraft_import_preview_session_created",
        table_name="aircraft_import_preview_sessions",
    )
    op.drop_table("aircraft_import_preview_sessions")
