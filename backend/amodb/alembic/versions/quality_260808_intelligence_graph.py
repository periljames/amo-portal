"""Add deterministic Quality signals and AMO approval impact graph.

Revision ID: quality_260808_intel_graph
Revises: quality_260808_assurance_cases
Create Date: 2026-08-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "quality_260808_intel_graph"
down_revision = "quality_260808_assurance_cases"
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
        CREATE POLICY {policy} ON "{table_name}"
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
    fn = f"prevent_{table_name}_mutation"
    trigger = f"trg_{table_name}_append_only"
    op.execute(sa.text(f"""
        CREATE OR REPLACE FUNCTION {fn}() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION '{table_name} is append-only'; END;
        $$ LANGUAGE plpgsql;
    """))
    op.execute(sa.text(f'CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON "{table_name}" FOR EACH ROW EXECUTE FUNCTION {fn}()'))


def _drop_append_only(table_name: str) -> None:
    if not _is_postgresql():
        return
    fn = f"prevent_{table_name}_mutation"
    trigger = f"trg_{table_name}_append_only"
    op.execute(sa.text(f'DROP TRIGGER IF EXISTS {trigger} ON "{table_name}"'))
    op.execute(sa.text(f'DROP FUNCTION IF EXISTS {fn}()'))


def upgrade() -> None:
    op.create_table(
        "quality_signal_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("rule_code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("metric", sa.String(length=48), nullable=False),
        sa.Column("operator", sa.String(length=8), nullable=False),
        sa.Column("threshold", sa.Numeric(18, 6), nullable=False),
        sa.Column("severity", sa.String(length=16), server_default="WATCH", nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("source_contract", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("metric IN ('PROGRAMME_COMPLETION_RATE','PROGRAMME_DEFERRAL_RATE','OPEN_FINDING_COUNT','FINDING_RECURRENCE_COUNT','OVERDUE_CAR_COUNT','CAR_AGE_DAYS','INEFFECTIVE_ACTION_RATE','AUDITOR_CAPACITY_EXCEPTIONS','OPEN_ASSURANCE_CASES')", name="ck_quality_signal_rule_metric"),
        sa.CheckConstraint("operator IN ('GT','GTE','LT','LTE','EQ')", name="ck_quality_signal_rule_operator"),
        sa.CheckConstraint("severity IN ('INFO','WATCH','WARNING','CRITICAL')", name="ck_quality_signal_rule_severity"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "rule_code", name="uq_quality_signal_rule_code"),
    )
    op.create_index("ix_quality_signal_rules_active", "quality_signal_rules", ["amo_id", "is_active", "metric"])

    op.create_table(
        "quality_signal_observations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("rule_id", sa.String(length=36), nullable=False),
        sa.Column("metric", sa.String(length=48), nullable=False),
        sa.Column("observed_value", sa.Numeric(18, 6), nullable=False),
        sa.Column("threshold", sa.Numeric(18, 6), nullable=False),
        sa.Column("operator", sa.String(length=8), nullable=False),
        sa.Column("triggered", sa.Boolean(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("source_references", sa.JSON(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(length=24), server_default="OPEN", nullable=False),
        sa.Column("assurance_case_id", sa.String(length=36), nullable=True),
        sa.Column("observed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("severity IN ('INFO','WATCH','WARNING','CRITICAL')", name="ck_quality_signal_observation_severity"),
        sa.CheckConstraint("state IN ('OPEN','ACKNOWLEDGED','CONVERTED_TO_CASE','CLOSED')", name="ck_quality_signal_observation_state"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["quality_signal_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assurance_case_id"], ["quality_assurance_cases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["observed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_signal_observations_open", "quality_signal_observations", ["amo_id", "state", "severity", "observed_at"])
    op.create_index("ix_quality_signal_observations_rule", "quality_signal_observations", ["amo_id", "rule_id", "observed_at"])

    op.create_table(
        "quality_requirement_nodes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("node_type", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source_owner_module", sa.String(length=80), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("source_id", sa.String(length=160), nullable=False),
        sa.Column("source_route", sa.String(length=500), nullable=True),
        sa.Column("support_state", sa.String(length=16), server_default="UNRESOLVED", nullable=False),
        sa.Column("state_reason", sa.Text(), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=True),
        sa.Column("evidence_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("node_type IN ('REQUIREMENT','APPROVAL','MANUAL','PROCEDURE','FORM','TRAINING','ROLE','CHECKLIST','EVIDENCE','MISSION','FINDING','ACTION','CAPABILITY')", name="ck_quality_requirement_node_type"),
        sa.CheckConstraint("support_state IN ('SUPPORTED','UNSUPPORTED','STALE','UNRESOLVED','BLOCKED')", name="ck_quality_requirement_node_state"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "node_type", "source_owner_module", "source_type", "source_id", name="uq_quality_requirement_node_source"),
    )
    op.create_index("ix_quality_requirement_nodes_state", "quality_requirement_nodes", ["amo_id", "node_type", "support_state"])
    op.create_index("ix_quality_requirement_nodes_owner", "quality_requirement_nodes", ["amo_id", "source_owner_module", "source_type"])

    op.create_table(
        "quality_requirement_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("from_node_id", sa.String(length=36), nullable=False),
        sa.Column("to_node_id", sa.String(length=36), nullable=False),
        sa.Column("relationship", sa.String(length=24), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_references", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("relationship IN ('REQUIRES','IMPLEMENTS','EVIDENCES','AUTHORIZES','DEPENDS_ON','AFFECTS','VERIFIES','BLOCKS','SUPERSEDES')", name="ck_quality_requirement_link_relationship"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_node_id"], ["quality_requirement_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_node_id"], ["quality_requirement_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "from_node_id", "to_node_id", "relationship", name="uq_quality_requirement_link"),
    )
    op.create_index("ix_quality_requirement_links_from", "quality_requirement_links", ["amo_id", "from_node_id", "relationship"])
    op.create_index("ix_quality_requirement_links_to", "quality_requirement_links", ["amo_id", "to_node_id", "relationship"])

    for table_name in (
        "quality_signal_rules",
        "quality_signal_observations",
        "quality_requirement_nodes",
        "quality_requirement_links",
    ):
        _enable_rls(table_name)
    _append_only("quality_signal_observations")
    _append_only("quality_requirement_links")


def downgrade() -> None:
    _drop_append_only("quality_requirement_links")
    _drop_append_only("quality_signal_observations")
    for table_name in (
        "quality_requirement_links",
        "quality_requirement_nodes",
        "quality_signal_observations",
        "quality_signal_rules",
    ):
        _disable_rls(table_name)
    op.drop_index("ix_quality_requirement_links_to", table_name="quality_requirement_links")
    op.drop_index("ix_quality_requirement_links_from", table_name="quality_requirement_links")
    op.drop_table("quality_requirement_links")
    op.drop_index("ix_quality_requirement_nodes_owner", table_name="quality_requirement_nodes")
    op.drop_index("ix_quality_requirement_nodes_state", table_name="quality_requirement_nodes")
    op.drop_table("quality_requirement_nodes")
    op.drop_index("ix_quality_signal_observations_rule", table_name="quality_signal_observations")
    op.drop_index("ix_quality_signal_observations_open", table_name="quality_signal_observations")
    op.drop_table("quality_signal_observations")
    op.drop_index("ix_quality_signal_rules_active", table_name="quality_signal_rules")
    op.drop_table("quality_signal_rules")
