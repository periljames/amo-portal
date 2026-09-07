"""Add programme scope and aircraft entities to the audit-area catalogue.

Revision ID: quality_260905_area_catalogue
Revises: quality_260904_prog_dates
Create Date: 2026-09-05
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260905_area_catalogue"
down_revision = "quality_260904_prog_dates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quality_audit_universe_items",
        sa.Column("programme_kind", sa.String(length=16), nullable=False, server_default="BOTH"),
    )
    op.create_check_constraint(
        "ck_quality_audit_universe_programme_kind",
        "quality_audit_universe_items",
        "programme_kind IN ('INTERNAL','EXTERNAL','BOTH')",
    )
    op.drop_constraint(
        "ck_quality_audit_universe_entity_type",
        "quality_audit_universe_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_quality_audit_universe_entity_type",
        "quality_audit_universe_items",
        "entity_type IN ('DEPARTMENT','FACILITY','STATION','SUPPLIER','CONTRACTOR','PROCESS',"
        "'CAPABILITY','APPROVAL_RATING','AIRCRAFT','AIRCRAFT_TYPE','PERSONNEL_GROUP','OTHER')",
    )
    op.create_index(
        "ix_quality_audit_universe_programme_kind",
        "quality_audit_universe_items",
        ["amo_id", "programme_kind", "active"],
        unique=False,
    )


def downgrade() -> None:
    op.execute(sa.text("UPDATE quality_audit_universe_items SET entity_type = 'AIRCRAFT_TYPE' WHERE entity_type = 'AIRCRAFT'"))
    op.drop_index("ix_quality_audit_universe_programme_kind", table_name="quality_audit_universe_items")
    op.drop_constraint(
        "ck_quality_audit_universe_entity_type",
        "quality_audit_universe_items",
        type_="check",
    )
    op.create_check_constraint(
        "ck_quality_audit_universe_entity_type",
        "quality_audit_universe_items",
        "entity_type IN ('DEPARTMENT','FACILITY','STATION','SUPPLIER','CONTRACTOR','PROCESS',"
        "'CAPABILITY','APPROVAL_RATING','AIRCRAFT_TYPE','PERSONNEL_GROUP','OTHER')",
    )
    op.drop_constraint(
        "ck_quality_audit_universe_programme_kind",
        "quality_audit_universe_items",
        type_="check",
    )
    op.drop_column("quality_audit_universe_items", "programme_kind")
