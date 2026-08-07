from __future__ import annotations

from alembic import op
import sqlalchemy as sa

UUID = sa.String(36)
NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade_u5() -> None:
    op.create_table(
        "aircraft_inductions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("amo_id", UUID, sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(50), sa.ForeignKey("aircraft.serial_number", ondelete="RESTRICT"), nullable=False),
        sa.Column("registration", sa.String(20), nullable=False),
        sa.Column("type_revision_id", UUID, sa.ForeignKey("aircraft_type_template_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("programme_revision_id", UUID, sa.ForeignKey("tenant_maintenance_programme_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="COMPLETED"),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("amo_id", "idempotency_key", name="uq_aircraft_induction_idempotency"),
        sa.UniqueConstraint("amo_id", "aircraft_serial_number", name="uq_aircraft_induction_aircraft"),
        sa.CheckConstraint("status = 'COMPLETED'", name="ck_aircraft_induction_status"),
    )
    op.create_index("ix_aircraft_induction_scope", "aircraft_inductions", ["amo_id", "registration", "status"])

    op.create_table(
        "aircraft_configuration_snapshots",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("induction_id", UUID, sa.ForeignKey("aircraft_inductions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amo_id", UUID, sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(50), sa.ForeignKey("aircraft.serial_number", ondelete="RESTRICT"), nullable=False),
        sa.Column("type_revision_id", UUID, sa.ForeignKey("aircraft_type_template_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("induction_id", name="uq_aircraft_configuration_snapshot_induction"),
    )
    op.create_index("ix_aircraft_configuration_snapshot_aircraft", "aircraft_configuration_snapshots", ["amo_id", "aircraft_serial_number"])

    op.create_table(
        "aircraft_applicability_snapshots",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("induction_id", UUID, sa.ForeignKey("aircraft_inductions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amo_id", UUID, sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(50), sa.ForeignKey("aircraft.serial_number", ondelete="RESTRICT"), nullable=False),
        sa.Column("programme_revision_id", UUID, sa.ForeignKey("tenant_maintenance_programme_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("context_json", sa.JSON(), nullable=False),
        sa.Column("task_results_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("induction_id", name="uq_aircraft_applicability_snapshot_induction"),
    )
    op.create_index("ix_aircraft_applicability_snapshot_aircraft", "aircraft_applicability_snapshots", ["amo_id", "aircraft_serial_number"])

    op.create_table(
        "aircraft_configuration_snapshot_items",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("snapshot_id", UUID, sa.ForeignKey("aircraft_configuration_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position_code", sa.String(50), nullable=False),
        sa.Column("definition_id", UUID, sa.ForeignKey("aircraft_type_component_definitions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("aircraft_component_id", sa.Integer(), sa.ForeignKey("aircraft_components.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("part_number", sa.String(50), nullable=True),
        sa.Column("serial_number", sa.String(50), nullable=True),
        sa.Column("baseline_hours", sa.Numeric(14, 2), nullable=True),
        sa.Column("baseline_cycles", sa.BigInteger(), nullable=True),
        sa.Column("source_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint("snapshot_id", "position_code", name="uq_aircraft_configuration_snapshot_position"),
    )
    op.create_index("ix_aircraft_configuration_snapshot_item_definition", "aircraft_configuration_snapshot_items", ["definition_id"])

    op.create_table(
        "aircraft_engineering_lineage",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("induction_id", UUID, sa.ForeignKey("aircraft_inductions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amo_id", UUID, sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(50), sa.ForeignKey("aircraft.serial_number", ondelete="RESTRICT"), nullable=False),
        sa.Column("type_revision_id", UUID, sa.ForeignKey("aircraft_type_template_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("programme_revision_id", UUID, sa.ForeignKey("tenant_maintenance_programme_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("configuration_snapshot_id", UUID, sa.ForeignKey("aircraft_configuration_snapshots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("applicability_snapshot_id", UUID, sa.ForeignKey("aircraft_applicability_snapshots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("type_content_hash", sa.String(64), nullable=False),
        sa.Column("programme_content_hash", sa.String(64), nullable=False),
        sa.Column("lineage_hash", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("induction_id", name="uq_aircraft_engineering_lineage_induction"),
        sa.UniqueConstraint("aircraft_serial_number", name="uq_aircraft_engineering_lineage_aircraft"),
    )
    op.create_index("ix_aircraft_engineering_lineage_scope", "aircraft_engineering_lineage", ["amo_id", "type_revision_id", "programme_revision_id"])

    op.create_table(
        "aircraft_component_utilisation_roles",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("amo_id", UUID, sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aircraft_component_id", sa.Integer(), sa.ForeignKey("aircraft_components.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("assignment_source", sa.String(24), nullable=False),
        sa.Column("source_definition_id", UUID, sa.ForeignKey("aircraft_type_component_definitions.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("source_reference", sa.String(255), nullable=False),
        sa.Column("assigned_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("aircraft_component_id", name="uq_aircraft_component_utilisation_role_component"),
        sa.CheckConstraint("role IN ('ENGINE','PROPELLER','APU','OTHER')", name="ck_aircraft_component_utilisation_role"),
        sa.CheckConstraint("assignment_source IN ('TYPE_DEFINITION','MANUAL_APPROVED')", name="ck_aircraft_component_utilisation_role_source"),
    )
    op.create_index("ix_aircraft_component_utilisation_role_scope", "aircraft_component_utilisation_roles", ["amo_id", "role"])

    op.create_table(
        "aircraft_exact_utilisation_states",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("amo_id", UUID, sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(50), sa.ForeignKey("aircraft.serial_number", ondelete="CASCADE"), nullable=False),
        sa.Column("total_hours", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_cycles", sa.BigInteger(), nullable=False),
        sa.Column("last_entry_id", UUID, sa.ForeignKey("aircraft_daily_utilisation_entries.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("approved_source_reference", sa.String(255), nullable=False),
        sa.Column("approved_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("amo_id", "aircraft_serial_number", name="uq_aircraft_exact_utilisation_state"),
        sa.CheckConstraint("total_hours >= 0", name="ck_aircraft_exact_hours_nonneg"),
        sa.CheckConstraint("total_cycles >= 0", name="ck_aircraft_exact_cycles_nonneg"),
    )
    op.create_index("ix_aircraft_exact_utilisation_scope", "aircraft_exact_utilisation_states", ["amo_id", "aircraft_serial_number"])

    op.create_table(
        "component_exact_utilisation_states",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("amo_id", UUID, sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aircraft_component_id", sa.Integer(), sa.ForeignKey("aircraft_components.id", ondelete="CASCADE"), nullable=False),
        sa.Column("total_hours", sa.Numeric(14, 2), nullable=True),
        sa.Column("total_cycles", sa.BigInteger(), nullable=True),
        sa.Column("last_entry_id", UUID, sa.ForeignKey("aircraft_daily_utilisation_entries.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("approved_source_reference", sa.String(255), nullable=False),
        sa.Column("approved_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("aircraft_component_id", name="uq_component_exact_utilisation_state"),
        sa.CheckConstraint("total_hours IS NULL OR total_hours >= 0", name="ck_component_exact_hours_nonneg"),
        sa.CheckConstraint("total_cycles IS NULL OR total_cycles >= 0", name="ck_component_exact_cycles_nonneg"),
    )
    op.create_index("ix_component_exact_utilisation_scope", "component_exact_utilisation_states", ["amo_id", "aircraft_component_id"])


def downgrade_u5() -> None:
    op.drop_index("ix_component_exact_utilisation_scope", table_name="component_exact_utilisation_states")
    op.drop_table("component_exact_utilisation_states")
    op.drop_index("ix_aircraft_exact_utilisation_scope", table_name="aircraft_exact_utilisation_states")
    op.drop_table("aircraft_exact_utilisation_states")
    op.drop_index("ix_aircraft_component_utilisation_role_scope", table_name="aircraft_component_utilisation_roles")
    op.drop_table("aircraft_component_utilisation_roles")
    op.drop_index("ix_aircraft_engineering_lineage_scope", table_name="aircraft_engineering_lineage")
    op.drop_table("aircraft_engineering_lineage")
    op.drop_index("ix_aircraft_configuration_snapshot_item_definition", table_name="aircraft_configuration_snapshot_items")
    op.drop_table("aircraft_configuration_snapshot_items")
    op.drop_index("ix_aircraft_applicability_snapshot_aircraft", table_name="aircraft_applicability_snapshots")
    op.drop_table("aircraft_applicability_snapshots")
    op.drop_index("ix_aircraft_configuration_snapshot_aircraft", table_name="aircraft_configuration_snapshots")
    op.drop_table("aircraft_configuration_snapshots")
    op.drop_index("ix_aircraft_induction_scope", table_name="aircraft_inductions")
    op.drop_table("aircraft_inductions")
