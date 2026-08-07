"""add controlled tenant AMP overlay and OEM lineage

Revision ID: aircraft_arch_20260807_tenant_amp
Revises: aircraft_arch_20260807_oem_backend_json
Create Date: 2026-08-07
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aircraft_arch_20260807_tenant_amp"
down_revision: Union[str, Sequence[str], None] = "aircraft_arch_20260807_oem_backend_json"
branch_labels = None
depends_on = None

UUID = sa.String(36)
NOW = sa.text("CURRENT_TIMESTAMP")
EMPTY_OBJECT = sa.text("'{}'::json")
EMPTY_LIST = sa.text("'[]'::json")


def upgrade() -> None:
    op.add_column("aircraft_type_templates", sa.Column("series", sa.String(80), nullable=True))
    op.create_index(
        "ix_aircraft_type_template_family_series",
        "aircraft_type_templates",
        ["family_id", "series", "status"],
    )

    op.add_column(
        "tenant_maintenance_programme_revisions",
        sa.Column(
            "base_content_pack_revision_id",
            UUID,
            sa.ForeignKey("aircraft_content_pack_revisions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.add_column(
        "tenant_maintenance_programme_revisions",
        sa.Column("source_currentness_at_approval", sa.String(40), nullable=True),
    )
    op.add_column(
        "tenant_maintenance_programme_revisions",
        sa.Column("approval_reference", sa.String(160), nullable=True),
    )
    op.create_index(
        "ix_tenant_programme_revision_oem_baseline",
        "tenant_maintenance_programme_revisions",
        ["base_content_pack_revision_id", "status"],
    )

    op.add_column(
        "tenant_maintenance_programme_tasks",
        sa.Column(
            "source_content_task_id",
            UUID,
            sa.ForeignKey("aircraft_content_pack_tasks.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.add_column(
        "tenant_maintenance_programme_tasks",
        sa.Column("decision", sa.String(20), nullable=False, server_default="LEGACY"),
    )
    op.add_column(
        "tenant_maintenance_programme_tasks",
        sa.Column("justification", sa.Text(), nullable=True),
    )
    op.add_column(
        "tenant_maintenance_programme_tasks",
        sa.Column("approval_reference", sa.String(160), nullable=True),
    )
    op.add_column(
        "tenant_maintenance_programme_tasks",
        sa.Column("source_task_hash", sa.String(64), nullable=True),
    )
    op.create_check_constraint(
        "ck_tenant_programme_task_decision",
        "tenant_maintenance_programme_tasks",
        "decision IN ('INHERIT','TIGHTEN','ADD','LEGACY')",
    )
    op.create_index(
        "ix_tenant_programme_task_source",
        "tenant_maintenance_programme_tasks",
        ["revision_id", "source_content_task_id", "decision"],
    )

    op.create_table(
        "tenant_programme_validation_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("amo_id", UUID, sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "revision_id",
            UUID,
            sa.ForeignKey("tenant_maintenance_programme_revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "baseline_revision_id",
            UUID,
            sa.ForeignKey("aircraft_content_pack_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("programme_content_hash", sa.String(64), nullable=False),
        sa.Column("baseline_content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("blocking_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("issues_json", sa.JSON(), nullable=False, server_default=EMPTY_LIST),
        sa.Column("summary_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint(
            "status IN ('PASS','WARN','BLOCKED')",
            name="ck_tenant_programme_validation_status",
        ),
    )
    op.create_index(
        "ix_tenant_programme_validation_revision",
        "tenant_programme_validation_runs",
        ["revision_id", "created_at"],
    )
    op.create_index(
        "ix_tenant_programme_validation_scope",
        "tenant_programme_validation_runs",
        ["amo_id", "status", "created_at"],
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION aircraft_guard_published_tenant_programme()
        RETURNS trigger AS $$
        DECLARE parent_status text;
        BEGIN
            IF TG_TABLE_NAME = 'tenant_maintenance_programme_revisions' THEN
                IF TG_OP = 'DELETE' AND OLD.status IN ('PUBLISHED','SUPERSEDED','WITHDRAWN') THEN
                    RAISE EXCEPTION 'controlled tenant programme revision cannot be deleted';
                END IF;
                IF TG_OP = 'UPDATE' AND OLD.status IN ('PUBLISHED','SUPERSEDED','WITHDRAWN') THEN
                    IF NEW.programme_id IS DISTINCT FROM OLD.programme_id
                       OR NEW.revision_code IS DISTINCT FROM OLD.revision_code
                       OR NEW.aircraft_type_revision_id IS DISTINCT FROM OLD.aircraft_type_revision_id
                       OR NEW.effectivity_rule_version_id IS DISTINCT FROM OLD.effectivity_rule_version_id
                       OR NEW.base_content_pack_revision_id IS DISTINCT FROM OLD.base_content_pack_revision_id
                       OR NEW.source_reference IS DISTINCT FROM OLD.source_reference
                       OR NEW.source_revision IS DISTINCT FROM OLD.source_revision
                       OR NEW.source_checksum_sha256 IS DISTINCT FROM OLD.source_checksum_sha256
                       OR NEW.approval_reference IS DISTINCT FROM OLD.approval_reference
                       OR NEW.content_hash IS DISTINCT FROM OLD.content_hash THEN
                        RAISE EXCEPTION 'published tenant programme identity/content is immutable';
                    END IF;
                END IF;
                RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
            END IF;

            SELECT r.status INTO parent_status
              FROM tenant_maintenance_programme_revisions r
             WHERE r.id = CASE WHEN TG_OP = 'DELETE' THEN OLD.revision_id ELSE NEW.revision_id END;
            IF parent_status IN ('PUBLISHED','SUPERSEDED','WITHDRAWN') THEN
                RAISE EXCEPTION 'tasks of a controlled tenant programme revision are immutable';
            END IF;
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_aircraft_tenant_programme_revision_controlled
          ON tenant_maintenance_programme_revisions;
        CREATE TRIGGER trg_aircraft_tenant_programme_revision_controlled
        BEFORE UPDATE OR DELETE ON tenant_maintenance_programme_revisions
        FOR EACH ROW EXECUTE FUNCTION aircraft_guard_published_tenant_programme();

        DROP TRIGGER IF EXISTS trg_aircraft_tenant_programme_task_controlled
          ON tenant_maintenance_programme_tasks;
        CREATE TRIGGER trg_aircraft_tenant_programme_task_controlled
        BEFORE UPDATE OR DELETE ON tenant_maintenance_programme_tasks
        FOR EACH ROW EXECUTE FUNCTION aircraft_guard_published_tenant_programme();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_aircraft_tenant_programme_task_controlled ON tenant_maintenance_programme_tasks")
    op.execute("DROP TRIGGER IF EXISTS trg_aircraft_tenant_programme_revision_controlled ON tenant_maintenance_programme_revisions")
    op.execute("DROP FUNCTION IF EXISTS aircraft_guard_published_tenant_programme()")

    op.drop_index("ix_tenant_programme_validation_scope", table_name="tenant_programme_validation_runs")
    op.drop_index("ix_tenant_programme_validation_revision", table_name="tenant_programme_validation_runs")
    op.drop_table("tenant_programme_validation_runs")

    op.drop_index("ix_tenant_programme_task_source", table_name="tenant_maintenance_programme_tasks")
    op.drop_constraint("ck_tenant_programme_task_decision", "tenant_maintenance_programme_tasks", type_="check")
    op.drop_column("tenant_maintenance_programme_tasks", "source_task_hash")
    op.drop_column("tenant_maintenance_programme_tasks", "approval_reference")
    op.drop_column("tenant_maintenance_programme_tasks", "justification")
    op.drop_column("tenant_maintenance_programme_tasks", "decision")
    op.drop_column("tenant_maintenance_programme_tasks", "source_content_task_id")

    op.drop_index("ix_tenant_programme_revision_oem_baseline", table_name="tenant_maintenance_programme_revisions")
    op.drop_column("tenant_maintenance_programme_revisions", "approval_reference")
    op.drop_column("tenant_maintenance_programme_revisions", "source_currentness_at_approval")
    op.drop_column("tenant_maintenance_programme_revisions", "base_content_pack_revision_id")

    op.drop_index("ix_aircraft_type_template_family_series", table_name="aircraft_type_templates")
    op.drop_column("aircraft_type_templates", "series")
