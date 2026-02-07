"""add workflow verification and approval fields

Revision ID: q1w2e3r4t5u7
Revises: p1q2r3s4t5u6
Create Date: 2026-03-05 00:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "q1w2e3r4t5u7"
down_revision = "p1q2r3s4t5u6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("qms_document_revisions") as batch_op:
        batch_op.add_column(sa.Column("approved_by_user_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_qms_docrev_approved_by_user",
            "users",
            ["approved_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("qms_audit_findings") as batch_op:
        batch_op.add_column(sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("verified_by_user_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_qms_finding_verified_by_user",
            "users",
            ["verified_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("qms_corrective_actions") as batch_op:
        batch_op.add_column(sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("verified_by_user_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_qms_cap_verified_by_user",
            "users",
            ["verified_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("qms_corrective_actions") as batch_op:
        batch_op.drop_constraint("fk_qms_cap_verified_by_user", type_="foreignkey")
        batch_op.drop_column("verified_by_user_id")
        batch_op.drop_column("verified_at")

    with op.batch_alter_table("qms_audit_findings") as batch_op:
        batch_op.drop_constraint("fk_qms_finding_verified_by_user", type_="foreignkey")
        batch_op.drop_column("verified_by_user_id")
        batch_op.drop_column("verified_at")

    with op.batch_alter_table("qms_document_revisions") as batch_op:
        batch_op.drop_constraint("fk_qms_docrev_approved_by_user", type_="foreignkey")
        batch_op.drop_column("approved_at")
        batch_op.drop_column("approved_by_user_id")
