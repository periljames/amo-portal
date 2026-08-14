"""Retain complete regulatory category scopes on personnel licences.

Revision ID: training_20260814_licence_text
Revises: training_20260813_readiness_audit
Create Date: 2026-08-14
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "training_20260814_licence_text"
down_revision = "training_20260813_readiness_audit"
branch_labels = None
depends_on = None


def _has_category_column() -> bool:
    inspector = sa.inspect(op.get_bind())
    if "personnel_licences" not in set(inspector.get_table_names()):
        return False
    return "category_code" in {
        str(column["name"])
        for column in inspector.get_columns("personnel_licences")
    }


def upgrade() -> None:
    if not _has_category_column():
        return
    op.alter_column(
        "personnel_licences",
        "category_code",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    if not _has_category_column():
        return
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        has_long_values = bool(
            bind.execute(
                sa.text(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM personnel_licences "
                    "WHERE char_length(category_code) > 255"
                    ")"
                )
            ).scalar()
        )
        if has_long_values:
            raise RuntimeError(
                "Cannot downgrade personnel_licences.category_code to VARCHAR(255): "
                "one or more governed licence scopes would be truncated."
            )
    op.alter_column(
        "personnel_licences",
        "category_code",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
