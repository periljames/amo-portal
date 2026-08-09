"""Add assurance cases, investigation statements and effectiveness plans.

Revision ID: quality_260808_assurance_cases
Revises: quality_260808_people_privileges
Create Date: 2026-08-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "quality_260808_assurance_cases"
down_revision = "quality_260808_people_privileges"
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
        "quality_assurance_cases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("case_ref", sa.String(length=64), nullable=False),
        sa.Column("case_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=16), server_default="MEDIUM", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="OPEN", nullable=False),
        sa.Column("source_references", sa.JSON(), nullable=False),
        sa.Column("regulatory_basis", sa.JSON(), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("closure_rationale", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("case_type IN ('SIGNAL','INVESTIGATION','RECURRING_FINDING','EFFECTIVENESS','SUPPLIER','REGULATORY','OTHER')", name="ck_quality_assurance_case_type"),
        sa.CheckConstraint("status IN ('OPEN','INVESTIGATING','ACTION_PENDING','EFFECTIVENESS_REVIEW','CLOSED','CANCELLED')", name="ck_quality_assurance_case_status"),
        sa.CheckConstraint("severity IN ('LOW','MEDIUM','HIGH','CRITICAL')", name="ck_quality_assurance_case_severity"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["closed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "case_ref", name="uq_quality_assurance_case_ref"),
    )
    op.create_index("ix_quality_assurance_cases_status", "quality_assurance_cases", ["amo_id", "status", "due_date"])
    op.create_index("ix_quality_assurance_cases_owner", "quality_assurance_cases", ["amo_id", "owner_user_id", "status"])
    op.create_index("ix_quality_assurance_cases_type", "quality_assurance_cases", ["amo_id", "case_type", "severity"])

    op.create_table(
        "quality_investigation_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("entry_type", sa.String(length=24), nullable=False),
        sa.Column("sequence_no", sa.Integer(), server_default="1", nullable=False),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("evidence_references", sa.JSON(), nullable=False),
        sa.Column("parent_entry_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("method IN ('FIVE_WHYS','ISHIKAWA','CAUSAL_FACTOR','BARRIER_ANALYSIS','CHANGE_ANALYSIS','HUMAN_ORGANIZATIONAL')", name="ck_quality_investigation_method"),
        sa.CheckConstraint("entry_type IN ('FACT','HYPOTHESIS','CAUSAL_CONCLUSION')", name="ck_quality_investigation_entry_type"),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 100)", name="ck_quality_investigation_confidence"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["quality_assurance_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_entry_id"], ["quality_investigation_entries.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_investigation_case", "quality_investigation_entries", ["amo_id", "case_id", "method", "sequence_no"])

    op.create_table(
        "quality_effectiveness_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=48), nullable=True),
        sa.Column("source_id", sa.String(length=160), nullable=True),
        sa.Column("source_route", sa.String(length=500), nullable=True),
        sa.Column("expected_outcome", sa.Text(), nullable=False),
        sa.Column("effectiveness_measure", sa.Text(), nullable=False),
        sa.Column("verification_method", sa.Text(), nullable=False),
        sa.Column("observation_window", sa.String(length=255), nullable=True),
        sa.Column("source_indicators", sa.JSON(), nullable=False),
        sa.Column("responsible_reviewer_user_id", sa.String(length=36), nullable=True),
        sa.Column("planned_review_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="PLANNED", nullable=False),
        sa.Column("conclusion", sa.String(length=24), nullable=True),
        sa.Column("conclusion_rationale", sa.Text(), nullable=True),
        sa.Column("conclusion_evidence", sa.JSON(), nullable=False),
        sa.Column("concluded_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("concluded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('PLANNED','OBSERVING','READY_FOR_REVIEW','CONCLUDED','REOPENED','CANCELLED')", name="ck_quality_effectiveness_status"),
        sa.CheckConstraint("conclusion IS NULL OR conclusion IN ('EFFECTIVE','PARTIALLY_EFFECTIVE','INEFFECTIVE','INCONCLUSIVE')", name="ck_quality_effectiveness_conclusion"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["quality_assurance_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["responsible_reviewer_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["concluded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_effectiveness_due", "quality_effectiveness_plans", ["amo_id", "planned_review_date", "status"])
    op.create_index("ix_quality_effectiveness_case", "quality_effectiveness_plans", ["amo_id", "case_id", "status"])
    op.create_index("ix_quality_effectiveness_source", "quality_effectiveness_plans", ["amo_id", "source_type", "source_id"])

    op.create_table(
        "quality_assurance_case_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("before_snapshot", sa.JSON(), nullable=True),
        sa.Column("after_snapshot", sa.JSON(), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("event_type IN ('CREATED','STATUS_CHANGED','INVESTIGATION_ADDED','EFFECTIVENESS_PLANNED','EFFECTIVENESS_CONCLUDED','REOPENED','ESCALATED','CLOSED','CANCELLED')", name="ck_quality_assurance_case_event_type"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["quality_assurance_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_assurance_case_events", "quality_assurance_case_events", ["amo_id", "case_id", "created_at"])

    for table_name in (
        "quality_assurance_cases",
        "quality_investigation_entries",
        "quality_effectiveness_plans",
        "quality_assurance_case_events",
    ):
        _enable_rls(table_name)
    _append_only("quality_investigation_entries")
    _append_only("quality_assurance_case_events")


def downgrade() -> None:
    _drop_append_only("quality_assurance_case_events")
    _drop_append_only("quality_investigation_entries")
    for table_name in (
        "quality_assurance_case_events",
        "quality_effectiveness_plans",
        "quality_investigation_entries",
        "quality_assurance_cases",
    ):
        _disable_rls(table_name)
    op.drop_index("ix_quality_assurance_case_events", table_name="quality_assurance_case_events")
    op.drop_table("quality_assurance_case_events")
    op.drop_index("ix_quality_effectiveness_source", table_name="quality_effectiveness_plans")
    op.drop_index("ix_quality_effectiveness_case", table_name="quality_effectiveness_plans")
    op.drop_index("ix_quality_effectiveness_due", table_name="quality_effectiveness_plans")
    op.drop_table("quality_effectiveness_plans")
    op.drop_index("ix_quality_investigation_case", table_name="quality_investigation_entries")
    op.drop_table("quality_investigation_entries")
    op.drop_index("ix_quality_assurance_cases_type", table_name="quality_assurance_cases")
    op.drop_index("ix_quality_assurance_cases_owner", table_name="quality_assurance_cases")
    op.drop_index("ix_quality_assurance_cases_status", table_name="quality_assurance_cases")
    op.drop_table("quality_assurance_cases")
