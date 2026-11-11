"""Persist source-bound Office reading renditions and human verification.

Revision ID: docx_fidelity_261028
Revises: quality_car_feedback_261027
"""
from alembic import op
import sqlalchemy as sa

revision = "docx_fidelity_261028"
down_revision = "quality_car_feedback_261027"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "manual_revision_renditions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manual_id", sa.String(36), sa.ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision_id", sa.String(36), sa.ForeignKey("manual_revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rendition_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="QUEUED"),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("pdf_sha256", sa.String(64)),
        sa.Column("storage_path", sa.Text()),
        sa.Column("converter", sa.String(96)),
        sa.Column("page_count", sa.Integer()),
        sa.Column("source_media_count", sa.Integer()),
        sa.Column("rendered_image_count", sa.Integer()),
        sa.Column("warning", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verified_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("verification_note", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("revision_id", "rendition_type", name="uq_manual_revision_rendition_type"),
    )
    for column in ("amo_id", "manual_id", "revision_id"):
        op.create_index("ix_manual_revision_renditions_" + column, "manual_revision_renditions", [column])


def downgrade():
    op.drop_table("manual_revision_renditions")
