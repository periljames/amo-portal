"""Complete QMS closing ceremony, WebAuthn and public verification records.

Revision ID: quality_260817_live_audit_completion
Revises: quality_260816_archive_package_artifact
Create Date: 2026-08-17
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260817_live_audit_completion"
down_revision = "quality_260816_archive_package_artifact"
branch_labels = None
depends_on = None

CREDENTIAL_TABLE = "quality_audit_webauthn_credentials"
CHALLENGE_TABLE = "quality_audit_webauthn_challenges"
ACK_TABLE = "quality_audit_closing_acknowledgements"
VERIFY_TABLE = "quality_audit_verification_tokens"
SIGNATURE_TABLE = "quality_audit_signature_evidence"
ATTEMPT_TABLE = "quality_audit_signature_attempts"


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
    op.execute(sa.text(f'DROP POLICY IF EXISTS {table_name}_amo_isolation ON "{table_name}"'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" NO FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))


def _drop_check(table: str, name: str) -> None:
    if _is_postgresql():
        op.drop_constraint(name, table, type_="check")
    else:
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(name, type_="check")


def _create_check(table: str, name: str, expression: str) -> None:
    if _is_postgresql():
        op.create_check_constraint(name, table, expression)
    else:
        with op.batch_alter_table(table) as batch:
            batch.create_check_constraint(name, expression)


def upgrade() -> None:
    # Preserve password re-auth compatibility while making WebAuthn a first-class
    # signing ceremony. Existing immutable evidence rows remain untouched.
    _drop_check(ATTEMPT_TABLE, "ck_quality_audit_signature_attempt_method")
    _create_check(
        ATTEMPT_TABLE,
        "ck_quality_audit_signature_attempt_method",
        "method IN ('PASSWORD_REAUTH','WEBAUTHN')",
    )
    _drop_check(SIGNATURE_TABLE, "ck_quality_audit_signature_evidence_method")
    _create_check(
        SIGNATURE_TABLE,
        "ck_quality_audit_signature_evidence_method",
        "method IN ('PASSWORD_REAUTH','WEBAUTHN')",
    )
    _drop_check(SIGNATURE_TABLE, "ck_quality_audit_signature_evidence_purpose")
    _create_check(
        SIGNATURE_TABLE,
        "ck_quality_audit_signature_evidence_purpose",
        "purpose IN ('APPROVED_REPORT','ISSUED_REPORT')",
    )

    op.add_column(SIGNATURE_TABLE, sa.Column("credential_id_hash", sa.String(length=64), nullable=True))
    op.add_column(SIGNATURE_TABLE, sa.Column("webauthn_sign_count", sa.BigInteger(), nullable=True))
    op.add_column(SIGNATURE_TABLE, sa.Column("webauthn_origin", sa.String(length=512), nullable=True))
    op.add_column(SIGNATURE_TABLE, sa.Column("webauthn_rp_id", sa.String(length=255), nullable=True))
    op.add_column(SIGNATURE_TABLE, sa.Column("ceremony_sha256", sa.String(length=64), nullable=True))

    op.create_table(
        CREDENTIAL_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("owner_type", sa.String(length=24), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("external_identity_id", sa.String(length=36), nullable=True),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("transports", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("nickname", sa.String(length=80), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["external_identity_id"], ["quality_external_identities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "credential_id", name="uq_quality_audit_webauthn_credential"),
        sa.CheckConstraint("owner_type IN ('INTERNAL_USER','EXTERNAL_IDENTITY')", name="ck_quality_audit_webauthn_owner_type"),
        sa.CheckConstraint(
            "(owner_type = 'INTERNAL_USER' AND user_id IS NOT NULL AND external_identity_id IS NULL) OR "
            "(owner_type = 'EXTERNAL_IDENTITY' AND user_id IS NULL AND external_identity_id IS NOT NULL)",
            name="ck_quality_audit_webauthn_owner_identity",
        ),
    )
    op.create_index(
        "ix_quality_audit_webauthn_credentials_owner",
        CREDENTIAL_TABLE,
        ["amo_id", "owner_type", "user_id", "external_identity_id", "is_active"],
    )

    op.create_table(
        CHALLENGE_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("owner_type", sa.String(length=24), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("external_identity_id", sa.String(length=36), nullable=True),
        sa.Column("audit_id", sa.Uuid(), nullable=True),
        sa.Column("report_revision_id", sa.String(length=36), nullable=True),
        sa.Column("challenge_type", sa.String(length=32), nullable=False),
        sa.Column("challenge_b64", sa.String(length=256), nullable=False),
        sa.Column("challenge_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["external_identity_id"], ["quality_external_identities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["report_revision_id"], ["quality_audit_report_revisions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("owner_type IN ('INTERNAL_USER','EXTERNAL_IDENTITY')", name="ck_quality_audit_webauthn_challenge_owner_type"),
        sa.CheckConstraint("challenge_type IN ('REGISTRATION','REPORT_SIGNATURE','EXTERNAL_ASSERTION')", name="ck_quality_audit_webauthn_challenge_type"),
        sa.CheckConstraint(
            "(owner_type = 'INTERNAL_USER' AND user_id IS NOT NULL AND external_identity_id IS NULL) OR "
            "(owner_type = 'EXTERNAL_IDENTITY' AND user_id IS NULL AND external_identity_id IS NOT NULL)",
            name="ck_quality_audit_webauthn_challenge_identity",
        ),
    )
    op.create_index(
        "ix_quality_audit_webauthn_challenge_active",
        CHALLENGE_TABLE,
        ["amo_id", "owner_type", "user_id", "external_identity_id", "challenge_type", "expires_at"],
    )

    op.create_table(
        ACK_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("grant_id", sa.String(length=36), nullable=False),
        sa.Column("report_revision_id", sa.String(length=36), nullable=False),
        sa.Column("report_sha256", sa.String(length=64), nullable=False),
        sa.Column("acknowledgement_status", sa.String(length=32), nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_id"], ["quality_audit_participants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["grant_id"], ["quality_audit_access_grants.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["report_revision_id"], ["quality_audit_report_revisions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "acknowledgement_status IN ('ACKNOWLEDGED','COMMENTED','DECLINED_TO_ACKNOWLEDGE')",
            name="ck_quality_audit_closing_ack_status",
        ),
    )
    op.create_index(
        "ix_quality_audit_closing_ack_report",
        ACK_TABLE,
        ["amo_id", "audit_id", "report_revision_id", "created_at"],
    )

    op.create_table(
        VERIFY_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("report_revision_id", sa.String(length=36), nullable=False),
        sa.Column("signature_evidence_id", sa.String(length=36), nullable=True),
        sa.Column("assurance_artifact_id", sa.String(length=36), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["report_revision_id"], ["quality_audit_report_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["signature_evidence_id"], ["quality_audit_signature_evidence.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assurance_artifact_id"], ["quality_audit_assurance_artifacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_quality_audit_verification_token_hash"),
    )
    op.create_index(
        "ix_quality_audit_verification_token_artifact",
        VERIFY_TABLE,
        ["amo_id", "audit_id", "report_revision_id", "expires_at"],
    )

    for table_name in (CREDENTIAL_TABLE, CHALLENGE_TABLE, ACK_TABLE, VERIFY_TABLE):
        _enable_rls(table_name)

    if _is_postgresql():
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_quality_closing_ack_mutation()
            RETURNS trigger AS $$ BEGIN
                RAISE EXCEPTION '% is append-only/immutable', TG_TABLE_NAME;
            END; $$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text(f"""
            CREATE TRIGGER trg_{ACK_TABLE}_append_only
            BEFORE UPDATE OR DELETE ON {ACK_TABLE}
            FOR EACH ROW EXECUTE FUNCTION prevent_quality_closing_ack_mutation();
        """))


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{ACK_TABLE}_append_only ON {ACK_TABLE}"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_quality_closing_ack_mutation()"))

    for table_name in (VERIFY_TABLE, ACK_TABLE, CHALLENGE_TABLE, CREDENTIAL_TABLE):
        _disable_rls(table_name)

    op.drop_index("ix_quality_audit_verification_token_artifact", table_name=VERIFY_TABLE)
    op.drop_table(VERIFY_TABLE)
    op.drop_index("ix_quality_audit_closing_ack_report", table_name=ACK_TABLE)
    op.drop_table(ACK_TABLE)
    op.drop_index("ix_quality_audit_webauthn_challenge_active", table_name=CHALLENGE_TABLE)
    op.drop_table(CHALLENGE_TABLE)
    op.drop_index("ix_quality_audit_webauthn_credentials_owner", table_name=CREDENTIAL_TABLE)
    op.drop_table(CREDENTIAL_TABLE)

    op.drop_column(SIGNATURE_TABLE, "ceremony_sha256")
    op.drop_column(SIGNATURE_TABLE, "webauthn_rp_id")
    op.drop_column(SIGNATURE_TABLE, "webauthn_origin")
    op.drop_column(SIGNATURE_TABLE, "webauthn_sign_count")
    op.drop_column(SIGNATURE_TABLE, "credential_id_hash")

    _drop_check(SIGNATURE_TABLE, "ck_quality_audit_signature_evidence_purpose")
    _create_check(SIGNATURE_TABLE, "ck_quality_audit_signature_evidence_purpose", "purpose IN ('ISSUED_REPORT')")
    _drop_check(SIGNATURE_TABLE, "ck_quality_audit_signature_evidence_method")
    _create_check(SIGNATURE_TABLE, "ck_quality_audit_signature_evidence_method", "method IN ('PASSWORD_REAUTH')")
    _drop_check(ATTEMPT_TABLE, "ck_quality_audit_signature_attempt_method")
    _create_check(ATTEMPT_TABLE, "ck_quality_audit_signature_attempt_method", "method IN ('PASSWORD_REAUTH')")
