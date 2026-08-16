"""Add closing output policy, signature evidence and supplementary artifacts.

Revision ID: quality_260816_closing_assurance
Revises: quality_260816_external_finding_drafts
Create Date: 2026-08-16
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260816_closing_assurance"
down_revision = "quality_260816_external_finding_drafts"
branch_labels = None
depends_on = None

POLICY_TABLE = "quality_audit_output_policy_revisions"
ATTEMPT_TABLE = "quality_audit_signature_attempts"
SIGNATURE_TABLE = "quality_audit_signature_evidence"
ARTIFACT_TABLE = "quality_audit_assurance_artifacts"
TABLES = (POLICY_TABLE, ATTEMPT_TABLE, SIGNATURE_TABLE, ARTIFACT_TABLE)


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


def upgrade() -> None:
    op.create_table(
        POLICY_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("artifact_policy", sa.String(length=24), nullable=False),
        sa.Column("artifact_title", sa.String(length=255), nullable=True),
        sa.Column("artifact_statement", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "revision_no", name="uq_quality_audit_output_policy_revision"),
        sa.CheckConstraint("revision_no >= 1", name="ck_quality_audit_output_policy_revision_no"),
        sa.CheckConstraint(
            "artifact_policy IN ('NONE','REPORT_ONLY','APPROVAL_LETTER','CERTIFICATE','ATTESTATION')",
            name="ck_quality_audit_output_policy_type",
        ),
    )
    op.create_index("ix_quality_audit_output_policy_latest", POLICY_TABLE, ["amo_id", "revision_no"])

    op.create_table(
        ATTEMPT_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("signer_user_id", sa.String(length=36), nullable=False),
        sa.Column("method", sa.String(length=24), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["signer_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("method IN ('PASSWORD_REAUTH')", name="ck_quality_audit_signature_attempt_method"),
    )
    op.create_index("ix_quality_audit_signature_attempt_window", ATTEMPT_TABLE, ["amo_id", "audit_id", "signer_user_id", "created_at"])

    op.create_table(
        SIGNATURE_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("report_revision_id", sa.String(length=36), nullable=False),
        sa.Column("signer_user_id", sa.String(length=36), nullable=False),
        sa.Column("method", sa.String(length=24), nullable=False),
        sa.Column("purpose", sa.String(length=24), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("signature_digest", sa.String(length=64), nullable=False),
        sa.Column("nonce", sa.String(length=64), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["report_revision_id"], ["quality_audit_report_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["signer_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("method IN ('PASSWORD_REAUTH')", name="ck_quality_audit_signature_evidence_method"),
        sa.CheckConstraint("purpose IN ('ISSUED_REPORT')", name="ck_quality_audit_signature_evidence_purpose"),
    )
    op.create_index("ix_quality_audit_signature_evidence_report", SIGNATURE_TABLE, ["amo_id", "audit_id", "report_revision_id", "signed_at"])

    op.create_table(
        ARTIFACT_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("output_policy_revision_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_type", sa.String(length=24), nullable=False),
        sa.Column("source_report_revision_id", sa.String(length=36), nullable=False),
        sa.Column("signature_evidence_id", sa.String(length=36), nullable=False),
        sa.Column("file_ref", sa.String(length=1024), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["output_policy_revision_id"], [f"{POLICY_TABLE}.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_report_revision_id"], ["quality_audit_report_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["signature_evidence_id"], [f"{SIGNATURE_TABLE}.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "amo_id", "audit_id", "artifact_type", "source_report_revision_id", "signature_evidence_id",
            name="uq_quality_audit_assurance_artifact_source",
        ),
        sa.CheckConstraint(
            "artifact_type IN ('APPROVAL_LETTER','CERTIFICATE','ATTESTATION')",
            name="ck_quality_audit_assurance_artifact_type",
        ),
    )
    op.create_index("ix_quality_audit_assurance_artifact_audit", ARTIFACT_TABLE, ["amo_id", "audit_id", "created_at"])

    for table_name in TABLES:
        _enable_rls(table_name)

    if _is_postgresql():
        op.execute(sa.text("""
            CREATE OR REPLACE FUNCTION prevent_quality_closing_assurance_mutation()
            RETURNS trigger AS $$ BEGIN
                RAISE EXCEPTION '% is append-only/immutable', TG_TABLE_NAME;
            END; $$ LANGUAGE plpgsql;
        """))
        for table_name in TABLES:
            op.execute(sa.text(f"""
                CREATE TRIGGER trg_{table_name}_append_only
                BEFORE UPDATE OR DELETE ON {table_name}
                FOR EACH ROW EXECUTE FUNCTION prevent_quality_closing_assurance_mutation();
            """))


def downgrade() -> None:
    if _is_postgresql():
        for table_name in reversed(TABLES):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{table_name}_append_only ON {table_name}"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_quality_closing_assurance_mutation()"))
    for table_name in reversed(TABLES):
        _disable_rls(table_name)
    op.drop_index("ix_quality_audit_assurance_artifact_audit", table_name=ARTIFACT_TABLE)
    op.drop_table(ARTIFACT_TABLE)
    op.drop_index("ix_quality_audit_signature_evidence_report", table_name=SIGNATURE_TABLE)
    op.drop_table(SIGNATURE_TABLE)
    op.drop_index("ix_quality_audit_signature_attempt_window", table_name=ATTEMPT_TABLE)
    op.drop_table(ATTEMPT_TABLE)
    op.drop_index("ix_quality_audit_output_policy_latest", table_name=POLICY_TABLE)
    op.drop_table(POLICY_TABLE)
