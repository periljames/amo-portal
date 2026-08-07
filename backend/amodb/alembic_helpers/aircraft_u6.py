from __future__ import annotations

from alembic import op
import sqlalchemy as sa

UUID = sa.String(36)
NOW = sa.text("CURRENT_TIMESTAMP")
EMPTY_OBJECT = sa.text("'{}'::json")
EMPTY_LIST = sa.text("'[]'::json")


def upgrade_u6() -> None:
    op.create_table(
        "aircraft_content_packs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("manufacturer", sa.String(120), nullable=False),
        sa.Column("family", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="SOURCE_INTAKE"),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("code", name="uq_aircraft_content_pack_code"),
        sa.CheckConstraint("status IN ('SOURCE_INTAKE','ACTIVE','INACTIVE')", name="ck_aircraft_content_pack_status"),
    )
    op.create_index("ix_aircraft_content_pack_family", "aircraft_content_packs", ["manufacturer", "family", "status"])

    op.create_table(
        "aircraft_content_pack_revisions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("pack_id", UUID, sa.ForeignKey("aircraft_content_packs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision_code", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("published_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("pack_id", "revision_code", name="uq_aircraft_content_pack_revision"),
        sa.CheckConstraint("status IN ('DRAFT','PUBLISHED','SUPERSEDED','WITHDRAWN')", name="ck_aircraft_content_pack_revision_status"),
    )
    op.create_index("ix_aircraft_content_pack_revision_status", "aircraft_content_pack_revisions", ["pack_id", "status"])

    op.create_table(
        "aircraft_content_pack_sources",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("revision_id", UUID, sa.ForeignKey("aircraft_content_pack_revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("reference", sa.String(255), nullable=False),
        sa.Column("source_revision", sa.String(80), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("authority", sa.String(80), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.UniqueConstraint("revision_id", "reference", "source_revision", name="uq_aircraft_content_pack_source"),
    )

    op.create_table(
        "aircraft_content_pack_positions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("revision_id", UUID, sa.ForeignKey("aircraft_content_pack_revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("position_kind", sa.String(40), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_reference", sa.String(255), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.UniqueConstraint("revision_id", "code", name="uq_aircraft_content_pack_position"),
    )

    op.create_table(
        "aircraft_content_pack_components",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("revision_id", UUID, sa.ForeignKey("aircraft_content_pack_revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("definition_code", sa.String(80), nullable=False),
        sa.Column("position_code", sa.String(50), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("component_class", sa.String(50), nullable=False),
        sa.Column("accepted_part_numbers_json", sa.JSON(), nullable=False, server_default=EMPTY_LIST),
        sa.Column("life_limit_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("source_reference", sa.String(255), nullable=False),
        sa.UniqueConstraint("revision_id", "definition_code", name="uq_aircraft_content_pack_component"),
    )

    op.create_table(
        "aircraft_content_pack_tasks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("revision_id", UUID, sa.ForeignKey("aircraft_content_pack_revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_code", sa.String(100), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("ata_chapter", sa.String(12), nullable=True),
        sa.Column("intervals_json", sa.JSON(), nullable=False),
        sa.Column("effectivity_expression_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("source_reference", sa.String(255), nullable=False),
        sa.Column("source_revision", sa.String(80), nullable=False),
        sa.Column("source_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.UniqueConstraint("revision_id", "task_code", name="uq_aircraft_content_pack_task"),
        sa.CheckConstraint("source_reference <> '' AND source_revision <> ''", name="ck_aircraft_content_pack_task_source"),
    )


def downgrade_u6() -> None:
    op.drop_table("aircraft_content_pack_tasks")
    op.drop_table("aircraft_content_pack_components")
    op.drop_table("aircraft_content_pack_positions")
    op.drop_table("aircraft_content_pack_sources")
    op.drop_index("ix_aircraft_content_pack_revision_status", table_name="aircraft_content_pack_revisions")
    op.drop_table("aircraft_content_pack_revisions")
    op.drop_index("ix_aircraft_content_pack_family", table_name="aircraft_content_packs")
    op.drop_table("aircraft_content_packs")
