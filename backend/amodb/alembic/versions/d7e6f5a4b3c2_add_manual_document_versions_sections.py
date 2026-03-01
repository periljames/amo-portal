"""add manual document_versions and document_sections tables

Revision ID: d7e6f5a4b3c2
Revises: c9d8e7f6a5b4
Create Date: 2026-03-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "d7e6f5a4b3c2"
down_revision = "c9d8e7f6a5b4"
branch_labels = None
depends_on = None


def _has_table(inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _has_table(inspector, "document_versions"):
        op.create_table(
            "document_versions",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("document_id", sa.String(length=36), sa.ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False),
            sa.Column("revision_id", sa.String(length=36), sa.ForeignKey("manual_revisions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("version_label", sa.String(length=32), nullable=False),
            sa.Column("content_json", sa.JSON(), nullable=False),
            sa.Column("delta_patch", sa.JSON(), nullable=False),
            sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
            sa.Column("state", sa.String(length=32), nullable=False, server_default="Draft"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])
        op.create_index("ix_document_versions_revision_id", "document_versions", ["revision_id"])
        op.create_index("ix_document_versions_checksum", "document_versions", ["checksum_sha256"])

    inspector = inspect(bind)
    if not _has_table(inspector, "document_sections"):
        op.create_table(
            "document_sections",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("document_version_id", sa.String(length=36), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("section_id", sa.String(length=128), nullable=False),
            sa.Column("heading", sa.String(length=255), nullable=False),
            sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("min_reading_time", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
        op.create_index("ix_document_sections_document_version", "document_sections", ["document_version_id"])
        op.create_index("ix_document_sections_section_id", "document_sections", ["section_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if _has_table(inspector, "document_sections"):
        op.drop_index("ix_document_sections_section_id", table_name="document_sections")
        op.drop_index("ix_document_sections_document_version", table_name="document_sections")
        op.drop_table("document_sections")

    inspector = inspect(bind)
    if _has_table(inspector, "document_versions"):
        op.drop_index("ix_document_versions_checksum", table_name="document_versions")
        op.drop_index("ix_document_versions_revision_id", table_name="document_versions")
        op.drop_index("ix_document_versions_document_id", table_name="document_versions")
        op.drop_table("document_versions")
