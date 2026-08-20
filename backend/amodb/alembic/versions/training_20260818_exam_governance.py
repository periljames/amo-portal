"""Add examination form, intelligence, moderation and appeal controls.

Revision ID: training_260818_examgov
Revises: training_260818_governance
Create Date: 2026-08-18
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from amodb.apps.accounts import models as _account_models  # noqa: F401
from amodb.apps.training import models as _legacy_training_models  # noqa: F401
from amodb.apps.training import governance_models as _governance_models  # noqa: F401
from amodb.apps.training import exam_governance_models as exam_models


revision = "training_260818_examgov"
down_revision = "training_260818_governance"
branch_labels = None
depends_on = None


TABLES = (
    "training_exam_forms",
    "training_exam_item_analysis",
    "training_exam_moderations",
    "training_exam_appeals",
)


def _policy_name(table_name: str) -> str:
    return f"{table_name}_tenant_isolation"


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    for table_name in TABLES:
        if table_name not in existing:
            exam_models.Base.metadata.tables[table_name].create(bind, checkfirst=True)
            existing.add(table_name)

    if bind.dialect.name != "postgresql":
        return
    for table_name in TABLES:
        policy_name = _policy_name(table_name)
        op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'DROP POLICY IF EXISTS "{policy_name}" ON "{table_name}"'))
        op.execute(sa.text(f'''CREATE POLICY "{policy_name}" ON "{table_name}"
            USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
            WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))'''))


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    if bind.dialect.name == "postgresql":
        for table_name in reversed(TABLES):
            if table_name in existing:
                op.execute(sa.text(f'DROP POLICY IF EXISTS "{_policy_name(table_name)}" ON "{table_name}"'))
                op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))
    for table_name in reversed(TABLES):
        if table_name in existing:
            exam_models.Base.metadata.tables[table_name].drop(bind, checkfirst=True)
