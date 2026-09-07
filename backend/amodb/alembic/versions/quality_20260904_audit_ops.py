"""Add governed audit times, tenant notice templates and safe audit purge support.

Revision ID: quality_260904_audit_ops
Revises: ai_260904_foundation
Create Date: 2026-09-04
"""
from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa


revision = "quality_260904_audit_ops"
down_revision = "ai_260904_foundation"
branch_labels = None
depends_on = None

SETTINGS_TABLE = "quality_audit_notice_template_settings"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _seed_tenant_notice_forms() -> None:
    if not {"manual_tenants", "manuals", SETTINGS_TABLE}.issubset(_table_names()):
        return
    connection = op.get_bind()
    tenants = connection.execute(sa.text("SELECT id, amo_id FROM manual_tenants")).mappings().all()
    for tenant in tenants:
        manual_id = connection.execute(
            sa.text("SELECT id FROM manuals WHERE tenant_id = :tenant_id AND lower(code) = 'qam/45' LIMIT 1"),
            {"tenant_id": tenant["id"]},
        ).scalar()
        if manual_id is None:
            manual_id = str(uuid.uuid4())
            connection.execute(
                sa.text(
                    """INSERT INTO manuals
                    (id, tenant_id, code, title, manual_type, owner_role, status)
                    VALUES (:id, :tenant_id, 'QAM/45', 'Audit Notice', 'FORM', 'QUALITY_MANAGER', 'ACTIVE')"""
                ),
                {"id": manual_id, "tenant_id": tenant["id"]},
            )
        exists = connection.execute(
            sa.text(f"SELECT id FROM {SETTINGS_TABLE} WHERE amo_id = :amo_id LIMIT 1"),
            {"amo_id": tenant["amo_id"]},
        ).scalar()
        if exists is None:
            connection.execute(
                sa.text(
                    f"""INSERT INTO {SETTINGS_TABLE}
                    (id, amo_id, document_id, created_at, updated_at)
                    VALUES (:id, :amo_id, :document_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"""
                ),
                {"id": str(uuid.uuid4()), "amo_id": tenant["amo_id"], "document_id": manual_id},
            )


def upgrade() -> None:
    op.add_column("qms_audits", sa.Column("planned_start_time", sa.Time(), server_default="09:00:00", nullable=True))
    op.add_column("qms_audits", sa.Column("planned_end_time", sa.Time(), server_default="17:00:00", nullable=True))
    op.execute(sa.text("UPDATE qms_audits SET planned_start_time = '09:00:00' WHERE planned_start IS NOT NULL AND planned_start_time IS NULL"))
    op.execute(sa.text("UPDATE qms_audits SET planned_end_time = '17:00:00' WHERE planned_end IS NOT NULL AND planned_end_time IS NULL"))
    if _is_postgresql():
        op.create_check_constraint(
            "ck_qms_audit_planned_start_business_hours",
            "qms_audits",
            "planned_start_time IS NULL OR (planned_start_time >= TIME '09:00:00' AND planned_start_time <= TIME '17:00:00')",
        )
        op.create_check_constraint(
            "ck_qms_audit_planned_end_business_hours",
            "qms_audits",
            "planned_end_time IS NULL OR (planned_end_time >= TIME '09:00:00' AND planned_end_time <= TIME '17:00:00')",
        )
        op.create_check_constraint(
            "ck_qms_audit_daily_time_order",
            "qms_audits",
            "planned_start IS NULL OR planned_end IS NULL OR planned_start_time IS NULL OR planned_end_time IS NULL OR planned_end_time > planned_start_time",
        )

    op.create_table(
        SETTINGS_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["manuals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", name="uq_quality_audit_notice_template_amo"),
    )
    op.create_index("ix_quality_audit_notice_template_document", SETTINGS_TABLE, ["amo_id", "document_id"])

    op.add_column("quality_audit_notices", sa.Column("template_document_id", sa.String(length=36), nullable=True))
    op.add_column("quality_audit_notices", sa.Column("template_revision_id", sa.String(length=36), nullable=True))
    op.add_column("quality_audit_notices", sa.Column("form_number", sa.String(length=64), server_default="QAM/45", nullable=False))
    op.add_column("quality_audit_notices", sa.Column("form_issue_date", sa.String(length=64), nullable=True))
    op.add_column("quality_audit_notices", sa.Column("form_revision", sa.String(length=32), nullable=True))
    op.create_foreign_key(
        "fk_quality_audit_notice_template_document",
        "quality_audit_notices",
        "manuals",
        ["template_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_quality_audit_notice_template_revision",
        "quality_audit_notices",
        "manual_revisions",
        ["template_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )

    _seed_tenant_notice_forms()

    if _is_postgresql():
        op.execute(sa.text(f'ALTER TABLE "{SETTINGS_TABLE}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{SETTINGS_TABLE}" FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f"""
            CREATE POLICY {SETTINGS_TABLE}_amo_isolation ON "{SETTINGS_TABLE}"
            USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
            WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
        """))
        # The original immutable triggers prevented the parent audit's ON DELETE
        # CASCADE. Preserve immutability for direct deletes while permitting a
        # governed audit purge after its parent row has been removed.
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_terminal_quality_audit_notice_mutation()
            RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    IF current_setting('app.qms_audit_purge_id', true) = OLD.audit_id::text THEN
                        RETURN OLD;
                    END IF;
                    RAISE EXCEPTION 'audit notice revisions cannot be deleted directly';
                END IF;
                IF OLD.status IN ('ACKNOWLEDGED','SUPERSEDED','CANCELLED') THEN
                    RAISE EXCEPTION 'terminal audit notice revisions are immutable';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_quality_audit_notice_events_mutation()
            RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'DELETE' AND current_setting('app.qms_audit_purge_id', true) = OLD.audit_id::text THEN
                    RETURN OLD;
                END IF;
                RAISE EXCEPTION 'quality_audit_notice_events is append-only';
            END;
            $$ LANGUAGE plpgsql;
        """))


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_quality_audit_notice_events_mutation()
            RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'quality_audit_notice_events is append-only'; END; $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_terminal_quality_audit_notice_mutation()
            RETURNS trigger AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'audit notice revisions cannot be deleted'; END IF;
                IF OLD.status IN ('ACKNOWLEDGED','SUPERSEDED','CANCELLED') THEN RAISE EXCEPTION 'terminal audit notice revisions are immutable'; END IF;
                RETURN NEW;
            END; $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text(f'DROP POLICY IF EXISTS {SETTINGS_TABLE}_amo_isolation ON "{SETTINGS_TABLE}"'))
    op.drop_constraint("fk_quality_audit_notice_template_revision", "quality_audit_notices", type_="foreignkey")
    op.drop_constraint("fk_quality_audit_notice_template_document", "quality_audit_notices", type_="foreignkey")
    for column in ("form_revision", "form_issue_date", "form_number", "template_revision_id", "template_document_id"):
        op.drop_column("quality_audit_notices", column)
    op.drop_index("ix_quality_audit_notice_template_document", table_name=SETTINGS_TABLE)
    op.drop_table(SETTINGS_TABLE)
    if _is_postgresql():
        for constraint in (
            "ck_qms_audit_daily_time_order",
            "ck_qms_audit_planned_end_business_hours",
            "ck_qms_audit_planned_start_business_hours",
        ):
            op.drop_constraint(constraint, "qms_audits", type_="check")
    op.drop_column("qms_audits", "planned_end_time")
    op.drop_column("qms_audits", "planned_start_time")
