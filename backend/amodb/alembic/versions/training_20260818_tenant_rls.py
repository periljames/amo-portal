"""Close Training tenant RLS gaps on post-operating-system tables.

Revision ID: training_260818_rls_gap
Revises: resilience_260816_commands
Create Date: 2026-08-18
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "training_260818_rls_gap"
down_revision = "resilience_260816_commands"
branch_labels = None
depends_on = None


TENANT_TABLES = (
    "training_configuration_revisions",
    "training_reference_resources",
    "training_controlled_form_templates",
    "training_automation_runs",
    "training_setup_versions",
    "training_change_requests",
    "training_workflow_instances",
    "training_workflow_steps",
    "training_session_invitations",
    "training_report_definitions",
    "training_report_jobs",
    "training_saved_views",
)


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _policy_name(table_name: str) -> str:
    return f"{table_name}_tenant_isolation"


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    existing = _existing_tables()
    for table_name in TENANT_TABLES:
        if table_name not in existing:
            continue
        policy_name = _policy_name(table_name)
        op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'DROP POLICY IF EXISTS "{policy_name}" ON "{table_name}"'))
        op.execute(
            sa.text(
                f'''CREATE POLICY "{policy_name}" ON "{table_name}"
                USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
                WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))'''
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    existing = _existing_tables()
    for table_name in TENANT_TABLES:
        if table_name not in existing:
            continue
        policy_name = _policy_name(table_name)
        op.execute(sa.text(f'DROP POLICY IF EXISTS "{policy_name}" ON "{table_name}"'))
        op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))
