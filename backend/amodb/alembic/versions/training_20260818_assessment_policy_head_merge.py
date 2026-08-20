"""Merge current application and Training heads; add explicit assessment policy.

Revision ID: training_260818_policy_merge
Revises: training_260818_examgov, rostering_260818_control_numbers
Create Date: 2026-08-18
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from amodb.apps.training import assessment_policy_models as policy_models


revision = "training_260818_policy_merge"
down_revision = (
    "training_260818_examgov",
    "rostering_260818_control_numbers",
)
branch_labels = None
depends_on = None

TABLE = "training_assessment_attempt_policies"
POLICY = f"{TABLE}_tenant_isolation"


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    if TABLE not in existing:
        policy_models.Base.metadata.tables[TABLE].create(bind, checkfirst=True)

    if bind.dialect.name != "postgresql":
        return
    op.execute(sa.text(f'ALTER TABLE "{TABLE}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'DROP POLICY IF EXISTS "{POLICY}" ON "{TABLE}"'))
    op.execute(sa.text(f'''CREATE POLICY "{POLICY}" ON "{TABLE}"
        USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
        WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))'''))


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    if TABLE not in existing:
        return
    if bind.dialect.name == "postgresql":
        op.execute(sa.text(f'DROP POLICY IF EXISTS "{POLICY}" ON "{TABLE}"'))
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" DISABLE ROW LEVEL SECURITY'))
    policy_models.Base.metadata.tables[TABLE].drop(bind, checkfirst=True)
