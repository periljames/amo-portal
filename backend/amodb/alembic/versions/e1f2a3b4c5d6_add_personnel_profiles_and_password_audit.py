"""Add personnel profiles table and password audit/secondary phone columns.

Revision ID: e1f2a3b4c5d6
Revises: d9e2f3a4b5c6
Create Date: 2026-04-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d9e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("secondary_phone", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "personnel_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("person_id", sa.String(length=64), nullable=False),
        sa.Column("first_name", sa.String(length=128), nullable=False),
        sa.Column("last_name", sa.String(length=128), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("national_id", sa.String(length=128), nullable=True),
        sa.Column("amel_no", sa.String(length=128), nullable=True),
        sa.Column("internal_certification_stamp_no", sa.String(length=255), nullable=True),
        sa.Column("initial_authorization_date", sa.Date(), nullable=True),
        sa.Column("department", sa.String(length=255), nullable=True),
        sa.Column("position_title", sa.String(length=255), nullable=True),
        sa.Column("phone_number", sa.String(length=64), nullable=True),
        sa.Column("secondary_phone", sa.String(length=64), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("hire_date", sa.Date(), nullable=True),
        sa.Column("employment_status", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False, server_default=sa.text("'Active'")),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("birth_place", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "email", name="uq_personnel_profiles_amo_email"),
        sa.UniqueConstraint("amo_id", "person_id", name="uq_personnel_profiles_amo_person_id"),
        sa.UniqueConstraint("user_id", name="uq_personnel_profiles_user_id"),
    )
    op.create_index(op.f("ix_personnel_profiles_amo_id"), "personnel_profiles", ["amo_id"], unique=False)
    op.create_index(op.f("ix_personnel_profiles_email"), "personnel_profiles", ["email"], unique=False)
    op.create_index(op.f("ix_personnel_profiles_status"), "personnel_profiles", ["status"], unique=False)
    op.create_index(op.f("ix_personnel_profiles_user_id"), "personnel_profiles", ["user_id"], unique=False)
    op.create_index("ix_personnel_profiles_amo_status", "personnel_profiles", ["amo_id", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_personnel_profiles_amo_status", table_name="personnel_profiles")
    op.drop_index(op.f("ix_personnel_profiles_user_id"), table_name="personnel_profiles")
    op.drop_index(op.f("ix_personnel_profiles_status"), table_name="personnel_profiles")
    op.drop_index(op.f("ix_personnel_profiles_email"), table_name="personnel_profiles")
    op.drop_index(op.f("ix_personnel_profiles_amo_id"), table_name="personnel_profiles")
    op.drop_table("personnel_profiles")

    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "secondary_phone")
