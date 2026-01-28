"""Add finance and inventory module tables.

Revision ID: 2c4d7e9f0a1b
Revises: 0f1e4ad3c5b1
Create Date: 2025-02-14 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "2c4d7e9f0a1b"
down_revision = "0f1e4ad3c5b1"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return bool(insp.has_table(table_name))


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table(table_name):
        return False
    cols = insp.get_columns(table_name)
    return any(c.get("name") == column_name for c in cols)


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table(table_name):
        return False
    idxs = insp.get_indexes(table_name)
    return any(i.get("name") == index_name for i in idxs)


def _has_fk_on_columns(table_name: str, constrained_columns: Sequence[str]) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table(table_name):
        return False
    want = set(constrained_columns)
    for fk in insp.get_foreign_keys(table_name):
        cols = set(fk.get("constrained_columns") or [])
        if cols == want:
            return True
    return False


def _pg_enum_create_if_missing(enum_name: str, values: Sequence[str]) -> None:
    quoted_vals = ", ".join([f"'{v}'" for v in values])
    op.execute(
        sa.text(
            f"""
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typname = '{enum_name}'
          AND n.nspname = current_schema()
    ) THEN
        CREATE TYPE {enum_name} AS ENUM ({quoted_vals});
    END IF;
END $$;
"""
        )
    )


def _pg_enum_ensure_values(enum_name: str, values: Sequence[str]) -> None:
    _pg_enum_create_if_missing(enum_name, values)
    for v in values:
        op.execute(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{v}'")


def upgrade() -> None:
    conn = op.get_bind()

    # --- Extend existing role enum (idempotent on Postgres) ---
    if conn.dialect.name == "postgresql":
        op.execute("ALTER TYPE account_role_enum ADD VALUE IF NOT EXISTS 'FINANCE_MANAGER'")
        op.execute("ALTER TYPE account_role_enum ADD VALUE IF NOT EXISTS 'ACCOUNTS_OFFICER'")
        op.execute("ALTER TYPE account_role_enum ADD VALUE IF NOT EXISTS 'STORES_MANAGER'")
        op.execute("ALTER TYPE account_role_enum ADD VALUE IF NOT EXISTS 'STOREKEEPER'")
        op.execute("ALTER TYPE account_role_enum ADD VALUE IF NOT EXISTS 'PROCUREMENT_OFFICER'")
        op.execute("ALTER TYPE account_role_enum ADD VALUE IF NOT EXISTS 'QUALITY_INSPECTOR'")
        op.execute("ALTER TYPE account_role_enum ADD VALUE IF NOT EXISTS 'AUDITOR'")

        # --- Ensure all new enums exist + values (idempotent) ---
        _pg_enum_ensure_values("module_subscription_status_enum", ("ENABLED", "DISABLED", "TRIAL", "SUSPENDED"))
        _pg_enum_ensure_values(
            "inventory_movement_type_enum",
            ("RECEIVE", "INSPECT", "TRANSFER", "ISSUE", "RETURN", "SCRAP", "VENDOR_RETURN", "ADJUSTMENT", "CYCLE_COUNT"),
        )
        _pg_enum_ensure_values("inventory_condition_enum", ("QUARANTINE", "SERVICEABLE", "UNSERVICEABLE"))
        _pg_enum_ensure_values("purchase_order_status_enum", ("DRAFT", "SUBMITTED", "APPROVED", "CLOSED", "CANCELLED"))
        _pg_enum_ensure_values("goods_receipt_status_enum", ("DRAFT", "POSTED"))
        _pg_enum_ensure_values("goods_receipt_condition_enum", ("QUARANTINE", "SERVICEABLE", "UNSERVICEABLE"))
        _pg_enum_ensure_values("tax_type_enum", ("VAT", "GST", "SALES", "NONE"))
        _pg_enum_ensure_values("gl_account_type_enum", ("ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE"))
        _pg_enum_ensure_values("invoice_status_enum", ("DRAFT", "FINALIZED", "VOID"))
        _pg_enum_ensure_values("credit_note_status_enum", ("DRAFT", "FINALIZED", "VOID"))
        _pg_enum_ensure_values("payment_status_enum", ("RECEIVED", "VOID"))
        _pg_enum_ensure_values("journal_status_enum", ("DRAFT", "POSTED", "REVERSED"))
        _pg_enum_ensure_values("accounting_period_status_enum", ("OPEN", "CLOSED"))

    # Dialect enums with create_type=False (do not attempt CREATE TYPE during table creation)
    module_subscription_status_enum = postgresql.ENUM(
        "ENABLED", "DISABLED", "TRIAL", "SUSPENDED", name="module_subscription_status_enum", create_type=False
    )
    inventory_movement_type_enum = postgresql.ENUM(
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
        create_type=False,
    )
    inventory_condition_enum = postgresql.ENUM(
        "QUARANTINE", "SERVICEABLE", "UNSERVICEABLE", name="inventory_condition_enum", create_type=False
    )
    purchase_order_status_enum = postgresql.ENUM(
        "DRAFT", "SUBMITTED", "APPROVED", "CLOSED", "CANCELLED", name="purchase_order_status_enum", create_type=False
    )
    goods_receipt_status_enum = postgresql.ENUM("DRAFT", "POSTED", name="goods_receipt_status_enum", create_type=False)
    goods_receipt_condition_enum = postgresql.ENUM(
        "QUARANTINE", "SERVICEABLE", "UNSERVICEABLE", name="goods_receipt_condition_enum", create_type=False
    )
    tax_type_enum = postgresql.ENUM("VAT", "GST", "SALES", "NONE", name="tax_type_enum", create_type=False)
    gl_account_type_enum = postgresql.ENUM(
        "ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE", name="gl_account_type_enum", create_type=False
    )
    invoice_status_enum = postgresql.ENUM("DRAFT", "FINALIZED", "VOID", name="invoice_status_enum", create_type=False)
    credit_note_status_enum = postgresql.ENUM(
        "DRAFT", "FINALIZED", "VOID", name="credit_note_status_enum", create_type=False
    )
    payment_status_enum = postgresql.ENUM("RECEIVED", "VOID", name="payment_status_enum", create_type=False)
    journal_status_enum = postgresql.ENUM("DRAFT", "POSTED", "REVERSED", name="journal_status_enum", create_type=False)
    accounting_period_status_enum = postgresql.ENUM(
        "OPEN", "CLOSED", name="accounting_period_status_enum", create_type=False
    )

    # -------------------------
    # module_subscriptions
    # -------------------------
    if not _table_exists("module_subscriptions"):
        op.create_table(
            "module_subscriptions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("module_code", sa.String(length=64), nullable=False),
            sa.Column("status", module_subscription_status_enum, nullable=False),
            sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
            sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
            sa.Column("plan_code", sa.String(length=64), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("amo_id", "module_code", name="uq_module_subscription"),
        )
    if _table_exists("module_subscriptions") and not _index_exists("module_subscriptions", "ix_module_subscriptions_amo"):
        op.create_index("ix_module_subscriptions_amo", "module_subscriptions", ["amo_id"])

    # -------------------------
    # part_movement_ledger safe column adds
    # -------------------------
    if not _column_exists("part_movement_ledger", "reason_code"):
        op.add_column("part_movement_ledger", sa.Column("reason_code", sa.String(length=64), nullable=True))

    if not _column_exists("part_movement_ledger", "created_by_user_id"):
        op.add_column("part_movement_ledger", sa.Column("created_by_user_id", sa.String(length=36), nullable=True))

    if _column_exists("part_movement_ledger", "created_by_user_id"):
        if not _index_exists("part_movement_ledger", "ix_part_movement_created_by"):
            op.create_index("ix_part_movement_created_by", "part_movement_ledger", ["created_by_user_id"])
        if not _has_fk_on_columns("part_movement_ledger", ["created_by_user_id"]):
            op.create_foreign_key(
                "fk_part_movement_created_by",
                "part_movement_ledger",
                "users",
                ["created_by_user_id"],
                ["id"],
                ondelete="SET NULL",
            )

    # -------------------------
    # Inventory master data
    # -------------------------
    if not _table_exists("inventory_parts"):
        op.create_table(
            "inventory_parts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("part_number", sa.String(length=64), nullable=False),
            sa.Column("description", sa.String(length=255), nullable=True),
            sa.Column("uom", sa.String(length=16), nullable=False),
            sa.Column("is_serialized", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("is_lot_controlled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("amo_id", "part_number", name="uq_inventory_part_number"),
        )
    if _table_exists("inventory_parts") and not _index_exists("inventory_parts", "ix_inventory_parts_amo_part"):
        op.create_index("ix_inventory_parts_amo_part", "inventory_parts", ["amo_id", "part_number"])

    if not _table_exists("inventory_locations"):
        op.create_table(
            "inventory_locations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("code", sa.String(length=32), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("amo_id", "code", name="uq_inventory_location_code"),
        )
    if _table_exists("inventory_locations") and not _index_exists("inventory_locations", "ix_inventory_locations_amo"):
        op.create_index("ix_inventory_locations_amo", "inventory_locations", ["amo_id"])

    if not _table_exists("inventory_lots"):
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
    if _table_exists("inventory_lots") and not _index_exists("inventory_lots", "ix_inventory_lots_part"):
        op.create_index("ix_inventory_lots_part", "inventory_lots", ["part_id"])

    if not _table_exists("inventory_serials"):
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
    if _table_exists("inventory_serials") and not _index_exists("inventory_serials", "ix_inventory_serials_part"):
        op.create_index("ix_inventory_serials_part", "inventory_serials", ["part_id"])

    if not _table_exists("inventory_movement_ledger"):
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
            sa.Column("event_type", inventory_movement_type_enum, nullable=False),
            sa.Column("condition", inventory_condition_enum, nullable=True),
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
    if _table_exists("inventory_movement_ledger") and not _index_exists("inventory_movement_ledger", "ix_inventory_ledger_amo_date"):
        op.create_index("ix_inventory_ledger_amo_date", "inventory_movement_ledger", ["amo_id", "occurred_at"])
    if _table_exists("inventory_movement_ledger") and not _index_exists("inventory_movement_ledger", "ix_inventory_ledger_part"):
        op.create_index("ix_inventory_ledger_part", "inventory_movement_ledger", ["part_id", "occurred_at"])

    # -------------------------
    # Finance reference tables (no FKs first)
    # -------------------------
    if not _table_exists("currencies"):
        op.create_table(
            "currencies",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(length=8), nullable=False),
            sa.Column("name", sa.String(length=64), nullable=False),
            sa.Column("symbol", sa.String(length=8), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.UniqueConstraint("code", name="uq_currency_code"),
        )

    if not _table_exists("tax_codes"):
        op.create_table(
            "tax_codes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(length=32), nullable=False),
            sa.Column("description", sa.String(length=128), nullable=True),
            sa.Column("tax_type", tax_type_enum, nullable=False),
            sa.Column("rate", sa.Numeric(6, 4), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.UniqueConstraint("code", name="uq_tax_code"),
        )

    # -------------------------
    # Customers + Vendors must exist BEFORE purchase_orders (fixes your error)
    # -------------------------
    if not _table_exists("customers"):
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
    if _table_exists("customers") and not _index_exists("customers", "ix_customers_amo"):
        op.create_index("ix_customers_amo", "customers", ["amo_id"])

    if not _table_exists("vendors"):
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
    if _table_exists("vendors") and not _index_exists("vendors", "ix_vendors_amo"):
        op.create_index("ix_vendors_amo", "vendors", ["amo_id"])

    # -------------------------
    # GL accounts
    # -------------------------
    if not _table_exists("gl_accounts"):
        op.create_table(
            "gl_accounts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("code", sa.String(length=32), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("account_type", gl_account_type_enum, nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.UniqueConstraint("amo_id", "code", name="uq_gl_account_code"),
        )
    if _table_exists("gl_accounts") and not _index_exists("gl_accounts", "ix_gl_accounts_amo"):
        op.create_index("ix_gl_accounts_amo", "gl_accounts", ["amo_id"])

    # -------------------------
    # Procurement (purchase_orders depends on vendors)
    # -------------------------
    if not _table_exists("purchase_orders"):
        op.create_table(
            "purchase_orders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("po_number", sa.String(length=64), nullable=False),
            sa.Column("vendor_id", sa.Integer(), sa.ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True),
            sa.Column("status", purchase_order_status_enum, nullable=False),
            sa.Column("currency", sa.String(length=8), nullable=False),
            sa.Column("requested_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("approved_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("amo_id", "po_number", name="uq_purchase_order_number"),
        )
    if _table_exists("purchase_orders") and not _index_exists("purchase_orders", "ix_purchase_orders_amo"):
        op.create_index("ix_purchase_orders_amo", "purchase_orders", ["amo_id"])

    if not _table_exists("purchase_order_lines"):
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
    if _table_exists("purchase_order_lines") and not _index_exists("purchase_order_lines", "ix_purchase_order_lines_po"):
        op.create_index("ix_purchase_order_lines_po", "purchase_order_lines", ["purchase_order_id"])

    if not _table_exists("goods_receipts"):
        op.create_table(
            "goods_receipts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("purchase_order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("received_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("status", goods_receipt_status_enum, nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
        )
    if _table_exists("goods_receipts") and not _index_exists("goods_receipts", "ix_goods_receipts_amo"):
        op.create_index("ix_goods_receipts_amo", "goods_receipts", ["amo_id"])

    if not _table_exists("goods_receipt_lines"):
        op.create_table(
            "goods_receipt_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("goods_receipt_id", sa.Integer(), sa.ForeignKey("goods_receipts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("part_id", sa.Integer(), sa.ForeignKey("inventory_parts.id", ondelete="SET NULL"), nullable=True),
            sa.Column("lot_number", sa.String(length=64), nullable=True),
            sa.Column("serial_number", sa.String(length=64), nullable=True),
            sa.Column("quantity", sa.Float(), nullable=False),
            sa.Column("uom", sa.String(length=16), nullable=False),
            sa.Column("condition", goods_receipt_condition_enum, nullable=True),
            sa.Column("location_id", sa.Integer(), sa.ForeignKey("inventory_locations.id", ondelete="SET NULL"), nullable=True),
        )
    if _table_exists("goods_receipt_lines") and not _index_exists("goods_receipt_lines", "ix_goods_receipt_lines_receipt"):
        op.create_index("ix_goods_receipt_lines_receipt", "goods_receipt_lines", ["goods_receipt_id"])

    # -------------------------
    # AR / Billing docs (depends on customers/tax_codes/inventory_movement_ledger)
    # -------------------------
    if not _table_exists("finance_invoices"):
        op.create_table(
            "finance_invoices",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("invoice_number", sa.String(length=64), nullable=False),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
            sa.Column("status", invoice_status_enum, nullable=False),
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
    if _table_exists("finance_invoices") and not _index_exists("finance_invoices", "ix_finance_invoices_amo"):
        op.create_index("ix_finance_invoices_amo", "finance_invoices", ["amo_id"])

    if not _table_exists("finance_invoice_lines"):
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
    if _table_exists("finance_invoice_lines") and not _index_exists("finance_invoice_lines", "ix_invoice_lines_invoice"):
        op.create_index("ix_invoice_lines_invoice", "finance_invoice_lines", ["invoice_id"])

    if not _table_exists("finance_credit_notes"):
        op.create_table(
            "finance_credit_notes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("credit_note_number", sa.String(length=64), nullable=False),
            sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("finance_invoices.id", ondelete="SET NULL"), nullable=True),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
            sa.Column("status", credit_note_status_enum, nullable=False),
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
    if _table_exists("finance_credit_notes") and not _index_exists("finance_credit_notes", "ix_credit_notes_amo"):
        op.create_index("ix_credit_notes_amo", "finance_credit_notes", ["amo_id"])

    if not _table_exists("finance_payments"):
        op.create_table(
            "finance_payments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("currency", sa.String(length=8), nullable=False),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", payment_status_enum, nullable=False),
            sa.Column("reference", sa.String(length=128), nullable=True),
            sa.Column("idempotency_key", sa.String(length=128), nullable=False),
            sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.UniqueConstraint("amo_id", "idempotency_key", name="uq_payment_idempotency"),
        )
    if _table_exists("finance_payments") and not _index_exists("finance_payments", "ix_payments_amo"):
        op.create_index("ix_payments_amo", "finance_payments", ["amo_id"])

    if not _table_exists("payment_allocations"):
        op.create_table(
            "payment_allocations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("payment_id", sa.Integer(), sa.ForeignKey("finance_payments.id", ondelete="CASCADE"), nullable=False),
            sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("finance_invoices.id", ondelete="SET NULL"), nullable=True),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        )
    if _table_exists("payment_allocations") and not _index_exists("payment_allocations", "ix_payment_allocations_payment"):
        op.create_index("ix_payment_allocations_payment", "payment_allocations", ["payment_id"])

    # -------------------------
    # Journals
    # -------------------------
    if not _table_exists("journal_entries"):
        op.create_table(
            "journal_entries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("description", sa.String(length=255), nullable=False),
            sa.Column("entry_date", sa.Date(), nullable=False),
            sa.Column("status", journal_status_enum, nullable=False),
            sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("posted_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("reversal_of_id", sa.Integer(), sa.ForeignKey("journal_entries.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if _table_exists("journal_entries") and not _index_exists("journal_entries", "ix_journal_entries_amo"):
        op.create_index("ix_journal_entries_amo", "journal_entries", ["amo_id"])

    if not _table_exists("journal_lines"):
        op.create_table(
            "journal_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("journal_entry_id", sa.Integer(), sa.ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False),
            sa.Column("gl_account_id", sa.Integer(), sa.ForeignKey("gl_accounts.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("description", sa.String(length=255), nullable=True),
            sa.Column("debit", sa.Numeric(12, 2), nullable=False),
            sa.Column("credit", sa.Numeric(12, 2), nullable=False),
        )
    if _table_exists("journal_lines") and not _index_exists("journal_lines", "ix_journal_lines_entry"):
        op.create_index("ix_journal_lines_entry", "journal_lines", ["journal_entry_id"])

    # -------------------------
    # Periods
    # -------------------------
    if not _table_exists("accounting_periods"):
        op.create_table(
            "accounting_periods",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("amo_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
            sa.Column("period", sa.String(length=16), nullable=False),
            sa.Column("status", accounting_period_status_enum, nullable=False),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("closed_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.UniqueConstraint("amo_id", "period", name="uq_accounting_period"),
        )
    if _table_exists("accounting_periods") and not _index_exists("accounting_periods", "ix_accounting_periods_amo"):
        op.create_index("ix_accounting_periods_amo", "accounting_periods", ["amo_id"])


def downgrade() -> None:
    # Guarded drops (safe if partially applied)
    if _index_exists("accounting_periods", "ix_accounting_periods_amo"):
        op.drop_index("ix_accounting_periods_amo", table_name="accounting_periods")
    if _table_exists("accounting_periods"):
        op.drop_table("accounting_periods")

    if _index_exists("journal_lines", "ix_journal_lines_entry"):
        op.drop_index("ix_journal_lines_entry", table_name="journal_lines")
    if _table_exists("journal_lines"):
        op.drop_table("journal_lines")

    if _index_exists("journal_entries", "ix_journal_entries_amo"):
        op.drop_index("ix_journal_entries_amo", table_name="journal_entries")
    if _table_exists("journal_entries"):
        op.drop_table("journal_entries")

    if _index_exists("payment_allocations", "ix_payment_allocations_payment"):
        op.drop_index("ix_payment_allocations_payment", table_name="payment_allocations")
    if _table_exists("payment_allocations"):
        op.drop_table("payment_allocations")

    if _index_exists("finance_payments", "ix_payments_amo"):
        op.drop_index("ix_payments_amo", table_name="finance_payments")
    if _table_exists("finance_payments"):
        op.drop_table("finance_payments")

    if _index_exists("finance_credit_notes", "ix_credit_notes_amo"):
        op.drop_index("ix_credit_notes_amo", table_name="finance_credit_notes")
    if _table_exists("finance_credit_notes"):
        op.drop_table("finance_credit_notes")

    if _index_exists("finance_invoice_lines", "ix_invoice_lines_invoice"):
        op.drop_index("ix_invoice_lines_invoice", table_name="finance_invoice_lines")
    if _table_exists("finance_invoice_lines"):
        op.drop_table("finance_invoice_lines")

    if _index_exists("finance_invoices", "ix_finance_invoices_amo"):
        op.drop_index("ix_finance_invoices_amo", table_name="finance_invoices")
    if _table_exists("finance_invoices"):
        op.drop_table("finance_invoices")

    if _index_exists("goods_receipt_lines", "ix_goods_receipt_lines_receipt"):
        op.drop_index("ix_goods_receipt_lines_receipt", table_name="goods_receipt_lines")
    if _table_exists("goods_receipt_lines"):
        op.drop_table("goods_receipt_lines")

    if _index_exists("goods_receipts", "ix_goods_receipts_amo"):
        op.drop_index("ix_goods_receipts_amo", table_name="goods_receipts")
    if _table_exists("goods_receipts"):
        op.drop_table("goods_receipts")

    if _index_exists("purchase_order_lines", "ix_purchase_order_lines_po"):
        op.drop_index("ix_purchase_order_lines_po", table_name="purchase_order_lines")
    if _table_exists("purchase_order_lines"):
        op.drop_table("purchase_order_lines")

    if _index_exists("purchase_orders", "ix_purchase_orders_amo"):
        op.drop_index("ix_purchase_orders_amo", table_name="purchase_orders")
    if _table_exists("purchase_orders"):
        op.drop_table("purchase_orders")

    if _index_exists("gl_accounts", "ix_gl_accounts_amo"):
        op.drop_index("ix_gl_accounts_amo", table_name="gl_accounts")
    if _table_exists("gl_accounts"):
        op.drop_table("gl_accounts")

    if _index_exists("vendors", "ix_vendors_amo"):
        op.drop_index("ix_vendors_amo", table_name="vendors")
    if _table_exists("vendors"):
        op.drop_table("vendors")

    if _index_exists("customers", "ix_customers_amo"):
        op.drop_index("ix_customers_amo", table_name="customers")
    if _table_exists("customers"):
        op.drop_table("customers")

    if _table_exists("tax_codes"):
        op.drop_table("tax_codes")
    if _table_exists("currencies"):
        op.drop_table("currencies")

    if _index_exists("inventory_movement_ledger", "ix_inventory_ledger_part"):
        op.drop_index("ix_inventory_ledger_part", table_name="inventory_movement_ledger")
    if _index_exists("inventory_movement_ledger", "ix_inventory_ledger_amo_date"):
        op.drop_index("ix_inventory_ledger_amo_date", table_name="inventory_movement_ledger")
    if _table_exists("inventory_movement_ledger"):
        op.drop_table("inventory_movement_ledger")

    if _index_exists("inventory_serials", "ix_inventory_serials_part"):
        op.drop_index("ix_inventory_serials_part", table_name="inventory_serials")
    if _table_exists("inventory_serials"):
        op.drop_table("inventory_serials")

    if _index_exists("inventory_lots", "ix_inventory_lots_part"):
        op.drop_index("ix_inventory_lots_part", table_name="inventory_lots")
    if _table_exists("inventory_lots"):
        op.drop_table("inventory_lots")

    if _index_exists("inventory_locations", "ix_inventory_locations_amo"):
        op.drop_index("ix_inventory_locations_amo", table_name="inventory_locations")
    if _table_exists("inventory_locations"):
        op.drop_table("inventory_locations")

    if _index_exists("inventory_parts", "ix_inventory_parts_amo_part"):
        op.drop_index("ix_inventory_parts_amo_part", table_name="inventory_parts")
    if _table_exists("inventory_parts"):
        op.drop_table("inventory_parts")

    # Drop FK/index we created on part_movement_ledger only if present
    bind = op.get_bind()
    if bind.dialect.name == "postgresql" and _table_exists("part_movement_ledger"):
        insp = inspect(bind)
        fk_names = {fk.get("name") for fk in insp.get_foreign_keys("part_movement_ledger")}
        if "fk_part_movement_created_by" in fk_names:
            op.drop_constraint("fk_part_movement_created_by", "part_movement_ledger", type_="foreignkey")
    if _index_exists("part_movement_ledger", "ix_part_movement_created_by"):
        op.drop_index("ix_part_movement_created_by", table_name="part_movement_ledger")

    # Do NOT drop shared columns in downgrade (they may be owned by another branch/migration)

    if _index_exists("module_subscriptions", "ix_module_subscriptions_amo"):
        op.drop_index("ix_module_subscriptions_amo", table_name="module_subscriptions")
    if _table_exists("module_subscriptions"):
        op.drop_table("module_subscriptions")
