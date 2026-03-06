"""esign phase2 crypto provider

Revision ID: g2p2r0v1d3r
Revises: f1h1a2r3d4n5
Create Date: 2026-03-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "g2p2r0v1d3r"
down_revision = "f1h1a2r3d4n5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("esign_signed_artifacts", sa.Column("signing_provider", sa.Text(), nullable=True))
    op.add_column("esign_signed_artifacts", sa.Column("cryptographic_validation_status", sa.String(length=16), nullable=False, server_default="NOT_RUN"))
    op.add_column("esign_signed_artifacts", sa.Column("certificate_subject", sa.Text(), nullable=True))
    op.add_column("esign_signed_artifacts", sa.Column("certificate_serial", sa.Text(), nullable=True))
    op.add_column("esign_signed_artifacts", sa.Column("signing_time", sa.DateTime(timezone=True), nullable=True))
    op.add_column("esign_signed_artifacts", sa.Column("timestamp_applied", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("esign_signed_artifacts", sa.Column("timestamp_valid", sa.Boolean(), nullable=True))
    op.add_column("esign_signed_artifacts", sa.Column("validation_last_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("esign_signed_artifacts", sa.Column("validation_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.create_table(
        "esign_provider_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), nullable=True),
        sa.Column("request_id", sa.String(length=36), nullable=True),
        sa.Column("provider_name", sa.Text(), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("correlation_id", sa.Text(), nullable=True),
        sa.Column("sanitized_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["esign_signed_artifacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["request_id"], ["esign_signature_requests.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_esign_provider_events_tenant_id"), "esign_provider_events", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_esign_provider_events_artifact_id"), "esign_provider_events", ["artifact_id"], unique=False)
    op.create_index(op.f("ix_esign_provider_events_request_id"), "esign_provider_events", ["request_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_esign_provider_events_request_id"), table_name="esign_provider_events")
    op.drop_index(op.f("ix_esign_provider_events_artifact_id"), table_name="esign_provider_events")
    op.drop_index(op.f("ix_esign_provider_events_tenant_id"), table_name="esign_provider_events")
    op.drop_table("esign_provider_events")
    op.drop_column("esign_signed_artifacts", "validation_summary_json")
    op.drop_column("esign_signed_artifacts", "validation_last_checked_at")
    op.drop_column("esign_signed_artifacts", "timestamp_valid")
    op.drop_column("esign_signed_artifacts", "timestamp_applied")
    op.drop_column("esign_signed_artifacts", "signing_time")
    op.drop_column("esign_signed_artifacts", "certificate_serial")
    op.drop_column("esign_signed_artifacts", "certificate_subject")
    op.drop_column("esign_signed_artifacts", "cryptographic_validation_status")
    op.drop_column("esign_signed_artifacts", "signing_provider")
