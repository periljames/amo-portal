"""Add governed aviation Training Operating System control envelope.

Revision ID: training_260818_governance
Revises: training_260818_rls_gap
Create Date: 2026-08-18

The migration is additive.  Legacy course/event/record/certificate/competence and
Accounts authorisation tables remain authoritative and are referenced by FK where
appropriate.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from amodb.apps.accounts import models as _account_models  # noqa: F401
from amodb.apps.training import models as _legacy_training_models  # noqa: F401
from amodb.apps.training import governance_models as governance


revision = "training_260818_governance"
down_revision = "training_260818_rls_gap"
branch_labels = None
depends_on = None


TABLES = (
    "training_authorities",
    "training_governance_rules",
    "training_governance_conflicts",
    "training_approvals",
    "training_facilities",
    "training_providers_governed",
    "training_approval_scopes",
    "training_technical_authorisations",
    "training_course_revisions",
    "training_course_modules",
    "training_learning_objectives",
    "training_practical_tasks",
    "training_course_prerequisites",
    "training_course_references",
    "training_material_revisions",
    "training_session_governance",
    "training_module_attendance",
    "training_practical_assessments",
    "training_question_bank_items",
    "training_question_revisions",
    "training_exam_blueprints",
    "training_exam_generations",
    "training_exam_attempts_governed",
    "training_exam_attempt_items",
    "training_exam_security_events",
    "training_impact_assessments",
    "training_impact_items",
    "training_session_closeouts",
    "training_learner_closeouts",
    "training_authority_submissions",
    "training_quality_links",
)


def _policy_name(table_name: str) -> str:
    return f"{table_name}_tenant_isolation"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    for table_name in TABLES:
        if table_name in existing:
            continue
        governance.Base.metadata.tables[table_name].create(bind, checkfirst=True)
        existing.add(table_name)

    if bind.dialect.name != "postgresql":
        return

    for table_name in TABLES:
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
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    if bind.dialect.name == "postgresql":
        for table_name in reversed(TABLES):
            if table_name not in existing:
                continue
            op.execute(sa.text(f'DROP POLICY IF EXISTS "{_policy_name(table_name)}" ON "{table_name}"'))
            op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))

    for table_name in reversed(TABLES):
        if table_name in existing:
            governance.Base.metadata.tables[table_name].drop(bind, checkfirst=True)
