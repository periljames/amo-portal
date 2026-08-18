"""Add tenant-scoped controlled roster form-number governance.

Revision ID: rostering_260818_control_numbers
Revises: rostering_260817_shift_semantics
Create Date: 2026-08-18

The portal must not manufacture a tenant's controlled form number. A tenant
configures the identifier and the database enforces uniqueness inside that
tenant only; another tenant may legitimately use the same identifier.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "rostering_260818_control_numbers"
down_revision = "rostering_260817_shift_semantics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "roster_controlled_document_settings",
        "form_number",
        existing_type=sa.String(length=64),
        nullable=False,
        server_default="",
    )
    op.execute(
        sa.text(
            """
            UPDATE roster_controlled_document_settings
               SET form_number = ''
             WHERE BTRIM(form_number) = 'ROSTER'
            """
        )
    )

    op.create_table(
        "roster_controlled_form_number_reservations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("normalized_number", sa.String(length=64), nullable=False),
        sa.Column("display_number", sa.String(length=64), nullable=False),
        sa.Column("owner_type", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "normalized_number", name="uq_roster_control_number_amo_number"),
        sa.UniqueConstraint("amo_id", "owner_type", "owner_id", name="uq_roster_control_number_amo_owner"),
    )
    op.create_index(
        "ix_roster_control_number_amo_owner",
        "roster_controlled_form_number_reservations",
        ["amo_id", "owner_type", "owner_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_roster_controlled_form_number_reservations_amo_id"),
        "roster_controlled_form_number_reservations",
        ["amo_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_roster_controlled_form_number_reservations_amo_id"),
        table_name="roster_controlled_form_number_reservations",
    )
    op.drop_index(
        "ix_roster_control_number_amo_owner",
        table_name="roster_controlled_form_number_reservations",
    )
    op.drop_table("roster_controlled_form_number_reservations")
    op.alter_column(
        "roster_controlled_document_settings",
        "form_number",
        existing_type=sa.String(length=64),
        nullable=False,
        server_default="ROSTER",
    )
