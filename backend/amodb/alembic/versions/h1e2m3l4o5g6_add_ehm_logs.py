"""add EHM raw logs and parsed records

Revision ID: h1e2m3l4o5g6
Revises: g1b2c3d4e5f6
Create Date: 2026-02-05 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "h1e2m3l4o5g6"
down_revision: Union[str, Sequence[str], None] = "g1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    parse_status_enum = sa.Enum(
        "PENDING",
        "PARSED",
        "FAILED",
        name="ehm_parse_status_enum",
        native_enum=False,
    )

    op.create_table(
        "ehm_raw_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(length=50), nullable=True),
        sa.Column("engine_position", sa.String(length=32), nullable=False),
        sa.Column("engine_serial_number", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sha256_hash", sa.String(length=64), nullable=False),
        sa.Column("decode_offset", sa.Integer(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("unit_identifiers", sa.JSON(), nullable=True),
        sa.Column("parse_status", parse_status_enum, nullable=False, server_default="PENDING"),
        sa.Column("parse_version", sa.String(length=32), nullable=True),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parsed_record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uploaded_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["aircraft_serial_number"],
            ["aircraft.serial_number"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "amo_id",
            "sha256_hash",
            "aircraft_serial_number",
            "engine_position",
            name="uq_ehm_log_dedupe",
        ),
    )
    op.create_index(op.f("ix_ehm_raw_logs_amo_id"), "ehm_raw_logs", ["amo_id"], unique=False)
    op.create_index(op.f("ix_ehm_raw_logs_aircraft_serial_number"), "ehm_raw_logs", ["aircraft_serial_number"], unique=False)
    op.create_index(op.f("ix_ehm_raw_logs_engine_position"), "ehm_raw_logs", ["engine_position"], unique=False)
    op.create_index(op.f("ix_ehm_raw_logs_engine_serial_number"), "ehm_raw_logs", ["engine_serial_number"], unique=False)
    op.create_index(op.f("ix_ehm_raw_logs_parse_status"), "ehm_raw_logs", ["parse_status"], unique=False)
    op.create_index(op.f("ix_ehm_raw_logs_sha256_hash"), "ehm_raw_logs", ["sha256_hash"], unique=False)
    op.create_index("ix_ehm_logs_amo_aircraft", "ehm_raw_logs", ["amo_id", "aircraft_serial_number"], unique=False)
    op.create_index("ix_ehm_logs_engine", "ehm_raw_logs", ["amo_id", "engine_position"], unique=False)
    op.create_index("ix_ehm_logs_created", "ehm_raw_logs", ["created_at"], unique=False)

    op.create_table(
        "ehm_parsed_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("raw_log_id", sa.String(length=36), nullable=False),
        sa.Column("record_type", sa.String(length=64), nullable=False),
        sa.Column("record_index", sa.Integer(), nullable=True),
        sa.Column("unit_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unit_time_raw", sa.String(length=64), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("parse_version", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["raw_log_id"], ["ehm_raw_logs.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_ehm_parsed_records_amo_id"), "ehm_parsed_records", ["amo_id"], unique=False)
    op.create_index(op.f("ix_ehm_parsed_records_raw_log_id"), "ehm_parsed_records", ["raw_log_id"], unique=False)
    op.create_index(op.f("ix_ehm_parsed_records_record_type"), "ehm_parsed_records", ["record_type"], unique=False)
    op.create_index(op.f("ix_ehm_parsed_records_unit_time"), "ehm_parsed_records", ["unit_time"], unique=False)
    op.create_index("ix_ehm_records_log", "ehm_parsed_records", ["raw_log_id"], unique=False)
    op.create_index("ix_ehm_records_type_time", "ehm_parsed_records", ["record_type", "unit_time"], unique=False)
    op.create_index("ix_ehm_records_amo_time", "ehm_parsed_records", ["amo_id", "unit_time"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ehm_records_amo_time", table_name="ehm_parsed_records")
    op.drop_index("ix_ehm_records_type_time", table_name="ehm_parsed_records")
    op.drop_index("ix_ehm_records_log", table_name="ehm_parsed_records")
    op.drop_index(op.f("ix_ehm_parsed_records_unit_time"), table_name="ehm_parsed_records")
    op.drop_index(op.f("ix_ehm_parsed_records_record_type"), table_name="ehm_parsed_records")
    op.drop_index(op.f("ix_ehm_parsed_records_raw_log_id"), table_name="ehm_parsed_records")
    op.drop_index(op.f("ix_ehm_parsed_records_amo_id"), table_name="ehm_parsed_records")
    op.drop_table("ehm_parsed_records")

    op.drop_index("ix_ehm_logs_created", table_name="ehm_raw_logs")
    op.drop_index("ix_ehm_logs_engine", table_name="ehm_raw_logs")
    op.drop_index("ix_ehm_logs_amo_aircraft", table_name="ehm_raw_logs")
    op.drop_index(op.f("ix_ehm_raw_logs_sha256_hash"), table_name="ehm_raw_logs")
    op.drop_index(op.f("ix_ehm_raw_logs_parse_status"), table_name="ehm_raw_logs")
    op.drop_index(op.f("ix_ehm_raw_logs_engine_serial_number"), table_name="ehm_raw_logs")
    op.drop_index(op.f("ix_ehm_raw_logs_engine_position"), table_name="ehm_raw_logs")
    op.drop_index(op.f("ix_ehm_raw_logs_aircraft_serial_number"), table_name="ehm_raw_logs")
    op.drop_index(op.f("ix_ehm_raw_logs_amo_id"), table_name="ehm_raw_logs")
    op.drop_table("ehm_raw_logs")

    parse_status_enum = sa.Enum(
        "PENDING",
        "PARSED",
        "FAILED",
        name="ehm_parse_status_enum",
        native_enum=False,
    )
    parse_status_enum.drop(op.get_bind(), checkfirst=False)
