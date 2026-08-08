"""Add governed Quality missions, readiness gates and decisions.

Revision ID: quality_260808_missions
Revises: docgov_rel_20260807_merge
Create Date: 2026-08-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260808_missions"
down_revision = "docgov_rel_20260807_merge"
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
    op.execute(
        sa.text(
            f"""
            CREATE POLICY {policy}
            ON "{table_name}"
            USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
            WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
            """
        )
    )


def _disable_rls(table_name: str) -> None:
    if not _is_postgresql():
        return
    policy = f"{table_name}_amo_isolation"
    op.execute(sa.text(f'DROP POLICY IF EXISTS {policy} ON "{table_name}"'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" NO FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))


def upgrade() -> None:
    op.create_table(
        "quality_missions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("mission_ref", sa.String(length=64), nullable=False),
        sa.Column("mission_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("regulatory_basis", sa.JSON(), nullable=False),
        sa.Column("risk_level", sa.String(length=16), server_default="MEDIUM", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="DRAFT", nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("sponsor_user_id", sa.String(length=36), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "mission_type IN ('CAPABILITY_ADDITION','CAPABILITY_CHANGE','LINE_STATION','SUPPLIER_APPROVAL','SUBCONTRACTOR_APPROVAL','REGULATORY_TRANSITION','AMO_RENEWAL','AUTHORIZATION_CAMPAIGN','PROCEDURE_CHANGE','IMPROVEMENT')",
            name="ck_quality_mission_type",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','PLANNING','IN_PROGRESS','GATE_REVIEW','READY_FOR_APPROVAL','APPROVED','SUBMITTED_TO_AUTHORITY','COMPLETE','CANCELLED')",
            name="ck_quality_mission_status",
        ),
        sa.CheckConstraint(
            "risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_quality_mission_risk",
        ),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sponsor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "mission_ref", name="uq_quality_mission_ref"),
    )
    op.create_index("ix_quality_missions_status", "quality_missions", ["amo_id", "status", "target_date"])
    op.create_index("ix_quality_missions_owner", "quality_missions", ["amo_id", "owner_user_id", "status"])
    op.create_index("ix_quality_missions_type", "quality_missions", ["amo_id", "mission_type", "status"])

    op.create_table(
        "quality_mission_gates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("mission_id", sa.String(length=36), nullable=False),
        sa.Column("gate_code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("gate_type", sa.String(length=12), server_default="HARD", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="PENDING", nullable=False),
        sa.Column("requirement_ref", sa.String(length=255), nullable=True),
        sa.Column("source_owner_module", sa.String(length=80), nullable=True),
        sa.Column("source_type", sa.String(length=48), nullable=True),
        sa.Column("source_id", sa.String(length=160), nullable=True),
        sa.Column("source_route", sa.String(length=500), nullable=True),
        sa.Column("source_snapshot", sa.JSON(), nullable=True),
        sa.Column("evidence_status", sa.String(length=16), server_default="UNLINKED", nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("blocking_reason", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="100", nullable=False),
        sa.Column("passed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("passed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("gate_type IN ('HARD','SOFT')", name="ck_quality_mission_gate_type"),
        sa.CheckConstraint(
            "status IN ('PENDING','IN_PROGRESS','PASS','FAIL','BLOCKED')",
            name="ck_quality_mission_gate_status",
        ),
        sa.CheckConstraint(
            "evidence_status IN ('UNLINKED','LINKED','VERIFIED','REJECTED','EXPIRED')",
            name="ck_quality_mission_gate_evidence_status",
        ),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mission_id"], ["quality_missions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["passed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mission_id", "gate_code", name="uq_quality_mission_gate_code"),
    )
    op.create_index(
        "ix_quality_mission_gates_state",
        "quality_mission_gates",
        ["amo_id", "mission_id", "gate_type", "status"],
    )
    op.create_index(
        "ix_quality_mission_gates_source",
        "quality_mission_gates",
        ["amo_id", "source_type", "source_id"],
    )
    op.create_index(
        "ix_quality_mission_gates_due",
        "quality_mission_gates",
        ["amo_id", "due_date", "status"],
    )

    op.create_table(
        "quality_mission_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("mission_id", sa.String(length=36), nullable=False),
        sa.Column("decision_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("decided_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision_type IN ('QUALITY_SELF_EVALUATION','ACCOUNTABLE_EXECUTIVE','AUTHORITY_SUBMISSION','AUTHORITY_ACCEPTANCE','CUSTOM')",
            name="ck_quality_mission_decision_type",
        ),
        sa.CheckConstraint(
            "status IN ('APPROVED','REJECTED','RETURNED')",
            name="ck_quality_mission_decision_status",
        ),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mission_id"], ["quality_missions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_quality_mission_decisions",
        "quality_mission_decisions",
        ["amo_id", "mission_id", "decision_type", "created_at"],
    )

    for table_name in ("quality_missions", "quality_mission_gates", "quality_mission_decisions"):
        _enable_rls(table_name)


def downgrade() -> None:
    for table_name in ("quality_mission_decisions", "quality_mission_gates", "quality_missions"):
        _disable_rls(table_name)

    op.drop_index("ix_quality_mission_decisions", table_name="quality_mission_decisions")
    op.drop_table("quality_mission_decisions")

    op.drop_index("ix_quality_mission_gates_due", table_name="quality_mission_gates")
    op.drop_index("ix_quality_mission_gates_source", table_name="quality_mission_gates")
    op.drop_index("ix_quality_mission_gates_state", table_name="quality_mission_gates")
    op.drop_table("quality_mission_gates")

    op.drop_index("ix_quality_missions_type", table_name="quality_missions")
    op.drop_index("ix_quality_missions_owner", table_name="quality_missions")
    op.drop_index("ix_quality_missions_status", table_name="quality_missions")
    op.drop_table("quality_missions")
