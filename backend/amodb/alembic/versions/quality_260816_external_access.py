"""Add governed external audit participants and released-data access.

Revision ID: quality_260816_external_access
Revises: workforce_260815_hire_dates
Create Date: 2026-08-16
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260816_external_access"
down_revision = "workforce_260815_hire_dates"
branch_labels = None
depends_on = None


TABLES = (
    "quality_external_identities",
    "quality_audit_participants",
    "quality_audit_access_grants",
    "quality_audit_access_events",
    "quality_audit_finding_release_events",
)


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _enable_rls(table_name: str) -> None:
    if not _is_postgresql():
        return
    policy = f"{table_name}_amo_isolation"
    op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f"""
        CREATE POLICY {policy}
        ON "{table_name}"
        USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
        WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
    """))


def _disable_rls(table_name: str) -> None:
    if not _is_postgresql():
        return
    policy = f"{table_name}_amo_isolation"
    op.execute(sa.text(f'DROP POLICY IF EXISTS {policy} ON "{table_name}"'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" NO FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))


def upgrade() -> None:
    op.create_table(
        "quality_external_identities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("organisation", sa.String(length=255), nullable=True),
        sa.Column("identity_status", sa.String(length=16), server_default="ACTIVE", nullable=False),
        sa.Column("assurance_level", sa.String(length=24), server_default="EMAIL_LINK", nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("identity_status IN ('ACTIVE','REVOKED')", name="ck_quality_external_identity_status"),
        sa.CheckConstraint("assurance_level IN ('EMAIL_LINK','MFA','PASSKEY')", name="ck_quality_external_identity_assurance"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "email", name="uq_quality_external_identity_email"),
    )
    op.create_index("ix_quality_external_identity_tenant_status", "quality_external_identities", ["amo_id", "identity_status", "email"])

    op.create_table(
        "quality_audit_participants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("participant_type", sa.String(length=24), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("external_identity_id", sa.String(length=36), nullable=True),
        sa.Column("role", sa.String(length=48), nullable=False),
        sa.Column("permissions_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="INVITED", nullable=False),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("participant_type IN ('INTERNAL_USER','EXTERNAL_AUDITOR','AUDITEE_GUEST')", name="ck_quality_audit_participant_type"),
        sa.CheckConstraint("status IN ('INVITED','ACTIVE','REVOKED','EXPIRED')", name="ck_quality_audit_participant_status"),
        sa.CheckConstraint("(participant_type = 'INTERNAL_USER' AND user_id IS NOT NULL AND external_identity_id IS NULL) OR (participant_type <> 'INTERNAL_USER' AND user_id IS NULL AND external_identity_id IS NOT NULL)", name="ck_quality_audit_participant_identity"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["external_identity_id"], ["quality_external_identities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "audit_id", "external_identity_id", "role", name="uq_quality_audit_external_participant_role"),
    )
    op.create_index("ix_quality_audit_participants_audit", "quality_audit_participants", ["amo_id", "audit_id", "status"])
    op.create_index("ix_quality_audit_participants_external", "quality_audit_participants", ["amo_id", "external_identity_id", "status"])

    op.create_table(
        "quality_audit_access_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("scope_json", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_id"], ["quality_audit_participants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_quality_audit_access_grant_token_hash"),
    )
    op.create_index("ix_quality_audit_access_grant_audit", "quality_audit_access_grants", ["amo_id", "audit_id", "expires_at"])
    op.create_index("ix_quality_audit_access_grant_participant", "quality_audit_access_grants", ["amo_id", "participant_id", "revoked_at"])

    op.create_table(
        "quality_audit_access_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("grant_id", sa.String(length=36), nullable=False),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("event_type IN ('CREATED','EXCHANGED','READ','ACKNOWLEDGED','REVOKED','EXPIRED')", name="ck_quality_audit_access_event_type"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["grant_id"], ["quality_audit_access_grants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_id"], ["quality_audit_participants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_audit_access_events_audit", "quality_audit_access_events", ["amo_id", "audit_id", "created_at"])

    op.create_table(
        "quality_audit_finding_release_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("include_objective_evidence", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("released_evidence_refs", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("action IN ('RELEASED','WITHDRAWN')", name="ck_quality_audit_finding_release_action"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["finding_id"], ["qms_audit_findings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_audit_finding_release_latest", "quality_audit_finding_release_events", ["amo_id", "audit_id", "finding_id", "created_at"])

    for table_name in TABLES:
        _enable_rls(table_name)

    if _is_postgresql():
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_quality_external_access_events_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'Quality external access/release history is append-only';
            END;
            $$ LANGUAGE plpgsql;
        """))
        for table_name in ("quality_audit_access_events", "quality_audit_finding_release_events"):
            op.execute(sa.text(f"""
                CREATE TRIGGER trg_{table_name}_append_only
                BEFORE UPDATE OR DELETE ON {table_name}
                FOR EACH ROW EXECUTE FUNCTION prevent_quality_external_access_events_mutation();
            """))


def downgrade() -> None:
    if _is_postgresql():
        for table_name in ("quality_audit_finding_release_events", "quality_audit_access_events"):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{table_name}_append_only ON {table_name}"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_quality_external_access_events_mutation()"))
    for table_name in reversed(TABLES):
        _disable_rls(table_name)
    op.drop_index("ix_quality_audit_finding_release_latest", table_name="quality_audit_finding_release_events")
    op.drop_table("quality_audit_finding_release_events")
    op.drop_index("ix_quality_audit_access_events_audit", table_name="quality_audit_access_events")
    op.drop_table("quality_audit_access_events")
    op.drop_index("ix_quality_audit_access_grant_participant", table_name="quality_audit_access_grants")
    op.drop_index("ix_quality_audit_access_grant_audit", table_name="quality_audit_access_grants")
    op.drop_table("quality_audit_access_grants")
    op.drop_index("ix_quality_audit_participants_external", table_name="quality_audit_participants")
    op.drop_index("ix_quality_audit_participants_audit", table_name="quality_audit_participants")
    op.drop_table("quality_audit_participants")
    op.drop_index("ix_quality_external_identity_tenant_status", table_name="quality_external_identities")
    op.drop_table("quality_external_identities")
