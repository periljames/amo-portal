"""Add template_type to aircraft import templates.

Revision ID: 3a1d2f1b6c4f
Revises: 70a4e360dd80
Create Date: 2025-01-12 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3a1d2f1b6c4f"
down_revision: Union[str, Sequence[str], None] = "70a4e360dd80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "aircraft_import_templates",
        sa.Column(
            "template_type",
            sa.String(length=32),
            nullable=False,
            server_default="aircraft",
        ),
    )
    op.drop_constraint(
        "uq_aircraft_import_template_name",
        "aircraft_import_templates",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_aircraft_import_template_type_name",
        "aircraft_import_templates",
        ["template_type", "name"],
    )
    op.create_index(
        "ix_aircraft_import_template_type",
        "aircraft_import_templates",
        ["template_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_aircraft_import_template_type",
        table_name="aircraft_import_templates",
    )
    op.drop_constraint(
        "uq_aircraft_import_template_type_name",
        "aircraft_import_templates",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_aircraft_import_template_name",
        "aircraft_import_templates",
        ["name"],
    )
    op.drop_column("aircraft_import_templates", "template_type")
