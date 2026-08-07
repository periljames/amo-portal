"""Add normalized Document Control governance, locations, annotations and backfill evidence.

Revision ID: docgov_20260806_governance
Revises: workforce_20260806_governance
Create Date: 2026-08-06
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "docgov_20260806_governance"
down_revision: Union[str, Sequence[str], None] = "workforce_20260806_governance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "document_responsibility_assignments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=True),
        sa.Column("responsibility_type", sa.String(length=48), nullable=False),
        sa.Column("assignee_type", sa.String(length=24), nullable=False),
        sa.Column("assignee_user_id", sa.String(length=36), nullable=True),
        sa.Column("assignee_department_id", sa.String(length=36), nullable=True),
        sa.Column("assignee_org_unit_id", sa.String(length=36), nullable=True),
        sa.Column("assignee_role", sa.String(length=96), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("delegated_from_id", sa.String(length=36), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("assignment_source", sa.String(length=24), nullable=False, server_default="MANUAL"),
        sa.Column("confidence_percent", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("confirmation_status", sa.String(length=24), nullable=False, server_default="CONFIRMED"),
        sa.Column("provenance_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("confirmed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("confidence_percent >= 0 AND confidence_percent <= 100", name="ck_doc_resp_confidence"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_doc_resp_effective_period"),
        sa.CheckConstraint(
            "(CASE WHEN assignee_user_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN assignee_department_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN assignee_org_unit_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN assignee_role IS NULL THEN 0 ELSE 1 END) = 1",
            name="ck_doc_resp_one_assignee",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assignee_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assignee_department_id"], ["departments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assignee_org_unit_id"], ["workforce_org_units.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["delegated_from_id"], ["document_responsibility_assignments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["superseded_by_id"], ["document_responsibility_assignments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_doc_resp_tenant_manual_type", "document_responsibility_assignments", ["tenant_id", "manual_id", "responsibility_type"])
    op.create_index("ix_doc_resp_tenant_status", "document_responsibility_assignments", ["tenant_id", "confirmation_status", "responsibility_type"])
    op.create_index("ix_doc_resp_user_effective", "document_responsibility_assignments", ["assignee_user_id", "effective_from", "effective_to"])
    op.create_index("ix_doc_resp_department_effective", "document_responsibility_assignments", ["assignee_department_id", "effective_from", "effective_to"])
    op.create_index("ix_doc_resp_org_effective", "document_responsibility_assignments", ["assignee_org_unit_id", "effective_from", "effective_to"])

    op.create_table(
        "document_locations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("location_key", sa.String(length=128), nullable=False),
        sa.Column("location_type", sa.String(length=32), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("normalized_rects_json", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("exact_quote", sa.Text(), nullable=True),
        sa.Column("prefix_context", sa.Text(), nullable=True),
        sa.Column("suffix_context", sa.Text(), nullable=True),
        sa.Column("section_id", sa.String(length=36), nullable=True),
        sa.Column("block_id", sa.String(length=36), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("sheet_name", sa.String(length=255), nullable=True),
        sa.Column("cell_range", sa.String(length=128), nullable=True),
        sa.Column("slide_number", sa.Integer(), nullable=True),
        sa.Column("object_id", sa.String(length=255), nullable=True),
        sa.Column("image_region_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("adapter_name", sa.String(length=64), nullable=False),
        sa.Column("adapter_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["section_id"], ["manual_sections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["block_id"], ["manual_blocks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "revision_id", "location_key", name="uq_document_location_revision_key"),
    )
    op.create_index("ix_document_location_revision_page", "document_locations", ["revision_id", "page_number"])
    op.create_index("ix_document_location_checksum", "document_locations", ["source_sha256", "location_type"])
    op.create_index("ix_document_location_section", "document_locations", ["section_id", "block_id"])

    op.create_table(
        "document_governed_relationships",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("source_manual_id", sa.String(length=36), nullable=False),
        sa.Column("source_revision_id", sa.String(length=36), nullable=True),
        sa.Column("source_location_id", sa.String(length=36), nullable=True),
        sa.Column("target_entity_type", sa.String(length=48), nullable=False),
        sa.Column("target_entity_id", sa.String(length=128), nullable=True),
        sa.Column("target_manual_id", sa.String(length=36), nullable=True),
        sa.Column("target_revision_id", sa.String(length=36), nullable=True),
        sa.Column("relationship_type", sa.String(length=48), nullable=False),
        sa.Column("relationship_source", sa.String(length=24), nullable=False, server_default="MANUAL"),
        sa.Column("occurrence_key", sa.String(length=128), nullable=False),
        sa.Column("exact_token", sa.String(length=255), nullable=True),
        sa.Column("exact_quote", sa.Text(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section_label", sa.String(length=255), nullable=True),
        sa.Column("confidence_percent", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("resolution_status", sa.String(length=24), nullable=False, server_default="CONFIRMED"),
        sa.Column("provenance_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("confirmed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("confidence_percent >= 0 AND confidence_percent <= 100", name="ck_doc_rel_confidence"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_revision_id"], ["manual_revisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_location_id"], ["document_locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_manual_id"], ["manuals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_revision_id"], ["manual_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["superseded_by_id"], ["document_governed_relationships.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "occurrence_key", name="uq_doc_relationship_occurrence"),
    )
    op.create_index("ix_doc_rel_source", "document_governed_relationships", ["tenant_id", "source_manual_id", "relationship_type"])
    op.create_index("ix_doc_rel_target_manual", "document_governed_relationships", ["tenant_id", "target_manual_id", "relationship_type"])
    op.create_index("ix_doc_rel_target_entity", "document_governed_relationships", ["tenant_id", "target_entity_type", "target_entity_id"])
    op.create_index("ix_doc_rel_resolution", "document_governed_relationships", ["tenant_id", "resolution_status", "relationship_type"])

    op.create_table(
        "document_annotations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("location_id", sa.String(length=36), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("annotation_type", sa.String(length=32), nullable=False),
        sa.Column("color", sa.String(length=16), nullable=False, server_default="YELLOW"),
        sa.Column("visibility", sa.String(length=24), nullable=False, server_default="PRIVATE"),
        sa.Column("note_text", sa.Text(), nullable=True),
        sa.Column("tags_json", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("linked_entity_type", sa.String(length=48), nullable=True),
        sa.Column("linked_entity_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="ACTIVE"),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["document_locations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_doc_annotation_revision_visibility", "document_annotations", ["tenant_id", "revision_id", "visibility"])
    op.create_index("ix_doc_annotation_creator", "document_annotations", ["tenant_id", "created_by_user_id", "created_at"])
    op.create_index("ix_doc_annotation_link", "document_annotations", ["tenant_id", "linked_entity_type", "linked_entity_id"])

    op.create_table(
        "document_governance_backfill_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("scope_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="QUEUED"),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("succeeded_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reconciliation_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_doc_backfill_tenant_key"),
    )
    op.create_index("ix_doc_backfill_status", "document_governance_backfill_runs", ["tenant_id", "status", "created_at"])

    op.create_table(
        "document_governance_backfill_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("action_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("result_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["run_id"], ["document_governance_backfill_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "manual_id", name="uq_doc_backfill_item_manual"),
    )
    op.create_index("ix_doc_backfill_item_status", "document_governance_backfill_items", ["run_id", "status", "sequence"])
    op.create_index("ix_doc_backfill_item_tenant_manual", "document_governance_backfill_items", ["tenant_id", "manual_id"])


def downgrade() -> None:
    op.drop_index("ix_doc_backfill_item_tenant_manual", table_name="document_governance_backfill_items")
    op.drop_index("ix_doc_backfill_item_status", table_name="document_governance_backfill_items")
    op.drop_table("document_governance_backfill_items")
    op.drop_index("ix_doc_backfill_status", table_name="document_governance_backfill_runs")
    op.drop_table("document_governance_backfill_runs")
    op.drop_index("ix_doc_annotation_link", table_name="document_annotations")
    op.drop_index("ix_doc_annotation_creator", table_name="document_annotations")
    op.drop_index("ix_doc_annotation_revision_visibility", table_name="document_annotations")
    op.drop_table("document_annotations")
    op.drop_index("ix_doc_rel_resolution", table_name="document_governed_relationships")
    op.drop_index("ix_doc_rel_target_entity", table_name="document_governed_relationships")
    op.drop_index("ix_doc_rel_target_manual", table_name="document_governed_relationships")
    op.drop_index("ix_doc_rel_source", table_name="document_governed_relationships")
    op.drop_table("document_governed_relationships")
    op.drop_index("ix_document_location_section", table_name="document_locations")
    op.drop_index("ix_document_location_checksum", table_name="document_locations")
    op.drop_index("ix_document_location_revision_page", table_name="document_locations")
    op.drop_table("document_locations")
    op.drop_index("ix_doc_resp_org_effective", table_name="document_responsibility_assignments")
    op.drop_index("ix_doc_resp_department_effective", table_name="document_responsibility_assignments")
    op.drop_index("ix_doc_resp_user_effective", table_name="document_responsibility_assignments")
    op.drop_index("ix_doc_resp_tenant_status", table_name="document_responsibility_assignments")
    op.drop_index("ix_doc_resp_tenant_manual_type", table_name="document_responsibility_assignments")
    op.drop_table("document_responsibility_assignments")
