"""add reliability core models

Revision ID: 9c6a7d2e8f10
Revises: f4c7f0c1d2ab
Create Date: 2025-01-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "9c6a7d2e8f10"
down_revision = "f4c7f0c1d2ab"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reliability_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(length=50), nullable=True),
        sa.Column("engine_position", sa.String(length=32), nullable=True),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("work_order_id", sa.Integer(), nullable=True),
        sa.Column("task_card_id", sa.Integer(), nullable=True),
        sa.Column(
            "event_type",
            sa.Enum(
                "DEFECT",
                "REMOVAL",
                "INSTALLATION",
                "OCTM",
                "ECTM",
                "FRACAS",
                "OTHER",
                name="reliability_event_type_enum",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum(
                "LOW",
                "MEDIUM",
                "HIGH",
                "CRITICAL",
                name="reliability_event_severity_enum",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column("ata_chapter", sa.String(length=20), nullable=True),
        sa.Column("reference_code", sa.String(length=64), nullable=True),
        sa.Column("source_system", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["aircraft_serial_number"], ["aircraft.serial_number"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["component_id"], ["aircraft_components.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_card_id"], ["task_cards.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reliability_events_aircraft_date", "reliability_events", ["aircraft_serial_number", "occurred_at"], unique=False)
    op.create_index("ix_reliability_events_amo_type", "reliability_events", ["amo_id", "event_type"], unique=False)
    op.create_index(op.f("ix_reliability_events_aircraft_serial_number"), "reliability_events", ["aircraft_serial_number"], unique=False)
    op.create_index(op.f("ix_reliability_events_component_id"), "reliability_events", ["component_id"], unique=False)
    op.create_index(op.f("ix_reliability_events_created_by_user_id"), "reliability_events", ["created_by_user_id"], unique=False)
    op.create_index(op.f("ix_reliability_events_engine_position"), "reliability_events", ["engine_position"], unique=False)
    op.create_index(op.f("ix_reliability_events_event_type"), "reliability_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_reliability_events_occurred_at"), "reliability_events", ["occurred_at"], unique=False)
    op.create_index(op.f("ix_reliability_events_reference_code"), "reliability_events", ["reference_code"], unique=False)
    op.create_index(op.f("ix_reliability_events_task_card_id"), "reliability_events", ["task_card_id"], unique=False)
    op.create_index(op.f("ix_reliability_events_work_order_id"), "reliability_events", ["work_order_id"], unique=False)

    op.create_table(
        "reliability_kpis",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("kpi_code", sa.String(length=64), nullable=False),
        sa.Column(
            "scope_type",
            sa.Enum(
                "FLEET",
                "AIRCRAFT",
                "ENGINE",
                "COMPONENT",
                "ATA",
                name="reliability_kpi_scope_enum",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("aircraft_serial_number", sa.String(length=50), nullable=True),
        sa.Column("engine_position", sa.String(length=32), nullable=True),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("ata_chapter", sa.String(length=20), nullable=True),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("numerator", sa.Float(), nullable=True),
        sa.Column("denominator", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("calculation_version", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["aircraft_serial_number"], ["aircraft.serial_number"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["component_id"], ["aircraft_components.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reliability_kpis_scope_window", "reliability_kpis", ["amo_id", "kpi_code", "window_start", "window_end"], unique=False)
    op.create_index(op.f("ix_reliability_kpis_aircraft_serial_number"), "reliability_kpis", ["aircraft_serial_number"], unique=False)
    op.create_index(op.f("ix_reliability_kpis_ata_chapter"), "reliability_kpis", ["ata_chapter"], unique=False)
    op.create_index(op.f("ix_reliability_kpis_component_id"), "reliability_kpis", ["component_id"], unique=False)
    op.create_index(op.f("ix_reliability_kpis_engine_position"), "reliability_kpis", ["engine_position"], unique=False)
    op.create_index(op.f("ix_reliability_kpis_kpi_code"), "reliability_kpis", ["kpi_code"], unique=False)
    op.create_index(op.f("ix_reliability_kpis_scope_type"), "reliability_kpis", ["scope_type"], unique=False)
    op.create_index(op.f("ix_reliability_kpis_window_end"), "reliability_kpis", ["window_end"], unique=False)
    op.create_index(op.f("ix_reliability_kpis_window_start"), "reliability_kpis", ["window_start"], unique=False)

    op.create_table(
        "reliability_threshold_sets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "scope_type",
            sa.Enum(
                "FLEET",
                "AIRCRAFT",
                "ENGINE",
                "COMPONENT",
                "ATA",
                name="reliability_threshold_scope_enum",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("scope_value", sa.String(length=128), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reliability_threshold_sets_scope", "reliability_threshold_sets", ["amo_id", "scope_type", "scope_value"], unique=False)
    op.create_index(op.f("ix_reliability_threshold_sets_amo_id"), "reliability_threshold_sets", ["amo_id"], unique=False)
    op.create_index(op.f("ix_reliability_threshold_sets_scope_type"), "reliability_threshold_sets", ["scope_type"], unique=False)
    op.create_index(op.f("ix_reliability_threshold_sets_scope_value"), "reliability_threshold_sets", ["scope_value"], unique=False)

    op.create_table(
        "reliability_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("kpi_id", sa.Integer(), nullable=True),
        sa.Column("threshold_set_id", sa.Integer(), nullable=True),
        sa.Column("alert_code", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "OPEN",
                "ACKNOWLEDGED",
                "CLOSED",
                name="reliability_alert_status_enum",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum(
                "LOW",
                "MEDIUM",
                "HIGH",
                "CRITICAL",
                name="reliability_alert_severity_enum",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("resolved_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["kpi_id"], ["reliability_kpis.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["threshold_set_id"], ["reliability_threshold_sets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reliability_alerts_status", "reliability_alerts", ["amo_id", "status"], unique=False)
    op.create_index("ix_reliability_alerts_triggered", "reliability_alerts", ["triggered_at"], unique=False)
    op.create_index(op.f("ix_reliability_alerts_alert_code"), "reliability_alerts", ["alert_code"], unique=False)
    op.create_index(op.f("ix_reliability_alerts_amo_id"), "reliability_alerts", ["amo_id"], unique=False)
    op.create_index(op.f("ix_reliability_alerts_created_by_user_id"), "reliability_alerts", ["created_by_user_id"], unique=False)
    op.create_index(op.f("ix_reliability_alerts_kpi_id"), "reliability_alerts", ["kpi_id"], unique=False)
    op.create_index(op.f("ix_reliability_alerts_resolved_by_user_id"), "reliability_alerts", ["resolved_by_user_id"], unique=False)
    op.create_index(op.f("ix_reliability_alerts_severity"), "reliability_alerts", ["severity"], unique=False)
    op.create_index(op.f("ix_reliability_alerts_status"), "reliability_alerts", ["status"], unique=False)
    op.create_index(op.f("ix_reliability_alerts_threshold_set_id"), "reliability_alerts", ["threshold_set_id"], unique=False)
    op.create_index(op.f("ix_reliability_alerts_triggered_at"), "reliability_alerts", ["triggered_at"], unique=False)

    op.create_table(
        "fracas_cases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "OPEN",
                "IN_ANALYSIS",
                "ACTIONS",
                "MONITORING",
                "CLOSED",
                name="fracas_status_enum",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum(
                "LOW",
                "MEDIUM",
                "HIGH",
                "CRITICAL",
                name="fracas_severity_enum",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column("classification", sa.String(length=64), nullable=True),
        sa.Column("aircraft_serial_number", sa.String(length=50), nullable=True),
        sa.Column("engine_position", sa.String(length=32), nullable=True),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("work_order_id", sa.Integer(), nullable=True),
        sa.Column("task_card_id", sa.Integer(), nullable=True),
        sa.Column("reliability_event_id", sa.Integer(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("root_cause", sa.Text(), nullable=True),
        sa.Column("corrective_action_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["aircraft_serial_number"], ["aircraft.serial_number"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["component_id"], ["aircraft_components.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reliability_event_id"], ["reliability_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_card_id"], ["task_cards.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fracas_cases_amo_status", "fracas_cases", ["amo_id", "status"], unique=False)
    op.create_index(op.f("ix_fracas_cases_aircraft_serial_number"), "fracas_cases", ["aircraft_serial_number"], unique=False)
    op.create_index(op.f("ix_fracas_cases_classification"), "fracas_cases", ["classification"], unique=False)
    op.create_index(op.f("ix_fracas_cases_component_id"), "fracas_cases", ["component_id"], unique=False)
    op.create_index(op.f("ix_fracas_cases_created_by_user_id"), "fracas_cases", ["created_by_user_id"], unique=False)
    op.create_index(op.f("ix_fracas_cases_engine_position"), "fracas_cases", ["engine_position"], unique=False)
    op.create_index(op.f("ix_fracas_cases_reliability_event_id"), "fracas_cases", ["reliability_event_id"], unique=False)
    op.create_index(op.f("ix_fracas_cases_severity"), "fracas_cases", ["severity"], unique=False)
    op.create_index(op.f("ix_fracas_cases_status"), "fracas_cases", ["status"], unique=False)
    op.create_index(op.f("ix_fracas_cases_task_card_id"), "fracas_cases", ["task_card_id"], unique=False)
    op.create_index(op.f("ix_fracas_cases_updated_by_user_id"), "fracas_cases", ["updated_by_user_id"], unique=False)
    op.create_index(op.f("ix_fracas_cases_work_order_id"), "fracas_cases", ["work_order_id"], unique=False)

    op.create_table(
        "fracas_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fracas_case_id", sa.Integer(), nullable=False),
        sa.Column(
            "action_type",
            sa.Enum("CORRECTIVE", "PREVENTIVE", name="fracas_action_type_enum", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "OPEN",
                "IN_PROGRESS",
                "DONE",
                "VERIFIED",
                "CANCELLED",
                name="fracas_action_status_enum",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effectiveness_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["fracas_case_id"], ["fracas_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fracas_actions_case_status", "fracas_actions", ["fracas_case_id", "status"], unique=False)
    op.create_index(op.f("ix_fracas_actions_action_type"), "fracas_actions", ["action_type"], unique=False)
    op.create_index(op.f("ix_fracas_actions_fracas_case_id"), "fracas_actions", ["fracas_case_id"], unique=False)
    op.create_index(op.f("ix_fracas_actions_owner_user_id"), "fracas_actions", ["owner_user_id"], unique=False)
    op.create_index(op.f("ix_fracas_actions_status"), "fracas_actions", ["status"], unique=False)

    op.create_table(
        "engine_flight_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(length=50), nullable=False),
        sa.Column("engine_position", sa.String(length=32), nullable=False),
        sa.Column("flight_date", sa.Date(), nullable=False),
        sa.Column("flight_leg", sa.String(length=32), nullable=True),
        sa.Column("flight_hours", sa.Float(), nullable=True),
        sa.Column("cycles", sa.Float(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("data_source", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["aircraft_serial_number"], ["aircraft.serial_number"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("aircraft_serial_number", "engine_position", "flight_date", "flight_leg", name="uq_engine_snapshot_flight"),
    )
    op.create_index("ix_engine_snapshots_aircraft_date", "engine_flight_snapshots", ["aircraft_serial_number", "flight_date"], unique=False)
    op.create_index(op.f("ix_engine_flight_snapshots_aircraft_serial_number"), "engine_flight_snapshots", ["aircraft_serial_number"], unique=False)
    op.create_index(op.f("ix_engine_flight_snapshots_engine_position"), "engine_flight_snapshots", ["engine_position"], unique=False)
    op.create_index(op.f("ix_engine_flight_snapshots_flight_date"), "engine_flight_snapshots", ["flight_date"], unique=False)

    op.create_table(
        "oil_uplifts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(length=50), nullable=False),
        sa.Column("engine_position", sa.String(length=32), nullable=True),
        sa.Column("uplift_date", sa.Date(), nullable=False),
        sa.Column("quantity_quarts", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["aircraft_serial_number"], ["aircraft.serial_number"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_oil_uplifts_aircraft_date", "oil_uplifts", ["aircraft_serial_number", "uplift_date"], unique=False)
    op.create_index(op.f("ix_oil_uplifts_aircraft_serial_number"), "oil_uplifts", ["aircraft_serial_number"], unique=False)
    op.create_index(op.f("ix_oil_uplifts_engine_position"), "oil_uplifts", ["engine_position"], unique=False)
    op.create_index(op.f("ix_oil_uplifts_uplift_date"), "oil_uplifts", ["uplift_date"], unique=False)

    op.create_table(
        "oil_consumption_rates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(length=50), nullable=False),
        sa.Column("engine_position", sa.String(length=32), nullable=True),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end", sa.Date(), nullable=False),
        sa.Column("oil_used_quarts", sa.Float(), nullable=False),
        sa.Column("flight_hours", sa.Float(), nullable=True),
        sa.Column("rate_qt_per_hour", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["aircraft_serial_number"], ["aircraft.serial_number"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_oil_rates_aircraft_window", "oil_consumption_rates", ["aircraft_serial_number", "window_start", "window_end"], unique=False)
    op.create_index(op.f("ix_oil_consumption_rates_aircraft_serial_number"), "oil_consumption_rates", ["aircraft_serial_number"], unique=False)
    op.create_index(op.f("ix_oil_consumption_rates_engine_position"), "oil_consumption_rates", ["engine_position"], unique=False)
    op.create_index(op.f("ix_oil_consumption_rates_window_end"), "oil_consumption_rates", ["window_end"], unique=False)
    op.create_index(op.f("ix_oil_consumption_rates_window_start"), "oil_consumption_rates", ["window_start"], unique=False)

    op.create_table(
        "component_instances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("part_number", sa.String(length=50), nullable=False),
        sa.Column("serial_number", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("component_class", sa.String(length=64), nullable=True),
        sa.Column("ata", sa.String(length=20), nullable=True),
        sa.Column("manufacturer_code", sa.String(length=32), nullable=True),
        sa.Column("operator_code", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("part_number", "serial_number", name="uq_component_instance_pn_sn"),
    )
    op.create_index("ix_component_instances_ata", "component_instances", ["ata"], unique=False)
    op.create_index(op.f("ix_component_instances_component_class"), "component_instances", ["component_class"], unique=False)
    op.create_index(op.f("ix_component_instances_manufacturer_code"), "component_instances", ["manufacturer_code"], unique=False)
    op.create_index(op.f("ix_component_instances_operator_code"), "component_instances", ["operator_code"], unique=False)
    op.create_index(op.f("ix_component_instances_part_number"), "component_instances", ["part_number"], unique=False)
    op.create_index(op.f("ix_component_instances_serial_number"), "component_instances", ["serial_number"], unique=False)

    op.create_table(
        "part_movement_ledger",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(length=50), nullable=True),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("component_instance_id", sa.Integer(), nullable=True),
        sa.Column("work_order_id", sa.Integer(), nullable=True),
        sa.Column("task_card_id", sa.Integer(), nullable=True),
        sa.Column(
            "event_type",
            sa.Enum("INSTALL", "REMOVE", "SWAP", "INSPECT", name="part_movement_type_enum", native_enum=False),
            nullable=False,
        ),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["aircraft_serial_number"], ["aircraft.serial_number"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["component_id"], ["aircraft_components.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["component_instance_id"], ["component_instances.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_card_id"], ["task_cards.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_part_movement_aircraft_date", "part_movement_ledger", ["aircraft_serial_number", "event_date"], unique=False)
    op.create_index("ix_part_movement_component", "part_movement_ledger", ["component_id", "event_date"], unique=False)
    op.create_index(op.f("ix_part_movement_ledger_aircraft_serial_number"), "part_movement_ledger", ["aircraft_serial_number"], unique=False)
    op.create_index(op.f("ix_part_movement_ledger_component_id"), "part_movement_ledger", ["component_id"], unique=False)
    op.create_index(op.f("ix_part_movement_ledger_component_instance_id"), "part_movement_ledger", ["component_instance_id"], unique=False)
    op.create_index(op.f("ix_part_movement_ledger_event_date"), "part_movement_ledger", ["event_date"], unique=False)
    op.create_index(op.f("ix_part_movement_ledger_event_type"), "part_movement_ledger", ["event_type"], unique=False)
    op.create_index(op.f("ix_part_movement_ledger_task_card_id"), "part_movement_ledger", ["task_card_id"], unique=False)
    op.create_index(op.f("ix_part_movement_ledger_work_order_id"), "part_movement_ledger", ["work_order_id"], unique=False)

    op.create_table(
        "removal_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(length=50), nullable=True),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("component_instance_id", sa.Integer(), nullable=True),
        sa.Column("part_movement_id", sa.Integer(), nullable=True),
        sa.Column("removal_reason", sa.String(length=128), nullable=True),
        sa.Column("hours_at_removal", sa.Float(), nullable=True),
        sa.Column("cycles_at_removal", sa.Float(), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["aircraft_serial_number"], ["aircraft.serial_number"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["component_id"], ["aircraft_components.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["component_instance_id"], ["component_instances.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["part_movement_id"], ["part_movement_ledger.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_removal_events_component_date", "removal_events", ["component_id", "removed_at"], unique=False)
    op.create_index(op.f("ix_removal_events_aircraft_serial_number"), "removal_events", ["aircraft_serial_number"], unique=False)
    op.create_index(op.f("ix_removal_events_component_id"), "removal_events", ["component_id"], unique=False)
    op.create_index(op.f("ix_removal_events_component_instance_id"), "removal_events", ["component_instance_id"], unique=False)
    op.create_index(op.f("ix_removal_events_part_movement_id"), "removal_events", ["part_movement_id"], unique=False)
    op.create_index(op.f("ix_removal_events_removed_at"), "removal_events", ["removed_at"], unique=False)
    op.create_index(op.f("ix_removal_events_removal_reason"), "removal_events", ["removal_reason"], unique=False)

    op.create_table(
        "aircraft_utilization_daily",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(length=50), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("flight_hours", sa.Float(), nullable=False),
        sa.Column("cycles", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["aircraft_serial_number"], ["aircraft.serial_number"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("aircraft_serial_number", "date", name="uq_aircraft_utilization_date"),
    )
    op.create_index("ix_aircraft_utilization_amo_date", "aircraft_utilization_daily", ["amo_id", "date"], unique=False)
    op.create_index(op.f("ix_aircraft_utilization_daily_aircraft_serial_number"), "aircraft_utilization_daily", ["aircraft_serial_number"], unique=False)
    op.create_index(op.f("ix_aircraft_utilization_daily_amo_id"), "aircraft_utilization_daily", ["amo_id"], unique=False)
    op.create_index(op.f("ix_aircraft_utilization_daily_date"), "aircraft_utilization_daily", ["date"], unique=False)

    op.create_table(
        "engine_utilization_daily",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(length=50), nullable=False),
        sa.Column("engine_position", sa.String(length=32), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("flight_hours", sa.Float(), nullable=False),
        sa.Column("cycles", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["aircraft_serial_number"], ["aircraft.serial_number"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("aircraft_serial_number", "engine_position", "date", name="uq_engine_utilization_date"),
    )
    op.create_index("ix_engine_utilization_amo_date", "engine_utilization_daily", ["amo_id", "date"], unique=False)
    op.create_index(op.f("ix_engine_utilization_daily_aircraft_serial_number"), "engine_utilization_daily", ["aircraft_serial_number"], unique=False)
    op.create_index(op.f("ix_engine_utilization_daily_amo_id"), "engine_utilization_daily", ["amo_id"], unique=False)
    op.create_index(op.f("ix_engine_utilization_daily_date"), "engine_utilization_daily", ["date"], unique=False)
    op.create_index(op.f("ix_engine_utilization_daily_engine_position"), "engine_utilization_daily", ["engine_position"], unique=False)

    op.create_table(
        "reliability_alert_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("threshold_set_id", sa.Integer(), nullable=False),
        sa.Column("kpi_code", sa.String(length=64), nullable=False),
        sa.Column(
            "comparator",
            sa.Enum("GT", "GTE", "LT", "LTE", "EQ", name="reliability_alert_comparator_enum", native_enum=False),
            nullable=False,
        ),
        sa.Column("threshold_value", sa.Float(), nullable=False),
        sa.Column(
            "severity",
            sa.Enum(
                "LOW",
                "MEDIUM",
                "HIGH",
                "CRITICAL",
                name="reliability_alert_rule_severity_enum",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["threshold_set_id"], ["reliability_threshold_sets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reliability_alert_rules_threshold", "reliability_alert_rules", ["threshold_set_id", "kpi_code"], unique=False)
    op.create_index(op.f("ix_reliability_alert_rules_comparator"), "reliability_alert_rules", ["comparator"], unique=False)
    op.create_index(op.f("ix_reliability_alert_rules_kpi_code"), "reliability_alert_rules", ["kpi_code"], unique=False)
    op.create_index(op.f("ix_reliability_alert_rules_severity"), "reliability_alert_rules", ["severity"], unique=False)
    op.create_index(op.f("ix_reliability_alert_rules_threshold_set_id"), "reliability_alert_rules", ["threshold_set_id"], unique=False)

    op.create_table(
        "reliability_control_chart_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("kpi_code", sa.String(length=64), nullable=False),
        sa.Column(
            "method",
            sa.Enum("EWMA", "CUSUM", "SLOPE", name="reliability_control_chart_method_enum", native_enum=False),
            nullable=False,
        ),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reliability_control_chart_kpi", "reliability_control_chart_configs", ["amo_id", "kpi_code"], unique=False)
    op.create_index(op.f("ix_reliability_control_chart_configs_amo_id"), "reliability_control_chart_configs", ["amo_id"], unique=False)
    op.create_index(op.f("ix_reliability_control_chart_configs_kpi_code"), "reliability_control_chart_configs", ["kpi_code"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_reliability_control_chart_configs_kpi_code"), table_name="reliability_control_chart_configs")
    op.drop_index(op.f("ix_reliability_control_chart_configs_amo_id"), table_name="reliability_control_chart_configs")
    op.drop_index("ix_reliability_control_chart_kpi", table_name="reliability_control_chart_configs")
    op.drop_table("reliability_control_chart_configs")

    op.drop_index(op.f("ix_reliability_alert_rules_threshold_set_id"), table_name="reliability_alert_rules")
    op.drop_index(op.f("ix_reliability_alert_rules_severity"), table_name="reliability_alert_rules")
    op.drop_index(op.f("ix_reliability_alert_rules_kpi_code"), table_name="reliability_alert_rules")
    op.drop_index(op.f("ix_reliability_alert_rules_comparator"), table_name="reliability_alert_rules")
    op.drop_index("ix_reliability_alert_rules_threshold", table_name="reliability_alert_rules")
    op.drop_table("reliability_alert_rules")

    op.drop_index(op.f("ix_engine_utilization_daily_engine_position"), table_name="engine_utilization_daily")
    op.drop_index(op.f("ix_engine_utilization_daily_date"), table_name="engine_utilization_daily")
    op.drop_index(op.f("ix_engine_utilization_daily_amo_id"), table_name="engine_utilization_daily")
    op.drop_index(op.f("ix_engine_utilization_daily_aircraft_serial_number"), table_name="engine_utilization_daily")
    op.drop_index("ix_engine_utilization_amo_date", table_name="engine_utilization_daily")
    op.drop_table("engine_utilization_daily")

    op.drop_index(op.f("ix_aircraft_utilization_daily_date"), table_name="aircraft_utilization_daily")
    op.drop_index(op.f("ix_aircraft_utilization_daily_amo_id"), table_name="aircraft_utilization_daily")
    op.drop_index(op.f("ix_aircraft_utilization_daily_aircraft_serial_number"), table_name="aircraft_utilization_daily")
    op.drop_index("ix_aircraft_utilization_amo_date", table_name="aircraft_utilization_daily")
    op.drop_table("aircraft_utilization_daily")

    op.drop_index(op.f("ix_removal_events_removal_reason"), table_name="removal_events")
    op.drop_index(op.f("ix_removal_events_removed_at"), table_name="removal_events")
    op.drop_index(op.f("ix_removal_events_part_movement_id"), table_name="removal_events")
    op.drop_index(op.f("ix_removal_events_component_instance_id"), table_name="removal_events")
    op.drop_index(op.f("ix_removal_events_component_id"), table_name="removal_events")
    op.drop_index(op.f("ix_removal_events_aircraft_serial_number"), table_name="removal_events")
    op.drop_index("ix_removal_events_component_date", table_name="removal_events")
    op.drop_table("removal_events")

    op.drop_index(op.f("ix_part_movement_ledger_work_order_id"), table_name="part_movement_ledger")
    op.drop_index(op.f("ix_part_movement_ledger_task_card_id"), table_name="part_movement_ledger")
    op.drop_index(op.f("ix_part_movement_ledger_event_type"), table_name="part_movement_ledger")
    op.drop_index(op.f("ix_part_movement_ledger_event_date"), table_name="part_movement_ledger")
    op.drop_index(op.f("ix_part_movement_ledger_component_instance_id"), table_name="part_movement_ledger")
    op.drop_index(op.f("ix_part_movement_ledger_component_id"), table_name="part_movement_ledger")
    op.drop_index(op.f("ix_part_movement_ledger_aircraft_serial_number"), table_name="part_movement_ledger")
    op.drop_index("ix_part_movement_component", table_name="part_movement_ledger")
    op.drop_index("ix_part_movement_aircraft_date", table_name="part_movement_ledger")
    op.drop_table("part_movement_ledger")

    op.drop_index(op.f("ix_component_instances_serial_number"), table_name="component_instances")
    op.drop_index(op.f("ix_component_instances_part_number"), table_name="component_instances")
    op.drop_index(op.f("ix_component_instances_operator_code"), table_name="component_instances")
    op.drop_index(op.f("ix_component_instances_manufacturer_code"), table_name="component_instances")
    op.drop_index(op.f("ix_component_instances_component_class"), table_name="component_instances")
    op.drop_index("ix_component_instances_ata", table_name="component_instances")
    op.drop_table("component_instances")

    op.drop_index(op.f("ix_oil_consumption_rates_window_start"), table_name="oil_consumption_rates")
    op.drop_index(op.f("ix_oil_consumption_rates_window_end"), table_name="oil_consumption_rates")
    op.drop_index(op.f("ix_oil_consumption_rates_engine_position"), table_name="oil_consumption_rates")
    op.drop_index(op.f("ix_oil_consumption_rates_aircraft_serial_number"), table_name="oil_consumption_rates")
    op.drop_index("ix_oil_rates_aircraft_window", table_name="oil_consumption_rates")
    op.drop_table("oil_consumption_rates")

    op.drop_index(op.f("ix_oil_uplifts_uplift_date"), table_name="oil_uplifts")
    op.drop_index(op.f("ix_oil_uplifts_engine_position"), table_name="oil_uplifts")
    op.drop_index(op.f("ix_oil_uplifts_aircraft_serial_number"), table_name="oil_uplifts")
    op.drop_index("ix_oil_uplifts_aircraft_date", table_name="oil_uplifts")
    op.drop_table("oil_uplifts")

    op.drop_index(op.f("ix_engine_flight_snapshots_flight_date"), table_name="engine_flight_snapshots")
    op.drop_index(op.f("ix_engine_flight_snapshots_engine_position"), table_name="engine_flight_snapshots")
    op.drop_index(op.f("ix_engine_flight_snapshots_aircraft_serial_number"), table_name="engine_flight_snapshots")
    op.drop_index("ix_engine_snapshots_aircraft_date", table_name="engine_flight_snapshots")
    op.drop_table("engine_flight_snapshots")

    op.drop_index(op.f("ix_fracas_actions_status"), table_name="fracas_actions")
    op.drop_index(op.f("ix_fracas_actions_owner_user_id"), table_name="fracas_actions")
    op.drop_index(op.f("ix_fracas_actions_fracas_case_id"), table_name="fracas_actions")
    op.drop_index(op.f("ix_fracas_actions_action_type"), table_name="fracas_actions")
    op.drop_index("ix_fracas_actions_case_status", table_name="fracas_actions")
    op.drop_table("fracas_actions")

    op.drop_index(op.f("ix_fracas_cases_work_order_id"), table_name="fracas_cases")
    op.drop_index(op.f("ix_fracas_cases_updated_by_user_id"), table_name="fracas_cases")
    op.drop_index(op.f("ix_fracas_cases_task_card_id"), table_name="fracas_cases")
    op.drop_index(op.f("ix_fracas_cases_status"), table_name="fracas_cases")
    op.drop_index(op.f("ix_fracas_cases_severity"), table_name="fracas_cases")
    op.drop_index(op.f("ix_fracas_cases_reliability_event_id"), table_name="fracas_cases")
    op.drop_index(op.f("ix_fracas_cases_engine_position"), table_name="fracas_cases")
    op.drop_index(op.f("ix_fracas_cases_created_by_user_id"), table_name="fracas_cases")
    op.drop_index(op.f("ix_fracas_cases_component_id"), table_name="fracas_cases")
    op.drop_index(op.f("ix_fracas_cases_classification"), table_name="fracas_cases")
    op.drop_index(op.f("ix_fracas_cases_aircraft_serial_number"), table_name="fracas_cases")
    op.drop_index("ix_fracas_cases_amo_status", table_name="fracas_cases")
    op.drop_table("fracas_cases")

    op.drop_index(op.f("ix_reliability_alerts_triggered_at"), table_name="reliability_alerts")
    op.drop_index(op.f("ix_reliability_alerts_threshold_set_id"), table_name="reliability_alerts")
    op.drop_index(op.f("ix_reliability_alerts_status"), table_name="reliability_alerts")
    op.drop_index(op.f("ix_reliability_alerts_severity"), table_name="reliability_alerts")
    op.drop_index(op.f("ix_reliability_alerts_resolved_by_user_id"), table_name="reliability_alerts")
    op.drop_index(op.f("ix_reliability_alerts_kpi_id"), table_name="reliability_alerts")
    op.drop_index(op.f("ix_reliability_alerts_created_by_user_id"), table_name="reliability_alerts")
    op.drop_index(op.f("ix_reliability_alerts_amo_id"), table_name="reliability_alerts")
    op.drop_index(op.f("ix_reliability_alerts_alert_code"), table_name="reliability_alerts")
    op.drop_index("ix_reliability_alerts_triggered", table_name="reliability_alerts")
    op.drop_index("ix_reliability_alerts_status", table_name="reliability_alerts")
    op.drop_table("reliability_alerts")

    op.drop_index(op.f("ix_reliability_threshold_sets_scope_value"), table_name="reliability_threshold_sets")
    op.drop_index(op.f("ix_reliability_threshold_sets_scope_type"), table_name="reliability_threshold_sets")
    op.drop_index(op.f("ix_reliability_threshold_sets_amo_id"), table_name="reliability_threshold_sets")
    op.drop_index("ix_reliability_threshold_sets_scope", table_name="reliability_threshold_sets")
    op.drop_table("reliability_threshold_sets")

    op.drop_index(op.f("ix_reliability_kpis_window_start"), table_name="reliability_kpis")
    op.drop_index(op.f("ix_reliability_kpis_window_end"), table_name="reliability_kpis")
    op.drop_index(op.f("ix_reliability_kpis_scope_type"), table_name="reliability_kpis")
    op.drop_index(op.f("ix_reliability_kpis_kpi_code"), table_name="reliability_kpis")
    op.drop_index(op.f("ix_reliability_kpis_engine_position"), table_name="reliability_kpis")
    op.drop_index(op.f("ix_reliability_kpis_component_id"), table_name="reliability_kpis")
    op.drop_index(op.f("ix_reliability_kpis_ata_chapter"), table_name="reliability_kpis")
    op.drop_index(op.f("ix_reliability_kpis_aircraft_serial_number"), table_name="reliability_kpis")
    op.drop_index("ix_reliability_kpis_scope_window", table_name="reliability_kpis")
    op.drop_table("reliability_kpis")

    op.drop_index(op.f("ix_reliability_events_work_order_id"), table_name="reliability_events")
    op.drop_index(op.f("ix_reliability_events_task_card_id"), table_name="reliability_events")
    op.drop_index(op.f("ix_reliability_events_reference_code"), table_name="reliability_events")
    op.drop_index(op.f("ix_reliability_events_occurred_at"), table_name="reliability_events")
    op.drop_index(op.f("ix_reliability_events_event_type"), table_name="reliability_events")
    op.drop_index(op.f("ix_reliability_events_engine_position"), table_name="reliability_events")
    op.drop_index(op.f("ix_reliability_events_created_by_user_id"), table_name="reliability_events")
    op.drop_index(op.f("ix_reliability_events_component_id"), table_name="reliability_events")
    op.drop_index(op.f("ix_reliability_events_aircraft_serial_number"), table_name="reliability_events")
    op.drop_index("ix_reliability_events_amo_type", table_name="reliability_events")
    op.drop_index("ix_reliability_events_aircraft_date", table_name="reliability_events")
    op.drop_table("reliability_events")

