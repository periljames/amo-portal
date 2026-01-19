"""add aircraft import templates table

Revision ID: ab12cd34ef56
Revises: 70a4e360dd80
Create Date: 2025-01-15 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ab12cd34ef56"
down_revision: Union[str, Sequence[str], None] = "70a4e360dd80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "aircraft_import_templates",
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
    op.create_index(
        "ix_aircraft_import_template_aircraft_template",
        "aircraft_import_templates",
        ["aircraft_template"],
    )
    op.create_index(
        "ix_aircraft_import_template_model_code",
        "aircraft_import_templates",
        ["model_code"],
    )
    op.create_index(
        "ix_aircraft_import_template_operator_code",
        "aircraft_import_templates",
        ["operator_code"],
    )
    op.create_index(
        "ix_aircraft_import_templates_name",
        "aircraft_import_templates",
        ["name"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_aircraft_import_templates_name", table_name="aircraft_import_templates")
    op.drop_index("ix_aircraft_import_template_operator_code", table_name="aircraft_import_templates")
    op.drop_index("ix_aircraft_import_template_model_code", table_name="aircraft_import_templates")
    op.drop_index("ix_aircraft_import_template_aircraft_template", table_name="aircraft_import_templates")
    op.drop_table("aircraft_import_templates")
