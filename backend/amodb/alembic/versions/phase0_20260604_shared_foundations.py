"""phase0 shared foundations base stations

Revision ID: phase0_20260604
Revises: None
Create Date: 2026-06-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "phase0_20260604"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "base_stations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("icao_code", sa.String(length=8), nullable=True),
        sa.Column("iata_code", sa.String(length=8), nullable=True),
        sa.Column("base_type", sa.String(length=32), nullable=False),
        sa.Column("time_zone", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "code", name="uq_base_stations_amo_code"),
    )
    op.create_index("ix_base_stations_amo_active", "base_stations", ["amo_id", "is_active"])
    op.create_index("ix_base_stations_amo_type", "base_stations", ["amo_id", "base_type"])
    op.create_index(op.f("ix_base_stations_amo_id"), "base_stations", ["amo_id"])
    op.create_index(op.f("ix_base_stations_icao_code"), "base_stations", ["icao_code"])
    op.create_index(op.f("ix_base_stations_iata_code"), "base_stations", ["iata_code"])

    op.create_table(
        "base_station_aliases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("base_station_id", sa.String(length=36), nullable=False),
        sa.Column("alias", sa.String(length=64), nullable=False),
        sa.Column("source_module", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["base_station_id"], ["base_stations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "alias", name="uq_base_station_aliases_amo_alias"),
    )
    op.create_index("ix_base_station_aliases_base", "base_station_aliases", ["base_station_id"])
    op.create_index(op.f("ix_base_station_aliases_amo_id"), "base_station_aliases", ["amo_id"])

    op.create_table(
        "user_base_assignments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("base_station_id", sa.String(length=36), nullable=False),
        sa.Column("assignment_kind", sa.String(length=32), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="ck_user_base_assignment_dates"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["base_station_id"], ["base_stations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_base_assignments_amo_user", "user_base_assignments", ["amo_id", "user_id"])
    op.create_index("ix_user_base_assignments_amo_base", "user_base_assignments", ["amo_id", "base_station_id"])
    op.create_index("ix_user_base_assignments_effective", "user_base_assignments", ["effective_from", "effective_to"])


def downgrade() -> None:
    op.drop_index("ix_user_base_assignments_effective", table_name="user_base_assignments")
    op.drop_index("ix_user_base_assignments_amo_base", table_name="user_base_assignments")
    op.drop_index("ix_user_base_assignments_amo_user", table_name="user_base_assignments")
    op.drop_table("user_base_assignments")
    op.drop_index(op.f("ix_base_station_aliases_amo_id"), table_name="base_station_aliases")
    op.drop_index("ix_base_station_aliases_base", table_name="base_station_aliases")
    op.drop_table("base_station_aliases")
    op.drop_index(op.f("ix_base_stations_iata_code"), table_name="base_stations")
    op.drop_index(op.f("ix_base_stations_icao_code"), table_name="base_stations")
    op.drop_index(op.f("ix_base_stations_amo_id"), table_name="base_stations")
    op.drop_index("ix_base_stations_amo_type", table_name="base_stations")
    op.drop_index("ix_base_stations_amo_active", table_name="base_stations")
    op.drop_table("base_stations")
