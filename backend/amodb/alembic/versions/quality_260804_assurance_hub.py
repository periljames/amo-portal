"""Add continuous assurance controls, evidence graph and governed insights.

Revision ID: quality_260804_assurance_hub
Revises: accounts_260804_portal_prefs
Create Date: 2026-08-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260804_assurance_hub"
down_revision = "accounts_260804_portal_prefs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quality_assurance_controls",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("control_code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("framework", sa.String(length=120), nullable=False, server_default="INTERNAL_QMS"),
        sa.Column("clause_reference", sa.String(length=255), nullable=True),
        sa.Column("process_area", sa.String(length=160), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("criticality", sa.String(length=16), nullable=False, server_default="MEDIUM"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ACTIVE"),
        sa.Column("test_frequency_days", sa.Integer(), nullable=False, server_default="365"),
        sa.Column("evidence_expectation", sa.Text(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_test_due", sa.Date(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "criticality IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_quality_assurance_control_criticality",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'ACTIVE', 'RETIRED')",
            name="ck_quality_assurance_control_status",
        ),
        sa.CheckConstraint("test_frequency_days > 0", name="ck_quality_assurance_control_frequency"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "control_code", name="uq_quality_assurance_control_code"),
    )
    op.create_index(
        "ix_quality_assurance_controls_due",
        "quality_assurance_controls",
        ["amo_id", "status", "next_test_due"],
        unique=False,
    )
    op.create_index(
        "ix_quality_assurance_controls_framework",
        "quality_assurance_controls",
        ["amo_id", "framework", "process_area"],
        unique=False,
    )

    op.create_table(
        "quality_assurance_evidence_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("control_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=48), nullable=False),
        sa.Column("source_id", sa.String(length=160), nullable=False),
        sa.Column("relationship", sa.String(length=48), nullable=False, server_default="EVIDENCES"),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("evidence_status", sa.String(length=16), nullable=False, server_default="LINKED"),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("verified_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "evidence_status IN ('LINKED', 'VERIFIED', 'EXPIRED', 'REJECTED')",
            name="ck_quality_assurance_evidence_status",
        ),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["control_id"], ["quality_assurance_controls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "control_id",
            "source_type",
            "source_id",
            "relationship",
            name="uq_quality_assurance_evidence_edge",
        ),
    )
    op.create_index(
        "ix_quality_assurance_evidence_control",
        "quality_assurance_evidence_links",
        ["amo_id", "control_id", "evidence_status"],
        unique=False,
    )
    op.create_index(
        "ix_quality_assurance_evidence_source",
        "quality_assurance_evidence_links",
        ["amo_id", "source_type", "source_id"],
        unique=False,
    )

    op.create_table(
        "quality_intelligence_reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("insight_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=160), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False, server_default="MEDIUM"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PROPOSED"),
        sa.Column("created_by", sa.String(length=32), nullable=False, server_default="RULE_ENGINE"),
        sa.Column("human_decision_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("human_decision_note", sa.Text(), nullable=True),
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('PROPOSED', 'ACCEPTED', 'DISMISSED', 'IMPLEMENTED')",
            name="ck_quality_intelligence_review_status",
        ),
        sa.CheckConstraint(
            "risk_level IN ('INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_quality_intelligence_review_risk",
        ),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["human_decision_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "source_fingerprint", name="uq_quality_intelligence_fingerprint"),
    )
    op.create_index(
        "ix_quality_intelligence_queue",
        "quality_intelligence_reviews",
        ["amo_id", "status", "risk_level", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_quality_intelligence_queue", table_name="quality_intelligence_reviews")
    op.drop_table("quality_intelligence_reviews")
    op.drop_index("ix_quality_assurance_evidence_source", table_name="quality_assurance_evidence_links")
    op.drop_index("ix_quality_assurance_evidence_control", table_name="quality_assurance_evidence_links")
    op.drop_table("quality_assurance_evidence_links")
    op.drop_index("ix_quality_assurance_controls_framework", table_name="quality_assurance_controls")
    op.drop_index("ix_quality_assurance_controls_due", table_name="quality_assurance_controls")
    op.drop_table("quality_assurance_controls")
