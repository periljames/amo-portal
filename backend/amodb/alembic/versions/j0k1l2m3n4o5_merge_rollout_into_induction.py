"""merge rollout lineage into universal induction

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-08-05 08:35:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "j0k1l2m3n4o5"
down_revision = "i9j0k1l2m3n4"
branch_labels = None
depends_on = None


def _find_fk(table_name: str, column_name: str) -> str | None:
    for fk in inspect(op.get_bind()).get_foreign_keys(table_name):
        if fk.get("constrained_columns") == [column_name]:
            return fk.get("name")
    return None


def _drop_if_exists(table_name: str) -> None:
    if inspect(op.get_bind()).has_table(table_name):
        op.drop_table(table_name)


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("rollout_wave_aircraft")}
    if "migration_batch_id" in columns:
        fk_name = _find_fk("rollout_wave_aircraft", "migration_batch_id")
        if fk_name:
            op.drop_constraint(fk_name, "rollout_wave_aircraft", type_="foreignkey")
        op.alter_column("rollout_wave_aircraft", "migration_batch_id", new_column_name="induction_id")
    op.execute("UPDATE rollout_wave_aircraft SET induction_id = NULL")
    if not _find_fk("rollout_wave_aircraft", "induction_id"):
        op.create_foreign_key(
            "fk_rollout_wave_aircraft_induction",
            "rollout_wave_aircraft",
            "aircraft_inductions",
            ["induction_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_rollout_wave_aircraft_induction", "rollout_wave_aircraft", ["induction_id"])

    for table_name in (
        "migration_reconciliation_items",
        "migration_checkpoints",
        "migration_rows",
        "migration_batches",
    ):
        _drop_if_exists(table_name)


def downgrade() -> None:
    op.create_table(
        "migration_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("preset", sa.String(64)),
        sa.Column("target_aircraft_serial_number", sa.String(50), sa.ForeignKey("aircraft.serial_number", ondelete="SET NULL")),
        sa.Column("target_registration", sa.String(20)),
        sa.Column("source_type", sa.String(24), nullable=False, server_default="SPREADSHEET"),
        sa.Column("source_reference", sa.String(255)),
        sa.Column("status", sa.String(24), nullable=False, server_default="DRAFT"),
        sa.Column("mode", sa.String(16), nullable=False, server_default="DRY_RUN"),
        sa.Column("scope_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("summary_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("cutover_checklist_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("rollback_manifest_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("approved_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("committed_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("committed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("amo_id", "name", name="uq_migration_batch_amo_name"),
    )
    op.create_table(
        "migration_rows",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("migration_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset", sa.String(32), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(160), nullable=False),
        sa.Column("raw_json", sa.JSON(), nullable=False),
        sa.Column("normalized_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("errors_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("local_object_type", sa.String(64)),
        sa.Column("local_object_id", sa.String(64)),
        sa.Column("before_json", sa.JSON()),
        sa.Column("after_json", sa.JSON()),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "migration_checkpoints",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("migration_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("checkpoint_key", sa.String(64), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("completed_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "migration_reconciliation_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("migration_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_id", sa.String(36), sa.ForeignKey("migration_rows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(48), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_json", sa.JSON(), nullable=False),
        sa.Column("local_json", sa.JSON(), nullable=False),
        sa.Column("differences_json", sa.JSON(), nullable=False),
        sa.Column("resolution", sa.String(24)),
        sa.Column("resolution_notes", sa.Text()),
        sa.Column("resolved_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    fk_name = _find_fk("rollout_wave_aircraft", "induction_id")
    if fk_name:
        op.drop_constraint(fk_name, "rollout_wave_aircraft", type_="foreignkey")
    op.drop_index("ix_rollout_wave_aircraft_induction", table_name="rollout_wave_aircraft")
    op.alter_column("rollout_wave_aircraft", "induction_id", new_column_name="migration_batch_id")
    op.create_foreign_key(
        "fk_rollout_wave_aircraft_migration_batch",
        "rollout_wave_aircraft",
        "migration_batches",
        ["migration_batch_id"],
        ["id"],
        ondelete="SET NULL",
    )
