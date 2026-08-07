"""add tenant maintenance programme overlays

Revision ID: aircraft_arch_20260805_u4_programmes
Revises: aircraft_arch_20260805_u3_imports
Create Date: 2026-08-05
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "aircraft_arch_20260805_u4_programmes"
down_revision: Union[str, Sequence[str], None] = "aircraft_arch_20260805_u3_imports"
branch_labels = None
depends_on = None

UUID = sa.String(length=36)
NOW = sa.text("CURRENT_TIMESTAMP")
EMPTY_OBJECT = sa.text("'{}'::json")


def _user(name: str) -> sa.Column:
    return sa.Column(name, UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def upgrade() -> None:
    op.create_table(
        "tenant_maintenance_programmes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("amo_id", UUID, sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("authority", sa.String(80), nullable=True),
        sa.Column("approval_reference", sa.String(160), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        _user("created_by_user_id"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("amo_id", "code", name="uq_tenant_maintenance_programme_code"),
        sa.CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_tenant_maintenance_programme_status"),
    )
    op.create_index("ix_tenant_maintenance_programmes_amo_id", "tenant_maintenance_programmes", ["amo_id"])
    op.create_index("ix_tenant_maintenance_programme_scope", "tenant_maintenance_programmes", ["amo_id", "status"])

    op.create_table(
        "tenant_maintenance_programme_revisions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("programme_id", UUID, sa.ForeignKey("tenant_maintenance_programmes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision_code", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("aircraft_type_revision_id", UUID, sa.ForeignKey("aircraft_type_template_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("effectivity_rule_version_id", UUID, sa.ForeignKey("aircraft_effectivity_rule_versions.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("source_reference", sa.String(255), nullable=False),
        sa.Column("source_revision", sa.String(80), nullable=False),
        sa.Column("source_checksum_sha256", sa.String(64), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("supersedes_revision_id", UUID, sa.ForeignKey("tenant_maintenance_programme_revisions.id", ondelete="RESTRICT"), nullable=True),
        _user("created_by_user_id"),
        _user("published_by_user_id"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("programme_id", "revision_code", name="uq_tenant_maintenance_programme_revision"),
        sa.CheckConstraint("status IN ('DRAFT','PUBLISHED','SUPERSEDED','WITHDRAWN')", name="ck_tenant_maintenance_programme_revision_status"),
    )
    op.create_index("ix_tenant_maintenance_programme_revisions_programme_id", "tenant_maintenance_programme_revisions", ["programme_id"])
    op.create_index("ix_tmp_revision_type", "tenant_maintenance_programme_revisions", ["aircraft_type_revision_id"])
    op.create_index("ix_tmp_revision_effectivity", "tenant_maintenance_programme_revisions", ["effectivity_rule_version_id"])
    op.create_index("ix_tenant_maintenance_programme_revision_status", "tenant_maintenance_programme_revisions", ["programme_id", "status"])

    op.create_table(
        "tenant_maintenance_programme_tasks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("revision_id", UUID, sa.ForeignKey("tenant_maintenance_programme_revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_code", sa.String(100), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("ata_chapter", sa.String(12), nullable=True),
        sa.Column("intervals_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("effectivity_expression_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("source_reference", sa.String(255), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.UniqueConstraint("revision_id", "task_code", name="uq_tenant_maintenance_programme_task"),
    )
    op.create_index("ix_tenant_maintenance_programme_tasks_revision_id", "tenant_maintenance_programme_tasks", ["revision_id"])
    op.create_index("ix_tenant_maintenance_programme_task_ata", "tenant_maintenance_programme_tasks", ["revision_id", "ata_chapter"])

    op.create_table(
        "tenant_programme_upgrade_proposals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("amo_id", UUID, sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("programme_id", UUID, sa.ForeignKey("tenant_maintenance_programmes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_revision_id", UUID, sa.ForeignKey("tenant_maintenance_programme_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("proposed_type_revision_id", UUID, sa.ForeignKey("aircraft_type_template_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("proposed_effectivity_version_id", UUID, sa.ForeignKey("aircraft_effectivity_rule_versions.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("impact_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        _user("requested_by_user_id"),
        _user("approved_by_user_id"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('DRAFT','IMPACT_REVIEW','APPROVED','REJECTED','APPLIED')", name="ck_tenant_programme_upgrade_proposal_status"),
    )
    op.create_index("ix_tenant_programme_upgrade_proposals_amo_id", "tenant_programme_upgrade_proposals", ["amo_id"])
    op.create_index("ix_tenant_programme_upgrade_proposals_programme_id", "tenant_programme_upgrade_proposals", ["programme_id"])
    op.create_index("ix_tenant_programme_upgrade_proposal_scope", "tenant_programme_upgrade_proposals", ["amo_id", "programme_id", "status"])


def downgrade() -> None:
    op.drop_table("tenant_programme_upgrade_proposals")
    op.drop_table("tenant_maintenance_programme_tasks")
    op.drop_table("tenant_maintenance_programme_revisions")
    op.drop_table("tenant_maintenance_programmes")
