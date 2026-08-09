"""Add governed audit programmes, universe and immutable programme events.

Revision ID: quality_260808_audit_programme
Revises: quality_260808_missions
Create Date: 2026-08-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "quality_260808_audit_programme"
down_revision = "quality_260808_missions"
branch_labels = None
depends_on = None


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _enable_rls(table: str) -> None:
    if not _postgres(): return
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'''CREATE POLICY {table}_amo_isolation ON "{table}"
        USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
        WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))'''))


def _disable_rls(table: str) -> None:
    if not _postgres(): return
    op.execute(sa.text(f'DROP POLICY IF EXISTS {table}_amo_isolation ON "{table}"'))
    op.execute(sa.text(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))


def _user_fk(column: str):
    return sa.ForeignKeyConstraint([column], ["users.id"], ondelete="SET NULL")


def upgrade() -> None:
    op.create_table(
        "quality_audit_programmes",
        sa.Column("id", sa.String(36), nullable=False), sa.Column("amo_id", sa.String(36), nullable=False),
        sa.Column("programme_ref", sa.String(72), nullable=False), sa.Column("programme_series", sa.String(64), nullable=False),
        sa.Column("programme_year", sa.Integer(), nullable=False), sa.Column("revision_no", sa.Integer(), server_default="1", nullable=False),
        sa.Column("title", sa.String(255), nullable=False), sa.Column("objectives", sa.JSON(), nullable=False),
        sa.Column("regulatory_basis", sa.JSON(), nullable=False), sa.Column("status", sa.String(24), server_default="DRAFT", nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False), sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("owner_user_id", sa.String(36), nullable=True), sa.Column("supersedes_programme_id", sa.String(36), nullable=True),
        sa.Column("approved_by_user_id", sa.String(36), nullable=True), sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True), sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), nullable=True), sa.Column("updated_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT','UNDER_REVIEW','APPROVED','ACTIVE','SUPERSEDED','CLOSED')", name="ck_quality_audit_programme_status"),
        sa.CheckConstraint("programme_year >= 2000 AND programme_year <= 2200", name="ck_quality_audit_programme_year"),
        sa.CheckConstraint("revision_no >= 1", name="ck_quality_audit_programme_revision"),
        sa.CheckConstraint("period_end >= period_start", name="ck_quality_audit_programme_period"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supersedes_programme_id"], ["quality_audit_programmes.id"], ondelete="SET NULL"),
        _user_fk("owner_user_id"), _user_fk("approved_by_user_id"), _user_fk("created_by_user_id"), _user_fk("updated_by_user_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "programme_ref", name="uq_quality_audit_programme_ref"),
        sa.UniqueConstraint("amo_id", "programme_series", "revision_no", name="uq_quality_audit_programme_revision"),
    )
    op.create_index("ix_quality_audit_programmes_year", "quality_audit_programmes", ["amo_id", "programme_year", "status"])
    op.create_index("ix_quality_audit_programmes_owner", "quality_audit_programmes", ["amo_id", "owner_user_id", "status"])
    op.create_index("ix_quality_audit_programmes_series", "quality_audit_programmes", ["amo_id", "programme_series", "revision_no"])

    op.create_table(
        "quality_audit_universe_items",
        sa.Column("id", sa.String(36), nullable=False), sa.Column("amo_id", sa.String(36), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False), sa.Column("display_label", sa.String(255), nullable=False),
        sa.Column("source_owner_module", sa.String(80), nullable=False), sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(160), nullable=False), sa.Column("source_route", sa.String(500), nullable=True),
        sa.Column("risk_classification", sa.String(16), server_default="MEDIUM", nullable=False),
        sa.Column("regulatory_criticality", sa.String(16), server_default="MEDIUM", nullable=False),
        sa.Column("surveillance_interval_days", sa.Integer(), nullable=True),
        sa.Column("mandatory_surveillance", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False), sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), nullable=True), sa.Column("updated_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("entity_type IN ('DEPARTMENT','FACILITY','STATION','SUPPLIER','CONTRACTOR','PROCESS','CAPABILITY','APPROVAL_RATING','AIRCRAFT_TYPE','PERSONNEL_GROUP','OTHER')", name="ck_quality_audit_universe_entity_type"),
        sa.CheckConstraint("risk_classification IN ('LOW','MEDIUM','HIGH','CRITICAL')", name="ck_quality_audit_universe_risk"),
        sa.CheckConstraint("regulatory_criticality IN ('LOW','MEDIUM','HIGH','CRITICAL')", name="ck_quality_audit_universe_regulatory"),
        sa.CheckConstraint("surveillance_interval_days IS NULL OR surveillance_interval_days > 0", name="ck_quality_audit_universe_interval"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"), _user_fk("created_by_user_id"), _user_fk("updated_by_user_id"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "source_owner_module", "source_type", "source_id", name="uq_quality_audit_universe_source"),
    )
    op.create_index("ix_quality_audit_universe_type", "quality_audit_universe_items", ["amo_id", "entity_type", "active"])
    op.create_index("ix_quality_audit_universe_risk", "quality_audit_universe_items", ["amo_id", "risk_classification", "regulatory_criticality"])
    op.create_index("ix_quality_audit_universe_source", "quality_audit_universe_items", ["amo_id", "source_owner_module", "source_type", "source_id"])

    op.create_table(
        "quality_audit_programme_items",
        sa.Column("id", sa.String(36), nullable=False), sa.Column("amo_id", sa.String(36), nullable=False),
        sa.Column("programme_id", sa.String(36), nullable=False), sa.Column("universe_item_id", sa.String(36), nullable=False),
        sa.Column("audit_type", sa.String(32), nullable=False), sa.Column("title", sa.String(255), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=True), sa.Column("scope", sa.Text(), nullable=False), sa.Column("criteria", sa.JSON(), nullable=False),
        sa.Column("mandatory_surveillance", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("recurrence", sa.String(20), server_default="ONE_TIME", nullable=False), sa.Column("custom_interval_days", sa.Integer(), nullable=True),
        sa.Column("target_start", sa.Date(), nullable=True), sa.Column("target_end", sa.Date(), nullable=True),
        sa.Column("state", sa.String(24), server_default="PLANNED", nullable=False), sa.Column("prioritization_basis", sa.JSON(), nullable=False),
        sa.Column("deferral_reason", sa.Text(), nullable=True), sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), nullable=True), sa.Column("updated_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("audit_type IN ('INTERNAL','DEPARTMENTAL','TECHNICAL','WORK_PACK','SUPPLIER','CONTRACTED_FUNCTION','FACILITY','PERSONNEL','PRODUCT','PROCESS','REGULATORY','SPECIAL','REACTIVE','FOLLOW_UP')", name="ck_quality_audit_programme_item_type"),
        sa.CheckConstraint("state IN ('PLANNED','SCHEDULED','COMPLETED','DEFERRED','CANCELLED','FOLLOW_UP_REQUIRED')", name="ck_quality_audit_programme_item_state"),
        sa.CheckConstraint("recurrence IN ('ONE_TIME','MONTHLY','QUARTERLY','SEMI_ANNUAL','ANNUAL','CUSTOM','RISK_TRIGGERED')", name="ck_quality_audit_programme_item_recurrence"),
        sa.CheckConstraint("target_end IS NULL OR target_start IS NULL OR target_end >= target_start", name="ck_quality_audit_programme_item_dates"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["programme_id"], ["quality_audit_programmes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["universe_item_id"], ["quality_audit_universe_items.id"], ondelete="RESTRICT"),
        _user_fk("created_by_user_id"), _user_fk("updated_by_user_id"), sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_audit_programme_items_period", "quality_audit_programme_items", ["amo_id", "programme_id", "target_start", "state"])
    op.create_index("ix_quality_audit_programme_items_universe", "quality_audit_programme_items", ["amo_id", "universe_item_id", "state"])
    op.create_index("ix_quality_audit_programme_items_type", "quality_audit_programme_items", ["amo_id", "audit_type", "state"])

    op.create_table(
        "quality_audit_programme_events",
        sa.Column("id", sa.String(36), nullable=False), sa.Column("amo_id", sa.String(36), nullable=False),
        sa.Column("programme_id", sa.String(36), nullable=False), sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False), sa.Column("before_snapshot", sa.JSON(), nullable=True), sa.Column("after_snapshot", sa.JSON(), nullable=True),
        sa.Column("actor_user_id", sa.String(36), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("event_type IN ('CREATED','UPDATED','SUBMITTED_FOR_REVIEW','RETURNED_TO_DRAFT','APPROVED','ACTIVATED','AMENDMENT_CREATED','SUPERSEDED','CLOSED','ITEM_ADDED','ITEM_UPDATED')", name="ck_quality_audit_programme_event_type"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["programme_id"], ["quality_audit_programmes.id"], ondelete="CASCADE"), _user_fk("actor_user_id"), sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_audit_programme_events", "quality_audit_programme_events", ["amo_id", "programme_id", "created_at"])

    for table in ("quality_audit_programmes", "quality_audit_universe_items", "quality_audit_programme_items", "quality_audit_programme_events"):
        _enable_rls(table)


def downgrade() -> None:
    for table in ("quality_audit_programme_events", "quality_audit_programme_items", "quality_audit_universe_items", "quality_audit_programmes"):
        _disable_rls(table)
    op.drop_index("ix_quality_audit_programme_events", table_name="quality_audit_programme_events"); op.drop_table("quality_audit_programme_events")
    for name in ("ix_quality_audit_programme_items_type", "ix_quality_audit_programme_items_universe", "ix_quality_audit_programme_items_period"):
        op.drop_index(name, table_name="quality_audit_programme_items")
    op.drop_table("quality_audit_programme_items")
    for name in ("ix_quality_audit_universe_source", "ix_quality_audit_universe_risk", "ix_quality_audit_universe_type"):
        op.drop_index(name, table_name="quality_audit_universe_items")
    op.drop_table("quality_audit_universe_items")
    for name in ("ix_quality_audit_programmes_series", "ix_quality_audit_programmes_owner", "ix_quality_audit_programmes_year"):
        op.drop_index(name, table_name="quality_audit_programmes")
    op.drop_table("quality_audit_programmes")
