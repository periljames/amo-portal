"""Phase 8: tenant-owned provider alert policy and durable dispatch ledger.

This outbox is NOT a notification centre: dispatched alerts are projected into
the existing QMS and partner notification registers and existing email service.
"""
from alembic import op
import sqlalchemy as sa

revision = "extprov_261018_alerts"
down_revision = "extprov_261017_main_merge"
branch_labels = None
depends_on = None

TABLES = ("external_provider_alert_policies", "external_provider_alert_jobs", "external_provider_alert_preferences")


def upgrade():
    op.create_table(
        "external_provider_alert_policies",
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("lead_days_json", sa.JSON(), nullable=False),
        sa.Column("escalation_days_json", sa.JSON(), nullable=False),
        sa.Column("routes_json", sa.JSON(), nullable=False),
        sa.Column("channels_json", sa.JSON(), nullable=False),
        sa.Column("templates_json", sa.JSON(), nullable=False),
        sa.Column("digest_json", sa.JSON(), nullable=False),
        sa.Column("quiet_hours_json", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("revision >= 1", name="ck_ext_alert_policy_revision"),
    )
    op.create_table(
        "external_provider_alert_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("event_key", sa.String(80), nullable=False),
        sa.Column("source_kind", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(80), nullable=False),
        sa.Column("source_stamp", sa.String(128), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("recipient_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("recipient_identity_id", sa.String(36), sa.ForeignKey("external_identities.id", ondelete="SET NULL")),
        sa.Column("recipient_provider_id", sa.String(36), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("in_app_id", sa.String(36), nullable=True),
        sa.Column("email_log_id", sa.String(36), sa.ForeignKey("email_logs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("amo_id", "fingerprint", name="uq_external_provider_alert_fingerprint"),
        sa.CheckConstraint("status IN ('PENDING','RETRY','DELIVERED','CANCELLED','FAILED')",
                           name="ck_external_provider_alert_status"),
        sa.CheckConstraint("attempts >= 0", name="ck_external_provider_alert_attempts"),
        sa.CheckConstraint("(recipient_user_id IS NOT NULL) <> (recipient_identity_id IS NOT NULL)",
                           name="ck_external_provider_alert_recipient"),
    )
    op.create_index("ix_ext_alert_jobs_due", "external_provider_alert_jobs",
                    ["status", "next_attempt_at", "due_at"])
    op.create_index("ix_ext_alert_jobs_tenant_source", "external_provider_alert_jobs",
                    ["amo_id", "source_kind", "source_id", "status"])
    op.create_index("ix_ext_alert_jobs_tenant_recipient", "external_provider_alert_jobs",
                    ["amo_id", "recipient_user_id", "created_at"])
    op.create_table(
        "external_provider_alert_preferences",
        sa.Column("amo_id", sa.String(36), nullable=False),
        sa.Column("tenant_provider_id", sa.String(36), nullable=False),
        sa.Column("identity_id", sa.String(36), sa.ForeignKey("external_identities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("in_app_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("digest_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("amo_id", "tenant_provider_id", "identity_id", name="pk_ext_alert_preferences"),
        sa.ForeignKeyConstraint(["amo_id", "tenant_provider_id"],
            ["external_tenant_providers.amo_id", "external_tenant_providers.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("revision >= 1", name="ck_ext_alert_pref_revision"),
    )
    if op.get_bind().dialect.name == "postgresql":
        for table in TABLES:
            op.execute(sa.text('ALTER TABLE "' + table + '" ENABLE ROW LEVEL SECURITY'))
            op.execute(sa.text('ALTER TABLE "' + table + '" FORCE ROW LEVEL SECURITY'))
            guard = (" AND (tenant_provider_id = NULLIF(current_setting('app.external_provider_id', true), '') "
                     "OR current_setting('app.external_provider_id', true) = '__INTERNAL_QUALITY_REVIEW__')"
                     if table == "external_provider_alert_preferences" else "")
            condition = "amo_id = NULLIF(current_setting('app.tenant_id', true), '')" + guard
            op.execute(sa.text('CREATE POLICY "' + table + '_tenant" ON "' + table + '" '
                               'USING (' + condition + ') WITH CHECK (' + condition + ')'))


def downgrade():
    for table in reversed(TABLES):
        op.drop_table(table)
