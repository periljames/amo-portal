"""Add audit-scoped governed applicability facts.

Revision ID: quality_261002_applicability_ctx
Revises: docctrl_261001_section_embed
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa


revision = "quality_261002_applicability_ctx"
down_revision = "docctrl_261001_section_embed"
branch_labels = None
depends_on = None

TABLE = "quality_audit_applicability_facts"


def _has_table() -> bool:
    return sa.inspect(op.get_bind()).has_table(TABLE)


def upgrade() -> None:
    if _has_table():
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("applicability_rule_id", sa.String(length=36), nullable=False),
        sa.Column("source_manual_id", sa.String(length=36), nullable=False),
        sa.Column("source_revision_id", sa.String(length=36), nullable=True),
        sa.Column("rule_type", sa.String(length=16), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=True),
        sa.Column("target_value", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("criteria_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["applicability_rule_id"], ["document_applicability_rules.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_manual_id"], ["manuals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_revision_id"], ["manual_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "audit_id", "applicability_rule_id", name="uq_quality_audit_applicability_fact_rule"),
        sa.CheckConstraint("rule_type IN ('INCLUDE','EXCLUDE','WARNING')", name="ck_quality_audit_applicability_fact_rule_type"),
    )
    op.create_index(
        "ix_quality_audit_applicability_fact_audit",
        TABLE,
        ["amo_id", "audit_id", "target_type"],
        unique=False,
    )


def downgrade() -> None:
    if _has_table():
        op.drop_table(TABLE)
