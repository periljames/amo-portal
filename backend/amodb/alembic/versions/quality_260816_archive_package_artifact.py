"""Add controlled audit archive package artifact and disposition evidence fields.

Revision ID: quality_260816_archive_package_artifact
Revises: quality_260816_archive_governance
Create Date: 2026-08-16
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260816_archive_package_artifact"
down_revision = "quality_260816_archive_governance"
branch_labels = None
depends_on = None

MANIFEST_TABLE = "quality_audit_archive_manifests"
DISPOSITION_TABLE = "quality_audit_disposition_events"


def upgrade() -> None:
    op.add_column(MANIFEST_TABLE, sa.Column("package_file_ref", sa.String(length=1024), nullable=True))
    op.add_column(MANIFEST_TABLE, sa.Column("package_filename", sa.String(length=255), nullable=True))
    op.add_column(MANIFEST_TABLE, sa.Column("package_content_type", sa.String(length=128), nullable=True))
    op.add_column(MANIFEST_TABLE, sa.Column("package_size_bytes", sa.Integer(), nullable=True))
    op.add_column(MANIFEST_TABLE, sa.Column("package_sha256", sa.String(length=64), nullable=True))
    op.add_column(DISPOSITION_TABLE, sa.Column("package_sha256", sa.String(length=64), nullable=True))
    op.add_column(DISPOSITION_TABLE, sa.Column("action_ref", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column(DISPOSITION_TABLE, "action_ref")
    op.drop_column(DISPOSITION_TABLE, "package_sha256")
    op.drop_column(MANIFEST_TABLE, "package_sha256")
    op.drop_column(MANIFEST_TABLE, "package_size_bytes")
    op.drop_column(MANIFEST_TABLE, "package_content_type")
    op.drop_column(MANIFEST_TABLE, "package_filename")
    op.drop_column(MANIFEST_TABLE, "package_file_ref")
