"""Store aviation cycles and landings as exact integers.

Revision ID: rel_20260805_ops_exact_counts
Revises: rel_20260805_ops_sources
Create Date: 2026-08-05
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "rel_20260805_ops_exact_counts"
down_revision: Union[str, Sequence[str], None] = "rel_20260805_ops_sources"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COUNT_COLUMNS = {
    "aircraft": ["total_cycles"],
    "aircraft_components": ["installed_cycles", "current_cycles", "tbo_cycles", "hsi_cycles", "last_overhaul_cycles"],
    "aircraft_usage": ["cycles", "tca_after", "tcesn_after", "tcsoh_after"],
    "maintenance_program_items": ["interval_cycles"],
    "maintenance_statuses": ["last_done_cycles", "next_due_cycles", "remaining_cycles"],
    "technical_aircraft_utilisation": ["cycles"],
    "technical_airworthiness_items": ["next_due_cycles"],
    "technical_airworthiness_compliance_events": ["next_due_cycles"],
    "technical_compliance_actions": ["due_cycles"],
}


def _columns(bind, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    tables = set(sa.inspect(bind).get_table_names())
    for table, columns in COUNT_COLUMNS.items():
        if table not in tables:
            continue
        existing = _columns(bind, table)
        for column in columns:
            if column not in existing:
                continue
            fractional = bind.execute(sa.text(
                f'SELECT count(*) FROM "{table}" WHERE "{column}" IS NOT NULL '
                f'AND "{column}" <> trunc("{column}")'
            )).scalar_one()
            if fractional:
                raise RuntimeError(
                    f"Cannot convert {table}.{column} to BIGINT: {fractional} fractional cycle value(s) require reconciliation."
                )
            op.alter_column(
                table,
                column,
                existing_type=sa.Numeric(20, 0),
                type_=sa.BigInteger(),
                postgresql_using=f'"{column}"::bigint',
                existing_nullable=True,
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    tables = set(sa.inspect(bind).get_table_names())
    for table, columns in COUNT_COLUMNS.items():
        if table not in tables:
            continue
        existing = _columns(bind, table)
        for column in columns:
            if column in existing:
                op.alter_column(
                    table,
                    column,
                    existing_type=sa.BigInteger(),
                    type_=sa.Numeric(20, 0),
                    postgresql_using=f'"{column}"::numeric',
                    existing_nullable=True,
                )
