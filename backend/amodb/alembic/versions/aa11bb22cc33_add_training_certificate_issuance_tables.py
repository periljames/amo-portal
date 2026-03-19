"""add training certificate issuance tables

Revision ID: aa11bb22cc33
Revises: b7d9f3a1c2e4
Create Date: 2026-03-05 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aa11bb22cc33"
down_revision: Union[str, Sequence[str], None] = "b7d9f3a1c2e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "training_certificate_issues",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("certificate_number", sa.String(length=128), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issued_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("template_id", sa.String(length=36), nullable=True),
        sa.Column("template_version", sa.String(length=64), nullable=True),
        sa.Column("artifact_path", sa.String(length=512), nullable=True),
        sa.Column("artifact_hash", sa.String(length=128), nullable=True),
        sa.Column("qr_value", sa.String(length=255), nullable=True),
        sa.Column("barcode_value", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="VALID"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["record_id"], ["training_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["issued_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "certificate_number", name="uq_training_certificate_issues_amo_number"),
    )
    op.create_index("idx_training_certificate_issues_amo_status", "training_certificate_issues", ["amo_id", "status"], unique=False)
    op.create_index("idx_training_certificate_issues_amo_record", "training_certificate_issues", ["amo_id", "record_id"], unique=False)
    op.create_index("idx_training_certificate_issues_amo_issued", "training_certificate_issues", ["amo_id", "issued_at"], unique=False)

    op.create_table(
        "training_certificate_status_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("certificate_issue_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["certificate_issue_id"], ["training_certificate_issues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_training_cert_status_history_issue", "training_certificate_status_history", ["certificate_issue_id", "created_at"], unique=False)

    op.execute(
        """
        INSERT INTO training_certificate_issues (
            id, amo_id, record_id, certificate_number, issued_at, status, created_at
        )
        SELECT
            lower(
                substr(seed.digest, 1, 8) || '-' ||
                substr(seed.digest, 9, 4) || '-' ||
                substr(seed.digest, 13, 4) || '-' ||
                substr(seed.digest, 17, 4) || '-' ||
                substr(seed.digest, 21, 12)
            ),
            tr.amo_id,
            tr.id,
            tr.certificate_reference,
            COALESCE(tr.created_at, CURRENT_TIMESTAMP),
            'VALID',
            COALESCE(tr.created_at, CURRENT_TIMESTAMP)
        FROM training_records tr
        CROSS JOIN LATERAL (
            SELECT md5(
                concat_ws(
                    ':',
                    tr.id,
                    tr.amo_id,
                    tr.certificate_reference,
                    clock_timestamp()::text,
                    random()::text
                )
            ) AS digest
        ) AS seed
        WHERE tr.certificate_reference IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM training_certificate_issues i
              WHERE i.amo_id = tr.amo_id AND i.certificate_number = tr.certificate_reference
          )
        """
    )


def downgrade() -> None:
    op.drop_index("idx_training_cert_status_history_issue", table_name="training_certificate_status_history")
    op.drop_table("training_certificate_status_history")
    op.drop_index("idx_training_certificate_issues_amo_issued", table_name="training_certificate_issues")
    op.drop_index("idx_training_certificate_issues_amo_record", table_name="training_certificate_issues")
    op.drop_index("idx_training_certificate_issues_amo_status", table_name="training_certificate_issues")
    op.drop_table("training_certificate_issues")
