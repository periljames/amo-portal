"""Add governed regulatory traceability metadata to assurance controls.

Revision ID: quality_260913_control_trace
Revises: quality_260913_assurance_idx
"""
from alembic import op
import sqlalchemy as sa

revision = "quality_260913_control_trace"
down_revision = "quality_260913_assurance_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("quality_assurance_controls", sa.Column("framework_version", sa.String(length=80), nullable=True))
    op.add_column("quality_assurance_controls", sa.Column("requirement_title", sa.String(length=255), nullable=True))
    op.add_column("quality_assurance_controls", sa.Column("requirement_source_reference", sa.String(length=500), nullable=True))
    op.add_column("quality_assurance_controls", sa.Column("requirement_effective_from", sa.Date(), nullable=True))
    op.add_column("quality_assurance_controls", sa.Column("requirement_effective_to", sa.Date(), nullable=True))
    op.add_column(
        "quality_assurance_controls",
        sa.Column("applicability_status", sa.String(length=24), nullable=False, server_default="PENDING_REVIEW"),
    )
    op.add_column("quality_assurance_controls", sa.Column("applicability_rationale", sa.Text(), nullable=True))
    op.add_column(
        "quality_assurance_controls",
        sa.Column("mapping_status", sa.String(length=24), nullable=False, server_default="NOT_ASSESSED"),
    )
    op.create_check_constraint(
        "ck_quality_assurance_control_applicability",
        "quality_assurance_controls",
        "applicability_status IN ('APPLICABLE', 'NOT_APPLICABLE', 'PENDING_REVIEW')",
    )
    op.create_check_constraint(
        "ck_quality_assurance_control_mapping_status",
        "quality_assurance_controls",
        "mapping_status IN ('MAPPED', 'EXCEPTION', 'NOT_ASSESSED', 'PENDING')",
    )
    op.create_index(
        "ix_quality_assurance_controls_framework_version",
        "quality_assurance_controls",
        ["amo_id", "framework", "framework_version", "applicability_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_quality_assurance_controls_framework_version", table_name="quality_assurance_controls")
    op.drop_constraint("ck_quality_assurance_control_mapping_status", "quality_assurance_controls", type_="check")
    op.drop_constraint("ck_quality_assurance_control_applicability", "quality_assurance_controls", type_="check")
    op.drop_column("quality_assurance_controls", "mapping_status")
    op.drop_column("quality_assurance_controls", "applicability_rationale")
    op.drop_column("quality_assurance_controls", "applicability_status")
    op.drop_column("quality_assurance_controls", "requirement_effective_to")
    op.drop_column("quality_assurance_controls", "requirement_effective_from")
    op.drop_column("quality_assurance_controls", "requirement_source_reference")
    op.drop_column("quality_assurance_controls", "requirement_title")
    op.drop_column("quality_assurance_controls", "framework_version")
