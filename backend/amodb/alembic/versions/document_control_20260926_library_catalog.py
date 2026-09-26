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
    "document_library_catalog_identifiers",
    "document_library_holdings",
    "document_library_circulation_events",
    "document_library_holds",
    "document_library_inventory_sessions",
    "document_library_inventory_observations",
    "document_record_series",
    "document_record_assets",
    "document_record_events",
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
    for table_name, label in (
        ("document_library_circulation_events", "Library circulation history"),
        ("document_record_events", "Record custody history"),
    ):
        function_name = f"prevent_{table_name}_mutation"
        trigger_name = f"trg_{table_name}_append_only"
        op.execute(sa.text(f"""
            CREATE OR REPLACE FUNCTION {function_name}()
            RETURNS trigger AS $append_only$
            BEGIN
                RAISE EXCEPTION '{label} is append-only';
            END;
            $append_only$ LANGUAGE plpgsql;
        """))
        op.execute(sa.text(f"""
            CREATE TRIGGER {trigger_name}
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION {function_name}();
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
        # Controlled documents already store normalized section/block text. These
        # indexes make company-wide content search use the same PostgreSQL search
        # engine instead of repeated wildcard scans over large manuals.
        op.execute(sa.text("""
            CREATE INDEX IF NOT EXISTS ix_manual_sections_heading_fts
            ON manual_sections
            USING gin (to_tsvector('simple', coalesce(heading, '')))
        """))
        op.execute(sa.text("""
            CREATE INDEX IF NOT EXISTS ix_manual_blocks_text_plain_fts
            ON manual_blocks
            USING gin (to_tsvector('simple', coalesce(text_plain, '')))
        """))

    op.create_table(
        "document_library_catalog_identifiers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("catalog_item_id", sa.String(length=36), sa.ForeignKey("document_library_catalog_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scheme", sa.String(length=32), nullable=False),
        sa.Column("normalized_value", sa.String(length=255), nullable=False),
        sa.Column("display_value", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="MANUAL"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "scheme", "normalized_value", name="uq_doc_library_identifier_tenant_scheme_value"),
    )
    op.create_index("ix_doc_library_identifier_item", "document_library_catalog_identifiers", ["catalog_item_id"])
    op.create_index("ix_doc_library_identifier_lookup", "document_library_catalog_identifiers", ["tenant_id", "normalized_value"])

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

    op.create_table(
        "document_library_inventory_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_prefix", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="OPEN"),
        sa.Column("expected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("observed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("misplaced_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("closed_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('OPEN','CLOSED','CANCELLED')", name="ck_doc_library_inventory_status"),
    )
    op.create_index("ix_doc_library_inventory_tenant_status", "document_library_inventory_sessions", ["tenant_id", "status", "started_at"])

    op.create_table(
        "document_library_inventory_observations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("document_library_inventory_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("holding_id", sa.String(length=36), sa.ForeignKey("document_library_holdings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("observed_location", sa.String(length=255), nullable=False),
        sa.Column("expected_location", sa.String(length=255), nullable=False),
        sa.Column("outcome", sa.String(length=24), nullable=False),
        sa.Column("observed_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("session_id", "holding_id", name="uq_doc_library_inventory_observation"),
        sa.CheckConstraint("outcome IN ('MATCH','MISPLACED','EXCEPTION')", name="ck_doc_library_inventory_observation_outcome"),
    )
    op.create_index("ix_doc_library_inventory_observation_session", "document_library_inventory_observations", ["session_id", "observed_at"])

    op.create_table(
        "document_record_series",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_department", sa.String(length=128), nullable=False),
        sa.Column("retention_years", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("disposition_method", sa.String(length=40), nullable=False, server_default="REVIEW_AT_EXPIRY"),
        sa.Column("restricted_flag", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("controllers_can_read", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("access_scope_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb") if _postgres() else None),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb") if _postgres() else None),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "code", name="uq_document_record_series_tenant_code"),
        sa.CheckConstraint("retention_years BETWEEN 1 AND 100", name="ck_document_record_series_retention"),
        sa.CheckConstraint("status IN ('ACTIVE','INACTIVE')", name="ck_document_record_series_status"),
        sa.CheckConstraint(
            "disposition_method IN ('REVIEW_AT_EXPIRY','ARCHIVE','TRANSFER','DESTROY')",
            name="ck_document_record_series_disposition",
        ),
    )
    op.create_index("ix_document_record_series_tenant_owner", "document_record_series", ["tenant_id", "owner_department", "status"])

    op.create_table(
        "document_record_assets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("series_id", sa.String(length=36), sa.ForeignKey("document_record_series.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("record_number", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("source_module", sa.String(length=64), nullable=False, server_default="DOCUMENT_CONTROL"),
        sa.Column("source_entity_type", sa.String(length=80), nullable=True),
        sa.Column("source_entity_id", sa.String(length=160), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("retention_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("legal_hold_reason", sa.Text(), nullable=True),
        sa.Column("legal_hold_set_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("legal_hold_set_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disposition_status", sa.String(length=40), nullable=False, server_default="ACTIVE"),
        sa.Column("disposed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disposed_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("disposition_reason", sa.Text(), nullable=True),
        sa.Column("search_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("access_scope_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb") if _postgres() else None),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb") if _postgres() else None),
        sa.Column("uploaded_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "record_number", name="uq_document_record_asset_tenant_number"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_document_record_asset_size"),
        sa.CheckConstraint(
            "disposition_status IN ('ACTIVE','ARCHIVED','TRANSFERRED','DISPOSED')",
            name="ck_document_record_asset_disposition",
        ),
    )
    op.create_index("ix_document_record_asset_series_capture", "document_record_assets", ["series_id", "captured_at"])
    op.create_index("ix_document_record_asset_tenant_retention", "document_record_assets", ["tenant_id", "retention_due_at", "disposition_status"])
    op.create_index("ix_document_record_asset_tenant_source", "document_record_assets", ["tenant_id", "source_module", "source_entity_type", "source_entity_id"])
    op.create_index("ix_document_record_asset_tenant_sha", "document_record_assets", ["tenant_id", "sha256"])
    if _postgres():
        op.execute(sa.text("""
            CREATE INDEX ix_document_record_asset_search_fts
            ON document_record_assets
            USING gin (to_tsvector('simple', coalesce(search_text, '')))
        """))

    op.create_table(
        "document_record_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("record_asset_id", sa.String(length=36), sa.ForeignKey("document_record_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb") if _postgres() else None),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_document_record_event_asset_created", "document_record_events", ["record_asset_id", "created_at"])
    op.create_index("ix_document_record_event_tenant_action", "document_record_events", ["tenant_id", "event_type", "created_at"])

    for table in _TABLES:
        _enable_rls(table)
    _append_only_events()


def downgrade() -> None:
    if _postgres():
        for table_name in ("document_record_events", "document_library_circulation_events"):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{table_name}_append_only ON {table_name}"))
            op.execute(sa.text(f"DROP FUNCTION IF EXISTS prevent_{table_name}_mutation()"))
    for table in reversed(_TABLES):
        _disable_rls(table)

    op.drop_index("ix_document_record_event_tenant_action", table_name="document_record_events")
    op.drop_index("ix_document_record_event_asset_created", table_name="document_record_events")
    op.drop_table("document_record_events")

    if _postgres():
        op.execute(sa.text("DROP INDEX IF EXISTS ix_document_record_asset_search_fts"))
    op.drop_index("ix_document_record_asset_tenant_sha", table_name="document_record_assets")
    op.drop_index("ix_document_record_asset_tenant_source", table_name="document_record_assets")
    op.drop_index("ix_document_record_asset_tenant_retention", table_name="document_record_assets")
    op.drop_index("ix_document_record_asset_series_capture", table_name="document_record_assets")
    op.drop_table("document_record_assets")

    op.drop_index("ix_document_record_series_tenant_owner", table_name="document_record_series")
    op.drop_table("document_record_series")

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

    op.drop_index("ix_doc_library_identifier_lookup", table_name="document_library_catalog_identifiers")
    op.drop_index("ix_doc_library_identifier_item", table_name="document_library_catalog_identifiers")
    op.drop_table("document_library_catalog_identifiers")

    if _postgres():
        op.execute(sa.text("DROP INDEX IF EXISTS ix_manual_blocks_text_plain_fts"))
        op.execute(sa.text("DROP INDEX IF EXISTS ix_manual_sections_heading_fts"))
        op.execute(sa.text("DROP INDEX IF EXISTS ix_doc_library_item_search_fts"))
    op.drop_index("ix_doc_library_item_tenant_title", table_name="document_library_catalog_items")
    op.drop_index("ix_doc_library_item_tenant_type_status", table_name="document_library_catalog_items")
    op.drop_table("document_library_catalog_items")
