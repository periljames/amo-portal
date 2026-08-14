"""Tenant-configurable training setup and durable automation ledger.

Revision ID: training_20260813_frontend_operability
Revises: training_20260813_expiry_plan
Create Date: 2026-08-13
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "training_20260813_frontend_operability"
down_revision = "training_20260813_expiry_plan"
branch_labels = None
depends_on = None


SETTINGS_COLUMNS = [
    sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
    sa.Column("plan_automation_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column("plan_run_day", sa.Integer(), nullable=False, server_default="1"),
    sa.Column("plan_run_hour", sa.Integer(), nullable=False, server_default="2"),
    sa.Column("notification_policy", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    sa.Column("certificate_number_prefix", sa.String(length=32), nullable=False, server_default="TRN"),
    sa.Column("certificate_template_reference", sa.String(length=128), nullable=True),
    sa.Column("certificate_signatories", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    sa.Column("certificate_public_privacy_text", sa.Text(), nullable=True),
    sa.Column("default_committee_positions", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    sa.Column("setup_status", sa.String(length=24), nullable=False, server_default="DRAFT"),
    sa.Column("configuration_revision_no", sa.Integer(), nullable=False, server_default="0"),
]


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _settings_columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("training_operating_settings")}


def upgrade() -> None:
    existing = _settings_columns()
    for column in SETTINGS_COLUMNS:
        if column.name not in existing:
            op.add_column("training_operating_settings", column)

    tables = _table_names()
    if "training_configuration_revisions" not in tables:
        op.create_table(
            "training_configuration_revisions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("revision_no", sa.Integer(), nullable=False),
            sa.Column("snapshot", sa.JSON(), nullable=False),
            sa.Column("change_summary", sa.Text(), nullable=True),
            sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("amo_id", "revision_no", name="uq_training_configuration_revision"),
        )
        op.create_index("ix_training_configuration_revision_amo_created", "training_configuration_revisions", ["amo_id", "created_at"])

    if "training_reference_resources" not in tables:
        op.create_table(
            "training_reference_resources",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("resource_type", sa.String(length=24), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("contact_name", sa.String(length=255), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("phone", sa.String(length=64), nullable=True),
            sa.Column("address", sa.Text(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("amo_id", "resource_type", "code", name="uq_training_reference_resource_code"),
        )
        op.create_index("ix_training_reference_resource_active", "training_reference_resources", ["amo_id", "resource_type", "active"])

    if "training_controlled_form_templates" not in tables:
        op.create_table(
            "training_controlled_form_templates",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("workflow", sa.String(length=64), nullable=False),
            sa.Column("revision_no", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="DRAFT"),
            sa.Column("dms_document_id", sa.String(length=36), nullable=True),
            sa.Column("dms_revision_id", sa.String(length=36), nullable=True),
            sa.Column("schema_json", sa.JSON(), nullable=False),
            sa.Column("retention_rule", sa.String(length=255), nullable=True),
            sa.Column("effective_from", sa.Date(), nullable=True),
            sa.Column("effective_to", sa.Date(), nullable=True),
            sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("approved_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("amo_id", "code", "revision_no", name="uq_training_controlled_form_revision"),
        )
        op.create_index("ix_training_controlled_form_active", "training_controlled_form_templates", ["amo_id", "workflow", "status"])

    if "training_automation_runs" not in tables:
        op.create_table(
            "training_automation_runs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("idempotency_key", sa.String(length=128), nullable=False),
            sa.Column("period_year", sa.Integer(), nullable=False),
            sa.Column("period_month", sa.Integer(), nullable=False),
            sa.Column("trigger", sa.String(length=24), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("plan_id", sa.String(length=36), sa.ForeignKey("training_plans.id", ondelete="SET NULL"), nullable=True),
            sa.Column("summary", sa.JSON(), nullable=False),
            sa.Column("error_text", sa.Text(), nullable=True),
            sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("amo_id", "idempotency_key", name="uq_training_automation_run_key"),
        )
        op.create_index("ix_training_automation_run_tenant_period", "training_automation_runs", ["amo_id", "period_year", "period_month"])


def downgrade() -> None:
    for table_name in (
        "training_automation_runs",
        "training_controlled_form_templates",
        "training_reference_resources",
        "training_configuration_revisions",
    ):
        if table_name in _table_names():
            op.drop_table(table_name)
    existing = _settings_columns()
    for column in reversed(SETTINGS_COLUMNS):
        if column.name in existing:
            op.drop_column("training_operating_settings", column.name)
