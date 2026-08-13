"""Training & Competence operating system.

Revision ID: training_20260813_operating_system
Revises: docctl_20260812_retention_approver
Create Date: 2026-08-13
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "training_20260813_operating_system"
down_revision = "docctl_20260812_retention_approver"
branch_labels = None
depends_on = None


TABLES = [
    "training_operating_settings",
    "training_plans",
    "training_plan_items",
    "training_plan_participants",
    "training_budgets",
    "training_budget_lines",
    "training_attendance_windows",
    "training_attendance_entries",
    "training_attendance_corrections",
    "training_assessment_templates",
    "training_assessment_questions",
    "training_authorization_cases",
    "training_assessment_instances",
    "training_experience_logs",
    "training_experience_reviews",
    "training_committee_decisions",
    "training_effectiveness_evaluations",
    "training_competence_reviews",
    "training_remedial_actions",
    "training_evidence_links",
]

CAPABILITIES = [
    "training.view", "training.self.view", "training.people.view", "training.people.manage",
    "training.course.view", "training.course.manage", "training.requirement.view", "training.requirement.manage",
    "training.plan.view", "training.plan.manage", "training.plan.review", "training.plan.approve",
    "training.budget.view", "training.budget.manage", "training.budget.review", "training.budget.approve",
    "training.session.view", "training.session.manage", "training.session.close",
    "training.attendance.view", "training.attendance.sign_self", "training.attendance.manage", "training.attendance.correct",
    "training.assessment.view", "training.assessment.create", "training.assessment.perform", "training.assessment.review", "training.assessment.approve",
    "training.authorization.view", "training.authorization.prepare", "training.authorization.recommend",
    "training.authorization.committee_decide", "training.authorization.issue", "training.authorization.renew",
    "training.authorization.restrict", "training.authorization.withdraw",
    "training.certificate.view", "training.certificate.issue", "training.certificate.revoke", "training.certificate.reissue",
    "training.report.view", "training.report.export", "training.settings.manage",
]

ROLE_CAPABILITIES = {
    "TRAINING_OFFICER": [code for code in CAPABILITIES if code not in {
        "training.plan.approve", "training.budget.approve", "training.assessment.approve",
        "training.authorization.committee_decide", "training.authorization.issue",
        "training.authorization.renew", "training.authorization.restrict", "training.authorization.withdraw",
        "training.settings.manage",
    }],
    "TRAINING_MANAGER": CAPABILITIES,
    "TRAINING_FINANCE": [
        "training.view", "training.self.view", "training.plan.view", "training.budget.view",
        "training.budget.review", "training.budget.approve", "training.report.view", "training.report.export",
    ],
    "TRAINING_ASSESSOR": [
        "training.view", "training.self.view", "training.people.view", "training.session.view",
        "training.attendance.view", "training.assessment.view", "training.assessment.perform",
    ],
    "TRAINING_QUALITY_REVIEWER": [code for code in CAPABILITIES if code not in {
        "training.people.manage", "training.course.manage", "training.requirement.manage", "training.plan.manage",
        "training.budget.manage", "training.session.manage", "training.settings.manage",
    }],
}


def _create_tables() -> None:
    # Use the canonical SQLAlchemy declarations so migration DDL and runtime
    # metadata cannot drift. All referenced legacy/account tables are loaded by
    # the training model module before creation.
    from amodb.apps.accounts import models as _accounts  # noqa: F401
    from amodb.apps.training import models as _training  # noqa: F401
    from amodb.apps.training import operating_models as operating

    bind = op.get_bind()
    for table_name in TABLES:
        operating.Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)


def _install_rls() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table_name in TABLES:
        op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'DROP POLICY IF EXISTS "{table_name}_tenant_isolation" ON "{table_name}"'))
        op.execute(sa.text(f'''
            CREATE POLICY "{table_name}_tenant_isolation" ON "{table_name}"
            USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
            WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
        '''))


def _seed_authorization() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for number, code in enumerate(CAPABILITIES, start=1):
        op.execute(sa.text("""
            INSERT INTO auth_capability_definitions (id, code, module, description)
            VALUES (:id, :code, 'training', :description)
            ON CONFLICT (code) DO UPDATE SET module = 'training', description = EXCLUDED.description
        """).bindparams(id=f"trn-cap-{number:03d}", code=code, description=code.replace("training.", "").replace(".", " ").title()))
    for number, (role, capabilities) in enumerate(ROLE_CAPABILITIES.items(), start=1):
        role_id = f"trn-role-{number:02d}"
        op.execute(sa.text("""
            INSERT INTO auth_role_definitions (id, code, scope_type, description, is_system)
            VALUES (:id, :code, 'AMO', :description, true)
            ON CONFLICT (code) DO UPDATE SET scope_type = 'AMO', description = EXCLUDED.description, is_system = true
        """).bindparams(id=role_id, code=role, description=role.replace("_", " ").title()))
        for code in capabilities:
            capability_id = f"trn-cap-{CAPABILITIES.index(code) + 1:03d}"
            op.execute(sa.text("""
                INSERT INTO auth_role_capability_bindings (id, role_id, capability_id, constraints_json)
                VALUES (:id, :role_id, :capability_id, '{}'::json)
                ON CONFLICT (role_id, capability_id) DO NOTHING
            """).bindparams(id=f"trn-bind-{number:02d}-{CAPABILITIES.index(code) + 1:03d}", role_id=role_id, capability_id=capability_id))
    # Backfill only roles that can be determined from authoritative department,
    # account-role, or position metadata. Ordinary employees remain self-service.
    assignments = [
        ("trn-role-01", "UPPER(d.code) IN ('TRAINING','TRAINING_AND_COMPETENCE','TRAINING-&-COMPETENCE') AND LOWER(COALESCE(u.position_title,'')) !~ '(head|manager|lead)'"),
        ("trn-role-02", "u.is_amo_admin = true OR CAST(u.role AS TEXT) IN ('AMO_ADMIN','QUALITY_MANAGER') OR (UPPER(d.code) IN ('TRAINING','TRAINING_AND_COMPETENCE','TRAINING-&-COMPETENCE') AND LOWER(COALESCE(u.position_title,'')) ~ '(head|manager|lead)')"),
        ("trn-role-03", "CAST(u.role AS TEXT) IN ('FINANCE_MANAGER','ACCOUNTS_OFFICER')"),
        ("trn-role-04", "LOWER(COALESCE(u.position_title,'')) ~ '(assessor|instructor|trainer)'"),
        ("trn-role-05", "CAST(u.role AS TEXT) IN ('QUALITY_INSPECTOR','AUDITOR') OR UPPER(d.code) IN ('QUALITY','QUALITY_ASSURANCE')"),
    ]
    for role_id, condition in assignments:
        op.execute(sa.text(f"""
            INSERT INTO auth_user_role_assignments (id, amo_id, user_id, role_id, valid_from, created_at)
            SELECT md5(u.amo_id || '|' || u.id || '|{role_id}'), u.amo_id, u.id, '{role_id}', now(), now()
            FROM users u LEFT JOIN departments d ON d.id = u.department_id
            WHERE u.amo_id IS NOT NULL AND u.is_active = true AND u.is_system_account = false
              AND ({condition})
              AND NOT EXISTS (
                SELECT 1 FROM auth_user_role_assignments a
                WHERE a.amo_id = u.amo_id AND a.user_id = u.id AND a.role_id = '{role_id}'
              )
        """))


def upgrade() -> None:
    supports_named_check_alter = op.get_bind().dialect.name != "sqlite"
    op.add_column("training_courses", sa.Column("assessment_required", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("training_courses", sa.Column("pass_threshold", sa.Integer(), nullable=True, server_default=sa.text("80")))
    op.add_column("training_courses", sa.Column("attendance_required", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("training_courses", sa.Column("ojt_signoff_required", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("training_courses", sa.Column("evidence_required", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("training_courses", sa.Column("certificate_policy", sa.String(length=32), nullable=False, server_default="ON_COMPLETION"))
    op.add_column("training_courses", sa.Column("external_completion_behavior", sa.String(length=32), nullable=False, server_default="REVIEW_REQUIRED"))
    if supports_named_check_alter:
        op.create_check_constraint("ck_training_course_pass_threshold", "training_courses", "pass_threshold IS NULL OR pass_threshold BETWEEN 0 AND 100")

    op.add_column("training_requirements", sa.Column("manual_reference", sa.String(length=255), nullable=True))
    op.add_column("training_requirements", sa.Column("planning_lead_days", sa.Integer(), nullable=True))
    op.add_column("training_requirements", sa.Column("assessment_required", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("training_requirements", sa.Column("certificate_required", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("training_requirements", sa.Column("authorization_relevance", sa.Text(), nullable=True))
    if supports_named_check_alter:
        op.create_check_constraint("ck_training_requirement_lead_days", "training_requirements", "planning_lead_days IS NULL OR planning_lead_days BETWEEN 1 AND 365")

    _create_tables()
    _install_rls()
    _seed_authorization()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        role_ids = list({f"trn-role-{number:02d}" for number in range(1, len(ROLE_CAPABILITIES) + 1)})
        codes = CAPABILITIES
        op.execute(sa.text("DELETE FROM auth_user_role_assignments WHERE role_id = ANY(:ids)").bindparams(ids=role_ids))
        op.execute(sa.text("DELETE FROM auth_role_capability_bindings WHERE role_id = ANY(:ids)").bindparams(ids=role_ids))
        op.execute(sa.text("DELETE FROM auth_role_definitions WHERE id = ANY(:ids)").bindparams(ids=role_ids))
        op.execute(sa.text("DELETE FROM auth_capability_definitions WHERE code = ANY(:codes)").bindparams(codes=codes))
    for table_name in reversed(TABLES):
        op.drop_table(table_name)
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("ck_training_requirement_lead_days", "training_requirements", type_="check")
    for column in ("authorization_relevance", "certificate_required", "assessment_required", "planning_lead_days", "manual_reference"):
        op.drop_column("training_requirements", column)
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("ck_training_course_pass_threshold", "training_courses", type_="check")
    for column in ("external_completion_behavior", "certificate_policy", "evidence_required", "ojt_signoff_required", "attendance_required", "pass_threshold", "assessment_required"):
        op.drop_column("training_courses", column)
