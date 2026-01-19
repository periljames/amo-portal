"""add multi-tenant workflow scaffold

Revision ID: e4b7d1a2c3f4
Revises: d1a2f3b4c5e6
Create Date: 2025-02-06 00:00:00.000000
"""

from __future__ import annotations

from datetime import datetime
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e4b7d1a2c3f4"
down_revision = "d1a2f3b4c5e6"
branch_labels = None
depends_on = None


def _ensure_default_amo(conn) -> str:
    amos = sa.table(
        "amos",
        sa.column("id", sa.String),
        sa.column("amo_code", sa.String),
        sa.column("name", sa.String),
        sa.column("login_slug", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    existing = conn.execute(sa.select(amos.c.id).limit(1)).scalar()
    if existing:
        return existing
    default_id = str(uuid.uuid4())
    conn.execute(
        amos.insert().values(
            id=default_id,
            amo_code="DEFAULT",
            name="Default AMO",
            login_slug="default",
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    return default_id


def upgrade() -> None:
    conn = op.get_bind()
    default_amo_id = _ensure_default_amo(conn)

    # Core tenancy columns
    op.add_column("aircraft", sa.Column("amo_id", sa.String(length=36), nullable=True))
    op.add_column("aircraft_components", sa.Column("amo_id", sa.String(length=36), nullable=True))
    op.add_column("aircraft_components", sa.Column("removed_date", sa.Date(), nullable=True))
    op.add_column("aircraft_components", sa.Column("is_installed", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("aircraft_usage", sa.Column("amo_id", sa.String(length=36), nullable=True))

    op.add_column("work_orders", sa.Column("amo_id", sa.String(length=36), nullable=True))
    op.add_column("work_orders", sa.Column("operator_event_id", sa.String(length=36), nullable=True))
    op.add_column("work_orders", sa.Column("closure_reason", sa.String(length=64), nullable=True))
    op.add_column("work_orders", sa.Column("closure_notes", sa.Text(), nullable=True))
    op.add_column("task_cards", sa.Column("amo_id", sa.String(length=36), nullable=True))
    op.add_column("task_cards", sa.Column("operator_event_id", sa.String(length=36), nullable=True))
    op.add_column("task_assignments", sa.Column("amo_id", sa.String(length=36), nullable=True))
    op.add_column("work_log_entries", sa.Column("amo_id", sa.String(length=36), nullable=True))

    op.add_column("reliability_events", sa.Column("operator_event_id", sa.String(length=36), nullable=True))
    op.add_column("part_movement_ledger", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.add_column("removal_events", sa.Column("removal_tracking_id", sa.String(length=36), nullable=True))

    # Backfill amo_id on existing rows
    for table in [
        "aircraft",
        "aircraft_components",
        "aircraft_usage",
        "work_orders",
        "task_cards",
        "task_assignments",
        "work_log_entries",
    ]:
        conn.execute(sa.text(f"UPDATE {table} SET amo_id = :amo_id WHERE amo_id IS NULL"), {"amo_id": default_amo_id})

    conn.execute(sa.text("UPDATE component_instances SET amo_id = :amo_id WHERE amo_id IS NULL"), {"amo_id": default_amo_id})

    # Backfill removal_tracking_id
    removal_rows = conn.execute(sa.text("SELECT id FROM removal_events WHERE removal_tracking_id IS NULL")).fetchall()
    for row in removal_rows:
        conn.execute(
            sa.text("UPDATE removal_events SET removal_tracking_id = :rid WHERE id = :id"),
            {"rid": str(uuid.uuid4()), "id": row[0]},
        )

    # Work order status normalization
    conn.execute(sa.text("UPDATE work_orders SET status = 'DRAFT' WHERE status = 'OPEN'"))
    conn.execute(sa.text("UPDATE work_orders SET status = 'IN_PROGRESS' WHERE status = 'ON_HOLD'"))

    # Add foreign keys + constraints
    op.create_foreign_key("fk_aircraft_amo_id_amos", "aircraft", "amos", ["amo_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_aircraft_components_amo_id_amos", "aircraft_components", "amos", ["amo_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_aircraft_usage_amo_id_amos", "aircraft_usage", "amos", ["amo_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_work_orders_amo_id_amos", "work_orders", "amos", ["amo_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_task_cards_amo_id_amos", "task_cards", "amos", ["amo_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_task_assignments_amo_id_amos", "task_assignments", "amos", ["amo_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_work_log_entries_amo_id_amos", "work_log_entries", "amos", ["amo_id"], ["id"], ondelete="CASCADE")

    # Nullability updates
    op.alter_column("aircraft", "amo_id", nullable=False)
    op.alter_column("aircraft_components", "amo_id", nullable=False)
    op.alter_column("aircraft_usage", "amo_id", nullable=False)
    op.alter_column("work_orders", "amo_id", nullable=False)
    op.alter_column("task_cards", "amo_id", nullable=False)
    op.alter_column("task_assignments", "amo_id", nullable=False)
    op.alter_column("work_log_entries", "amo_id", nullable=False)
    op.alter_column("component_instances", "amo_id", nullable=False)
    op.alter_column("removal_events", "removal_tracking_id", nullable=False)

    # Unique constraints + indexes
    op.create_unique_constraint("uq_work_orders_amo_number", "work_orders", ["amo_id", "wo_number"])
    op.create_index("ix_work_orders_amo_status", "work_orders", ["amo_id", "status"])
    op.create_index("ix_work_orders_amo_aircraft", "work_orders", ["amo_id", "aircraft_serial_number"])

    op.create_index("ix_task_cards_amo_status", "task_cards", ["amo_id", "status"])
    op.create_index("ix_task_cards_amo_aircraft", "task_cards", ["amo_id", "aircraft_serial_number"])
    op.create_index("ix_task_assignments_amo_status", "task_assignments", ["amo_id", "status"])
    op.create_index("ix_task_assignments_amo_user", "task_assignments", ["amo_id", "user_id"])
    op.create_index("ix_work_log_amo_time", "work_log_entries", ["amo_id", "start_time"])

    op.create_index("ix_aircraft_amo_status_active", "aircraft", ["amo_id", "status", "is_active"])
    op.create_index("ix_aircraft_amo_serial", "aircraft", ["amo_id", "serial_number"])
    op.create_unique_constraint("uq_aircraft_amo_registration", "aircraft", ["amo_id", "registration"])

    op.create_index("ix_aircraft_usage_amo_date", "aircraft_usage", ["amo_id", "date"])

    op.create_unique_constraint("uq_part_movement_idempotency", "part_movement_ledger", ["amo_id", "idempotency_key"])
    op.create_unique_constraint("uq_removal_tracking_id", "removal_events", ["amo_id", "removal_tracking_id"])

    op.create_index(
        "uq_aircraft_component_position_installed",
        "aircraft_components",
        ["amo_id", "aircraft_serial_number", "position"],
        unique=True,
        postgresql_where=sa.text("is_installed = true"),
    )

    # New tables
    op.create_table(
        "task_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("step_no", sa.Integer(), nullable=False),
        sa.Column("instruction_text", sa.Text(), nullable=False),
        sa.Column("required_flag", sa.Boolean(), nullable=False),
        sa.Column("measurement_type", sa.String(length=32), nullable=True),
        sa.Column("expected_range", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["task_cards.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "step_no", name="uq_task_steps_task_stepno"),
    )
    op.create_index("ix_task_steps_task", "task_steps", ["task_id"])

    op.create_table(
        "task_step_executions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("task_step_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("performed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_text", sa.Text(), nullable=True),
        sa.Column("measurement_value", sa.Float(), nullable=True),
        sa.Column("attachment_id", sa.String(length=64), nullable=True),
        sa.Column("signed_flag", sa.Boolean(), nullable=False),
        sa.Column("signature_hash", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["task_cards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_step_id"], ["task_steps.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["performed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_step_exec_task", "task_step_executions", ["task_id", "performed_at"])
    op.create_index("ix_task_step_exec_user", "task_step_executions", ["performed_by_user_id", "performed_at"])

    op.create_table(
        "inspector_signoffs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("task_card_id", sa.Integer(), nullable=True),
        sa.Column("work_order_id", sa.Integer(), nullable=True),
        sa.Column("inspector_user_id", sa.String(length=36), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("signed_flag", sa.Boolean(), nullable=False),
        sa.Column("signature_hash", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_card_id"], ["task_cards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inspector_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inspector_signoffs_task", "inspector_signoffs", ["amo_id", "task_card_id"])
    op.create_index("ix_inspector_signoffs_workorder", "inspector_signoffs", ["amo_id", "work_order_id"])

    op.create_table(
        "aircraft_configuration_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(length=50), nullable=True),
        sa.Column("component_instance_id", sa.Integer(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.Enum("INSTALL", "REMOVE", "SWAP", name="config_event_type_enum", native_enum=False), nullable=False),
        sa.Column("position", sa.String(length=50), nullable=True),
        sa.Column("part_number", sa.String(length=50), nullable=True),
        sa.Column("serial_number", sa.String(length=50), nullable=True),
        sa.Column("from_part_number", sa.String(length=50), nullable=True),
        sa.Column("from_serial_number", sa.String(length=50), nullable=True),
        sa.Column("work_order_id", sa.Integer(), nullable=True),
        sa.Column("task_card_id", sa.Integer(), nullable=True),
        sa.Column("removal_tracking_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["aircraft_serial_number"], ["aircraft.serial_number"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["component_instance_id"], ["component_instances.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_card_id"], ["task_cards.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_config_events_amo_aircraft_date", "aircraft_configuration_events", ["amo_id", "aircraft_serial_number", "occurred_at"])
    op.create_index("ix_config_events_amo_position_date", "aircraft_configuration_events", ["amo_id", "position", "occurred_at"])
    op.create_index("ix_config_events_removal_tracking", "aircraft_configuration_events", ["amo_id", "removal_tracking_id"])

    op.create_table(
        "defect_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(length=50), nullable=True),
        sa.Column("reported_by", sa.String(length=255), nullable=True),
        sa.Column("source", sa.Enum("SYSTEM", "PILOT", "LOGBOOK", "API", name="defect_source_enum", native_enum=False), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("ata_chapter", sa.String(length=20), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("operator_event_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("work_order_id", sa.Integer(), nullable=True),
        sa.Column("task_card_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["aircraft_serial_number"], ["aircraft.serial_number"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_card_id"], ["task_cards.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "operator_event_id", name="uq_defect_report_operator_event"),
        sa.UniqueConstraint("amo_id", "idempotency_key", name="uq_defect_report_idempotency"),
    )
    op.create_index("ix_defect_reports_amo_aircraft", "defect_reports", ["amo_id", "aircraft_serial_number"])
    op.create_index("ix_defect_reports_amo_occurred", "defect_reports", ["amo_id", "occurred_at"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_amo_entity", "audit_events", ["amo_id", "entity_type", "entity_id"])
    op.create_index("ix_audit_events_amo_action", "audit_events", ["amo_id", "action"])
    op.create_index("ix_audit_events_amo_time", "audit_events", ["amo_id", "occurred_at"])

    op.create_table(
        "shop_visits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("shop_record_id", sa.String(length=36), nullable=False),
        sa.Column("component_instance_id", sa.Integer(), nullable=True),
        sa.Column("work_order_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["component_instance_id"], ["component_instances.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "shop_record_id", name="uq_shop_visit_record"),
    )
    op.create_index("ix_shop_visits_component", "shop_visits", ["amo_id", "component_instance_id"])


def downgrade() -> None:
    op.drop_index("ix_shop_visits_component", table_name="shop_visits")
    op.drop_table("shop_visits")

    op.drop_index("ix_audit_events_amo_time", table_name="audit_events")
    op.drop_index("ix_audit_events_amo_action", table_name="audit_events")
    op.drop_index("ix_audit_events_amo_entity", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index("ix_defect_reports_amo_occurred", table_name="defect_reports")
    op.drop_index("ix_defect_reports_amo_aircraft", table_name="defect_reports")
    op.drop_table("defect_reports")

    op.drop_index("ix_config_events_removal_tracking", table_name="aircraft_configuration_events")
    op.drop_index("ix_config_events_amo_position_date", table_name="aircraft_configuration_events")
    op.drop_index("ix_config_events_amo_aircraft_date", table_name="aircraft_configuration_events")
    op.drop_table("aircraft_configuration_events")

    op.drop_index("ix_inspector_signoffs_workorder", table_name="inspector_signoffs")
    op.drop_index("ix_inspector_signoffs_task", table_name="inspector_signoffs")
    op.drop_table("inspector_signoffs")

    op.drop_index("ix_task_step_exec_user", table_name="task_step_executions")
    op.drop_index("ix_task_step_exec_task", table_name="task_step_executions")
    op.drop_table("task_step_executions")

    op.drop_index("ix_task_steps_task", table_name="task_steps")
    op.drop_table("task_steps")

    op.drop_index("uq_aircraft_component_position_installed", table_name="aircraft_components", postgresql_where=sa.text("is_installed = true"))
    op.drop_constraint("uq_part_movement_idempotency", "part_movement_ledger", type_="unique")
    op.drop_constraint("uq_removal_tracking_id", "removal_events", type_="unique")

    op.drop_index("ix_aircraft_usage_amo_date", table_name="aircraft_usage")
    op.drop_index("ix_aircraft_amo_serial", table_name="aircraft")
    op.drop_index("ix_aircraft_amo_status_active", table_name="aircraft")
    op.drop_constraint("uq_aircraft_amo_registration", "aircraft", type_="unique")

    op.drop_index("ix_work_log_amo_time", table_name="work_log_entries")
    op.drop_index("ix_task_assignments_amo_user", table_name="task_assignments")
    op.drop_index("ix_task_assignments_amo_status", table_name="task_assignments")
    op.drop_index("ix_task_cards_amo_aircraft", table_name="task_cards")
    op.drop_index("ix_task_cards_amo_status", table_name="task_cards")
    op.drop_index("ix_work_orders_amo_aircraft", table_name="work_orders")
    op.drop_index("ix_work_orders_amo_status", table_name="work_orders")
    op.drop_constraint("uq_work_orders_amo_number", "work_orders", type_="unique")

    op.drop_column("removal_events", "removal_tracking_id")
    op.drop_column("part_movement_ledger", "idempotency_key")
    op.drop_column("reliability_events", "operator_event_id")

    op.drop_constraint("fk_work_log_entries_amo_id_amos", "work_log_entries", type_="foreignkey")
    op.drop_constraint("fk_task_assignments_amo_id_amos", "task_assignments", type_="foreignkey")
    op.drop_constraint("fk_task_cards_amo_id_amos", "task_cards", type_="foreignkey")
    op.drop_constraint("fk_work_orders_amo_id_amos", "work_orders", type_="foreignkey")
    op.drop_constraint("fk_aircraft_usage_amo_id_amos", "aircraft_usage", type_="foreignkey")
    op.drop_constraint("fk_aircraft_components_amo_id_amos", "aircraft_components", type_="foreignkey")
    op.drop_constraint("fk_aircraft_amo_id_amos", "aircraft", type_="foreignkey")

    op.drop_column("work_log_entries", "amo_id")
    op.drop_column("task_assignments", "amo_id")
    op.drop_column("task_cards", "operator_event_id")
    op.drop_column("task_cards", "amo_id")
    op.drop_column("work_orders", "closure_notes")
    op.drop_column("work_orders", "closure_reason")
    op.drop_column("work_orders", "operator_event_id")
    op.drop_column("work_orders", "amo_id")

    op.drop_column("aircraft_usage", "amo_id")
    op.drop_column("aircraft_components", "is_installed")
    op.drop_column("aircraft_components", "removed_date")
    op.drop_column("aircraft_components", "amo_id")
    op.drop_column("aircraft", "amo_id")

    op.alter_column("component_instances", "amo_id", nullable=True)
