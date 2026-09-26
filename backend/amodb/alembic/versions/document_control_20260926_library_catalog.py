"""Add tenant library catalogue, physical holdings, holds and circulation history.

Revision ID: docctl_260926_library_catalog
Revises: quality_260922_people_authz
Create Date: 2026-09-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "docctl_260926_library_catalog"
down_revision = "quality_260922_people_authz"
branch_labels = None
depends_on = None

_TABLES = (
    "document_library_catalog_items",
    "document_library_holdings",
    "document_library_circulation_events",
    "document_library_holds",
)


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _enable_rls(table_name: str) -> None:
    if not _postgres():
        return
    policy = f"{table_name}_tenant_isolation"
    op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f"""
        CREATE POLICY {policy}
        ON "{table_name}"
        USING (tenant_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
        WITH CHECK (tenant_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
    """))


def _disable_rls(table_name: str) -> None:
    if not _postgres():
        return
    policy = f"{table_name}_tenant_isolation"
    op.execute(sa.text(f'DROP POLICY IF EXISTS {policy} ON "{table_name}"'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" NO FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY'))


def _append_only_events() -> None:
    if not _postgres():
        return
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION prevent_document_library_circulation_event_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Library circulation history is append-only';
        END;
        $$ LANGUAGE plpgsql;
    """))
    op.execute(sa.text("""
        CREATE TRIGGER trg_document_library_circulation_events_append_only
        BEFORE UPDATE OR DELETE ON document_library_circulation_events
        FOR EACH ROW EXECUTE FUNCTION prevent_document_library_circulation_event_mutation();
    """))


def upgrade() -> None:
    op.create_table(
        "document_library_catalog_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("catalogue_code", sa.String(length=128), nullable=False),
        sa.Column("material_type", sa.String(length=40), nullable=False, server_default="BOOK"),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("subtitle", sa.String(length=500), nullable=True),
        sa.Column("authors_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb") if _postgres() else None),
        sa.Column("publisher", sa.String(length=255), nullable=True),
        sa.Column("publication_year", sa.Integer(), nullable=True),
        sa.Column("edition", sa.String(length=128), nullable=True),
        sa.Column("language", sa.String(length=32), nullable=True),
        sa.Column("identifiers_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb") if _postgres() else None),
        sa.Column("subjects_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb") if _postgres() else None),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("search_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_provider", sa.String(length=64), nullable=False, server_default="MANUAL"),
        sa.Column("source_record_id", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("cover_url", sa.Text(), nullable=True),
        sa.Column("restricted_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("access_scope_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb") if _postgres() else None),
        sa.Column("circulation_policy_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb") if _postgres() else None),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb") if _postgres() else None),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "catalogue_code", name="uq_doc_library_item_tenant_code"),
        sa.CheckConstraint(
            "material_type IN ('BOOK','JOURNAL','MAGAZINE','REFERENCE','MEDIA','MAP','ARCHIVE_OBJECT','OTHER')",
            name="ck_doc_library_item_material_type",
        ),
        sa.CheckConstraint("status IN ('ACTIVE','ARCHIVED','DELETED')", name="ck_doc_library_item_status"),
    )
    op.create_index("ix_doc_library_item_tenant_type_status", "document_library_catalog_items", ["tenant_id", "material_type", "status"])
    op.create_index("ix_doc_library_item_tenant_title", "document_library_catalog_items", ["tenant_id", "title"])
    if _postgres():
        op.execute(sa.text("""
            CREATE INDEX ix_doc_library_item_search_fts
            ON document_library_catalog_items
            USING gin (to_tsvector('simple', coalesce(search_text, '')))
        """))

    op.create_table(
        "document_library_holdings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("catalog_item_id", sa.String(length=36), sa.ForeignKey("document_library_catalog_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("barcode", sa.String(length=128), nullable=False),
        sa.Column("qr_token", sa.String(length=64), nullable=False),
        sa.Column("accession_number", sa.String(length=128), nullable=True),
        sa.Column("call_number", sa.String(length=128), nullable=True),
        sa.Column("format", sa.String(length=32), nullable=False, server_default="PHYSICAL"),
        sa.Column("home_location", sa.String(length=255), nullable=False),
        sa.Column("current_location", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="AVAILABLE"),
        sa.Column("holder_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("checked_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("renewal_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_inventory_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acquired_on", sa.Date(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb") if _postgres() else None),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "barcode", name="uq_doc_library_holding_tenant_barcode"),
        sa.UniqueConstraint("tenant_id", "qr_token", name="uq_doc_library_holding_tenant_qr"),
        sa.CheckConstraint(
            "status IN ('AVAILABLE','CHECKED_OUT','ON_HOLD','LOST','DAMAGED','WITHDRAWN','IN_REPAIR')",
            name="ck_doc_library_holding_status",
        ),
        sa.CheckConstraint("renewal_count >= 0", name="ck_doc_library_holding_renewals"),
    )
    op.create_index("ix_doc_library_holding_tenant_status", "document_library_holdings", ["tenant_id", "status"])
    op.create_index("ix_doc_library_holding_catalog_status", "document_library_holdings", ["catalog_item_id", "status"])
    op.create_index("ix_doc_library_holding_holder_due", "document_library_holdings", ["holder_user_id", "due_at"])

    op.create_table(
        "document_library_circulation_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("holding_id", sa.String(length=36), sa.ForeignKey("document_library_holdings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("patron_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column("from_location", sa.String(length=255), nullable=True),
        sa.Column("to_location", sa.String(length=255), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb") if _postgres() else None),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_doc_library_event_holding_created", "document_library_circulation_events", ["holding_id", "created_at"])
    op.create_index("ix_doc_library_event_tenant_patron", "document_library_circulation_events", ["tenant_id", "patron_user_id", "created_at"])

    op.create_table(
        "document_library_holds",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("catalog_item_id", sa.String(length=36), sa.ForeignKey("document_library_catalog_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("pickup_location", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fulfilled_holding_id", sa.String(length=36), sa.ForeignKey("document_library_holdings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('ACTIVE','READY','FULFILLED','CANCELLED','EXPIRED')", name="ck_doc_library_hold_status"),
    )
    op.create_index("ix_doc_library_hold_item_status", "document_library_holds", ["catalog_item_id", "status", "created_at"])
    op.create_index("ix_doc_library_hold_user_status", "document_library_holds", ["tenant_id", "user_id", "status"])

    for table in _TABLES:
        _enable_rls(table)
    _append_only_events()


def downgrade() -> None:
    if _postgres():
        op.execute(sa.text(
            "DROP TRIGGER IF EXISTS trg_document_library_circulation_events_append_only "
            "ON document_library_circulation_events"
        ))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_document_library_circulation_event_mutation()"))
    for table in reversed(_TABLES):
        _disable_rls(table)

    op.drop_index("ix_doc_library_hold_user_status", table_name="document_library_holds")
    op.drop_index("ix_doc_library_hold_item_status", table_name="document_library_holds")
    op.drop_table("document_library_holds")

    op.drop_index("ix_doc_library_event_tenant_patron", table_name="document_library_circulation_events")
    op.drop_index("ix_doc_library_event_holding_created", table_name="document_library_circulation_events")
    op.drop_table("document_library_circulation_events")

    op.drop_index("ix_doc_library_holding_holder_due", table_name="document_library_holdings")
    op.drop_index("ix_doc_library_holding_catalog_status", table_name="document_library_holdings")
    op.drop_index("ix_doc_library_holding_tenant_status", table_name="document_library_holdings")
    op.drop_table("document_library_holdings")

    if _postgres():
        op.execute(sa.text("DROP INDEX IF EXISTS ix_doc_library_item_search_fts"))
    op.drop_index("ix_doc_library_item_tenant_title", table_name="document_library_catalog_items")
    op.drop_index("ix_doc_library_item_tenant_type_status", table_name="document_library_catalog_items")
    op.drop_table("document_library_catalog_items")
