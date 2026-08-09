"""Add immutable programme occurrence links for custom and risk-triggered audits.

Revision ID: quality_260809_programme_occ
Revises: merge_260809_qms_reliability
Create Date: 2026-08-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "quality_260809_programme_occ"
down_revision = "merge_260809_qms_reliability"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "quality_audit_programme_occurrence_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("programme_id", sa.String(length=36), nullable=False),
        sa.Column("programme_item_id", sa.String(length=36), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=False),
        sa.Column("occurrence_type", sa.String(length=24), nullable=False),
        sa.Column("occurrence_key", sa.String(length=160), nullable=False),
        sa.Column("source_signal_id", sa.String(length=36), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("occurrence_type IN ('CUSTOM','RISK_TRIGGERED')", name="ck_quality_audit_programme_occurrence_type"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["programme_id"], ["quality_audit_programmes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["programme_item_id"], ["quality_audit_programme_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["schedule_id"], ["qms_audit_schedules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_signal_id"], ["quality_signal_observations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "schedule_id", name="uq_quality_audit_programme_occurrence_schedule"),
        sa.UniqueConstraint("amo_id", "programme_item_id", "occurrence_key", name="uq_quality_audit_programme_occurrence_key"),
    )
    op.create_index("ix_quality_audit_programme_occurrence_item", "quality_audit_programme_occurrence_links", ["amo_id", "programme_item_id", "created_at"])
    op.create_index("ix_quality_audit_programme_occurrence_source", "quality_audit_programme_occurrence_links", ["amo_id", "source_signal_id"])

    if _is_postgresql():
        op.execute(sa.text('ALTER TABLE "quality_audit_programme_occurrence_links" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text('ALTER TABLE "quality_audit_programme_occurrence_links" FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text("""
            CREATE POLICY quality_audit_programme_occurrence_links_amo_isolation
            ON quality_audit_programme_occurrence_links
            USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
            WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
        """))
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_quality_audit_programme_occurrence_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'quality_audit_programme_occurrence_links is immutable';
            END;
            $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text("""
            CREATE TRIGGER trg_quality_audit_programme_occurrence_immutable
            BEFORE UPDATE OR DELETE ON quality_audit_programme_occurrence_links
            FOR EACH ROW EXECUTE FUNCTION prevent_quality_audit_programme_occurrence_mutation();
        """))


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_quality_audit_programme_occurrence_immutable ON quality_audit_programme_occurrence_links"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_quality_audit_programme_occurrence_mutation()"))
        op.execute(sa.text("DROP POLICY IF EXISTS quality_audit_programme_occurrence_links_amo_isolation ON quality_audit_programme_occurrence_links"))
        op.execute(sa.text('ALTER TABLE "quality_audit_programme_occurrence_links" NO FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text('ALTER TABLE "quality_audit_programme_occurrence_links" DISABLE ROW LEVEL SECURITY'))
    op.drop_index("ix_quality_audit_programme_occurrence_source", table_name="quality_audit_programme_occurrence_links")
    op.drop_index("ix_quality_audit_programme_occurrence_item", table_name="quality_audit_programme_occurrence_links")
    op.drop_table("quality_audit_programme_occurrence_links")
