"""create missing billing invoice and quality CAR tables

Revision ID: a4d6f8b0c2e1
Revises: s9t8u7v6w5x4
Create Date: 2026-02-11 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a4d6f8b0c2e1"
down_revision: Union[str, Sequence[str], None] = "s9t8u7v6w5x4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _pg_enum_ensure_values(enum_name: str, values: Sequence[str]) -> None:
    value_literals = ", ".join([f"'{v}'" for v in values])
    op.execute(
        sa.text(
            f"""
DO $$
DECLARE
    v text;
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = '{enum_name}'
          AND n.nspname = current_schema()
    ) THEN
        FOREACH v IN ARRAY ARRAY[{value_literals}] LOOP
            IF NOT EXISTS (
                SELECT 1
                FROM pg_enum e
                JOIN pg_type t2 ON t2.oid = e.enumtypid
                JOIN pg_namespace n2 ON n2.oid = t2.typnamespace
                WHERE t2.typname = '{enum_name}'
                  AND n2.nspname = current_schema()
                  AND e.enumlabel = v
            ) THEN
                EXECUTE format('ALTER TYPE {enum_name} ADD VALUE %L', v);
            END IF;
        END LOOP;
    END IF;
END $$;
"""
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    _pg_enum_ensure_values("invoice_status_enum", ("DRAFT", "FINALIZED", "VOID", "PENDING", "PAID"))

    if not insp.has_table("billing_invoices"):
        invoice_status_enum = postgresql.ENUM(
            "DRAFT",
            "FINALIZED",
            "VOID",
            "PENDING",
            "PAID",
            name="invoice_status_enum",
            create_type=False,
        )
        op.create_table(
            "billing_invoices",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("amo_id", sa.String(length=36), nullable=False),
            sa.Column("license_id", sa.String(length=36), nullable=True),
            sa.Column("ledger_entry_id", sa.String(length=36), nullable=True),
            sa.Column("amount_cents", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(length=8), nullable=False),
            sa.Column("status", invoice_status_enum, nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("idempotency_key", sa.String(length=128), nullable=False),
            sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], name=op.f("fk_billing_invoices_amo_id_amos"), ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["ledger_entry_id"], ["ledger_entries.id"], name=op.f("fk_billing_invoices_ledger_entry_id_ledger_entries"), ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["license_id"], ["tenant_licenses.id"], name=op.f("fk_billing_invoices_license_id_tenant_licenses"), ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_billing_invoices")),
            sa.UniqueConstraint("amo_id", "idempotency_key", name=op.f("uq_invoice_idempotency")),
        )
        op.create_index(op.f("ix_billing_invoices_amo_id"), "billing_invoices", ["amo_id"], unique=False)
        op.create_index(op.f("ix_billing_invoices_issued_at"), "billing_invoices", ["issued_at"], unique=False)
        op.create_index(op.f("ix_billing_invoices_ledger_entry_id"), "billing_invoices", ["ledger_entry_id"], unique=False)
        op.create_index(op.f("ix_billing_invoices_license_id"), "billing_invoices", ["license_id"], unique=False)
        op.create_index(op.f("ix_billing_invoices_status"), "billing_invoices", ["status"], unique=False)

    if not insp.has_table("quality_cars"):
        op.create_table(
            "quality_cars",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("program", sa.Enum("QUALITY", "RELIABILITY", name="quality_car_program", native_enum=False), nullable=False),
            sa.Column("car_number", sa.String(length=32), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("requested_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("assigned_to_user_id", sa.String(length=36), nullable=True),
            sa.Column("priority", sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="quality_car_priority", native_enum=False), nullable=False),
            sa.Column("status", sa.Enum("DRAFT", "OPEN", "IN_PROGRESS", "PENDING_VERIFICATION", "CLOSED", "ESCALATED", "CANCELLED", name="quality_car_status", native_enum=False), nullable=False),
            sa.Column("invite_token", sa.String(length=128), nullable=True),
            sa.Column("reminder_interval_days", sa.Integer(), nullable=False),
            sa.Column("next_reminder_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("containment_action", sa.Text(), nullable=True),
            sa.Column("root_cause", sa.Text(), nullable=True),
            sa.Column("corrective_action", sa.Text(), nullable=True),
            sa.Column("preventive_action", sa.Text(), nullable=True),
            sa.Column("evidence_ref", sa.String(length=512), nullable=True),
            sa.Column("submitted_by_name", sa.String(length=255), nullable=True),
            sa.Column("submitted_by_email", sa.String(length=255), nullable=True),
            sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("target_closure_date", sa.Date(), nullable=True),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finding_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], name=op.f("fk_quality_cars_assigned_to_user_id_users"), ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["finding_id"], ["qms_audit_findings.id"], name=op.f("fk_quality_cars_finding_id_qms_audit_findings"), ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], name=op.f("fk_quality_cars_requested_by_user_id_users"), ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_quality_cars")),
            sa.UniqueConstraint("invite_token", name=op.f("uq_quality_cars_invite_token")),
            sa.UniqueConstraint("program", "car_number", name="uq_quality_car_number"),
        )
        op.create_index(op.f("ix_quality_cars_assigned_to_user_id"), "quality_cars", ["assigned_to_user_id"], unique=False)
        op.create_index(op.f("ix_quality_cars_car_number"), "quality_cars", ["car_number"], unique=False)
        op.create_index(op.f("ix_quality_cars_due_date"), "quality_cars", ["due_date"], unique=False)
        op.create_index(op.f("ix_quality_cars_escalated_at"), "quality_cars", ["escalated_at"], unique=False)
        op.create_index(op.f("ix_quality_cars_finding_id"), "quality_cars", ["finding_id"], unique=False)
        op.create_index(op.f("ix_quality_cars_next_reminder_at"), "quality_cars", ["next_reminder_at"], unique=False)
        op.create_index(op.f("ix_quality_cars_priority"), "quality_cars", ["priority"], unique=False)
        op.create_index(op.f("ix_quality_cars_program"), "quality_cars", ["program"], unique=False)
        op.create_index(op.f("ix_quality_cars_requested_by_user_id"), "quality_cars", ["requested_by_user_id"], unique=False)
        op.create_index(op.f("ix_quality_cars_status"), "quality_cars", ["status"], unique=False)
        op.create_index(op.f("ix_quality_cars_submitted_at"), "quality_cars", ["submitted_at"], unique=False)
        op.create_index("ix_quality_cars_program_status", "quality_cars", ["program", "status"], unique=False)
        op.create_index("ix_quality_cars_program_due", "quality_cars", ["program", "due_date"], unique=False)
        op.create_index("ix_quality_cars_reminders", "quality_cars", ["next_reminder_at"], unique=False)

    if not insp.has_table("quality_car_actions"):
        op.create_table(
            "quality_car_actions",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("car_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("action_type", sa.Enum("COMMENT", "STATUS_CHANGE", "REMINDER", "ESCALATION", "ASSIGNMENT", name="quality_car_action_type", native_enum=False), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("actor_user_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name=op.f("fk_quality_car_actions_actor_user_id_users"), ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["car_id"], ["quality_cars.id"], name=op.f("fk_quality_car_actions_car_id_quality_cars"), ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_quality_car_actions")),
        )
        op.create_index(op.f("ix_quality_car_actions_action_type"), "quality_car_actions", ["action_type"], unique=False)
        op.create_index(op.f("ix_quality_car_actions_actor_user_id"), "quality_car_actions", ["actor_user_id"], unique=False)
        op.create_index(op.f("ix_quality_car_actions_car_id"), "quality_car_actions", ["car_id"], unique=False)
        op.create_index("ix_quality_car_actions_car_type", "quality_car_actions", ["car_id", "action_type"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("quality_car_actions"):
        op.drop_index("ix_quality_car_actions_car_type", table_name="quality_car_actions")
        op.drop_index(op.f("ix_quality_car_actions_car_id"), table_name="quality_car_actions")
        op.drop_index(op.f("ix_quality_car_actions_actor_user_id"), table_name="quality_car_actions")
        op.drop_index(op.f("ix_quality_car_actions_action_type"), table_name="quality_car_actions")
        op.drop_table("quality_car_actions")

    if insp.has_table("quality_cars"):
        op.drop_index("ix_quality_cars_reminders", table_name="quality_cars")
        op.drop_index("ix_quality_cars_program_due", table_name="quality_cars")
        op.drop_index("ix_quality_cars_program_status", table_name="quality_cars")
        op.drop_index(op.f("ix_quality_cars_submitted_at"), table_name="quality_cars")
        op.drop_index(op.f("ix_quality_cars_status"), table_name="quality_cars")
        op.drop_index(op.f("ix_quality_cars_requested_by_user_id"), table_name="quality_cars")
        op.drop_index(op.f("ix_quality_cars_program"), table_name="quality_cars")
        op.drop_index(op.f("ix_quality_cars_priority"), table_name="quality_cars")
        op.drop_index(op.f("ix_quality_cars_next_reminder_at"), table_name="quality_cars")
        op.drop_index(op.f("ix_quality_cars_finding_id"), table_name="quality_cars")
        op.drop_index(op.f("ix_quality_cars_escalated_at"), table_name="quality_cars")
        op.drop_index(op.f("ix_quality_cars_due_date"), table_name="quality_cars")
        op.drop_index(op.f("ix_quality_cars_car_number"), table_name="quality_cars")
        op.drop_index(op.f("ix_quality_cars_assigned_to_user_id"), table_name="quality_cars")
        op.drop_table("quality_cars")

    if insp.has_table("billing_invoices"):
        op.drop_index(op.f("ix_billing_invoices_status"), table_name="billing_invoices")
        op.drop_index(op.f("ix_billing_invoices_license_id"), table_name="billing_invoices")
        op.drop_index(op.f("ix_billing_invoices_ledger_entry_id"), table_name="billing_invoices")
        op.drop_index(op.f("ix_billing_invoices_issued_at"), table_name="billing_invoices")
        op.drop_index(op.f("ix_billing_invoices_amo_id"), table_name="billing_invoices")
        op.drop_table("billing_invoices")
