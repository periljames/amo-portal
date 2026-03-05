"""add esign phase1 tables

Revision ID: e5s1g2n3m4o5
Revises: y3z4a5b6c7d8
Create Date: 2026-03-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "e5s1g2n3m4o5"
down_revision = "y3z4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "esign_document_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("storage_ref", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_esign_document_versions_tenant_id"), "esign_document_versions", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_esign_document_versions_document_id"), "esign_document_versions", ["document_id"], unique=False)
    op.create_index(op.f("ix_esign_document_versions_content_sha256"), "esign_document_versions", ["content_sha256"], unique=False)

    op.create_table(
        "esign_signature_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("doc_version_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["doc_version_id"], ["esign_document_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_esign_signature_requests_tenant_id"), "esign_signature_requests", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_esign_signature_requests_doc_version_id"), "esign_signature_requests", ["doc_version_id"], unique=False)

    op.create_table(
        "esign_signers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("signature_request_id", sa.String(length=36), nullable=False),
        sa.Column("signer_type", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("signing_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["signature_request_id"], ["esign_signature_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_esign_signers_tenant_id"), "esign_signers", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_esign_signers_signature_request_id"), "esign_signers", ["signature_request_id"], unique=False)

    op.create_table(
        "esign_signing_intents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("signer_id", sa.String(length=36), nullable=False),
        sa.Column("doc_version_id", sa.String(length=36), nullable=False),
        sa.Column("intent_sha256", sa.String(length=64), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="CREATED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["doc_version_id"], ["esign_document_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["signer_id"], ["esign_signers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(op.f("ix_esign_signing_intents_tenant_id"), "esign_signing_intents", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_esign_signing_intents_signer_id"), "esign_signing_intents", ["signer_id"], unique=False)

    op.create_table(
        "esign_webauthn_credentials",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("owner_type", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("transports", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("aaguid", sa.String(length=36), nullable=True),
        sa.Column("attestation_format", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credential_id"),
    )

    op.create_table(
        "esign_signed_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("signature_request_id", sa.String(length=36), nullable=False),
        sa.Column("doc_version_id", sa.String(length=36), nullable=False),
        sa.Column("storage_ref", sa.Text(), nullable=False),
        sa.Column("signed_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("appearance_applied", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("cryptographic_signature_applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["doc_version_id"], ["esign_document_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["signature_request_id"], ["esign_signature_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "esign_verification_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), nullable=False),
        sa.Column("token", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["artifact_id"], ["esign_signed_artifacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )

    op.create_table(
        "esign_webauthn_challenges",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("challenge_type", sa.String(length=32), nullable=False),
        sa.Column("challenge", sa.String(length=512), nullable=False),
        sa.Column("intent_id", sa.String(length=36), nullable=True),
        sa.Column("request_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "esign_signer_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("signer_id", sa.String(length=36), nullable=False),
        sa.Column("session_token", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["signer_id"], ["esign_signers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_token"),
    )


def downgrade() -> None:
    op.drop_table("esign_signer_sessions")
    op.drop_table("esign_webauthn_challenges")
    op.drop_table("esign_verification_tokens")
    op.drop_table("esign_signed_artifacts")
    op.drop_table("esign_webauthn_credentials")
    op.drop_index(op.f("ix_esign_signing_intents_signer_id"), table_name="esign_signing_intents")
    op.drop_index(op.f("ix_esign_signing_intents_tenant_id"), table_name="esign_signing_intents")
    op.drop_table("esign_signing_intents")
    op.drop_index(op.f("ix_esign_signers_signature_request_id"), table_name="esign_signers")
    op.drop_index(op.f("ix_esign_signers_tenant_id"), table_name="esign_signers")
    op.drop_table("esign_signers")
    op.drop_index(op.f("ix_esign_signature_requests_doc_version_id"), table_name="esign_signature_requests")
    op.drop_index(op.f("ix_esign_signature_requests_tenant_id"), table_name="esign_signature_requests")
    op.drop_table("esign_signature_requests")
    op.drop_index(op.f("ix_esign_document_versions_content_sha256"), table_name="esign_document_versions")
    op.drop_index(op.f("ix_esign_document_versions_document_id"), table_name="esign_document_versions")
    op.drop_index(op.f("ix_esign_document_versions_tenant_id"), table_name="esign_document_versions")
    op.drop_table("esign_document_versions")
