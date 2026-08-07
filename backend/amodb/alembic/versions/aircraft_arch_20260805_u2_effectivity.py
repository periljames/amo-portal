"""add explainable aircraft effectivity engine

Revision ID: aircraft_arch_20260805_u2_effectivity
Revises: aircraft_arch_20260805_u1_merge
Create Date: 2026-08-05
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "aircraft_arch_20260805_u2_effectivity"
down_revision: Union[str, Sequence[str], None] = "aircraft_arch_20260805_u1_merge"
branch_labels = None
depends_on = None

UUID = sa.String(length=36)
NOW = sa.text("CURRENT_TIMESTAMP")
EMPTY_OBJECT = sa.text("'{}'::json")


def upgrade() -> None:
    op.create_table(
        "aircraft_effectivity_rule_sets",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("target_kind", sa.String(40), nullable=False),
        sa.Column("target_reference", sa.String(160), nullable=False),
        sa.Column("aircraft_type_template_id", UUID, sa.ForeignKey("aircraft_type_templates.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("code", name="uq_aircraft_effectivity_rule_set_code"),
        sa.CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_aircraft_effectivity_rule_set_status"),
    )
    op.create_index("ix_aircraft_effectivity_rule_set_target", "aircraft_effectivity_rule_sets", ["target_kind", "status"])
    op.create_index("ix_aircraft_effectivity_rule_sets_aircraft_type_template_id", "aircraft_effectivity_rule_sets", ["aircraft_type_template_id"])

    op.create_table(
        "aircraft_effectivity_rule_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("rule_set_id", UUID, sa.ForeignKey("aircraft_effectivity_rule_sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_code", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("expression_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("source_reference", sa.String(255), nullable=False),
        sa.Column("source_revision", sa.String(80), nullable=False),
        sa.Column("source_checksum_sha256", sa.String(64), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("supersedes_version_id", UUID, sa.ForeignKey("aircraft_effectivity_rule_versions.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("published_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("rule_set_id", "version_code", name="uq_aircraft_effectivity_rule_version"),
        sa.CheckConstraint("status IN ('DRAFT','PUBLISHED','SUPERSEDED','WITHDRAWN')", name="ck_aircraft_effectivity_rule_version_status"),
    )
    op.create_index("ix_aircraft_effectivity_rule_versions_rule_set_id", "aircraft_effectivity_rule_versions", ["rule_set_id"])
    op.create_index("ix_aircraft_effectivity_rule_version_status", "aircraft_effectivity_rule_versions", ["rule_set_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_aircraft_effectivity_rule_version_status", table_name="aircraft_effectivity_rule_versions")
    op.drop_index("ix_aircraft_effectivity_rule_versions_rule_set_id", table_name="aircraft_effectivity_rule_versions")
    op.drop_table("aircraft_effectivity_rule_versions")
    op.drop_index("ix_aircraft_effectivity_rule_sets_aircraft_type_template_id", table_name="aircraft_effectivity_rule_sets")
    op.drop_index("ix_aircraft_effectivity_rule_set_target", table_name="aircraft_effectivity_rule_sets")
    op.drop_table("aircraft_effectivity_rule_sets")
