"""Add finance and inventory module tables.

Revision ID: 2c4d7e9f0a1b
Revises: 0f1e4ad3c5b1
Create Date: 2025-02-14 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2c4d7e9f0a1b"
down_revision = "0f1e4ad3c5b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("ALTER TYPE account_role_enum ADD VALUE IF NOT EXISTS 'FINANCE_MANAGER'")
        op.execute("ALTER TYPE account_role_enum ADD VALUE IF NOT EXISTS 'ACCOUNTS_OFFICER'")
        op.execute("ALTER TYPE account_role_enum ADD VALUE IF NOT EXISTS 'STORES_MANAGER'")
        op.execute("ALTER TYPE account_role_enum ADD VALUE IF NOT EXISTS 'STOREKEEPER'")
        op.execute("ALTER TYPE account_role_enum ADD VALUE IF NOT EXISTS 'PROCUREMENT_OFFICER'")
        op.execute("ALTER TYPE account_role_enum ADD VALUE IF NOT EXISTS 'QUALITY_INSPECTOR'")
        op.execute("ALTER TYPE account_role_enum ADD VALUE IF NOT EXISTS 'AUDITOR'")

    op.create_table(
        "module_subscriptions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("module_code", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ENABLED",
                "DISABLED",
                "TRIAL",
                "SUSPENDED",
                name="module_subscription_status_enum",
            ),
            nullable=False,
        ),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("plan_code", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("amo_id", "module_code", name="uq_module_subscription"),
    )
    op.create_index("ix_module_subscriptions_amo", "module_subscriptions", ["amo_id"])

    op.add_column("part_movement_ledger", sa.Column("reason_code", sa.String(length=64), nullable=True))
    op.add_column(
        "part_movement_ledger",
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
    )
    op.create_index("ix_part_movement_created_by", "part_movement_ledger", ["created_by_user_id"])
    op.create_foreign_key(
        "fk_part_movement_created_by",
        "part_movement_ledger",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "inventory_parts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("part_number", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("uom", sa.String(length=16), nullable=False),
        sa.Column("is_serialized", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_lot_controlled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("amo_id", "part_number", name="uq_inventory_part_number"),
    )
    op.create_index("ix_inventory_parts_amo_part", "inventory_parts", ["amo_id", "part_number"])

    op.create_table(
        "inventory_locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("amo_id", "code", name="uq_inventory_location_code"),
    )
    op.create_index("ix_inventory_locations_amo", "inventory_locations", ["amo_id"])

    op.create_table(
        "inventory_lots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("part_id", sa.Integer(), sa.ForeignKey("inventory_parts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lot_number", sa.String(length=64), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("received_date", sa.Date(), nullable=True),
        sa.UniqueConstraint("amo_id", "part_id", "lot_number", name="uq_inventory_lot"),
    )
    op.create_index("ix_inventory_lots_part", "inventory_lots", ["part_id"])

    op.create_table(
        "inventory_serials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("part_id", sa.Integer(), sa.ForeignKey("inventory_parts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("serial_number", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("amo_id", "part_id", "serial_number", name="uq_inventory_serial"),
    )
    op.create_index("ix_inventory_serials_part", "inventory_serials", ["part_id"])

    op.create_table(
        "inventory_movement_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("part_id", sa.Integer(), sa.ForeignKey("inventory_parts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lot_id", sa.Integer(), sa.ForeignKey("inventory_lots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("serial_id", sa.Integer(), sa.ForeignKey("inventory_serials.id", ondelete="SET NULL"), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("uom", sa.String(length=16), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "RECEIVE",
                "INSPECT",
                "TRANSFER",
                "ISSUE",
                "RETURN",
                "SCRAP",
                "VENDOR_RETURN",
                "ADJUSTMENT",
                "CYCLE_COUNT",
                name="inventory_movement_type_enum",
            ),
            nullable=False,
        ),
        sa.Column(
            "condition",
            sa.Enum(
                "QUARANTINE",
                "SERVICEABLE",
                "UNSERVICEABLE",
                name="inventory_condition_enum",
            ),
            nullable=True,
        ),
        sa.Column("from_location_id", sa.Integer(), sa.ForeignKey("inventory_locations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("to_location_id", sa.Integer(), sa.ForeignKey("inventory_locations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("task_card_id", sa.Integer(), sa.ForeignKey("task_cards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reference_type", sa.String(length=64), nullable=True),
        sa.Column("reference_id", sa.String(length=64), nullable=True),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("amo_id", "idempotency_key", name="uq_inventory_ledger_idempotency"),
    )
    op.create_index("ix_inventory_ledger_amo_date", "inventory_movement_ledger", ["amo_id", "occurred_at"])
    op.create_index("ix_inventory_ledger_part", "inventory_movement_ledger", ["part_id", "occurred_at"])

    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("po_number", sa.String(length=64), nullable=False),
        sa.Column("vendor_id", sa.Integer(), sa.ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "SUBMITTED",
                "APPROVED",
                "CLOSED",
                "CANCELLED",
                name="purchase_order_status_enum",
            ),
            nullable=False,
        ),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("requested_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("amo_id", "po_number", name="uq_purchase_order_number"),
    )
    op.create_index("ix_purchase_orders_amo", "purchase_orders", ["amo_id"])

    op.create_table(
        "purchase_order_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("purchase_order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("part_id", sa.Integer(), sa.ForeignKey("inventory_parts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("uom", sa.String(length=16), nullable=False),
        sa.Column("unit_price", sa.Float(), nullable=False),
    )
    op.create_index("ix_purchase_order_lines_po", "purchase_order_lines", ["purchase_order_id"])

    op.create_table(
        "goods_receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purchase_order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "POSTED", name="goods_receipt_status_enum"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_goods_receipts_amo", "goods_receipts", ["amo_id"])

    op.create_table(
        "goods_receipt_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("goods_receipt_id", sa.Integer(), sa.ForeignKey("goods_receipts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("part_id", sa.Integer(), sa.ForeignKey("inventory_parts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lot_number", sa.String(length=64), nullable=True),
        sa.Column("serial_number", sa.String(length=64), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("uom", sa.String(length=16), nullable=False),
        sa.Column(
            "condition",
            sa.Enum(
                "QUARANTINE",
                "SERVICEABLE",
                "UNSERVICEABLE",
                name="goods_receipt_condition_enum",
            ),
            nullable=True,
        ),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("inventory_locations.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_goods_receipt_lines_receipt", "goods_receipt_lines", ["goods_receipt_id"])

    op.create_table(
        "currencies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=8), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("code", name="uq_currency_code"),
    )

    op.create_table(
        "tax_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=128), nullable=True),
        sa.Column(
            "tax_type",
            sa.Enum("VAT", "GST", "SALES", "NONE", name="tax_type_enum"),
            nullable=False,
        ),
        sa.Column("rate", sa.Numeric(6, 4), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("code", name="uq_tax_code"),
    )

    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("billing_address", sa.Text(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("amo_id", "code", name="uq_customer_code"),
    )
    op.create_index("ix_customers_amo", "customers", ["amo_id"])

    op.create_table(
        "vendors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("remit_to_address", sa.Text(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("amo_id", "code", name="uq_vendor_code"),
    )
    op.create_index("ix_vendors_amo", "vendors", ["amo_id"])

    op.create_table(
        "gl_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "account_type",
            sa.Enum("ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE", name="gl_account_type_enum"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("amo_id", "code", name="uq_gl_account_code"),
    )
    op.create_index("ix_gl_accounts_amo", "gl_accounts", ["amo_id"])

    op.create_table(
        "finance_invoices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invoice_number", sa.String(length=64), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "FINALIZED", "VOID", name="invoice_status_enum"),
            nullable=False,
        ),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("issued_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("tax_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("amo_id", "invoice_number", name="uq_invoice_number"),
        sa.UniqueConstraint("amo_id", "idempotency_key", name="uq_finance_invoice_idempotency"),
    )
    op.create_index("ix_finance_invoices_amo", "finance_invoices", ["amo_id"])

    op.create_table(
        "finance_invoice_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("finance_invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("tax_code_id", sa.Integer(), sa.ForeignKey("tax_codes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("inventory_movement_id", sa.Integer(), sa.ForeignKey("inventory_movement_ledger.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_invoice_lines_invoice", "finance_invoice_lines", ["invoice_id"])

    op.create_table(
        "finance_credit_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("credit_note_number", sa.String(length=64), nullable=False),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("finance_invoices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "FINALIZED", "VOID", name="credit_note_status_enum"),
            nullable=False,
        ),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("tax_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("amo_id", "credit_note_number", name="uq_credit_note_number"),
        sa.UniqueConstraint("amo_id", "idempotency_key", name="uq_credit_note_idempotency"),
    )
    op.create_index("ix_credit_notes_amo", "finance_credit_notes", ["amo_id"])

    op.create_table(
        "finance_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("RECEIVED", "VOID", name="payment_status_enum"),
            nullable=False,
        ),
        sa.Column("reference", sa.String(length=128), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("amo_id", "idempotency_key", name="uq_payment_idempotency"),
    )
    op.create_index("ix_payments_amo", "finance_payments", ["amo_id"])

    op.create_table(
        "payment_allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("finance_payments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("finance_invoices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
    )
    op.create_index("ix_payment_allocations_payment", "payment_allocations", ["payment_id"])

    op.create_table(
        "journal_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "POSTED", "REVERSED", name="journal_status_enum"),
            nullable=False,
        ),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("posted_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reversal_of_id", sa.Integer(), sa.ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_journal_entries_amo", "journal_entries", ["amo_id"])

    op.create_table(
        "journal_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("journal_entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gl_account_id", sa.Integer(), sa.ForeignKey("gl_accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("debit", sa.Numeric(12, 2), nullable=False),
        sa.Column("credit", sa.Numeric(12, 2), nullable=False),
    )
    op.create_index("ix_journal_lines_entry", "journal_lines", ["journal_entry_id"])

    op.create_table(
        "accounting_periods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", sa.String(length=16), nullable=False),
        sa.Column(
            "status",
            sa.Enum("OPEN", "CLOSED", name="accounting_period_status_enum"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("amo_id", "period", name="uq_accounting_period"),
    )
    op.create_index("ix_accounting_periods_amo", "accounting_periods", ["amo_id"])


def downgrade() -> None:
    op.drop_index("ix_accounting_periods_amo", table_name="accounting_periods")
    op.drop_table("accounting_periods")

    op.drop_index("ix_journal_lines_entry", table_name="journal_lines")
    op.drop_table("journal_lines")

    op.drop_index("ix_journal_entries_amo", table_name="journal_entries")
    op.drop_table("journal_entries")

    op.drop_index("ix_payment_allocations_payment", table_name="payment_allocations")
    op.drop_table("payment_allocations")

    op.drop_index("ix_payments_amo", table_name="finance_payments")
    op.drop_table("finance_payments")

    op.drop_index("ix_credit_notes_amo", table_name="finance_credit_notes")
    op.drop_table("finance_credit_notes")

    op.drop_index("ix_invoice_lines_invoice", table_name="finance_invoice_lines")
    op.drop_table("finance_invoice_lines")

    op.drop_index("ix_finance_invoices_amo", table_name="finance_invoices")
    op.drop_table("finance_invoices")

    op.drop_index("ix_gl_accounts_amo", table_name="gl_accounts")
    op.drop_table("gl_accounts")

    op.drop_index("ix_vendors_amo", table_name="vendors")
    op.drop_table("vendors")

    op.drop_index("ix_customers_amo", table_name="customers")
    op.drop_table("customers")

    op.drop_table("tax_codes")
    op.drop_table("currencies")

    op.drop_index("ix_goods_receipt_lines_receipt", table_name="goods_receipt_lines")
    op.drop_table("goods_receipt_lines")

    op.drop_index("ix_goods_receipts_amo", table_name="goods_receipts")
    op.drop_table("goods_receipts")

    op.drop_index("ix_purchase_order_lines_po", table_name="purchase_order_lines")
    op.drop_table("purchase_order_lines")

    op.drop_index("ix_purchase_orders_amo", table_name="purchase_orders")
    op.drop_table("purchase_orders")

    op.drop_index("ix_inventory_ledger_part", table_name="inventory_movement_ledger")
    op.drop_index("ix_inventory_ledger_amo_date", table_name="inventory_movement_ledger")
    op.drop_table("inventory_movement_ledger")

    op.drop_index("ix_inventory_serials_part", table_name="inventory_serials")
    op.drop_table("inventory_serials")

    op.drop_index("ix_inventory_lots_part", table_name="inventory_lots")
    op.drop_table("inventory_lots")

    op.drop_index("ix_inventory_locations_amo", table_name="inventory_locations")
    op.drop_table("inventory_locations")

    op.drop_index("ix_inventory_parts_amo_part", table_name="inventory_parts")
    op.drop_table("inventory_parts")

    op.drop_constraint("fk_part_movement_created_by", "part_movement_ledger", type_="foreignkey")
    op.drop_index("ix_part_movement_created_by", table_name="part_movement_ledger")
    op.drop_column("part_movement_ledger", "created_by_user_id")
    op.drop_column("part_movement_ledger", "reason_code")

    op.drop_index("ix_module_subscriptions_amo", table_name="module_subscriptions")
    op.drop_table("module_subscriptions")
