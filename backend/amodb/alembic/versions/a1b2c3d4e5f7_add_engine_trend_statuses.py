"""add engine trend statuses and snapshot context fields

Revision ID: a1b2c3d4e5f7
Revises: 0f1e4ad3c5b1
Create Date: 2025-03-26 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, Sequence[str], None] = "0f1e4ad3c5b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "engine_flight_snapshots",
        sa.Column("engine_serial_number", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "engine_flight_snapshots",
        sa.Column("phase", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "engine_flight_snapshots",
        sa.Column("power_reference_type", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "engine_flight_snapshots",
        sa.Column("power_reference_value", sa.Float(), nullable=True),
    )
    op.add_column(
        "engine_flight_snapshots",
        sa.Column("pressure_altitude_ft", sa.Float(), nullable=True),
    )
    op.add_column(
        "engine_flight_snapshots",
        sa.Column("oat_c", sa.Float(), nullable=True),
    )
    op.add_column(
        "engine_flight_snapshots",
        sa.Column("isa_dev_c", sa.Float(), nullable=True),
    )
    op.add_column(
        "engine_flight_snapshots",
        sa.Column("source_record_id", sa.String(length=128), nullable=True),
    )

    op.create_index(
        op.f("ix_engine_flight_snapshots_engine_serial_number"),
        "engine_flight_snapshots",
        ["engine_serial_number"],
        unique=False,
    )

    trend_status_enum = sa.Enum(
        "Trend Normal",
        "Trend Shift",
        name="engine_trend_status_enum",
        native_enum=False,
    )

    op.create_table(
        "engine_trend_statuses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(length=50), nullable=False),
        sa.Column("engine_position", sa.String(length=32), nullable=False),
        sa.Column("engine_serial_number", sa.String(length=64), nullable=True),
        sa.Column("last_upload_date", sa.Date(), nullable=True),
        sa.Column("last_trend_date", sa.Date(), nullable=True),
        sa.Column("last_review_date", sa.Date(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("previous_status", trend_status_enum, nullable=True),
        sa.Column("current_status", trend_status_enum, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["aircraft_serial_number"],
            ["aircraft.serial_number"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "amo_id",
            "aircraft_serial_number",
            "engine_position",
            "engine_serial_number",
            name="uq_engine_trend_status_engine",
        ),
    )
    op.create_index(
        op.f("ix_engine_trend_statuses_amo_id"),
        "engine_trend_statuses",
        ["amo_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_engine_trend_statuses_aircraft_serial_number"),
        "engine_trend_statuses",
        ["aircraft_serial_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_engine_trend_statuses_engine_position"),
        "engine_trend_statuses",
        ["engine_position"],
        unique=False,
    )
    op.create_index(
        op.f("ix_engine_trend_statuses_engine_serial_number"),
        "engine_trend_statuses",
        ["engine_serial_number"],
        unique=False,
    )
    op.create_index(
        "ix_engine_trend_status_aircraft",
        "engine_trend_statuses",
        ["aircraft_serial_number"],
        unique=False,
    )
    op.create_index(
        "ix_engine_trend_status_engine",
        "engine_trend_statuses",
        ["engine_serial_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_engine_trend_status_engine", table_name="engine_trend_statuses")
    op.drop_index("ix_engine_trend_status_aircraft", table_name="engine_trend_statuses")
    op.drop_index(op.f("ix_engine_trend_statuses_engine_serial_number"), table_name="engine_trend_statuses")
    op.drop_index(op.f("ix_engine_trend_statuses_engine_position"), table_name="engine_trend_statuses")
    op.drop_index(op.f("ix_engine_trend_statuses_aircraft_serial_number"), table_name="engine_trend_statuses")
    op.drop_index(op.f("ix_engine_trend_statuses_amo_id"), table_name="engine_trend_statuses")
    op.drop_table("engine_trend_statuses")

    op.drop_index(
        op.f("ix_engine_flight_snapshots_engine_serial_number"),
        table_name="engine_flight_snapshots",
    )
    op.drop_column("engine_flight_snapshots", "source_record_id")
    op.drop_column("engine_flight_snapshots", "isa_dev_c")
    op.drop_column("engine_flight_snapshots", "oat_c")
    op.drop_column("engine_flight_snapshots", "pressure_altitude_ft")
    op.drop_column("engine_flight_snapshots", "power_reference_value")
    op.drop_column("engine_flight_snapshots", "power_reference_type")
    op.drop_column("engine_flight_snapshots", "phase")
    op.drop_column("engine_flight_snapshots", "engine_serial_number")

    trend_status_enum = sa.Enum(
        "Trend Normal",
        "Trend Shift",
        name="engine_trend_status_enum",
        native_enum=False,
    )
    trend_status_enum.drop(op.get_bind(), checkfirst=False)
