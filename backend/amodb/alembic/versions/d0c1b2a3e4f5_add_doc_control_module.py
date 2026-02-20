"""add doc control module tables

Revision ID: d0c1b2a3e4f5
Revises: 463febfffd67
Create Date: 2026-02-20
"""

from alembic import op
import sqlalchemy as sa


revision = "d0c1b2a3e4f5"
down_revision = "463febfffd67"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "doc_control_settings",
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("default_retention_years", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("default_review_interval_months", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("regulated_workflow_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("default_ack_required", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    def _create(name, *cols):
        op.create_table(name, *cols)

    _create(
        "doc_control_documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doc_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("doc_type", sa.String(length=64), nullable=False),
        sa.Column("owner_department", sa.String(length=128), nullable=False),
        sa.Column("issue_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("revision_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.String(length=32), nullable=False, server_default="1.0"),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="Draft"),
        sa.Column("regulated_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("authority_name", sa.String(length=255), nullable=True),
        sa.Column("authority_approval_status", sa.String(length=32), nullable=True),
        sa.Column("authority_evidence_asset_id", sa.String(length=255), nullable=True),
        sa.Column("restricted_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("access_policy_id", sa.String(length=64), nullable=True),
        sa.Column("current_asset_id", sa.String(length=255), nullable=True),
        sa.Column("physical_locations", sa.JSON(), nullable=False),
        sa.Column("next_review_due", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "doc_id", name="uq_doc_control_documents_tenant_doc_id"),
    )
    op.create_index("ix_doc_control_documents_tenant_id", "doc_control_documents", ["tenant_id"])

    for name, pk in [
        ("doc_control_drafts", "draft_id"),
        ("doc_control_change_proposals", "proposal_id"),
        ("doc_control_revision_packages", "package_id"),
        ("doc_control_leps", "lep_id"),
        ("doc_control_temporary_revisions", "tr_id"),
        ("doc_control_distribution_list_entries", "entry_id"),
        ("doc_control_distribution_events", "event_id"),
        ("doc_control_distribution_recipients", "id"),
        ("doc_control_acknowledgements", "ack_id"),
        ("doc_control_archive_records", "archive_id"),
        ("doc_control_reviews", "review_id"),
        ("doc_control_audit_events", "id"),
    ]:
        cols = [
            sa.Column(pk, sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        ]
        if name == "doc_control_drafts":
            cols += [sa.Column("doc_id", sa.String(length=64), nullable=False), sa.Column("metadata_snapshot_json", sa.JSON(), nullable=False), sa.Column("asset_id", sa.String(length=255)), sa.Column("status", sa.String(length=32), nullable=False), sa.Column("authority_evidence_asset_id", sa.String(length=255)), sa.Column("created_at", sa.DateTime(), nullable=False)]
        elif name == "doc_control_change_proposals":
            cols += [sa.Column("doc_id", sa.String(length=64), nullable=False), sa.Column("proposer_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("description", sa.Text(), nullable=False), sa.Column("attachment_asset_ids", sa.JSON(), nullable=False), sa.Column("dept_head_decision", sa.String(length=64)), sa.Column("quality_decision", sa.String(length=64)), sa.Column("accountable_manager_decision", sa.String(length=64)), sa.Column("authority_status", sa.String(length=64)), sa.Column("authority_evidence_asset_ids", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False)]
        elif name == "doc_control_revision_packages":
            cols += [sa.Column("doc_id", sa.String(length=64), nullable=False), sa.Column("revision_no", sa.Integer(), nullable=False), sa.Column("reference_serial_no", sa.String(length=128), nullable=False), sa.Column("change_summary", sa.Text(), nullable=False), sa.Column("transmittal_notice", sa.Text(), nullable=False), sa.Column("filing_instructions", sa.Text(), nullable=False), sa.Column("replacement_pages", sa.JSON(), nullable=False), sa.Column("effective_date", sa.Date(), nullable=False), sa.Column("internal_approval_status", sa.String(length=64), nullable=False), sa.Column("authority_status", sa.String(length=64)), sa.Column("authority_evidence_asset_id", sa.String(length=255)), sa.Column("published_at", sa.DateTime()), sa.Column("published_revision_asset_id", sa.String(length=255))]
        elif name == "doc_control_leps":
            cols += [sa.Column("doc_id", sa.String(length=64), nullable=False), sa.Column("revision_no", sa.Integer(), nullable=False), sa.Column("lep_date", sa.Date(), nullable=False), sa.Column("rows", sa.JSON(), nullable=False), sa.Column("export_asset_id", sa.String(length=255))]
        elif name == "doc_control_temporary_revisions":
            cols += [sa.Column("doc_id", sa.String(length=64), nullable=False), sa.Column("tr_no", sa.String(length=64), nullable=False), sa.Column("effective_date", sa.Date(), nullable=False), sa.Column("expiry_date", sa.Date(), nullable=False), sa.Column("reason", sa.Text(), nullable=False), sa.Column("filing_instructions", sa.Text(), nullable=False), sa.Column("updated_lep_asset_id", sa.String(length=255)), sa.Column("tr_pages", sa.JSON(), nullable=False), sa.Column("status", sa.String(length=32), nullable=False), sa.Column("incorporated_revision_package_id", sa.String(length=36))]
        elif name == "doc_control_distribution_list_entries":
            cols += [sa.Column("doc_id", sa.String(length=64), nullable=False), sa.Column("copy_no", sa.String(length=64), nullable=False), sa.Column("holder_name", sa.String(length=255), nullable=False), sa.Column("location_text", sa.String(length=255), nullable=False), sa.Column("format", sa.String(length=16), nullable=False)]
        elif name == "doc_control_distribution_events":
            cols += [sa.Column("doc_id", sa.String(length=64), nullable=False), sa.Column("source_type", sa.String(length=32), nullable=False), sa.Column("source_id", sa.String(length=36), nullable=False), sa.Column("method", sa.String(length=32), nullable=False), sa.Column("sent_at", sa.DateTime()), sa.Column("acknowledgement_required", sa.Boolean(), nullable=False), sa.Column("status", sa.String(length=16), nullable=False)]
        elif name == "doc_control_distribution_recipients":
            cols += [sa.Column("event_id", sa.String(length=36), sa.ForeignKey("doc_control_distribution_events.event_id", ondelete="CASCADE"), nullable=False), sa.Column("recipient_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("copy_no", sa.String(length=64))]
        elif name == "doc_control_acknowledgements":
            cols += [sa.Column("event_id", sa.String(length=36), sa.ForeignKey("doc_control_distribution_events.event_id", ondelete="CASCADE"), nullable=False), sa.Column("recipient_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("copy_no", sa.String(length=64)), sa.Column("acknowledged_at", sa.DateTime(), nullable=False), sa.Column("method", sa.String(length=32), nullable=False), sa.Column("evidence_asset_id", sa.String(length=255))]
        elif name == "doc_control_archive_records":
            cols += [sa.Column("doc_id", sa.String(length=64), nullable=False), sa.Column("revision_no", sa.Integer(), nullable=False), sa.Column("archived_at", sa.DateTime(), nullable=False), sa.Column("archival_marking", sa.String(length=255), nullable=False), sa.Column("retention_until", sa.Date(), nullable=False), sa.Column("disposal_status", sa.String(length=32), nullable=False), sa.Column("outsourced_vendor", sa.String(length=255)), sa.Column("evidence_asset_id", sa.String(length=255))]
        elif name == "doc_control_reviews":
            cols += [sa.Column("doc_id", sa.String(length=64), nullable=False), sa.Column("due_date", sa.Date(), nullable=False), sa.Column("completed_at", sa.DateTime()), sa.Column("outcome", sa.String(length=32)), sa.Column("actions", sa.JSON(), nullable=False)]
        elif name == "doc_control_audit_events":
            cols += [sa.Column("object_type", sa.String(length=64), nullable=False), sa.Column("object_id", sa.String(length=64), nullable=False), sa.Column("action", sa.String(length=32), nullable=False), sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL")), sa.Column("timestamp", sa.DateTime(), nullable=False), sa.Column("diff_json", sa.JSON(), nullable=False)]
        op.create_table(name, *cols)
        op.create_index(f"ix_{name}_tenant_id", name, ["tenant_id"])


def downgrade() -> None:
    for name in [
        "doc_control_audit_events",
        "doc_control_reviews",
        "doc_control_archive_records",
        "doc_control_acknowledgements",
        "doc_control_distribution_recipients",
        "doc_control_distribution_events",
        "doc_control_distribution_list_entries",
        "doc_control_temporary_revisions",
        "doc_control_leps",
        "doc_control_revision_packages",
        "doc_control_change_proposals",
        "doc_control_drafts",
        "doc_control_documents",
        "doc_control_settings",
    ]:
        try:
            op.drop_index(f"ix_{name}_tenant_id", table_name=name)
        except Exception:
            pass
        op.drop_table(name)
