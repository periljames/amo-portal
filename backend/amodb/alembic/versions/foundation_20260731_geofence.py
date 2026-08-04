"""add private base geofence and location consensus fields

Revision ID: foundation_20260731_geofence
Revises: saas_20260731_route_latency_hist
Depends on: phase0_20260604
Create Date: 2026-07-31
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "foundation_20260731_geofence"
down_revision: Union[str, Sequence[str], None] = "saas_20260731_route_latency_hist"
branch_labels: Union[str, Sequence[str], None] = None
# The geofence branch alters base_stations, which is created on the independent
# shared-foundations branch. Alembic must order that branch before this revision.
depends_on: Union[str, Sequence[str], None] = "phase0_20260604"


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _columns(name: str) -> set[str]:
    if not _has_table(name):
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(name)}


def upgrade() -> None:
    if not _has_table("base_stations"):
        raise RuntimeError(
            "foundation_20260731_geofence requires phase0_20260604 to create base_stations"
        )

    columns = _columns("base_stations")
    additions = [
        ("latitude", sa.Float(), True, None),
        ("longitude", sa.Float(), True, None),
        ("coordinate_accuracy_m", sa.Float(), True, None),
        ("location_source", sa.String(length=32), True, None),
        ("airport_reference_ident", sa.String(length=16), True, None),
        ("location_verified_at", sa.DateTime(timezone=True), True, None),
        ("location_verified_by_user_id", sa.String(length=36), True, None),
        ("geofence_radius_m", sa.Integer(), False, "250"),
        ("checkin_prompt_enabled", sa.Boolean(), False, sa.false()),
        ("checkout_reminder_enabled", sa.Boolean(), False, sa.false()),
        ("suspicious_location_review_enabled", sa.Boolean(), False, sa.false()),
    ]
    for name, type_, nullable, default in additions:
        if name not in columns:
            op.add_column(
                "base_stations",
                sa.Column(name, type_, nullable=nullable, server_default=default),
            )

    inspector = sa.inspect(op.get_bind())
    foreign_keys = {fk.get("name") for fk in inspector.get_foreign_keys("base_stations")}
    if "fk_base_stations_location_verified_by_user_id" not in foreign_keys:
        op.create_foreign_key(
            "fk_base_stations_location_verified_by_user_id",
            "base_stations",
            "users",
            ["location_verified_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
    indexes = {index["name"] for index in inspector.get_indexes("base_stations")}
    if "ix_base_stations_amo_location" not in indexes:
        op.create_index(
            "ix_base_stations_amo_location",
            "base_stations",
            ["amo_id", "latitude", "longitude"],
            unique=False,
        )

    if not _has_table("base_location_observations"):
        op.create_table(
            "base_location_observations",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("amo_id", sa.String(length=36), nullable=False),
            sa.Column("base_station_id", sa.String(length=36), nullable=False),
            sa.Column("submitted_by_user_id", sa.String(length=36), nullable=False),
            sa.Column("latitude", sa.Float(), nullable=False),
            sa.Column("longitude", sa.Float(), nullable=False),
            sa.Column("accuracy_m", sa.Float(), nullable=False),
            sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["base_station_id"], ["base_stations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_base_location_observations_amo_id", "base_location_observations", ["amo_id"], unique=False)
        op.create_index(
            "ix_base_location_observations_station_created",
            "base_location_observations",
            ["base_station_id", "created_at"],
            unique=False,
        )
        op.create_index(
            "ix_base_location_observations_expiry",
            "base_location_observations",
            ["expires_at"],
            unique=False,
        )


def downgrade() -> None:
    if _has_table("base_location_observations"):
        op.drop_table("base_location_observations")
    if not _has_table("base_stations"):
        return
    columns = _columns("base_stations")
    for name in [
        "suspicious_location_review_enabled",
        "checkout_reminder_enabled",
        "checkin_prompt_enabled",
        "geofence_radius_m",
        "location_verified_by_user_id",
        "location_verified_at",
        "airport_reference_ident",
        "location_source",
        "coordinate_accuracy_m",
        "longitude",
        "latitude",
    ]:
        if name in columns:
            op.drop_column("base_stations", name)
