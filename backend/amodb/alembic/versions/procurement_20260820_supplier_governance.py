"""Add governed supplier evaluation, approval and re-evaluation controls.

Revision ID: procurement_260820_supplier_gov
Revises: quality_260820_wf_schema, quality_260817_canonical_document_bridge
Create Date: 2026-08-20
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from amodb.apps.procurement import supplier_governance_models as governance


revision = "procurement_260820_supplier_gov"
down_revision = (
    "quality_260820_wf_schema",
    "quality_260817_canonical_document_bridge",
)
branch_labels = None
depends_on = None

TABLES = [
    "procurement_supplier_governance_policies",
    "procurement_supplier_evaluation_templates",
    "procurement_supplier_evaluation_criteria",
    "procurement_supplier_evaluations",
    "procurement_supplier_evaluation_responses",
    "procurement_supplier_governance_decisions",
    "procurement_supplier_reevaluation_actions",
]


def _rls_policy(table_name: str) -> str:
    return f"{table_name}_tenant_isolation"


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    metadata = governance.Base.metadata
    for table_name in TABLES:
        if table_name not in existing:
            metadata.tables[table_name].create(bind, checkfirst=True)

    if bind.dialect.name != "postgresql":
        return
    for table_name in TABLES:
        policy = _rls_policy(table_name)
        op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'DROP POLICY IF EXISTS "{policy}" ON "{table_name}"'))
        op.execute(sa.text(
            f'''CREATE POLICY "{policy}" ON "{table_name}"
                USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
                WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))'''
        ))


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    metadata = governance.Base.metadata
    for table_name in reversed(TABLES):
        if table_name not in existing:
            continue
        if bind.dialect.name == "postgresql":
            policy = _rls_policy(table_name)
            op.execute(sa.text(f'DROP POLICY IF EXISTS "{policy}" ON "{table_name}"'))
            op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))
        metadata.tables[table_name].drop(bind, checkfirst=True)
