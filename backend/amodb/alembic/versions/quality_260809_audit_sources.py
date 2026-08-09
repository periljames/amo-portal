"""Add immutable source lineage from Missions and Intelligence to Planner audits.

Revision ID: quality_260809_audit_sources
Revises: quality_260809_deferrals
Create Date: 2026-08-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "quality_260809_audit_sources"
down_revision = "quality_260809_deferrals"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "quality_audit_source_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=24), nullable=False),
        sa.Column("source_id", sa.String(length=160), nullable=False),
        sa.Column("source_route", sa.String(length=500), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("source_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source_type IN ('MISSION','SIGNAL','ASSURANCE_CASE','PROGRAMME','OTHER')", name="ck_quality_audit_source_link_type"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["schedule_id"], ["qms_audit_schedules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "schedule_id", "source_type", "source_id", name="uq_quality_audit_source_link"),
    )
    op.create_index("ix_quality_audit_source_link_schedule", "quality_audit_source_links", ["amo_id", "schedule_id", "source_type"])
    op.create_index("ix_quality_audit_source_link_source", "quality_audit_source_links", ["amo_id", "source_type", "source_id"])

    if _is_postgresql():
        op.execute(sa.text('ALTER TABLE "quality_audit_source_links" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text('ALTER TABLE "quality_audit_source_links" FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text("""
            CREATE POLICY quality_audit_source_links_amo_isolation ON quality_audit_source_links
            USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
            WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
        """))
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_quality_audit_source_link_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'quality_audit_source_links is immutable';
            END;
            $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text("""
            CREATE TRIGGER trg_quality_audit_source_links_immutable
            BEFORE UPDATE OR DELETE ON quality_audit_source_links
            FOR EACH ROW EXECUTE FUNCTION prevent_quality_audit_source_link_mutation();
        """))


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_quality_audit_source_links_immutable ON quality_audit_source_links"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_quality_audit_source_link_mutation()"))
        op.execute(sa.text("DROP POLICY IF EXISTS quality_audit_source_links_amo_isolation ON quality_audit_source_links"))
        op.execute(sa.text('ALTER TABLE "quality_audit_source_links" NO FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text('ALTER TABLE "quality_audit_source_links" DISABLE ROW LEVEL SECURITY'))
    op.drop_index("ix_quality_audit_source_link_source", table_name="quality_audit_source_links")
    op.drop_index("ix_quality_audit_source_link_schedule", table_name="quality_audit_source_links")
    op.drop_table("quality_audit_source_links")
