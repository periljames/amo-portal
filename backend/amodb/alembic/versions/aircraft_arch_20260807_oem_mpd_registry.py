"""add OEM MPD source registry and rich maintenance-planning content

Revision ID: aircraft_arch_20260807_oem_mpd
Revises: merge_20260807_qms_planner_aircraft
Create Date: 2026-08-07
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aircraft_arch_20260807_oem_mpd"
down_revision: Union[str, Sequence[str], None] = "merge_20260807_qms_planner_aircraft"
branch_labels = None
depends_on = None

UUID = sa.String(36)
NOW = sa.text("CURRENT_TIMESTAMP")
EMPTY_OBJECT = sa.text("'{}'::json")
EMPTY_LIST = sa.text("'[]'::json")


def upgrade() -> None:
    op.add_column(
        "aircraft_content_packs",
        sa.Column("series", sa.String(80), nullable=True),
    )

    op.create_table(
        "aircraft_oem_publications",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("manufacturer", sa.String(120), nullable=False),
        sa.Column("family", sa.String(120), nullable=False),
        sa.Column("series", sa.String(80), nullable=True),
        sa.Column("publication_code", sa.String(120), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("publication_kind", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "created_by_user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("code", name="uq_aircraft_oem_publication_code"),
        sa.CheckConstraint(
            "status IN ('ACTIVE','INACTIVE')",
            name="ck_aircraft_oem_publication_status",
        ),
    )
    op.create_index(
        "ix_aircraft_oem_publication_family",
        "aircraft_oem_publications",
        ["manufacturer", "family", "series", "status"],
    )

    op.create_table(
        "aircraft_oem_publication_revisions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "publication_id",
            UUID,
            sa.ForeignKey("aircraft_oem_publications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision_code", sa.String(80), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="CANDIDATE"),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=True),
        sa.Column("storage_locator", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column(
            "supersedes_revision_id",
            UUID,
            sa.ForeignKey("aircraft_oem_publication_revisions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "submitted_by_user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "submitted_by_amo_id",
            UUID,
            sa.ForeignKey("amos.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "verified_by_user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint(
            "publication_id",
            "revision_code",
            name="uq_aircraft_oem_publication_revision",
        ),
        sa.CheckConstraint(
            "status IN ('CANDIDATE','VERIFIED','CURRENT','SUPERSEDED','WITHDRAWN','REJECTED')",
            name="ck_aircraft_oem_publication_revision_status",
        ),
    )
    op.create_index(
        "ix_aircraft_oem_publication_revision_status",
        "aircraft_oem_publication_revisions",
        ["publication_id", "status", "effective_date"],
    )

    op.create_table(
        "aircraft_oem_temporary_revisions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "publication_revision_id",
            UUID,
            sa.ForeignKey("aircraft_oem_publication_revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("temporary_revision_code", sa.String(80), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=True),
        sa.Column("storage_locator", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("replaces_temporary_revision_code", sa.String(80), nullable=True),
        sa.Column("filing_instructions", sa.Text(), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column(
            "submitted_by_user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "submitted_by_amo_id",
            UUID,
            sa.ForeignKey("amos.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "verified_by_user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint(
            "publication_revision_id",
            "temporary_revision_code",
            name="uq_aircraft_oem_temporary_revision",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','INCORPORATED','SUPERSEDED','WITHDRAWN','REPLACED')",
            name="ck_aircraft_oem_temporary_revision_status",
        ),
    )
    op.create_index(
        "ix_aircraft_oem_temporary_revision_status",
        "aircraft_oem_temporary_revisions",
        ["publication_revision_id", "status"],
    )

    op.create_table(
        "aircraft_oem_source_watches",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "publication_id",
            UUID,
            sa.ForeignKey("aircraft_oem_publications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel_type", sa.String(20), nullable=False),
        sa.Column("reference", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_marker", sa.String(255), nullable=True),
        sa.Column("last_result", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column(
            "created_by_user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint(
            "publication_id",
            "channel_type",
            "reference",
            name="uq_aircraft_oem_source_watch",
        ),
        sa.CheckConstraint(
            "channel_type IN ('MANUAL_UPLOAD','OEM_PORTAL','EMAIL_NOTICE','RSS','API','OTHER')",
            name="ck_aircraft_oem_source_watch_channel",
        ),
    )
    op.create_index(
        "ix_aircraft_oem_source_watch_active",
        "aircraft_oem_source_watches",
        ["publication_id", "is_active"],
    )

    op.add_column(
        "aircraft_content_pack_sources",
        sa.Column(
            "publication_revision_id",
            UUID,
            sa.ForeignKey("aircraft_oem_publication_revisions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "aircraft_content_pack_sources",
        sa.Column(
            "temporary_revision_id",
            UUID,
            sa.ForeignKey("aircraft_oem_temporary_revisions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "aircraft_content_pack_sources",
        sa.Column("source_page_ref", sa.String(120), nullable=True),
    )
    op.add_column(
        "aircraft_content_pack_sources",
        sa.Column("document_locator", sa.Text(), nullable=True),
    )

    task_columns = (
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("programme_section", sa.String(40), nullable=True),
        sa.Column("task_type", sa.String(16), nullable=True),
        sa.Column("raw_interval_text", sa.Text(), nullable=True),
        sa.Column("raw_effectivity_text", sa.Text(), nullable=True),
        sa.Column("source_requirements_json", sa.JSON(), nullable=False, server_default=EMPTY_LIST),
        sa.Column("task_card_number", sa.String(120), nullable=True),
        sa.Column("task_card_configuration", sa.String(120), nullable=True),
        sa.Column("amm_reference", sa.String(120), nullable=True),
        sa.Column("zones_json", sa.JSON(), nullable=False, server_default=EMPTY_LIST),
        sa.Column("panels_json", sa.JSON(), nullable=False, server_default=EMPTY_LIST),
        sa.Column("general_references_json", sa.JSON(), nullable=False, server_default=EMPTY_LIST),
        sa.Column("skill_code", sa.String(40), nullable=True),
        sa.Column("labour_hours", sa.String(24), nullable=True),
        sa.Column("number_of_persons", sa.Integer(), nullable=True),
        sa.Column("program_notes_json", sa.JSON(), nullable=False, server_default=EMPTY_LIST),
        sa.Column("packaging_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("source_page_ref", sa.String(120), nullable=True),
    )
    for column in task_columns:
        op.add_column("aircraft_content_pack_tasks", column)
    op.create_index(
        "ix_aircraft_content_pack_task_section",
        "aircraft_content_pack_tasks",
        ["revision_id", "programme_section", "ata_chapter"],
    )

    op.create_table(
        "aircraft_content_pack_resources",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "revision_id",
            UUID,
            sa.ForeignKey("aircraft_content_pack_revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("resource_kind", sa.String(50), nullable=False),
        sa.Column("resource_code", sa.String(140), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("source_reference", sa.String(255), nullable=False),
        sa.Column("source_revision", sa.String(80), nullable=False),
        sa.Column("source_checksum_sha256", sa.String(64), nullable=False),
        sa.Column("source_page_ref", sa.String(120), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.UniqueConstraint(
            "revision_id",
            "resource_kind",
            "resource_code",
            name="uq_aircraft_content_pack_resource",
        ),
    )
    op.create_index(
        "ix_aircraft_content_pack_resource_kind",
        "aircraft_content_pack_resources",
        ["revision_id", "resource_kind"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_aircraft_content_pack_resource_kind",
        table_name="aircraft_content_pack_resources",
    )
    op.drop_table("aircraft_content_pack_resources")

    op.drop_index(
        "ix_aircraft_content_pack_task_section",
        table_name="aircraft_content_pack_tasks",
    )
    for column_name in (
        "source_page_ref",
        "packaging_json",
        "program_notes_json",
        "number_of_persons",
        "labour_hours",
        "skill_code",
        "general_references_json",
        "panels_json",
        "zones_json",
        "amm_reference",
        "task_card_configuration",
        "task_card_number",
        "source_requirements_json",
        "raw_effectivity_text",
        "raw_interval_text",
        "task_type",
        "programme_section",
        "description",
    ):
        op.drop_column("aircraft_content_pack_tasks", column_name)

    for column_name in (
        "document_locator",
        "source_page_ref",
        "temporary_revision_id",
        "publication_revision_id",
    ):
        op.drop_column("aircraft_content_pack_sources", column_name)

    op.drop_index(
        "ix_aircraft_oem_source_watch_active",
        table_name="aircraft_oem_source_watches",
    )
    op.drop_table("aircraft_oem_source_watches")

    op.drop_index(
        "ix_aircraft_oem_temporary_revision_status",
        table_name="aircraft_oem_temporary_revisions",
    )
    op.drop_table("aircraft_oem_temporary_revisions")

    op.drop_index(
        "ix_aircraft_oem_publication_revision_status",
        table_name="aircraft_oem_publication_revisions",
    )
    op.drop_table("aircraft_oem_publication_revisions")

    op.drop_index(
        "ix_aircraft_oem_publication_family",
        table_name="aircraft_oem_publications",
    )
    op.drop_table("aircraft_oem_publications")

    op.drop_column("aircraft_content_packs", "series")
