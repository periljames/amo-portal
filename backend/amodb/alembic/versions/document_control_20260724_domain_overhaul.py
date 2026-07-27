"""Create the canonical Document Control governance domain.

Revision ID: document_control_20260724_domain
Revises: rostering_20260724_governance
Create Date: 2026-07-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "document_control_20260724_domain"
down_revision = "rostering_20260724_governance"
branch_labels = None
depends_on = None


JSON_VALUE = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "document_control_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("document_class", sa.String(length=32), nullable=False, server_default="INTERNAL"),
        sa.Column("owner_department", sa.String(length=128), nullable=False, server_default="DOCUMENT_CONTROL"),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("language", sa.String(length=32), nullable=False, server_default="English"),
        sa.Column("criticality", sa.String(length=32), nullable=False, server_default="STANDARD"),
        sa.Column("regulated_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("restricted_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("requires_authority_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("acknowledgement_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("review_interval_months", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("next_review_due", sa.Date(), nullable=True),
        sa.Column("access_scope_json", JSON_VALUE, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("tags_json", JSON_VALUE, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata_json", JSON_VALUE, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("document_class IN ('INTERNAL','EXTERNAL','RECORD')", name="ck_document_control_profile_class"),
        sa.CheckConstraint("review_interval_months BETWEEN 1 AND 120", name="ck_document_control_profile_review_interval"),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "manual_id", name="uq_document_control_profile_tenant_manual"),
    )
    op.create_index("ix_document_control_profiles_tenant_class", "document_control_profiles", ["tenant_id", "document_class"], unique=False)
    op.create_index("ix_document_control_profiles_tenant_review", "document_control_profiles", ["tenant_id", "next_review_due"], unique=False)

    op.create_table(
        "document_change_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=True),
        sa.Column("source_module", sa.String(length=64), nullable=False, server_default="DOCUMENT_CONTROL"),
        sa.Column("source_entity_type", sa.String(length=64), nullable=True),
        sa.Column("source_entity_id", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="NORMAL"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="OPEN"),
        sa.Column("proposer_user_id", sa.String(length=36), nullable=True),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("impact_json", JSON_VALUE, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("training_impact_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("qms_blocking", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["proposer_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_change_requests_tenant_status", "document_change_requests", ["tenant_id", "status"], unique=False)
    op.create_index("ix_document_change_requests_manual_status", "document_change_requests", ["manual_id", "status"], unique=False)
    op.create_index("ix_document_change_requests_source", "document_change_requests", ["source_module", "source_entity_type", "source_entity_id"], unique=False)

    op.create_table(
        "document_workflow_instances",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("state", sa.String(length=48), nullable=False, server_default="DRAFT"),
        sa.Column("requires_authority", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("training_impact_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("training_readiness_status", sa.String(length=32), nullable=False, server_default="NOT_REQUIRED"),
        sa.Column("qms_readiness_status", sa.String(length=32), nullable=False, server_default="NOT_REQUIRED"),
        sa.Column("distribution_readiness_status", sa.String(length=32), nullable=False, server_default="NOT_REQUIRED"),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "revision_id", name="uq_document_workflow_tenant_revision"),
    )
    op.create_index("ix_document_workflows_tenant_state", "document_workflow_instances", ["tenant_id", "state"], unique=False)
    op.create_index("ix_document_workflows_manual_state", "document_workflow_instances", ["manual_id", "state"], unique=False)

    op.create_table(
        "document_workflow_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("step_code", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("from_state", sa.String(length=48), nullable=False),
        sa.Column("to_state", sa.String(length=48), nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("evidence_json", JSON_VALUE, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["document_workflow_instances.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_workflow_decisions_workflow", "document_workflow_decisions", ["workflow_id", "created_at"], unique=False)

    op.create_table(
        "document_authority_submissions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("workflow_id", sa.String(length=36), nullable=True),
        sa.Column("authority_name", sa.String(length=255), nullable=False),
        sa.Column("submission_reference", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("response_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_summary", sa.Text(), nullable=True),
        sa.Column("evidence_json", JSON_VALUE, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["document_workflow_instances.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_authority_tenant_status", "document_authority_submissions", ["tenant_id", "status"], unique=False)
    op.create_index("ix_document_authority_revision", "document_authority_submissions", ["revision_id", "created_at"], unique=False)

    op.create_table(
        "document_temporary_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("base_revision_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=True),
        sa.Column("tr_number", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("affected_sections_json", JSON_VALUE, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("filing_instructions", sa.Text(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("approval_status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("distribution_campaign_id", sa.String(length=36), nullable=True),
        sa.Column("incorporated_revision_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("expiry_date >= effective_date", name="ck_document_tr_effective_window"),
        sa.ForeignKeyConstraint(["base_revision_id"], ["manual_revisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["incorporated_revision_id"], ["manual_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "manual_id", "tr_number", name="uq_document_tr_tenant_manual_number"),
    )
    op.create_index("ix_document_tr_tenant_status_expiry", "document_temporary_revisions", ["tenant_id", "status", "expiry_date"], unique=False)

    op.create_table(
        "document_distribution_campaigns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("temporary_revision_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("audience_json", JSON_VALUE, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("acknowledgement_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issued_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("metadata_json", JSON_VALUE, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["issued_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["temporary_revision_id"], ["document_temporary_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_distribution_tenant_status", "document_distribution_campaigns", ["tenant_id", "status"], unique=False)
    op.create_index("ix_document_distribution_revision", "document_distribution_campaigns", ["revision_id", "issued_at"], unique=False)

    op.create_foreign_key(
        "fk_document_tr_distribution_campaign",
        "document_temporary_revisions",
        "document_distribution_campaigns",
        ["distribution_campaign_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "document_distribution_campaign_recipients",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("recipient_user_id", sa.String(length=36), nullable=True),
        sa.Column("copy_number", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminder_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exemption_reason", sa.Text(), nullable=True),
        sa.Column("evidence_json", JSON_VALUE, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.ForeignKeyConstraint(["campaign_id"], ["document_distribution_campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_distribution_recipient_campaign_status", "document_distribution_campaign_recipients", ["campaign_id", "status"], unique=False)
    op.create_index("ix_document_distribution_recipient_user_status", "document_distribution_campaign_recipients", ["recipient_user_id", "status"], unique=False)

    op.create_table(
        "document_review_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=True),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="SCHEDULED"),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("findings_json", JSON_VALUE, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("actions_json", JSON_VALUE, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_review_plans_tenant_status_due", "document_review_plans", ["tenant_id", "status", "due_at"], unique=False)
    op.create_index("ix_document_review_plans_manual", "document_review_plans", ["manual_id", "due_at"], unique=False)

    op.create_table(
        "document_controlled_copies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("copy_number", sa.String(length=64), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False, server_default="HARDCOPY"),
        sa.Column("holder_user_id", sa.String(length=36), nullable=True),
        sa.Column("holder_name", sa.String(length=255), nullable=True),
        sa.Column("location_text", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ISSUED"),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issued_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("due_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", JSON_VALUE, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(["holder_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["issued_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "manual_id", "copy_number", name="uq_document_copy_tenant_manual_number"),
    )
    op.create_index("ix_document_copies_tenant_status", "document_controlled_copies", ["tenant_id", "status"], unique=False)

    op.create_table(
        "document_controlled_copy_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("controlled_copy_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("from_holder_user_id", sa.String(length=36), nullable=True),
        sa.Column("to_holder_user_id", sa.String(length=36), nullable=True),
        sa.Column("from_location", sa.String(length=255), nullable=True),
        sa.Column("to_location", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("evidence_json", JSON_VALUE, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["controlled_copy_id"], ["document_controlled_copies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_holder_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_holder_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_copy_events_copy", "document_controlled_copy_events", ["controlled_copy_id", "created_at"], unique=False)

    op.create_table(
        "external_document_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=255), nullable=False),
        sa.Column("authority", sa.String(length=255), nullable=True),
        sa.Column("subscription_reference", sa.String(length=255), nullable=True),
        sa.Column("access_url", sa.Text(), nullable=True),
        sa.Column("update_method", sa.String(length=32), nullable=False, server_default="MANUAL_CHECK"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_check_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", JSON_VALUE, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "manual_id", name="uq_external_document_source_tenant_manual"),
    )
    op.create_index("ix_external_document_sources_tenant_status", "external_document_sources", ["tenant_id", "status"], unique=False)

    op.create_table(
        "external_revision_receipts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("revision_label", sa.String(length=128), nullable=False),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("currency_status", sa.String(length=32), nullable=False, server_default="UNVERIFIED"),
        sa.Column("applicability_status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("evidence_json", JSON_VALUE, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["received_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_id"], ["external_document_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_external_revision_receipts_source_received", "external_revision_receipts", ["source_id", "received_at"], unique=False)
    op.create_index("ix_external_revision_receipts_tenant_currency", "external_revision_receipts", ["tenant_id", "currency_status"], unique=False)

    op.create_table(
        "document_applicability_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=True),
        sa.Column("rule_type", sa.String(length=32), nullable=False, server_default="INCLUDE"),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=True),
        sa.Column("target_value", sa.String(length=255), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="MANUAL"),
        sa.Column("criteria_json", JSON_VALUE, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from", name="ck_document_applicability_effective_window"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_applicability_manual_status", "document_applicability_rules", ["manual_id", "status"], unique=False)
    op.create_index("ix_document_applicability_target", "document_applicability_rules", ["target_type", "target_id"], unique=False)

    op.create_table(
        "document_integration_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=True),
        sa.Column("change_request_id", sa.String(length=36), nullable=True),
        sa.Column("workflow_id", sa.String(length=36), nullable=True),
        sa.Column("source_module", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status_snapshot", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", JSON_VALUE, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["change_request_id"], ["document_change_requests.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["document_workflow_instances.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "manual_id",
            "source_module",
            "entity_type",
            "entity_id",
            "relation_type",
            name="uq_document_integration_link_identity",
        ),
    )
    op.create_index("ix_document_integration_links_manual", "document_integration_links", ["manual_id", "source_module"], unique=False)
    op.create_index("ix_document_integration_links_source", "document_integration_links", ["source_module", "entity_type", "entity_id"], unique=False)

    op.execute(
        sa.text(
            """
            INSERT INTO document_control_profiles (
                id, tenant_id, manual_id, document_class, owner_department,
                language, criticality, regulated_flag, restricted_flag,
                requires_authority_approval, acknowledgement_required,
                review_interval_months, access_scope_json, tags_json,
                metadata_json, version, created_at, updated_at
            )
            SELECT
                md5(random()::text || clock_timestamp()::text || m.id)::uuid::text,
                t.amo_id,
                m.id,
                'INTERNAL',
                COALESCE(NULLIF(upper(m.owner_role), ''), 'DOCUMENT_CONTROL'),
                'English',
                'STANDARD',
                false,
                false,
                COALESCE(r.requires_authority_approval_bool, false),
                true,
                24,
                '{}'::jsonb,
                '[]'::jsonb,
                jsonb_build_object('backfilled_from', 'manuals'),
                1,
                now(),
                now()
            FROM manuals m
            JOIN manual_tenants t ON t.id = m.tenant_id
            LEFT JOIN manual_revisions r ON r.id = m.current_published_rev_id
            ON CONFLICT (tenant_id, manual_id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_document_integration_links_source", table_name="document_integration_links")
    op.drop_index("ix_document_integration_links_manual", table_name="document_integration_links")
    op.drop_table("document_integration_links")
    op.drop_index("ix_document_applicability_target", table_name="document_applicability_rules")
    op.drop_index("ix_document_applicability_manual_status", table_name="document_applicability_rules")
    op.drop_table("document_applicability_rules")
    op.drop_index("ix_external_revision_receipts_tenant_currency", table_name="external_revision_receipts")
    op.drop_index("ix_external_revision_receipts_source_received", table_name="external_revision_receipts")
    op.drop_table("external_revision_receipts")
    op.drop_index("ix_external_document_sources_tenant_status", table_name="external_document_sources")
    op.drop_table("external_document_sources")
    op.drop_index("ix_document_copy_events_copy", table_name="document_controlled_copy_events")
    op.drop_table("document_controlled_copy_events")
    op.drop_index("ix_document_copies_tenant_status", table_name="document_controlled_copies")
    op.drop_table("document_controlled_copies")
    op.drop_index("ix_document_review_plans_manual", table_name="document_review_plans")
    op.drop_index("ix_document_review_plans_tenant_status_due", table_name="document_review_plans")
    op.drop_table("document_review_plans")
    op.drop_index("ix_document_distribution_recipient_user_status", table_name="document_distribution_campaign_recipients")
    op.drop_index("ix_document_distribution_recipient_campaign_status", table_name="document_distribution_campaign_recipients")
    op.drop_table("document_distribution_campaign_recipients")
    op.drop_constraint("fk_document_tr_distribution_campaign", "document_temporary_revisions", type_="foreignkey")
    op.drop_index("ix_document_distribution_revision", table_name="document_distribution_campaigns")
    op.drop_index("ix_document_distribution_tenant_status", table_name="document_distribution_campaigns")
    op.drop_table("document_distribution_campaigns")
    op.drop_index("ix_document_tr_tenant_status_expiry", table_name="document_temporary_revisions")
    op.drop_table("document_temporary_revisions")
    op.drop_index("ix_document_authority_revision", table_name="document_authority_submissions")
    op.drop_index("ix_document_authority_tenant_status", table_name="document_authority_submissions")
    op.drop_table("document_authority_submissions")
    op.drop_index("ix_document_workflow_decisions_workflow", table_name="document_workflow_decisions")
    op.drop_table("document_workflow_decisions")
    op.drop_index("ix_document_workflows_manual_state", table_name="document_workflow_instances")
    op.drop_index("ix_document_workflows_tenant_state", table_name="document_workflow_instances")
    op.drop_table("document_workflow_instances")
    op.drop_index("ix_document_change_requests_source", table_name="document_change_requests")
    op.drop_index("ix_document_change_requests_manual_status", table_name="document_change_requests")
    op.drop_index("ix_document_change_requests_tenant_status", table_name="document_change_requests")
    op.drop_table("document_change_requests")
    op.drop_index("ix_document_control_profiles_tenant_review", table_name="document_control_profiles")
    op.drop_index("ix_document_control_profiles_tenant_class", table_name="document_control_profiles")
    op.drop_table("document_control_profiles")
