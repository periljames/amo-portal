"""add immutable aircraft type catalogue

Revision ID: aircraft_arch_20260805_u1_catalogue
Revises: foundation_20260805_timestamp_defaults
Create Date: 2026-08-05
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "aircraft_arch_20260805_u1_catalogue"
down_revision: Union[str, Sequence[str], None] = "foundation_20260805_timestamp_defaults"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = sa.String(length=36)
NOW = sa.text("CURRENT_TIMESTAMP")
EMPTY_OBJECT = sa.text("'{}'::json")
EMPTY_ARRAY = sa.text("'[]'::json")


def _user_fk(name: str = "created_by_user_id") -> sa.Column:
    return sa.Column(name, UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def upgrade() -> None:
    op.create_table(
        "aircraft_type_families",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("manufacturer", sa.String(120), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("description", sa.Text(), nullable=True),
        _user_fk(),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("code", name="uq_aircraft_type_family_code"),
        sa.CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_aircraft_type_family_status"),
    )
    op.create_index("ix_aircraft_type_family_manufacturer", "aircraft_type_families", ["manufacturer", "status"])

    op.create_table(
        "aircraft_type_templates",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("family_id", UUID, sa.ForeignKey("aircraft_type_families.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("manufacturer", sa.String(120), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("variant", sa.String(80), nullable=True),
        sa.Column("type_certificate", sa.String(80), nullable=True),
        sa.Column("icao_type_designator", sa.String(8), nullable=True),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        _user_fk(),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("code", name="uq_aircraft_type_template_code"),
        sa.CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_aircraft_type_template_status"),
    )
    op.create_index("ix_aircraft_type_template_family_status", "aircraft_type_templates", ["family_id", "status"])

    op.create_table(
        "aircraft_type_template_revisions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("template_id", UUID, sa.ForeignKey("aircraft_type_templates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("revision_code", sa.String(40), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("supersedes_revision_id", UUID, sa.ForeignKey("aircraft_type_template_revisions.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("configuration_schema_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("applicability_defaults_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        _user_fk(),
        _user_fk("published_by_user_id"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("template_id", "revision_code", name="uq_aircraft_type_template_revision"),
        sa.CheckConstraint("status IN ('DRAFT','PUBLISHED','SUPERSEDED','WITHDRAWN')", name="ck_aircraft_type_revision_status"),
    )
    op.create_index("ix_aircraft_type_revision_template_status", "aircraft_type_template_revisions", ["template_id", "status"])

    op.create_table(
        "aircraft_type_positions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("revision_id", UUID, sa.ForeignKey("aircraft_type_template_revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("position_kind", sa.String(40), nullable=False),
        sa.Column("parent_code", sa.String(50), nullable=True),
        sa.Column("sequence_no", sa.String(20), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("effectivity_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.UniqueConstraint("revision_id", "code", name="uq_aircraft_type_position_code"),
    )
    op.create_index("ix_aircraft_type_position_revision_kind", "aircraft_type_positions", ["revision_id", "position_kind"])

    op.create_table(
        "aircraft_type_component_definitions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("revision_id", UUID, sa.ForeignKey("aircraft_type_template_revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("definition_code", sa.String(80), nullable=False),
        sa.Column("position_code", sa.String(50), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("component_class", sa.String(50), nullable=False),
        sa.Column("accepted_part_numbers_json", sa.JSON(), nullable=False, server_default=EMPTY_ARRAY),
        sa.Column("life_limit_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("effectivity_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.UniqueConstraint("revision_id", "definition_code", name="uq_aircraft_type_component_definition"),
    )
    op.create_index("ix_aircraft_type_component_revision_position", "aircraft_type_component_definitions", ["revision_id", "position_code"])

    op.create_table(
        "aircraft_type_sources",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("revision_id", UUID, sa.ForeignKey("aircraft_type_template_revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("reference", sa.String(200), nullable=False),
        sa.Column("source_revision", sa.String(80), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        sa.Column("authority", sa.String(80), nullable=True),
        sa.Column("provenance_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        _user_fk(),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("revision_id", "source_type", "reference", "source_revision", name="uq_aircraft_type_source"),
    )
    op.create_index("ix_aircraft_type_source_revision_type", "aircraft_type_sources", ["revision_id", "source_type"])


def downgrade() -> None:
    for index_name, table_name in (
        ("ix_aircraft_type_source_revision_type", "aircraft_type_sources"),
        ("ix_aircraft_type_component_revision_position", "aircraft_type_component_definitions"),
        ("ix_aircraft_type_position_revision_kind", "aircraft_type_positions"),
        ("ix_aircraft_type_revision_template_status", "aircraft_type_template_revisions"),
        ("ix_aircraft_type_template_family_status", "aircraft_type_templates"),
        ("ix_aircraft_type_family_manufacturer", "aircraft_type_families"),
    ):
        op.drop_index(index_name, table_name=table_name)
        op.drop_table(table_name)
