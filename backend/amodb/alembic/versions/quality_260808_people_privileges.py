"""Add governed Quality people privileges and independence declarations.

Revision ID: quality_260808_people_privileges
Revises: quality_260808_prog_schedule
Create Date: 2026-08-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "quality_260808_people_privileges"
down_revision = "quality_260808_prog_schedule"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _enable_rls(table_name: str) -> None:
    if not _is_postgresql():
        return
    policy = f"{table_name}_amo_isolation"
    op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f"""
        CREATE POLICY {policy}
        ON "{table_name}"
        USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
        WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
    """))


def _disable_rls(table_name: str) -> None:
    if not _is_postgresql():
        return
    policy = f"{table_name}_amo_isolation"
    op.execute(sa.text(f'DROP POLICY IF EXISTS {policy} ON "{table_name}"'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" NO FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))


def _append_only(table_name: str) -> None:
    if not _is_postgresql():
        return
    function_name = f"prevent_{table_name}_mutation"
    trigger_name = f"trg_{table_name}_append_only"
    op.execute(sa.text(f"""
        CREATE OR REPLACE FUNCTION {function_name}()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '{table_name} is append-only';
        END;
        $$ LANGUAGE plpgsql;
    """))
    op.execute(sa.text(f"""
        CREATE TRIGGER {trigger_name}
        BEFORE UPDATE OR DELETE ON "{table_name}"
        FOR EACH ROW EXECUTE FUNCTION {function_name}();
    """))


def _drop_append_only(table_name: str) -> None:
    if not _is_postgresql():
        return
    function_name = f"prevent_{table_name}_mutation"
    trigger_name = f"trg_{table_name}_append_only"
    op.execute(sa.text(f'DROP TRIGGER IF EXISTS {trigger_name} ON "{table_name}"'))
    op.execute(sa.text(f'DROP FUNCTION IF EXISTS {function_name}()'))


def upgrade() -> None:
    op.create_table(
        "quality_privilege_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("privilege_code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("privilege_type", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("required_training_course_codes", sa.JSON(), nullable=False),
        sa.Column("independence_required", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("max_concurrent_assignments", sa.Integer(), nullable=True),
        sa.Column("scope_schema", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "privilege_type IN ('AUDITOR','LEAD_AUDITOR','QUALITY_INSPECTOR','AUTHORIZATION_REVIEWER','CUSTOM')",
            name="ck_quality_privilege_rule_type",
        ),
        sa.CheckConstraint("max_concurrent_assignments IS NULL OR max_concurrent_assignments >= 1", name="ck_quality_privilege_rule_capacity"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "privilege_code", name="uq_quality_privilege_rule_code"),
    )
    op.create_index("ix_quality_privilege_rules_active", "quality_privilege_rules", ["amo_id", "is_active", "privilege_type"])

    op.create_table(
        "quality_privileges",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("rule_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("privilege_code", sa.String(length=64), nullable=False),
        sa.Column("scope_key", sa.String(length=255), server_default="GLOBAL", nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="DRAFT", nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("latest_decision_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT','ACTIVE','SUSPENDED','REVOKED','EXPIRED')", name="ck_quality_privilege_status"),
        sa.CheckConstraint("effective_from IS NULL OR expires_on IS NULL OR expires_on >= effective_from", name="ck_quality_privilege_dates"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["quality_privilege_rules.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "user_id", "privilege_code", "scope_key", name="uq_quality_privilege_identity"),
    )
    op.create_index("ix_quality_privileges_person", "quality_privileges", ["amo_id", "user_id", "status"])
    op.create_index("ix_quality_privileges_code", "quality_privileges", ["amo_id", "privilege_code", "status"])
    op.create_index("ix_quality_privileges_expiry", "quality_privileges", ["amo_id", "expires_on", "status"])

    op.create_table(
        "quality_privilege_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("privilege_id", sa.String(length=36), nullable=False),
        sa.Column("decision_type", sa.String(length=16), nullable=False),
        sa.Column("resulting_status", sa.String(length=16), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("eligibility_snapshot", sa.JSON(), nullable=False),
        sa.Column("source_references", sa.JSON(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("decided_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("decision_type IN ('GRANT','RENEW','SUSPEND','REINSTATE','REVOKE','EXPIRE','REJECT')", name="ck_quality_privilege_decision_type"),
        sa.CheckConstraint("resulting_status IN ('DRAFT','ACTIVE','SUSPENDED','REVOKED','EXPIRED')", name="ck_quality_privilege_decision_status"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["privilege_id"], ["quality_privileges.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_privilege_decisions_history", "quality_privilege_decisions", ["amo_id", "privilege_id", "created_at"])
    op.create_index("ix_quality_privilege_decisions_actor", "quality_privilege_decisions", ["amo_id", "decided_by_user_id", "created_at"])
    op.create_foreign_key(
        "fk_quality_privilege_latest_decision",
        "quality_privileges",
        "quality_privilege_decisions",
        ["latest_decision_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "quality_independence_declarations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("context_type", sa.String(length=24), nullable=False),
        sa.Column("context_id", sa.String(length=160), nullable=False),
        sa.Column("declaration", sa.String(length=24), nullable=False),
        sa.Column("relationship_to_subject", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("source_references", sa.JSON(), nullable=False),
        sa.Column("declared_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("declared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("declaration IN ('INDEPENDENT','CONFLICT','REQUIRES_REVIEW')", name="ck_quality_independence_declaration"),
        sa.CheckConstraint("context_type IN ('AUDIT','AUDIT_SCHEDULE','PROGRAMME_ITEM','ASSURANCE_CASE','MISSION','OTHER')", name="ck_quality_independence_context"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["declared_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "user_id", "context_type", "context_id", name="uq_quality_independence_context"),
    )
    op.create_index("ix_quality_independence_lookup", "quality_independence_declarations", ["amo_id", "context_type", "context_id", "declaration"])
    op.create_index("ix_quality_independence_person", "quality_independence_declarations", ["amo_id", "user_id", "created_at"])

    for table_name in (
        "quality_privilege_rules",
        "quality_privileges",
        "quality_privilege_decisions",
        "quality_independence_declarations",
    ):
        _enable_rls(table_name)
    _append_only("quality_privilege_decisions")
    _append_only("quality_independence_declarations")


def downgrade() -> None:
    _drop_append_only("quality_independence_declarations")
    _drop_append_only("quality_privilege_decisions")
    for table_name in (
        "quality_independence_declarations",
        "quality_privilege_decisions",
        "quality_privileges",
        "quality_privilege_rules",
    ):
        _disable_rls(table_name)

    op.drop_index("ix_quality_independence_person", table_name="quality_independence_declarations")
    op.drop_index("ix_quality_independence_lookup", table_name="quality_independence_declarations")
    op.drop_table("quality_independence_declarations")
    op.drop_constraint("fk_quality_privilege_latest_decision", "quality_privileges", type_="foreignkey")
    op.drop_index("ix_quality_privilege_decisions_actor", table_name="quality_privilege_decisions")
    op.drop_index("ix_quality_privilege_decisions_history", table_name="quality_privilege_decisions")
    op.drop_table("quality_privilege_decisions")
    op.drop_index("ix_quality_privileges_expiry", table_name="quality_privileges")
    op.drop_index("ix_quality_privileges_code", table_name="quality_privileges")
    op.drop_index("ix_quality_privileges_person", table_name="quality_privileges")
    op.drop_table("quality_privileges")
    op.drop_index("ix_quality_privilege_rules_active", table_name="quality_privilege_rules")
    op.drop_table("quality_privilege_rules")
