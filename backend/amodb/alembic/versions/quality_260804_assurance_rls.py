"""Enforce tenant row-level security on continuous assurance tables.

Revision ID: quality_260804_assurance_rls
Revises: quality_260804_assurance_hub
Create Date: 2026-08-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260804_assurance_rls"
down_revision = "quality_260804_assurance_hub"
branch_labels = None
depends_on = None


_TABLES = (
    "quality_assurance_controls",
    "quality_assurance_evidence_links",
    "quality_intelligence_reviews",
)


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _policy_name(table_name: str) -> str:
    return f"{table_name}_amo_isolation"


def upgrade() -> None:
    if not _is_postgresql():
        return
    for table_name in _TABLES:
        policy_name = _policy_name(table_name)
        op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY'))
        op.execute(
            sa.text(
                f"""
                CREATE POLICY {policy_name}
                ON "{table_name}"
                USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
                WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
                """
            )
        )


def downgrade() -> None:
    if not _is_postgresql():
        return
    for table_name in reversed(_TABLES):
        policy_name = _policy_name(table_name)
        op.execute(sa.text(f'DROP POLICY IF EXISTS {policy_name} ON "{table_name}"'))
        op.execute(sa.text(f'ALTER TABLE "{table_name}" NO FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))
