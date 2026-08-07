"""add controlled aircraft import staging

Revision ID: aircraft_arch_20260805_u3_imports
Revises: aircraft_arch_20260805_u2_effectivity
Create Date: 2026-08-05
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "aircraft_arch_20260805_u3_imports"
down_revision: Union[str, Sequence[str], None] = "aircraft_arch_20260805_u2_effectivity"
branch_labels = None
depends_on = None

UUID = sa.String(length=36)
NOW = sa.text("CURRENT_TIMESTAMP")
EMPTY_OBJECT = sa.text("'{}'::json")


def _user(name: str) -> sa.Column:
    return sa.Column(name, UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def upgrade() -> None:
    op.create_table(
        "aircraft_import_mapping_profiles",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("amo_id", UUID, sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False, server_default="TENANT"),
        sa.Column("source_system", sa.String(40), nullable=False),
        sa.Column("dataset_kind", sa.String(60), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        _user("created_by_user_id"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("amo_id", "code", name="uq_aircraft_import_mapping_profile_scope_code"),
        sa.CheckConstraint("scope IN ('GLOBAL','TENANT')", name="ck_aircraft_import_mapping_profile_scope"),
        sa.CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_aircraft_import_mapping_profile_status"),
    )
    op.create_index("ix_aircraft_import_mapping_profiles_amo_id", "aircraft_import_mapping_profiles", ["amo_id"])
    op.create_index("ix_aircraft_import_mapping_profile_source", "aircraft_import_mapping_profiles", ["source_system", "dataset_kind"])

    op.create_table(
        "aircraft_import_mapping_profile_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("profile_id", UUID, sa.ForeignKey("aircraft_import_mapping_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_code", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("header_fingerprint", sa.String(64), nullable=False),
        sa.Column("mapping_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("parser_options_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("content_hash", sa.String(64), nullable=True),
        _user("created_by_user_id"),
        _user("published_by_user_id"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("profile_id", "version_code", name="uq_aircraft_import_mapping_profile_version"),
        sa.CheckConstraint("status IN ('DRAFT','PUBLISHED','SUPERSEDED','WITHDRAWN')", name="ck_aircraft_import_mapping_profile_version_status"),
    )
    op.create_index("ix_aircraft_import_mapping_profile_versions_profile_id", "aircraft_import_mapping_profile_versions", ["profile_id"])
    op.create_index("ix_aircraft_import_mapping_profile_version_status", "aircraft_import_mapping_profile_versions", ["profile_id", "status"])

    op.create_table(
        "aircraft_import_batches",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("amo_id", UUID, sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_system", sa.String(40), nullable=False),
        sa.Column("idempotency_key", sa.String(96), nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="STAGED"),
        _user("created_by_user_id"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("amo_id", "idempotency_key", name="uq_aircraft_import_batch_idempotency"),
        sa.CheckConstraint("status IN ('STAGED','VALIDATED','RECONCILED','APPROVED','COMMITTED','FAILED','CANCELLED')", name="ck_aircraft_import_batch_status"),
    )
    op.create_index("ix_aircraft_import_batches_amo_id", "aircraft_import_batches", ["amo_id"])
    op.create_index("ix_aircraft_import_batch_scope_status", "aircraft_import_batches", ["amo_id", "status", "created_at"])

    op.create_table(
        "aircraft_import_datasets",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("batch_id", UUID, sa.ForeignKey("aircraft_import_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_kind", sa.String(60), nullable=False),
        sa.Column("adapter_code", sa.String(40), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("header_fingerprint", sa.String(64), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("batch_id", "content_hash", name="uq_aircraft_import_dataset_content"),
    )
    op.create_index("ix_aircraft_import_datasets_batch_id", "aircraft_import_datasets", ["batch_id"])
    op.create_index("ix_aircraft_import_dataset_kind", "aircraft_import_datasets", ["batch_id", "dataset_kind"])

    op.create_table(
        "aircraft_import_staging_rows",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("dataset_id", UUID, sa.ForeignKey("aircraft_import_datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("identity_key", sa.String(200), nullable=True),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("source_json", sa.JSON(), nullable=False),
        sa.Column("normalized_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="STAGED"),
        sa.UniqueConstraint("dataset_id", "row_number", name="uq_aircraft_import_staging_row_number"),
        sa.UniqueConstraint("dataset_id", "row_hash", name="uq_aircraft_import_staging_row_hash"),
        sa.CheckConstraint("status IN ('STAGED','VALID','INVALID','RESOLVED')", name="ck_aircraft_import_staging_row_status"),
    )
    op.create_index("ix_aircraft_import_staging_rows_dataset_id", "aircraft_import_staging_rows", ["dataset_id"])
    op.create_index("ix_aircraft_import_staging_row_identity", "aircraft_import_staging_rows", ["dataset_id", "identity_key"])

    op.create_table(
        "aircraft_import_issues",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("batch_id", UUID, sa.ForeignKey("aircraft_import_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_id", UUID, sa.ForeignKey("aircraft_import_datasets.id", ondelete="CASCADE"), nullable=True),
        sa.Column("row_id", UUID, sa.ForeignKey("aircraft_import_staging_rows.id", ondelete="CASCADE"), nullable=True),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("path", sa.String(200), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("resolution_status", sa.String(16), nullable=False, server_default="OPEN"),
        sa.CheckConstraint("severity IN ('INFO','WARNING','ERROR')", name="ck_aircraft_import_issue_severity"),
        sa.CheckConstraint("resolution_status IN ('OPEN','RESOLVED','WAIVED')", name="ck_aircraft_import_issue_resolution"),
    )
    op.create_index("ix_aircraft_import_issues_batch_id", "aircraft_import_issues", ["batch_id"])
    op.create_index("ix_aircraft_import_issues_dataset_id", "aircraft_import_issues", ["dataset_id"])
    op.create_index("ix_aircraft_import_issues_row_id", "aircraft_import_issues", ["row_id"])
    op.create_index("ix_aircraft_import_issue_open", "aircraft_import_issues", ["batch_id", "severity", "resolution_status"])

    op.create_table(
        "aircraft_import_decisions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("issue_id", UUID, sa.ForeignKey("aircraft_import_issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("correction_json", sa.JSON(), nullable=False, server_default=EMPTY_OBJECT),
        _user("decided_by_user_id"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint("decision IN ('ACCEPT','REJECT','CORRECT','WAIVE')", name="ck_aircraft_import_decision"),
    )
    op.create_index("ix_aircraft_import_decisions_issue_id", "aircraft_import_decisions", ["issue_id"])


def downgrade() -> None:
    for table in (
        "aircraft_import_decisions",
        "aircraft_import_issues",
        "aircraft_import_staging_rows",
        "aircraft_import_datasets",
        "aircraft_import_batches",
        "aircraft_import_mapping_profile_versions",
        "aircraft_import_mapping_profiles",
    ):
        op.drop_table(table)
