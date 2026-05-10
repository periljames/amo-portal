"""phase1 qms tenant guardrails

Revision ID: qms_p1_rls_20260426
Revises: p0a6_train_record
Create Date: 2026-04-26

This migration is intentionally defensive. The existing schema already contains
several QMS/quality tenant-scoping migrations. This migration only fills the
known ORM/schema gap for qms_corrective_actions and enables PostgreSQL RLS
policies on QMS tables that already expose amo_id.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "qms_p1_rls_20260426"
# This migration is deliberately linear.
# It previously declared several independent branch heads as down_revisions.
# That caused KeyError failures in production databases whose alembic_version table
# did not contain every listed parent head. The migration body is defensive and
# checks table/column/policy existence, so it only needs to run after the training
# record integrity migration that is part of the current active branch.
down_revision = "p0a6_train_record"
branch_labels = None
depends_on = None


QMS_AMO_SCOPED_TABLES = (
    "qms_documents",
    "qms_document_revisions",
    "qms_document_distributions",
    "qms_audits",
    "qms_audit_schedules",
    "qms_audit_findings",
    "qms_corrective_actions",
    "qms_notifications",
    "quality_cars",
    "training_courses",
    "training_records",
    "training_requirements",
    "training_events",
)


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _table_exists(table_name: str) -> bool:
    return bool(op.get_bind().execute(sa.text("SELECT to_regclass(:table_name)"), {"table_name": f"public.{table_name}"}).scalar())


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return bool(
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                  AND column_name = :column_name
                """
            ),
            {"table_name": table_name, "column_name": column_name},
        )
        .first()
    )


def _constraint_exists(table_name: str, constraint_name: str) -> bool:
    return bool(
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = 'public'
                  AND t.relname = :table_name
                  AND c.conname = :constraint_name
                """
            ),
            {"table_name": table_name, "constraint_name": constraint_name},
        )
        .first()
    )


def _index_exists(index_name: str) -> bool:
    return bool(op.get_bind().execute(sa.text("SELECT to_regclass(:index_name)"), {"index_name": f"public.{index_name}"}).scalar())


def _policy_exists(table_name: str, policy_name: str) -> bool:
    return bool(
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT 1
                FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename = :table_name
                  AND policyname = :policy_name
                """
            ),
            {"table_name": table_name, "policy_name": policy_name},
        )
        .first()
    )


def _ensure_qms_corrective_actions_amo_id() -> None:
    if not _table_exists("qms_corrective_actions"):
        return
    if not _column_exists("qms_corrective_actions", "amo_id"):
        op.add_column("qms_corrective_actions", sa.Column("amo_id", sa.String(length=36), nullable=True))
    if _table_exists("qms_audit_findings") and _column_exists("qms_audit_findings", "amo_id"):
        op.execute(
            """
            UPDATE qms_corrective_actions cap
            SET amo_id = finding.amo_id
            FROM qms_audit_findings finding
            WHERE cap.finding_id = finding.id
              AND cap.amo_id IS NULL
              AND finding.amo_id IS NOT NULL
            """
        )
    if not _index_exists("ix_qms_corrective_actions_amo_id"):
        op.create_index("ix_qms_corrective_actions_amo_id", "qms_corrective_actions", ["amo_id"])
    if not _constraint_exists("qms_corrective_actions", "fk_qms_corrective_actions_amo_id"):
        op.create_foreign_key(
            "fk_qms_corrective_actions_amo_id",
            "qms_corrective_actions",
            "amos",
            ["amo_id"],
            ["id"],
            ondelete="CASCADE",
        )
    null_count = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM qms_corrective_actions WHERE amo_id IS NULL")).scalar()
    if not null_count:
        op.alter_column("qms_corrective_actions", "amo_id", nullable=False)


def _enable_rls(table_name: str) -> None:
    if not _table_exists(table_name) or not _column_exists(table_name, "amo_id"):
        return
    policy_name = f"{table_name}_amo_isolation"
    op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
    if not _policy_exists(table_name, policy_name):
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


def upgrade() -> None:
    if not _is_postgresql():
        return
    _ensure_qms_corrective_actions_amo_id()
    for table_name in QMS_AMO_SCOPED_TABLES:
        _enable_rls(table_name)


def downgrade() -> None:
    if not _is_postgresql():
        return
    for table_name in QMS_AMO_SCOPED_TABLES:
        if not _table_exists(table_name):
            continue
        policy_name = f"{table_name}_amo_isolation"
        if _policy_exists(table_name, policy_name):
            op.execute(sa.text(f'DROP POLICY {policy_name} ON "{table_name}"'))
        op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))
    if _table_exists("qms_corrective_actions") and _column_exists("qms_corrective_actions", "amo_id"):
        if _constraint_exists("qms_corrective_actions", "fk_qms_corrective_actions_amo_id"):
            op.drop_constraint("fk_qms_corrective_actions_amo_id", "qms_corrective_actions", type_="foreignkey")
        if _index_exists("ix_qms_corrective_actions_amo_id"):
            op.drop_index("ix_qms_corrective_actions_amo_id", table_name="qms_corrective_actions")
        op.drop_column("qms_corrective_actions", "amo_id")
