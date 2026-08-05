"""Add immutable revisions to Reliability calculation runs.

Revision ID: rel_20260804_calc_revisions
Revises: rel_quality_20260804_merge
Create Date: 2026-08-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "rel_20260804_calc_revisions"
down_revision: Union[str, Sequence[str], None] = "rel_quality_20260804_merge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

IDENTITY_COLUMNS = [
    "amo_id",
    "metric_definition_id",
    "scope_type",
    "scope_id",
    "period_start",
    "period_end",
    "formula_version",
]


def upgrade() -> None:
    op.add_column(
        "reliability_calculation_runs",
        sa.Column("revision", sa.Integer(), nullable=True, server_default=sa.text("1")),
    )
    op.execute("UPDATE reliability_calculation_runs SET revision = 1 WHERE revision IS NULL")
    op.alter_column(
        "reliability_calculation_runs",
        "revision",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("1"),
    )
    op.drop_constraint(
        "uq_reliability_calculation_identity",
        "reliability_calculation_runs",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_reliability_calculation_identity",
        "reliability_calculation_runs",
        [*IDENTITY_COLUMNS, "revision"],
    )
    op.create_index(
        "ix_reliability_calculation_identity_revision",
        "reliability_calculation_runs",
        [*IDENTITY_COLUMNS, "revision"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    later_revisions = bind.execute(
        sa.text("SELECT COUNT(*) FROM reliability_calculation_runs WHERE revision > 1")
    ).scalar_one()
    if later_revisions:
        raise RuntimeError(
            "Cannot downgrade calculation-run revisions while immutable revisions greater than 1 exist."
        )
    op.drop_index(
        "ix_reliability_calculation_identity_revision",
        table_name="reliability_calculation_runs",
    )
    op.drop_constraint(
        "uq_reliability_calculation_identity",
        "reliability_calculation_runs",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_reliability_calculation_identity",
        "reliability_calculation_runs",
        IDENTITY_COLUMNS,
    )
    op.drop_column("reliability_calculation_runs", "revision")
