"""add billing and licensing tables

Revision ID: 1b2c3d4e6f70
Revises: 0f1e4ad3c5b1
Create Date: 2025-12-30 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "1b2c3d4e6f70"
down_revision: Union[str, Sequence[str], None] = "0f1e4ad3c5b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ensure_pg_enum(enum_name: str, values: Sequence[str]) -> None:
    """
    Create a PostgreSQL ENUM type only if it does not already exist.

    This avoids failures when:
    - migrations were run before and the ENUM types remained
    - tables were dropped but types were not
    - Alembic/SQLAlchemy tries to recreate the ENUM during table creation
    """
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


def _drop_pg_enum_safely(enum_name: str) -> None:
    """
    Drop a PostgreSQL ENUM type if it exists.
    Do not fail downgrade if something still depends on it.
    """
    op.execute(
        sa.text(
            f"""
DO $$
BEGIN
    EXECUTE 'DROP TYPE IF EXISTS {enum_name}';
EXCEPTION
    WHEN dependent_objects_still_exist THEN
        -- If some other object still depends on the type, do not break downgrade.
        NULL;
END $$;
"""
        )
    )


def upgrade() -> None:
    # --- Ensure enums exist (idempotent) ---
    _ensure_pg_enum("billing_term_enum", ("MONTHLY", "ANNUAL", "BI_ANNUAL"))
    _ensure_pg_enum("license_status_enum", ("TRIALING", "ACTIVE", "CANCELLED", "EXPIRED"))
    _ensure_pg_enum(
        "ledger_entry_type_enum", ("CHARGE", "REFUND", "ADJUSTMENT", "PAYMENT", "USAGE")
    )
    _ensure_pg_enum("payment_provider_enum", ("STRIPE", "OFFLINE", "MANUAL"))

    # IMPORTANT:
    # Use dialect ENUM + create_type=False so table creation does NOT attempt CREATE TYPE again.
    billing_term_enum = postgresql.ENUM(
        "MONTHLY",
        "ANNUAL",
        "BI_ANNUAL",
        name="billing_term_enum",
        create_type=False,
    )
    license_status_enum = postgresql.ENUM(
        "TRIALING",
        "ACTIVE",
        "CANCELLED",
        "EXPIRED",
        name="license_status_enum",
        create_type=False,
    )
    ledger_entry_type_enum = postgresql.ENUM(
        "CHARGE",
        "REFUND",
        "ADJUSTMENT",
        "PAYMENT",
        "USAGE",
        name="ledger_entry_type_enum",
        create_type=False,
    )
    payment_provider_enum = postgresql.ENUM(
        "STRIPE",
        "OFFLINE",
        "MANUAL",
        name="payment_provider_enum",
        create_type=False,
    )

    op.create_table(
        "catalog_skus",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("term", billing_term_enum, nullable=False),
        sa.Column("trial_days", sa.Integer(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "amount_cents >= 0", name=op.f("ck_catalog_skus_amount_nonneg")
        ),
        sa.CheckConstraint(
            "trial_days >= 0", name=op.f("ck_catalog_skus_trial_days_nonneg")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_skus")),
        sa.UniqueConstraint("code", name=op.f("uq_catalog_skus_code")),
    )
    op.create_index(op.f("ix_catalog_skus_code"), "catalog_skus", ["code"], unique=True)
    op.create_index(
        op.f("ix_catalog_skus_is_active"),
        "catalog_skus",
        ["is_active"],
        unique=False,
    )
    op.create_index(op.f("ix_catalog_skus_term"), "catalog_skus", ["term"], unique=False)

    op.create_table(
        "tenant_licenses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("sku_id", sa.String(length=36), nullable=False),
        sa.Column("term", billing_term_enum, nullable=False),
        sa.Column("status", license_status_enum, nullable=False),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["amo_id"],
            ["amos.id"],
            name=op.f("fk_tenant_licenses_amo_id_amos"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sku_id"],
            ["catalog_skus.id"],
            name=op.f("fk_tenant_licenses_sku_id_catalog_skus"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant_licenses")),
    )
    op.create_index(
        op.f("ix_tenant_licenses_amo_id"),
        "tenant_licenses",
        ["amo_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tenant_licenses_sku_id"),
        "tenant_licenses",
        ["sku_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tenant_licenses_status"),
        "tenant_licenses",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tenant_licenses_term"),
        "tenant_licenses",
        ["term"],
        unique=False,
    )
    op.create_index(
        "idx_tenant_licenses_status_term",
        "tenant_licenses",
        ["status", "term"],
        unique=False,
    )

    op.create_table(
        "license_entitlements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("license_id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("limit", sa.Integer(), nullable=True),
        sa.Column("is_unlimited", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["license_id"],
            ["tenant_licenses.id"],
            name=op.f("fk_license_entitlements_license_id_tenant_licenses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_license_entitlements")),
        sa.UniqueConstraint(
            "license_id", "key", name=op.f("uq_license_entitlement_unique")
        ),
    )
    op.create_index(
        op.f("ix_license_entitlements_license_id"),
        "license_entitlements",
        ["license_id"],
        unique=False,
    )

    op.create_table(
        "usage_meters",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("license_id", sa.String(length=36), nullable=True),
        sa.Column("meter_key", sa.String(length=128), nullable=False),
        sa.Column("used_units", sa.Integer(), nullable=False),
        sa.Column("last_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["amo_id"],
            ["amos.id"],
            name=op.f("fk_usage_meters_amo_id_amos"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["license_id"],
            ["tenant_licenses.id"],
            name=op.f("fk_usage_meters_license_id_tenant_licenses"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_meters")),
        sa.UniqueConstraint("amo_id", "meter_key", name=op.f("uq_usage_meter_key")),
    )
    # FIX: Alembic expects unique as a keyword arg (not a positional arg).
    op.create_index(
        op.f("ix_usage_meters_amo_id"),
        "usage_meters",
        ["amo_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_usage_meters_license_id"),
        "usage_meters",
        ["license_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_usage_meters_meter_key"),
        "usage_meters",
        ["meter_key"],
        unique=False,
    )

    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("license_id", sa.String(length=36), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("entry_type", ledger_entry_type_enum, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["amo_id"],
            ["amos.id"],
            name=op.f("fk_ledger_entries_amo_id_amos"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["license_id"],
            ["tenant_licenses.id"],
            name=op.f("fk_ledger_entries_license_id_tenant_licenses"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ledger_entries")),
        sa.UniqueConstraint(
            "amo_id",
            "idempotency_key",
            name=op.f("uq_ledger_entry_idempotent"),
        ),
    )
    # FIX: unique must be keyword arg.
    op.create_index(
        op.f("ix_ledger_entries_amo_id"),
        "ledger_entries",
        ["amo_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ledger_entries_entry_type"),
        "ledger_entries",
        ["entry_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ledger_entries_license_id"),
        "ledger_entries",
        ["license_id"],
        unique=False,
    )
    op.create_index(
        "idx_ledger_entries_amo_recorded",
        "ledger_entries",
        ["amo_id", "recorded_at"],
        unique=False,
    )

    op.create_table(
        "payment_methods",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("provider", payment_provider_enum, nullable=False),
        sa.Column("external_ref", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("card_last4", sa.String(length=4), nullable=True),
        sa.Column("card_exp_month", sa.Integer(), nullable=True),
        sa.Column("card_exp_year", sa.Integer(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["amo_id"],
            ["amos.id"],
            name=op.f("fk_payment_methods_amo_id_amos"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_methods")),
        sa.UniqueConstraint(
            "amo_id",
            "provider",
            "external_ref",
            name=op.f("uq_payment_method_external_ref"),
        ),
    )
    # FIX: unique must be keyword arg.
    op.create_index(
        op.f("ix_payment_methods_amo_id"),
        "payment_methods",
        ["amo_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_methods_is_default"),
        "payment_methods",
        ["is_default"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_methods_provider"),
        "payment_methods",
        ["provider"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_payment_methods_provider"), table_name="payment_methods")
    op.drop_index(op.f("ix_payment_methods_is_default"), table_name="payment_methods")
    op.drop_index(op.f("ix_payment_methods_amo_id"), table_name="payment_methods")
    op.drop_table("payment_methods")

    op.drop_index("idx_ledger_entries_amo_recorded", table_name="ledger_entries")
    op.drop_index(op.f("ix_ledger_entries_license_id"), table_name="ledger_entries")
    op.drop_index(op.f("ix_ledger_entries_entry_type"), table_name="ledger_entries")
    op.drop_index(op.f("ix_ledger_entries_amo_id"), table_name="ledger_entries")
    op.drop_table("ledger_entries")

    op.drop_index(op.f("ix_usage_meters_meter_key"), table_name="usage_meters")
    op.drop_index(op.f("ix_usage_meters_license_id"), table_name="usage_meters")
    op.drop_index(op.f("ix_usage_meters_amo_id"), table_name="usage_meters")
    op.drop_table("usage_meters")

    op.drop_index(
        op.f("ix_license_entitlements_license_id"),
        table_name="license_entitlements",
    )
    op.drop_table("license_entitlements")

    op.drop_index("idx_tenant_licenses_status_term", table_name="tenant_licenses")
    op.drop_index(op.f("ix_tenant_licenses_term"), table_name="tenant_licenses")
    op.drop_index(op.f("ix_tenant_licenses_status"), table_name="tenant_licenses")
    op.drop_index(op.f("ix_tenant_licenses_sku_id"), table_name="tenant_licenses")
    op.drop_index(op.f("ix_tenant_licenses_amo_id"), table_name="tenant_licenses")
    op.drop_table("tenant_licenses")

    op.drop_index(op.f("ix_catalog_skus_term"), table_name="catalog_skus")
    op.drop_index(op.f("ix_catalog_skus_is_active"), table_name="catalog_skus")
    op.drop_index(op.f("ix_catalog_skus_code"), table_name="catalog_skus")
    op.drop_table("catalog_skus")

    # Drop enums last, and do not fail downgrade if they still have dependencies.
    _drop_pg_enum_safely("payment_provider_enum")
    _drop_pg_enum_safely("ledger_entry_type_enum")
    _drop_pg_enum_safely("license_status_enum")
    _drop_pg_enum_safely("billing_term_enum")
