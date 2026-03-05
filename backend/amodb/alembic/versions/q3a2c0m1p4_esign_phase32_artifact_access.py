"""esign phase 3.2 artifact access policy

Revision ID: q3a2c0m1p4
Revises: p2h1t0r5t9
Create Date: 2026-03-05 06:05:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "q3a2c0m1p4"
down_revision = "p2h1t0r5t9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("esign_signature_policies", sa.Column("allow_private_artifact_preview", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("esign_signature_policies", sa.Column("allow_private_artifact_download", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("esign_signature_policies", sa.Column("allow_public_artifact_access", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("esign_signature_policies", sa.Column("allow_public_artifact_download", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("esign_signature_policies", sa.Column("allow_public_evidence_summary_download", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("esign_signature_policies", sa.Column("watermark_public_downloads", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("esign_signature_policies", sa.Column("require_auth_for_original_artifact", sa.Boolean(), nullable=False, server_default=sa.text("true")))


def downgrade() -> None:
    op.drop_column("esign_signature_policies", "require_auth_for_original_artifact")
    op.drop_column("esign_signature_policies", "watermark_public_downloads")
    op.drop_column("esign_signature_policies", "allow_public_evidence_summary_download")
    op.drop_column("esign_signature_policies", "allow_public_artifact_download")
    op.drop_column("esign_signature_policies", "allow_public_artifact_access")
    op.drop_column("esign_signature_policies", "allow_private_artifact_download")
    op.drop_column("esign_signature_policies", "allow_private_artifact_preview")
