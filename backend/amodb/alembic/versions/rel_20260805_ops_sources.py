"""Install authoritative Reliability operational sources and exact aviation values.

Revision ID: rel_20260805_ops_sources
Revises: rel_20260805_workpack_merge
Create Date: 2026-08-05
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "rel_20260805_ops_sources"
down_revision: Union[str, Sequence[str], None] = "rel_20260805_workpack_merge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ID = sa.String(length=36)


def _audit_columns():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def _create_source_tables() -> None:
    op.create_table(
        "reliability_flight_operations",
        sa.Column("id", ID, primary_key=True),
        sa.Column("amo_id", ID, sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("record_number", sa.String(80), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(50), sa.ForeignKey("aircraft.serial_number", ondelete="RESTRICT"), nullable=False),
        sa.Column("flight_number", sa.String(24), nullable=False),
        sa.Column("origin_station", sa.String(8)),
        sa.Column("destination_station", sa.String(8)),
        sa.Column("scheduled_departure_at", sa.DateTime(timezone=True)),
        sa.Column("actual_departure_at", sa.DateTime(timezone=True)),
        sa.Column("delay_minutes", sa.Integer()),
        sa.Column("dispatch_impact", sa.String(40)),
        sa.Column("severity", sa.String(16), nullable=False, server_default="MEDIUM"),
        sa.Column("ata_chapter", sa.String(20)),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="DRAFT"),
        sa.Column("canonical_event_id", sa.Integer(), sa.ForeignKey("reliability_events.id", ondelete="SET NULL")),
        sa.Column("created_by_user_id", ID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_by_user_id", ID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("closed_by_user_id", ID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("closure_note", sa.Text()),
        *_audit_columns(),
        sa.UniqueConstraint("amo_id", "record_number", name="uq_rel_flight_record"),
        sa.CheckConstraint("delay_minutes IS NULL OR delay_minutes >= 0", name="ck_rel_flight_delay"),
    )
    op.create_index("ix_rel_flight_amo_occurred", "reliability_flight_operations", ["amo_id", "occurred_at"])
    op.create_index("ix_rel_flight_amo_status", "reliability_flight_operations", ["amo_id", "status"])

    op.create_table(
        "reliability_mel_cdl_deferrals",
        sa.Column("id", ID, primary_key=True),
        sa.Column("amo_id", ID, sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("deferral_number", sa.String(80), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deferral_type", sa.String(8), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(50), sa.ForeignKey("aircraft.serial_number", ondelete="RESTRICT"), nullable=False),
        sa.Column("defect_reference", sa.String(80), nullable=False),
        sa.Column("item_reference", sa.String(80), nullable=False),
        sa.Column("category", sa.String(16)),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("control_basis", sa.Text(), nullable=False),
        sa.Column("operational_procedure", sa.Text()),
        sa.Column("maintenance_procedure", sa.Text()),
        sa.Column("repetitive_inspection_minutes", sa.Integer()),
        sa.Column("flight_number", sa.String(24)),
        sa.Column("ata_chapter", sa.String(20)),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="MEDIUM"),
        sa.Column("status", sa.String(24), nullable=False, server_default="DRAFT"),
        sa.Column("extension_history_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("closure_evidence_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("canonical_event_id", sa.Integer(), sa.ForeignKey("reliability_events.id", ondelete="SET NULL")),
        sa.Column("created_by_user_id", ID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_by_user_id", ID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("closed_by_user_id", ID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        *_audit_columns(),
        sa.UniqueConstraint("amo_id", "deferral_number", name="uq_rel_deferral_number"),
        sa.CheckConstraint("expires_at >= applied_at", name="ck_rel_deferral_expiry"),
        sa.CheckConstraint("repetitive_inspection_minutes IS NULL OR repetitive_inspection_minutes > 0", name="ck_rel_deferral_repeat_interval"),
    )
    op.create_index("ix_rel_deferral_amo_expiry", "reliability_mel_cdl_deferrals", ["amo_id", "expires_at"])
    op.create_index("ix_rel_deferral_amo_status", "reliability_mel_cdl_deferrals", ["amo_id", "status"])

    op.create_table(
        "reliability_component_shop_findings",
        sa.Column("id", ID, primary_key=True),
        sa.Column("amo_id", ID, sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shop_order_reference", sa.String(120), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("component_id", sa.Integer(), sa.ForeignKey("aircraft_components.id", ondelete="SET NULL")),
        sa.Column("aircraft_serial_number", sa.String(50), sa.ForeignKey("aircraft.serial_number", ondelete="SET NULL")),
        sa.Column("part_number", sa.String(80), nullable=False),
        sa.Column("component_serial_number", sa.String(80), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("inspected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ata_chapter", sa.String(20)),
        sa.Column("confirmed_failure", sa.Boolean()),
        sa.Column("test_result", sa.Text(), nullable=False),
        sa.Column("disposition", sa.Text(), nullable=False),
        sa.Column("release_reference", sa.String(120)),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="MEDIUM"),
        sa.Column("status", sa.String(24), nullable=False, server_default="DRAFT"),
        sa.Column("canonical_event_id", sa.Integer(), sa.ForeignKey("reliability_events.id", ondelete="SET NULL")),
        sa.Column("created_by_user_id", ID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_by_user_id", ID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("released_by_user_id", ID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        *_audit_columns(),
        sa.UniqueConstraint("amo_id", "shop_order_reference", name="uq_rel_shop_order"),
        sa.CheckConstraint("event_type <> 'NO_FAULT_FOUND' OR confirmed_failure = false", name="ck_rel_shop_nff_false"),
    )
    op.create_index("ix_rel_shop_amo_status", "reliability_component_shop_findings", ["amo_id", "status"])
    op.create_index("ix_rel_shop_component", "reliability_component_shop_findings", ["amo_id", "part_number", "component_serial_number"])

    op.create_table(
        "reliability_sms_occurrences",
        sa.Column("id", ID, primary_key=True),
        sa.Column("amo_id", ID, sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sms_reference", sa.String(120), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(50), sa.ForeignKey("aircraft.serial_number", ondelete="SET NULL")),
        sa.Column("hazard_reference", sa.String(120)),
        sa.Column("risk_classification", sa.String(80), nullable=False),
        sa.Column("investigation_status", sa.String(40), nullable=False, server_default="OPEN"),
        sa.Column("reliability_relevant", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reliability_link_reason", sa.Text()),
        sa.Column("ata_chapter", sa.String(20)),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="MEDIUM"),
        sa.Column("status", sa.String(24), nullable=False, server_default="DRAFT"),
        sa.Column("canonical_event_id", sa.Integer(), sa.ForeignKey("reliability_events.id", ondelete="SET NULL")),
        sa.Column("created_by_user_id", ID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("assessed_by_user_id", ID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("assessed_at", sa.DateTime(timezone=True)),
        *_audit_columns(),
        sa.UniqueConstraint("amo_id", "sms_reference", name="uq_rel_sms_reference"),
        sa.CheckConstraint("reliability_relevant = false OR reliability_link_reason IS NOT NULL", name="ck_rel_sms_link_reason"),
    )
    op.create_index("ix_rel_sms_amo_status", "reliability_sms_occurrences", ["amo_id", "status"])
    op.create_index("ix_rel_sms_amo_occurred", "reliability_sms_occurrences", ["amo_id", "occurred_at"])

    op.create_table(
        "reliability_workbook_imports",
        sa.Column("id", ID, primary_key=True),
        sa.Column("amo_id", ID, sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("header_row", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("mapping_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("defaults_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(24), nullable=False, server_default="UPLOADED"),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("approved_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ingested_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_user_id", ID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_by_user_id", ID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("ingested_by_user_id", ID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("ingested_at", sa.DateTime(timezone=True)),
        *_audit_columns(),
        sa.UniqueConstraint("amo_id", "content_hash", name="uq_rel_workbook_hash"),
    )
    op.create_index("ix_rel_workbook_amo_status", "reliability_workbook_imports", ["amo_id", "status"])

    op.create_table(
        "reliability_workbook_rows",
        sa.Column("id", ID, primary_key=True),
        sa.Column("amo_id", ID, sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("import_id", ID, sa.ForeignKey("reliability_workbook_imports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sheet_name", sa.String(255), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("raw_json", sa.JSON(), nullable=False),
        sa.Column("mapped_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("validation_errors_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("status", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("decision_note", sa.Text()),
        sa.Column("decided_by_user_id", ID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("canonical_event_id", sa.Integer(), sa.ForeignKey("reliability_events.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("import_id", "sheet_name", "source_row_number", name="uq_rel_workbook_row"),
    )
    op.create_index("ix_rel_workbook_row_status", "reliability_workbook_rows", ["import_id", "status"])
    op.create_index("ix_rel_workbook_row_hash", "reliability_workbook_rows", ["amo_id", "row_hash"])

    op.create_table(
        "reliability_source_revision_events",
        sa.Column("id", ID, primary_key=True),
        sa.Column("amo_id", ID, sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("source_id", ID, nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("actor_user_id", ID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_rel_source_revision_chain", "reliability_source_revision_events", ["amo_id", "source_type", "source_id", "created_at"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION prevent_reliability_source_revision_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'Reliability source revision history is append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_rel_source_revision_append_only
            BEFORE UPDATE OR DELETE ON reliability_source_revision_events
            FOR EACH ROW EXECUTE FUNCTION prevent_reliability_source_revision_mutation()
            """
        )


def _exact_columns():
    hours = {
        "aircraft": ["total_hours"],
        "aircraft_components": ["installed_hours", "current_hours", "tbo_hours", "hsi_hours", "last_overhaul_hours"],
        "aircraft_usage": ["block_hours", "ttaf_after", "ttesn_after", "ttsoh_after", "ttshsi_after", "pttsn_after", "pttso_after", "tscoa_after", "hours_to_mx"],
        "maintenance_program_items": ["interval_hours"],
        "maintenance_statuses": ["last_done_hours", "next_due_hours", "remaining_hours"],
        "technical_aircraft_utilisation": ["hours"],
        "technical_airworthiness_items": ["next_due_hours"],
        "technical_airworthiness_compliance_events": ["next_due_hours"],
        "technical_compliance_actions": ["due_hours"],
    }
    counts = {
        "aircraft": ["total_cycles"],
        "aircraft_components": ["installed_cycles", "current_cycles", "tbo_cycles", "hsi_cycles", "last_overhaul_cycles"],
        "aircraft_usage": ["cycles", "tca_after", "tcesn_after", "tcsoh_after"],
        "maintenance_program_items": ["interval_cycles"],
        "maintenance_statuses": ["last_done_cycles", "next_due_cycles", "remaining_cycles"],
        "technical_aircraft_utilisation": ["cycles"],
        "technical_airworthiness_items": ["next_due_cycles"],
        "technical_airworthiness_compliance_events": ["next_due_cycles"],
        "technical_compliance_actions": ["due_cycles"],
    }
    return hours, counts


def _convert_exact_values() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    hours, counts = _exact_columns()
    for table, columns in counts.items():
        if table not in tables:
            continue
        existing = {column["name"] for column in inspector.get_columns(table)}
        for column in columns:
            if column not in existing:
                continue
            fractional = bind.execute(sa.text(
                f'SELECT count(*) FROM "{table}" WHERE "{column}" IS NOT NULL '
                f'AND "{column}"::numeric <> trunc("{column}"::numeric)'
            )).scalar_one()
            if fractional:
                raise RuntimeError(
                    f"Cannot convert {table}.{column} to an exact cycle count: {fractional} fractional value(s) require reconciliation."
                )
    for table, columns in hours.items():
        if table not in tables:
            continue
        existing = {column["name"] for column in inspector.get_columns(table)}
        for column in columns:
            if column in existing:
                op.alter_column(
                    table,
                    column,
                    existing_type=sa.Float(),
                    type_=sa.Numeric(20, 3),
                    postgresql_using=f'ROUND("{column}"::numeric, 3)',
                    existing_nullable=True,
                )
    for table, columns in counts.items():
        if table not in tables:
            continue
        existing = {column["name"] for column in inspector.get_columns(table)}
        for column in columns:
            if column in existing:
                op.alter_column(
                    table,
                    column,
                    existing_type=sa.Float(),
                    type_=sa.Numeric(20, 0),
                    postgresql_using=f'"{column}"::numeric',
                    existing_nullable=True,
                )


def upgrade() -> None:
    _create_source_tables()
    _convert_exact_values()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        inspector = sa.inspect(bind)
        tables = set(inspector.get_table_names())
        hours, counts = _exact_columns()
        for collection in (hours, counts):
            for table, columns in collection.items():
                if table not in tables:
                    continue
                existing = {column["name"] for column in inspector.get_columns(table)}
                for column in columns:
                    if column in existing:
                        op.alter_column(
                            table,
                            column,
                            existing_type=sa.Numeric(),
                            type_=sa.Float(),
                            postgresql_using=f'"{column}"::double precision',
                            existing_nullable=True,
                        )
        op.execute("DROP TRIGGER IF EXISTS trg_rel_source_revision_append_only ON reliability_source_revision_events")
        op.execute("DROP FUNCTION IF EXISTS prevent_reliability_source_revision_mutation()")
    op.drop_index("ix_rel_source_revision_chain", table_name="reliability_source_revision_events")
    op.drop_table("reliability_source_revision_events")
    op.drop_index("ix_rel_workbook_row_hash", table_name="reliability_workbook_rows")
    op.drop_index("ix_rel_workbook_row_status", table_name="reliability_workbook_rows")
    op.drop_table("reliability_workbook_rows")
    op.drop_index("ix_rel_workbook_amo_status", table_name="reliability_workbook_imports")
    op.drop_table("reliability_workbook_imports")
    op.drop_index("ix_rel_sms_amo_occurred", table_name="reliability_sms_occurrences")
    op.drop_index("ix_rel_sms_amo_status", table_name="reliability_sms_occurrences")
    op.drop_table("reliability_sms_occurrences")
    op.drop_index("ix_rel_shop_component", table_name="reliability_component_shop_findings")
    op.drop_index("ix_rel_shop_amo_status", table_name="reliability_component_shop_findings")
    op.drop_table("reliability_component_shop_findings")
    op.drop_index("ix_rel_deferral_amo_status", table_name="reliability_mel_cdl_deferrals")
    op.drop_index("ix_rel_deferral_amo_expiry", table_name="reliability_mel_cdl_deferrals")
    op.drop_table("reliability_mel_cdl_deferrals")
    op.drop_index("ix_rel_flight_amo_status", table_name="reliability_flight_operations")
    op.drop_index("ix_rel_flight_amo_occurred", table_name="reliability_flight_operations")
    op.drop_table("reliability_flight_operations")
