"""Add authoritative audit lifecycle, retained checklist versions and report issue records.

Revision ID: quality_20260724_audit_lifecycle
Revises: rostering_20260724_governance
Create Date: 2026-07-24
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import PurePosixPath

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "quality_20260724_audit_lifecycle"
down_revision = "rostering_20260724_governance"
branch_labels = None
depends_on = None


def _index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {str(index.get("name")) for index in inspector.get_indexes(table_name)}


def _basename(value: str, fallback: str) -> str:
    normalized = value.replace("\\", "/")
    name = PurePosixPath(normalized).name.strip()
    return name or fallback


def _content_type(name: str) -> str:
    lowered = name.lower()
    if lowered.endswith(".pdf"):
        return "application/pdf"
    if lowered.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if lowered.endswith(".doc"):
        return "application/msword"
    return "application/octet-stream"


def upgrade() -> None:
    op.create_table(
        "quality_audit_checklist_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False, server_default="UPLOAD"),
        sa.Column("fillable", sa.String(length=16), nullable=False, server_default="UNKNOWN"),
        sa.Column("field_count", sa.Integer(), nullable=True),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False, server_default="SOURCE"),
        sa.Column("uploaded_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("version_number > 0", name="ck_quality_audit_checklist_version_positive"),
        sa.CheckConstraint("size_bytes > 0", name="ck_quality_audit_checklist_size_positive"),
        sa.CheckConstraint("field_count IS NULL OR field_count >= 0", name="ck_quality_audit_checklist_field_count_nonnegative"),
        sa.CheckConstraint("lifecycle_status IN ('SOURCE','WORKING_DRAFT','COMMITTED','SUPERSEDED','RETAINED')", name="ck_quality_audit_checklist_lifecycle"),
        sa.CheckConstraint("fillable IN ('UNKNOWN','YES','NO')", name="ck_quality_audit_checklist_fillable"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_version_id"], ["quality_audit_checklist_documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("audit_id", "version_number", name="uq_quality_audit_checklist_version"),
    )
    op.create_index("ix_quality_audit_checklist_documents_amo_id", "quality_audit_checklist_documents", ["amo_id"])
    op.create_index("ix_quality_audit_checklist_documents_audit_id", "quality_audit_checklist_documents", ["audit_id"])
    op.create_index("ix_quality_audit_checklist_documents_parent_version_id", "quality_audit_checklist_documents", ["parent_version_id"])
    op.create_index("ix_quality_audit_checklist_documents_sha256", "quality_audit_checklist_documents", ["sha256"])
    op.create_index("ix_quality_audit_checklist_documents_lifecycle_status", "quality_audit_checklist_documents", ["lifecycle_status"])
    op.create_index("ix_quality_audit_checklist_documents_uploaded_by_user_id", "quality_audit_checklist_documents", ["uploaded_by_user_id"])
    op.create_index("ix_quality_audit_checklist_documents_committed_at", "quality_audit_checklist_documents", ["committed_at"])
    op.create_index("ix_quality_audit_checklist_audit_status", "quality_audit_checklist_documents", ["audit_id", "lifecycle_status"])
    op.create_index("ix_quality_audit_checklist_audit_created", "quality_audit_checklist_documents", ["audit_id", "created_at"])

    op.create_table(
        "quality_audit_report_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("issue_label", sa.String(length=64), nullable=True),
        sa.Column("uploaded_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("issued_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("distribution_status", sa.String(length=32), nullable=False, server_default="NOT_DISTRIBUTED"),
        sa.CheckConstraint("version_number > 0", name="ck_quality_audit_report_version_positive"),
        sa.CheckConstraint("size_bytes > 0", name="ck_quality_audit_report_size_positive"),
        sa.CheckConstraint("lifecycle_status IN ('DRAFT','ISSUED','SUPERSEDED','RETAINED')", name="ck_quality_audit_report_lifecycle"),
        sa.CheckConstraint("distribution_status IN ('NOT_DISTRIBUTED','PARTIAL','DISTRIBUTED')", name="ck_quality_audit_report_distribution"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_version_id"], ["quality_audit_report_documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["issued_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("audit_id", "version_number", name="uq_quality_audit_report_version"),
    )
    op.create_index("ix_quality_audit_report_documents_amo_id", "quality_audit_report_documents", ["amo_id"])
    op.create_index("ix_quality_audit_report_documents_audit_id", "quality_audit_report_documents", ["audit_id"])
    op.create_index("ix_quality_audit_report_documents_parent_version_id", "quality_audit_report_documents", ["parent_version_id"])
    op.create_index("ix_quality_audit_report_documents_sha256", "quality_audit_report_documents", ["sha256"])
    op.create_index("ix_quality_audit_report_documents_lifecycle_status", "quality_audit_report_documents", ["lifecycle_status"])
    op.create_index("ix_quality_audit_report_documents_uploaded_by_user_id", "quality_audit_report_documents", ["uploaded_by_user_id"])
    op.create_index("ix_quality_audit_report_documents_issued_by_user_id", "quality_audit_report_documents", ["issued_by_user_id"])
    op.create_index("ix_quality_audit_report_documents_issued_at", "quality_audit_report_documents", ["issued_at"])
    op.create_index("ix_quality_audit_report_audit_status", "quality_audit_report_documents", ["audit_id", "lifecycle_status"])
    op.create_index("ix_quality_audit_report_audit_issued", "quality_audit_report_documents", ["audit_id", "issued_at"])

    op.create_table(
        "quality_audit_stage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_id", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("stage_id IN ('war-room','checklist','findings','cars','evidence','report','closeout')", name="ck_quality_audit_stage_id"),
        sa.CheckConstraint("state IN ('NOT_READY','READY','IN_PROGRESS','BLOCKED','COMPLETE','LOCKED')", name="ck_quality_audit_stage_state"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_audit_stage_records_amo_id", "quality_audit_stage_records", ["amo_id"])
    op.create_index("ix_quality_audit_stage_records_audit_id", "quality_audit_stage_records", ["audit_id"])
    op.create_index("ix_quality_audit_stage_records_actor_user_id", "quality_audit_stage_records", ["actor_user_id"])
    op.create_index("ix_quality_audit_stage_records_occurred_at", "quality_audit_stage_records", ["occurred_at"])
    op.create_index("ix_quality_audit_stage_audit_stage_time", "quality_audit_stage_records", ["audit_id", "stage_id", "occurred_at"])

    op.create_table(
        "quality_audit_evidence_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("entity_type IN ('CHECKLIST_VERSION','FINDING_ATTACHMENT','CAR_ATTACHMENT','REPORT_VERSION','OTHER')", name="ck_quality_audit_evidence_entity_type"),
        sa.CheckConstraint("status IN ('PENDING','ACCEPTED','REJECTED')", name="ck_quality_audit_evidence_status"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("audit_id", "entity_type", "entity_id", name="uq_quality_audit_evidence_entity"),
    )
    op.create_index("ix_quality_audit_evidence_reviews_amo_id", "quality_audit_evidence_reviews", ["amo_id"])
    op.create_index("ix_quality_audit_evidence_reviews_audit_id", "quality_audit_evidence_reviews", ["audit_id"])
    op.create_index("ix_quality_audit_evidence_reviews_status", "quality_audit_evidence_reviews", ["status"])
    op.create_index("ix_quality_audit_evidence_reviews_reviewed_by_user_id", "quality_audit_evidence_reviews", ["reviewed_by_user_id"])
    op.create_index("ix_quality_audit_evidence_reviews_reviewed_at", "quality_audit_evidence_reviews", ["reviewed_at"])
    op.create_index("ix_quality_audit_evidence_audit_status", "quality_audit_evidence_reviews", ["audit_id", "status"])

    existing_indexes = _index_names("qms_audits")
    if "ix_qms_audits_amo_scope_actual_end" not in existing_indexes:
        op.create_index("ix_qms_audits_amo_scope_actual_end", "qms_audits", ["amo_id", "audit_scope_id", "actual_end"])
    if "ix_qms_audits_amo_auditee_actual_end" not in existing_indexes:
        op.create_index("ix_qms_audits_amo_auditee_actual_end", "qms_audits", ["amo_id", "auditee_user_id", "actual_end"])
    if "ix_qms_audits_amo_status_actual_end" not in existing_indexes:
        op.create_index("ix_qms_audits_amo_status_actual_end", "qms_audits", ["amo_id", "status", "actual_end"])

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, amo_id, checklist_file_ref, report_file_ref, created_by_user_id, created_at
            FROM qms_audits
            WHERE checklist_file_ref IS NOT NULL OR report_file_ref IS NOT NULL
            """
        )
    ).mappings().all()

    checklist_table = sa.table(
        "quality_audit_checklist_documents",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("amo_id", sa.String),
        sa.column("audit_id", postgresql.UUID(as_uuid=True)),
        sa.column("version_number", sa.Integer),
        sa.column("parent_version_id", postgresql.UUID(as_uuid=True)),
        sa.column("filename", sa.String),
        sa.column("storage_key", sa.String),
        sa.column("content_type", sa.String),
        sa.column("size_bytes", sa.Integer),
        sa.column("sha256", sa.String),
        sa.column("source_type", sa.String),
        sa.column("fillable", sa.String),
        sa.column("field_count", sa.Integer),
        sa.column("lifecycle_status", sa.String),
        sa.column("uploaded_by_user_id", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("committed_at", sa.DateTime(timezone=True)),
        sa.column("superseded_at", sa.DateTime(timezone=True)),
    )
    report_table = sa.table(
        "quality_audit_report_documents",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("amo_id", sa.String),
        sa.column("audit_id", postgresql.UUID(as_uuid=True)),
        sa.column("version_number", sa.Integer),
        sa.column("parent_version_id", postgresql.UUID(as_uuid=True)),
        sa.column("filename", sa.String),
        sa.column("storage_key", sa.String),
        sa.column("content_type", sa.String),
        sa.column("size_bytes", sa.Integer),
        sa.column("sha256", sa.String),
        sa.column("lifecycle_status", sa.String),
        sa.column("issue_label", sa.String),
        sa.column("uploaded_by_user_id", sa.String),
        sa.column("issued_by_user_id", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("issued_at", sa.DateTime(timezone=True)),
        sa.column("superseded_at", sa.DateTime(timezone=True)),
        sa.column("distribution_status", sa.String),
    )

    for row in rows:
        created_at = row["created_at"]
        if row["checklist_file_ref"]:
            storage_key = str(row["checklist_file_ref"])
            filename = _basename(storage_key, "legacy-checklist")
            bind.execute(
                checklist_table.insert().values(
                    id=uuid.uuid4(),
                    amo_id=row["amo_id"],
                    audit_id=row["id"],
                    version_number=1,
                    parent_version_id=None,
                    filename=filename,
                    storage_key=storage_key,
                    content_type=_content_type(filename),
                    size_bytes=1,
                    sha256=hashlib.sha256(storage_key.encode("utf-8")).hexdigest(),
                    source_type="LEGACY_IMPORT",
                    fillable="UNKNOWN",
                    field_count=None,
                    lifecycle_status="COMMITTED",
                    uploaded_by_user_id=row["created_by_user_id"],
                    created_at=created_at,
                    committed_at=created_at,
                    superseded_at=None,
                )
            )
        if row["report_file_ref"]:
            storage_key = str(row["report_file_ref"])
            filename = _basename(storage_key, "legacy-report")
            bind.execute(
                report_table.insert().values(
                    id=uuid.uuid4(),
                    amo_id=row["amo_id"],
                    audit_id=row["id"],
                    version_number=1,
                    parent_version_id=None,
                    filename=filename,
                    storage_key=storage_key,
                    content_type=_content_type(filename),
                    size_bytes=1,
                    sha256=hashlib.sha256(storage_key.encode("utf-8")).hexdigest(),
                    lifecycle_status="ISSUED",
                    issue_label="Legacy issued report",
                    uploaded_by_user_id=row["created_by_user_id"],
                    issued_by_user_id=row["created_by_user_id"],
                    created_at=created_at,
                    issued_at=created_at,
                    superseded_at=None,
                    distribution_status="NOT_DISTRIBUTED",
                )
            )


def downgrade() -> None:
    existing_indexes = _index_names("qms_audits")
    for index_name in (
        "ix_qms_audits_amo_status_actual_end",
        "ix_qms_audits_amo_auditee_actual_end",
        "ix_qms_audits_amo_scope_actual_end",
    ):
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name="qms_audits")

    op.drop_table("quality_audit_evidence_reviews")
    op.drop_table("quality_audit_stage_records")
    op.drop_table("quality_audit_report_documents")
    op.drop_table("quality_audit_checklist_documents")
