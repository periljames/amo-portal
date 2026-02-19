"""add manuals reader controlled revisions scaffold

Revision ID: m2n3u4a5l6s7
Revises: y3z4a5b6c7d8
Create Date: 2026-02-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m2n3u4a5l6s7"
down_revision: Union[str, Sequence[str], None] = "y3z4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "manual_tenants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("settings_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "manuals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("manual_type", sa.String(length=64), nullable=False),
        sa.Column("owner_role", sa.String(length=64), nullable=False),
        sa.Column("current_published_rev_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["manual_tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_manual_code_tenant"),
    )
    op.create_table(
        "manual_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("manual_id", sa.String(length=36), nullable=False),
        sa.Column("rev_number", sa.String(length=32), nullable=False),
        sa.Column("issue_number", sa.String(length=32), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("status_enum", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by_rev_id", sa.String(length=36), nullable=True),
        sa.Column("requires_authority_approval_bool", sa.Boolean(), nullable=False),
        sa.Column("authority_approval_ref", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("immutable_locked", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["manual_id"], ["manuals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("manual_id", "rev_number", name="uq_manual_rev_number"),
    )
    op.create_foreign_key("fk_manuals_current_rev", "manuals", "manual_revisions", ["current_published_rev_id"], ["id"], ondelete="SET NULL")
    op.create_table(
        "manual_sections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("parent_section_id", sa.String(length=36), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("heading", sa.String(length=255), nullable=False),
        sa.Column("anchor_slug", sa.String(length=255), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["parent_section_id"], ["manual_sections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "manual_blocks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("section_id", sa.String(length=36), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("block_type", sa.String(length=64), nullable=False),
        sa.Column("html_sanitized", sa.Text(), nullable=False),
        sa.Column("text_plain", sa.Text(), nullable=False),
        sa.Column("change_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["section_id"], ["manual_sections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "revision_diff_index",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("baseline_revision_id", sa.String(length=36), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["baseline_revision_id"], ["manual_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "acknowledgements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("holder_user_id", sa.String(length=36), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledgement_text", sa.Text(), nullable=True),
        sa.Column("evidence_uri", sa.Text(), nullable=True),
        sa.Column("status_enum", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["holder_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revision_id"], ["manual_revisions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("acknowledgements")
    op.drop_table("revision_diff_index")
    op.drop_table("manual_blocks")
    op.drop_table("manual_sections")
    op.drop_constraint("fk_manuals_current_rev", "manuals", type_="foreignkey")
    op.drop_table("manual_revisions")
    op.drop_table("manuals")
    op.drop_table("manual_tenants")
