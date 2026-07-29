"""Create governed documentation hierarchy and reference graph.

Revision ID: document_control_20260729_knowledge_graph
Revises: document_control_20260725_integrity
Create Date: 2026-07-29
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "document_control_20260729_knowledge_graph"
down_revision = "document_control_20260725_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documentation_nodes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("manual_id", sa.String(length=36), nullable=True),
        sa.Column("node_type", sa.String(length=40), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("normalized_code", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("path", sa.String(length=2048), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["documentation_nodes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "normalized_code", name="uq_documentation_node_tenant_code"),
        sa.UniqueConstraint("tenant_id", "manual_id", name="uq_documentation_node_tenant_manual"),
    )
    op.create_index("ix_documentation_nodes_tenant_parent_order", "documentation_nodes", ["tenant_id", "parent_id", "order_index"])
    op.create_index("ix_documentation_nodes_tenant_type", "documentation_nodes", ["tenant_id", "node_type"])
    op.create_index("ix_documentation_nodes_tenant_path", "documentation_nodes", ["tenant_id", "path"])

    op.create_table(
        "documentation_execution_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("execution_type", sa.String(length=40), nullable=False, server_default="NONE"),
        sa.Column("submission_mode", sa.String(length=40), nullable=False, server_default="DOWNLOAD_ONLY"),
        sa.Column("record_series_node_id", sa.String(length=36), nullable=True),
        sa.Column("retention_years", sa.Integer(), nullable=True),
        sa.Column("naming_pattern", sa.String(length=255), nullable=False, server_default="{code}-{date}-{sequence}"),
        sa.Column("allow_download", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_save_draft", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("requires_signature", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("requires_review", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("schema_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("access_scope_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["record_series_node_id"], ["documentation_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "manual_id", name="uq_documentation_execution_tenant_manual"),
    )
    op.create_index("ix_documentation_execution_tenant_type", "documentation_execution_profiles", ["tenant_id", "execution_type"])
    op.create_index("ix_documentation_execution_record_series", "documentation_execution_profiles", ["record_series_node_id"])

    op.create_table(
        "documentation_references",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("source_manual_id", sa.String(length=36), nullable=False),
        sa.Column("source_revision_id", sa.String(length=36), nullable=False),
        sa.Column("source_section_id", sa.String(length=36), nullable=True),
        sa.Column("source_block_id", sa.String(length=36), nullable=True),
        sa.Column("source_page_number", sa.Integer(), nullable=True),
        sa.Column("source_char_start", sa.Integer(), nullable=True),
        sa.Column("source_char_end", sa.Integer(), nullable=True),
        sa.Column("source_bbox_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source_quote", sa.Text(), nullable=False),
        sa.Column("source_context", sa.Text(), nullable=True),
        sa.Column("source_change_hash", sa.String(length=128), nullable=True),
        sa.Column("occurrence_key", sa.String(length=128), nullable=False),
        sa.Column("raw_token", sa.String(length=255), nullable=False),
        sa.Column("normalized_token", sa.String(length=128), nullable=False),
        sa.Column("relationship_type", sa.String(length=40), nullable=False, server_default="REFERENCES"),
        sa.Column("resolution_policy", sa.String(length=40), nullable=False, server_default="CURRENT_EFFECTIVE"),
        sa.Column("target_manual_id", sa.String(length=36), nullable=True),
        sa.Column("target_revision_id", sa.String(length=36), nullable=True),
        sa.Column("target_section_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="UNRESOLVED"),
        sa.Column("confidence_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("detection_method", sa.String(length=40), nullable=False, server_default="TEXT_ALIAS"),
        sa.Column("candidates_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("verified_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_revision_id"], ["manual_revisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_section_id"], ["manual_sections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_block_id"], ["manual_blocks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_manual_id"], ["manuals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_revision_id"], ["manual_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_section_id"], ["manual_sections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "source_revision_id", "occurrence_key", name="uq_documentation_reference_occurrence"),
        sa.CheckConstraint("confidence_percent >= 0 AND confidence_percent <= 100", name="documentation_reference_confidence_range"),
    )
    op.create_index("ix_documentation_references_source_page", "documentation_references", ["source_revision_id", "source_page_number"])
    op.create_index("ix_documentation_references_source_section", "documentation_references", ["source_section_id", "source_block_id"])
    op.create_index("ix_documentation_references_target_manual", "documentation_references", ["target_manual_id", "status"])
    op.create_index("ix_documentation_references_tenant_status", "documentation_references", ["tenant_id", "status"])
    op.create_index("ix_documentation_references_normalized_token", "documentation_references", ["tenant_id", "normalized_token"])

    op.create_table(
        "documentation_index_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("index_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("detected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resolved_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unresolved_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("broken_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "revision_id", name="uq_documentation_index_tenant_revision"),
    )
    op.create_index("ix_documentation_index_jobs_tenant_status", "documentation_index_jobs", ["tenant_id", "status"])
    op.create_index("ix_documentation_index_jobs_revision_checksum", "documentation_index_jobs", ["revision_id", "source_sha256"])

    op.create_table(
        "documentation_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("record_number", sa.String(length=128), nullable=False),
        sa.Column("template_manual_id", sa.String(length=36), nullable=False),
        sa.Column("template_revision_id", sa.String(length=36), nullable=False),
        sa.Column("source_reference_id", sa.String(length=36), nullable=True),
        sa.Column("record_series_node_id", sa.String(length=36), nullable=True),
        sa.Column("source_context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("artifact_storage_path", sa.Text(), nullable=False),
        sa.Column("artifact_filename", sa.String(length=255), nullable=False),
        sa.Column("artifact_mime_type", sa.String(length=128), nullable=False, server_default="application/pdf"),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="SUBMITTED"),
        sa.Column("retention_years", sa.Integer(), nullable=True),
        sa.Column("retention_disposition", sa.String(length=64), nullable=False, server_default="REVIEW_AT_EXPIRY"),
        sa.Column("submitted_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("reviewed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_manual_id"], ["manuals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["template_revision_id"], ["manual_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_reference_id"], ["documentation_references.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["record_series_node_id"], ["documentation_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "record_number", name="uq_documentation_record_tenant_number"),
    )
    op.create_index("ix_documentation_records_template_revision", "documentation_records", ["template_revision_id", "submitted_at"])
    op.create_index("ix_documentation_records_series_status", "documentation_records", ["record_series_node_id", "status"])
    op.create_index("ix_documentation_records_tenant_submitter", "documentation_records", ["tenant_id", "submitted_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_documentation_records_tenant_submitter", table_name="documentation_records")
    op.drop_index("ix_documentation_records_series_status", table_name="documentation_records")
    op.drop_index("ix_documentation_records_template_revision", table_name="documentation_records")
    op.drop_table("documentation_records")
    op.drop_index("ix_documentation_index_jobs_revision_checksum", table_name="documentation_index_jobs")
    op.drop_index("ix_documentation_index_jobs_tenant_status", table_name="documentation_index_jobs")
    op.drop_table("documentation_index_jobs")
    op.drop_index("ix_documentation_references_normalized_token", table_name="documentation_references")
    op.drop_index("ix_documentation_references_tenant_status", table_name="documentation_references")
    op.drop_index("ix_documentation_references_target_manual", table_name="documentation_references")
    op.drop_index("ix_documentation_references_source_section", table_name="documentation_references")
    op.drop_index("ix_documentation_references_source_page", table_name="documentation_references")
    op.drop_table("documentation_references")
    op.drop_index("ix_documentation_execution_record_series", table_name="documentation_execution_profiles")
    op.drop_index("ix_documentation_execution_tenant_type", table_name="documentation_execution_profiles")
    op.drop_table("documentation_execution_profiles")
    op.drop_index("ix_documentation_nodes_tenant_path", table_name="documentation_nodes")
    op.drop_index("ix_documentation_nodes_tenant_type", table_name="documentation_nodes")
    op.drop_index("ix_documentation_nodes_tenant_parent_order", table_name="documentation_nodes")
    op.drop_table("documentation_nodes")
