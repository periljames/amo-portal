"""Add controlled roster governance, aliases and calendar subscriptions.

Revision ID: rostering_control_260812
Revises: rostering_codes_260811
Create Date: 2026-08-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "rostering_control_260812"
down_revision = "rostering_codes_260811"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "roster_shift_template_policies",
        sa.Column("duty_semantic", sa.String(length=16), nullable=False, server_default="DUTY"),
    )
    op.add_column(
        "roster_shift_template_policies",
        sa.Column("verification_status", sa.String(length=24), nullable=False, server_default="UNRESOLVED"),
    )
    op.create_index(
        "ix_roster_shift_policy_verification",
        "roster_shift_template_policies",
        ["amo_id", "verification_status"],
        unique=False,
    )
    op.execute(
        """
        UPDATE roster_shift_template_policies
        SET verification_status = 'CONFIRMED'
        WHERE shift_template_id IN (
            SELECT id FROM shift_templates
            WHERE UPPER(code) IN ('DY','AM','PM','XD','WD','NT','F1','F2','FD','SB','TR','OF','RD')
        )
        """
    )
    op.execute(
        """
        UPDATE roster_shift_template_policies
        SET duty_semantic = CASE
            WHEN shift_template_id IN (SELECT id FROM shift_templates WHERE UPPER(code) = 'SB') THEN 'STANDBY'
            WHEN shift_template_id IN (SELECT id FROM shift_templates WHERE UPPER(code) = 'TR') THEN 'TRAINING'
            WHEN shift_template_id IN (SELECT id FROM shift_templates WHERE UPPER(code) = 'OF') THEN 'OFF'
            WHEN shift_template_id IN (SELECT id FROM shift_templates WHERE UPPER(code) = 'RD') THEN 'REST'
            ELSE 'DUTY'
        END
        """
    )

    op.create_table(
        "roster_shift_aliases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("alias", sa.String(length=64), nullable=False),
        sa.Column("shift_template_id", sa.String(length=36), nullable=False),
        sa.Column("context_label", sa.String(length=128), nullable=True),
        sa.Column("aircraft_registration", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shift_template_id"], ["shift_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "alias", name="uq_roster_shift_alias_amo_alias"),
    )
    op.create_index("ix_roster_shift_alias_amo_template", "roster_shift_aliases", ["amo_id", "shift_template_id"], unique=False)
    op.create_index(op.f("ix_roster_shift_aliases_amo_id"), "roster_shift_aliases", ["amo_id"], unique=False)
    op.create_index(op.f("ix_roster_shift_aliases_shift_template_id"), "roster_shift_aliases", ["shift_template_id"], unique=False)

    op.create_table(
        "roster_controlled_document_settings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("form_number", sa.String(length=64), nullable=False, server_default="ROSTER"),
        sa.Column("revision_label", sa.String(length=64), nullable=True),
        sa.Column("revision_date", sa.Date(), nullable=True),
        sa.Column("footer_note", sa.Text(), nullable=True),
        sa.Column("prepared_by_label", sa.String(length=64), nullable=False, server_default="Prepared by"),
        sa.Column("approved_by_label", sa.String(length=64), nullable=False, server_default="Approved by"),
        sa.Column("page_size", sa.String(length=8), nullable=False, server_default="A3"),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", name="uq_roster_controlled_settings_amo"),
    )
    op.create_index(op.f("ix_roster_controlled_document_settings_amo_id"), "roster_controlled_document_settings", ["amo_id"], unique=False)

    op.create_table(
        "roster_publication_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["version_id"], ["roster_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", name="uq_roster_publication_snapshot_version"),
    )
    op.create_index("ix_roster_publication_snapshot_amo_version", "roster_publication_snapshots", ["amo_id", "version_id"], unique=False)
    op.create_index(op.f("ix_roster_publication_snapshots_amo_id"), "roster_publication_snapshots", ["amo_id"], unique=False)
    op.create_index(op.f("ix_roster_publication_snapshots_version_id"), "roster_publication_snapshots", ["version_id"], unique=False)
    op.create_index(op.f("ix_roster_publication_snapshots_snapshot_hash"), "roster_publication_snapshots", ["snapshot_hash"], unique=False)

    op.create_table(
        "roster_calendar_subscriptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "user_id", name="uq_roster_calendar_subscription_user"),
        sa.UniqueConstraint("token_hash", name="uq_roster_calendar_subscription_token_hash"),
    )
    op.create_index("ix_roster_calendar_subscription_active", "roster_calendar_subscriptions", ["amo_id", "user_id", "revoked_at"], unique=False)
    op.create_index(op.f("ix_roster_calendar_subscriptions_amo_id"), "roster_calendar_subscriptions", ["amo_id"], unique=False)
    op.create_index(op.f("ix_roster_calendar_subscriptions_user_id"), "roster_calendar_subscriptions", ["user_id"], unique=False)
    op.create_index(op.f("ix_roster_calendar_subscriptions_token_hash"), "roster_calendar_subscriptions", ["token_hash"], unique=False)
    op.create_index(op.f("ix_roster_calendar_subscriptions_revoked_at"), "roster_calendar_subscriptions", ["revoked_at"], unique=False)

    op.create_table(
        "roster_assignment_lineages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("assignment_id", sa.String(length=36), nullable=False),
        sa.Column("source_assignment_id", sa.String(length=36), nullable=True),
        sa.Column("lineage_key", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assignment_id"], ["roster_assignments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_assignment_id"], ["roster_assignments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assignment_id", name="uq_roster_assignment_lineage_assignment"),
    )
    op.create_index("ix_roster_assignment_lineage_amo_key", "roster_assignment_lineages", ["amo_id", "lineage_key"], unique=False)
    op.create_index(op.f("ix_roster_assignment_lineages_amo_id"), "roster_assignment_lineages", ["amo_id"], unique=False)
    op.create_index(op.f("ix_roster_assignment_lineages_assignment_id"), "roster_assignment_lineages", ["assignment_id"], unique=False)
    op.create_index(op.f("ix_roster_assignment_lineages_source_assignment_id"), "roster_assignment_lineages", ["source_assignment_id"], unique=False)
    op.create_index(op.f("ix_roster_assignment_lineages_lineage_key"), "roster_assignment_lineages", ["lineage_key"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_roster_assignment_lineages_lineage_key"), table_name="roster_assignment_lineages")
    op.drop_index(op.f("ix_roster_assignment_lineages_source_assignment_id"), table_name="roster_assignment_lineages")
    op.drop_index(op.f("ix_roster_assignment_lineages_assignment_id"), table_name="roster_assignment_lineages")
    op.drop_index(op.f("ix_roster_assignment_lineages_amo_id"), table_name="roster_assignment_lineages")
    op.drop_index("ix_roster_assignment_lineage_amo_key", table_name="roster_assignment_lineages")
    op.drop_table("roster_assignment_lineages")

    op.drop_index(op.f("ix_roster_calendar_subscriptions_revoked_at"), table_name="roster_calendar_subscriptions")
    op.drop_index(op.f("ix_roster_calendar_subscriptions_token_hash"), table_name="roster_calendar_subscriptions")
    op.drop_index(op.f("ix_roster_calendar_subscriptions_user_id"), table_name="roster_calendar_subscriptions")
    op.drop_index(op.f("ix_roster_calendar_subscriptions_amo_id"), table_name="roster_calendar_subscriptions")
    op.drop_index("ix_roster_calendar_subscription_active", table_name="roster_calendar_subscriptions")
    op.drop_table("roster_calendar_subscriptions")

    op.drop_index(op.f("ix_roster_publication_snapshots_snapshot_hash"), table_name="roster_publication_snapshots")
    op.drop_index(op.f("ix_roster_publication_snapshots_version_id"), table_name="roster_publication_snapshots")
    op.drop_index(op.f("ix_roster_publication_snapshots_amo_id"), table_name="roster_publication_snapshots")
    op.drop_index("ix_roster_publication_snapshot_amo_version", table_name="roster_publication_snapshots")
    op.drop_table("roster_publication_snapshots")

    op.drop_index(op.f("ix_roster_controlled_document_settings_amo_id"), table_name="roster_controlled_document_settings")
    op.drop_table("roster_controlled_document_settings")

    op.drop_index(op.f("ix_roster_shift_aliases_shift_template_id"), table_name="roster_shift_aliases")
    op.drop_index(op.f("ix_roster_shift_aliases_amo_id"), table_name="roster_shift_aliases")
    op.drop_index("ix_roster_shift_alias_amo_template", table_name="roster_shift_aliases")
    op.drop_table("roster_shift_aliases")

    op.drop_index("ix_roster_shift_policy_verification", table_name="roster_shift_template_policies")
    op.drop_column("roster_shift_template_policies", "verification_status")
    op.drop_column("roster_shift_template_policies", "duty_semantic")
