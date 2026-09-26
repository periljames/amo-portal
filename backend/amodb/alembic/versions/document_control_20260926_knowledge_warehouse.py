"""Add canonical tenant knowledge warehouse registry.

Revision ID: docctl_260926_knowledge_wh
Revises: docctl_260926_library_catalog
Create Date: 2026-09-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "docctl_260926_knowledge_wh"
down_revision = "docctl_260926_library_catalog"
branch_labels = None
depends_on = None

_TABLES = (
    "document_warehouse_content_records",
    "document_warehouse_content_versions",
    "document_warehouse_binary_objects",
    "document_warehouse_identifiers",
    "document_warehouse_locations",
    "document_warehouse_item_copies",
    "document_warehouse_relationships",
    "document_warehouse_external_references",
    "document_warehouse_access_policies",
    "document_warehouse_acknowledgements",
    "document_warehouse_audit_events",
    "document_warehouse_collections",
    "document_warehouse_collection_memberships",
    "document_warehouse_patrons",
    "document_warehouse_loans",
    "document_warehouse_holds",
    "document_warehouse_item_events",
    "document_warehouse_workflows",
    "document_warehouse_retention_rules",
)


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _json_object_default():
    return sa.text("'{}'::jsonb") if _postgres() else None


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


def _append_only(table_name: str, label: str) -> None:
    if not _postgres():
        return
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


def _protect_version_identity() -> None:
    if not _postgres():
        return
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION prevent_document_warehouse_version_identity_mutation()
        RETURNS trigger AS $immutable_version$
        BEGIN
            IF OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
               OR OLD.content_record_id IS DISTINCT FROM NEW.content_record_id
               OR OLD.source_version_type IS DISTINCT FROM NEW.source_version_type
               OR OLD.source_version_id IS DISTINCT FROM NEW.source_version_id
               OR OLD.sequence IS DISTINCT FROM NEW.sequence
               OR OLD.version_label IS DISTINCT FROM NEW.version_label
               OR (OLD.file_hash IS NOT NULL AND OLD.file_hash IS DISTINCT FROM NEW.file_hash) THEN
                RAISE EXCEPTION 'Warehouse version identity and source hash are immutable';
            END IF;
            RETURN NEW;
        END;
        $immutable_version$ LANGUAGE plpgsql;
    """))
    op.execute(sa.text("""
        CREATE TRIGGER trg_document_warehouse_version_identity_immutable
        BEFORE UPDATE ON document_warehouse_content_versions
        FOR EACH ROW EXECUTE FUNCTION prevent_document_warehouse_version_identity_mutation();
    """))


def upgrade() -> None:
    op.create_table(
        "document_warehouse_content_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("canonical_code", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("classification", sa.String(length=32), nullable=False, server_default="INTERNAL"),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("owner_department", sa.String(length=128), nullable=True),
        sa.Column("source_entity_type", sa.String(length=64), nullable=False),
        sa.Column("source_entity_id", sa.String(length=128), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_json_object_default()),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "resource_type", "canonical_code", name="uq_doc_wh_record_tenant_type_code"),
        sa.UniqueConstraint("tenant_id", "source_entity_type", "source_entity_id", name="uq_doc_wh_record_source"),
    )
    op.create_index("ix_doc_wh_record_tenant_type_status", "document_warehouse_content_records", ["tenant_id", "resource_type", "lifecycle_status"])
    op.create_index("ix_doc_wh_record_tenant_title", "document_warehouse_content_records", ["tenant_id", "title"])
    if _postgres():
        op.execute(sa.text("""
            CREATE INDEX ix_doc_wh_record_search_fts
            ON document_warehouse_content_records
            USING gin (
                to_tsvector(
                    'simple',
                    coalesce(canonical_code, '') || ' ' ||
                    coalesce(title, '') || ' ' ||
                    coalesce(description, '')
                )
            )
        """))

    op.create_table(
        "document_warehouse_content_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_record_id", sa.String(length=36), sa.ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_label", sa.String(length=128), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("source_version_type", sa.String(length=64), nullable=False),
        sa.Column("source_version_id", sa.String(length=128), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("immutable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_json_object_default()),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "content_record_id", "sequence", name="uq_doc_wh_version_sequence"),
        sa.UniqueConstraint("tenant_id", "source_version_type", "source_version_id", name="uq_doc_wh_version_source"),
        sa.CheckConstraint("sequence >= 1", name="ck_doc_wh_version_sequence"),
    )
    op.create_index("ix_doc_wh_version_record_status", "document_warehouse_content_versions", ["content_record_id", "lifecycle_status", "sequence"])
    op.create_index("ix_doc_wh_version_tenant_effective", "document_warehouse_content_versions", ["tenant_id", "effective_at"])

    op.create_table(
        "document_warehouse_binary_objects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_version_id", sa.String(length=36), sa.ForeignKey("document_warehouse_content_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("object_role", sa.String(length=32), nullable=False, server_default="ORIGINAL"),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("derived_from_binary_id", sa.String(length=36), sa.ForeignKey("document_warehouse_binary_objects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_json_object_default()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "content_version_id", "sha256", "object_role", name="uq_doc_wh_binary_version_hash_role"),
        sa.CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="ck_doc_wh_binary_size"),
    )
    op.create_index("ix_doc_wh_binary_version", "document_warehouse_binary_objects", ["content_version_id", "object_role"])

    op.create_table(
        "document_warehouse_identifiers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_record_id", sa.String(length=36), sa.ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scheme", sa.String(length=32), nullable=False),
        sa.Column("normalized_value", sa.String(length=255), nullable=False),
        sa.Column("display_value", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="SYSTEM"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "scheme", "normalized_value", name="uq_doc_wh_identifier_lookup"),
    )
    op.create_index("ix_doc_wh_identifier_record", "document_warehouse_identifiers", ["content_record_id", "scheme"])

    op.create_table(
        "document_warehouse_locations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("location_type", sa.String(length=40), nullable=False, server_default="SHELF"),
        sa.Column("parent_id", sa.String(length=36), sa.ForeignKey("document_warehouse_locations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("path_text", sa.String(length=1000), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="ACTIVE"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_json_object_default()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "code", name="uq_doc_wh_location_tenant_code"),
    )
    op.create_index("ix_doc_wh_location_parent", "document_warehouse_locations", ["tenant_id", "parent_id", "status"])

    op.create_table(
        "document_warehouse_item_copies",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_record_id", sa.String(length=36), sa.ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_version_id", sa.String(length=36), sa.ForeignKey("document_warehouse_content_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_entity_type", sa.String(length=64), nullable=False),
        sa.Column("source_entity_id", sa.String(length=128), nullable=False),
        sa.Column("copy_number", sa.String(length=128), nullable=True),
        sa.Column("barcode", sa.String(length=128), nullable=False),
        sa.Column("qr_token", sa.String(length=128), nullable=False),
        sa.Column("format", sa.String(length=32), nullable=False, server_default="PHYSICAL"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="AVAILABLE"),
        sa.Column("home_location_id", sa.String(length=36), sa.ForeignKey("document_warehouse_locations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("current_location_id", sa.String(length=36), sa.ForeignKey("document_warehouse_locations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("location_text", sa.String(length=1000), nullable=True),
        sa.Column("custodian_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("installed_version_label", sa.String(length=128), nullable=True),
        sa.Column("required_version_label", sa.String(length=128), nullable=True),
        sa.Column("revision_compliance", sa.String(length=32), nullable=False, server_default="NOT_APPLICABLE"),
        sa.Column("last_inventory_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_json_object_default()),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "barcode", name="uq_doc_wh_copy_barcode"),
        sa.UniqueConstraint("tenant_id", "qr_token", name="uq_doc_wh_copy_qr"),
        sa.UniqueConstraint("tenant_id", "source_entity_type", "source_entity_id", name="uq_doc_wh_copy_source"),
        sa.CheckConstraint(
            "revision_compliance IN ('NOT_APPLICABLE','CURRENT','REVISION_REQUIRED','UNVERIFIED')",
            name="ck_doc_wh_copy_revision_compliance",
        ),
    )
    op.create_index("ix_doc_wh_copy_record_status", "document_warehouse_item_copies", ["content_record_id", "status"])
    op.create_index("ix_doc_wh_copy_revision_compliance", "document_warehouse_item_copies", ["tenant_id", "revision_compliance", "status"])
    op.create_index("ix_doc_wh_copy_location", "document_warehouse_item_copies", ["tenant_id", "current_location_id", "status"])

    op.create_table(
        "document_warehouse_relationships",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_record_id", sa.String(length=36), sa.ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_version_id", sa.String(length=36), sa.ForeignKey("document_warehouse_content_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("relationship_type", sa.String(length=64), nullable=False),
        sa.Column("target_record_id", sa.String(length=36), sa.ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_version_id", sa.String(length=36), sa.ForeignKey("document_warehouse_content_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="ACTIVE"),
        sa.Column("verified_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_json_object_default()),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("source_record_id <> target_record_id", name="ck_doc_wh_relationship_distinct_records"),
    )
    op.create_index("ix_doc_wh_rel_source", "document_warehouse_relationships", ["tenant_id", "source_record_id", "relationship_type", "status"])
    op.create_index("ix_doc_wh_rel_target", "document_warehouse_relationships", ["tenant_id", "target_record_id", "relationship_type", "status"])

    op.create_table(
        "document_warehouse_external_references",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_record_id", sa.String(length=36), sa.ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("reference_type", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_json_object_default()),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_doc_wh_external_record", "document_warehouse_external_references", ["content_record_id", "provider", "reference_type"])

    op.create_table(
        "document_warehouse_access_policies",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_record_id", sa.String(length=36), sa.ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False, server_default="READ"),
        sa.Column("effect", sa.String(length=16), nullable=False, server_default="ALLOW"),
        sa.Column("principal_type", sa.String(length=32), nullable=False, server_default="ROLE"),
        sa.Column("principal_value", sa.String(length=255), nullable=False),
        sa.Column("conditions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_json_object_default()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("effect IN ('ALLOW','DENY')", name="ck_doc_wh_access_effect"),
    )
    op.create_index("ix_doc_wh_access_record_action", "document_warehouse_access_policies", ["content_record_id", "action", "priority"])

    op.create_table(
        "document_warehouse_acknowledgements",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_record_id", sa.String(length=36), sa.ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_version_id", sa.String(length=36), sa.ForeignKey("document_warehouse_content_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=True),
        sa.Column("acknowledgement_method", sa.String(length=40), nullable=False, server_default="READER_SIGNOFF"),
        sa.Column("session_metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_json_object_default()),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "content_version_id", "user_id", name="uq_doc_wh_ack_version_user"),
    )
    op.create_index("ix_doc_wh_ack_record_user", "document_warehouse_acknowledgements", ["content_record_id", "user_id", "acknowledged_at"])

    op.create_table(
        "document_warehouse_audit_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_record_id", sa.String(length=36), sa.ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_version_id", sa.String(length=36), sa.ForeignKey("document_warehouse_content_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("item_copy_id", sa.String(length=36), sa.ForeignKey("document_warehouse_item_copies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("transaction_id", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_json_object_default()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_doc_wh_audit_record_created", "document_warehouse_audit_events", ["content_record_id", "created_at"])
    op.create_index("ix_doc_wh_audit_tenant_event", "document_warehouse_audit_events", ["tenant_id", "event_type", "created_at"])
    op.create_index("ix_doc_wh_audit_transaction", "document_warehouse_audit_events", ["tenant_id", "transaction_id"])

    op.create_table(
        "document_warehouse_collections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("collection_type", sa.String(length=40), nullable=False, server_default="GENERAL"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="ACTIVE"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_json_object_default()),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "code", name="uq_doc_wh_collection_code"),
    )
    op.create_index("ix_doc_wh_collection_type_status", "document_warehouse_collections", ["tenant_id", "collection_type", "status"])

    op.create_table(
        "document_warehouse_collection_memberships",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("collection_id", sa.String(length=36), sa.ForeignKey("document_warehouse_collections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_record_id", sa.String(length=36), sa.ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("added_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "collection_id", "content_record_id", name="uq_doc_wh_collection_member"),
    )
    op.create_index("ix_doc_wh_collection_member_record", "document_warehouse_collection_memberships", ["tenant_id", "content_record_id"])

    op.create_table(
        "document_warehouse_patrons",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patron_barcode", sa.String(length=128), nullable=True),
        sa.Column("patron_type", sa.String(length=32), nullable=False, server_default="EMPLOYEE"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="ACTIVE"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_json_object_default()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_doc_wh_patron_user"),
        sa.UniqueConstraint("tenant_id", "patron_barcode", name="uq_doc_wh_patron_barcode"),
    )
    op.create_index("ix_doc_wh_patron_status_type", "document_warehouse_patrons", ["tenant_id", "status", "patron_type"])

    op.create_table(
        "document_warehouse_loans",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_copy_id", sa.String(length=36), sa.ForeignKey("document_warehouse_item_copies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patron_id", sa.String(length=36), sa.ForeignKey("document_warehouse_patrons.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_entity_type", sa.String(length=64), nullable=False),
        sa.Column("source_entity_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="ACTIVE"),
        sa.Column("checked_out_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("renewal_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_json_object_default()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "source_entity_type", "source_entity_id", name="uq_doc_wh_loan_source"),
        sa.CheckConstraint("renewal_count >= 0", name="ck_doc_wh_loan_renewals"),
    )
    op.create_index("ix_doc_wh_loan_patron_status", "document_warehouse_loans", ["tenant_id", "patron_id", "status", "due_at"])
    op.create_index("ix_doc_wh_loan_item_status", "document_warehouse_loans", ["item_copy_id", "status"])

    op.create_table(
        "document_warehouse_holds",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_record_id", sa.String(length=36), sa.ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("patron_id", sa.String(length=36), sa.ForeignKey("document_warehouse_patrons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fulfilled_item_copy_id", sa.String(length=36), sa.ForeignKey("document_warehouse_item_copies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_entity_type", sa.String(length=64), nullable=False),
        sa.Column("source_entity_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="ACTIVE"),
        sa.Column("pickup_location", sa.String(length=1000), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "source_entity_type", "source_entity_id", name="uq_doc_wh_hold_source"),
    )
    op.create_index("ix_doc_wh_hold_record_status", "document_warehouse_holds", ["content_record_id", "status", "created_at"])
    op.create_index("ix_doc_wh_hold_patron_status", "document_warehouse_holds", ["patron_id", "status", "created_at"])

    op.create_table(
        "document_warehouse_item_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_copy_id", sa.String(length=36), sa.ForeignKey("document_warehouse_item_copies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("source_event_type", sa.String(length=64), nullable=False),
        sa.Column("source_event_id", sa.String(length=128), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("patron_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column("from_location", sa.String(length=1000), nullable=True),
        sa.Column("to_location", sa.String(length=1000), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_json_object_default()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "source_event_type", "source_event_id", name="uq_doc_wh_item_event_source"),
    )
    op.create_index("ix_doc_wh_item_event_copy_created", "document_warehouse_item_events", ["item_copy_id", "created_at"])
    op.create_index("ix_doc_wh_item_event_tenant_type", "document_warehouse_item_events", ["tenant_id", "event_type", "created_at"])

    op.create_table(
        "document_warehouse_workflows",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_record_id", sa.String(length=36), sa.ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_version_id", sa.String(length=36), sa.ForeignKey("document_warehouse_content_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_workflow_type", sa.String(length=64), nullable=False),
        sa.Column("source_workflow_id", sa.String(length=128), nullable=False),
        sa.Column("state", sa.String(length=48), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_json_object_default()),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "source_workflow_type", "source_workflow_id", name="uq_doc_wh_workflow_source"),
    )
    op.create_index("ix_doc_wh_workflow_record_state", "document_warehouse_workflows", ["content_record_id", "state"])

    op.create_table(
        "document_warehouse_retention_rules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_rule_type", sa.String(length=64), nullable=False),
        sa.Column("source_rule_id", sa.String(length=128), nullable=False),
        sa.Column("retention_months", sa.Integer(), nullable=False),
        sa.Column("trigger_event", sa.String(length=64), nullable=False, server_default="CAPTURED"),
        sa.Column("disposition_action", sa.String(length=32), nullable=False, server_default="REVIEW_AT_EXPIRY"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="ACTIVE"),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=_json_object_default()),
        sa.Column("created_by_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "source_rule_type", "source_rule_id", name="uq_doc_wh_retention_source"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_doc_wh_retention_code"),
        sa.CheckConstraint("retention_months >= 0", name="ck_doc_wh_retention_months"),
    )
    op.create_index("ix_doc_wh_retention_status", "document_warehouse_retention_rules", ["tenant_id", "status", "disposition_action"])

    for table in _TABLES:
        _enable_rls(table)
    _append_only("document_warehouse_acknowledgements", "Warehouse acknowledgement history")
    _append_only("document_warehouse_audit_events", "Warehouse audit history")
    _protect_version_identity()


def downgrade() -> None:
    if _postgres():
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_document_warehouse_version_identity_immutable ON document_warehouse_content_versions"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_document_warehouse_version_identity_mutation()"))
        for table_name in ("document_warehouse_audit_events", "document_warehouse_acknowledgements"):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS trg_{table_name}_append_only ON {table_name}"))
            op.execute(sa.text(f"DROP FUNCTION IF EXISTS prevent_{table_name}_mutation()"))

    for table in reversed(_TABLES):
        _disable_rls(table)

    op.drop_index("ix_doc_wh_retention_status", table_name="document_warehouse_retention_rules")
    op.drop_table("document_warehouse_retention_rules")

    op.drop_index("ix_doc_wh_workflow_record_state", table_name="document_warehouse_workflows")
    op.drop_table("document_warehouse_workflows")

    op.drop_index("ix_doc_wh_item_event_tenant_type", table_name="document_warehouse_item_events")
    op.drop_index("ix_doc_wh_item_event_copy_created", table_name="document_warehouse_item_events")
    op.drop_table("document_warehouse_item_events")

    op.drop_index("ix_doc_wh_hold_patron_status", table_name="document_warehouse_holds")
    op.drop_index("ix_doc_wh_hold_record_status", table_name="document_warehouse_holds")
    op.drop_table("document_warehouse_holds")

    op.drop_index("ix_doc_wh_loan_item_status", table_name="document_warehouse_loans")
    op.drop_index("ix_doc_wh_loan_patron_status", table_name="document_warehouse_loans")
    op.drop_table("document_warehouse_loans")

    op.drop_index("ix_doc_wh_patron_status_type", table_name="document_warehouse_patrons")
    op.drop_table("document_warehouse_patrons")

    op.drop_index("ix_doc_wh_collection_member_record", table_name="document_warehouse_collection_memberships")
    op.drop_table("document_warehouse_collection_memberships")

    op.drop_index("ix_doc_wh_collection_type_status", table_name="document_warehouse_collections")
    op.drop_table("document_warehouse_collections")

    op.drop_index("ix_doc_wh_audit_transaction", table_name="document_warehouse_audit_events")
    op.drop_index("ix_doc_wh_audit_tenant_event", table_name="document_warehouse_audit_events")
    op.drop_index("ix_doc_wh_audit_record_created", table_name="document_warehouse_audit_events")
    op.drop_table("document_warehouse_audit_events")

    op.drop_index("ix_doc_wh_ack_record_user", table_name="document_warehouse_acknowledgements")
    op.drop_table("document_warehouse_acknowledgements")

    op.drop_index("ix_doc_wh_access_record_action", table_name="document_warehouse_access_policies")
    op.drop_table("document_warehouse_access_policies")

    op.drop_index("ix_doc_wh_external_record", table_name="document_warehouse_external_references")
    op.drop_table("document_warehouse_external_references")

    op.drop_index("ix_doc_wh_rel_target", table_name="document_warehouse_relationships")
    op.drop_index("ix_doc_wh_rel_source", table_name="document_warehouse_relationships")
    op.drop_table("document_warehouse_relationships")

    op.drop_index("ix_doc_wh_copy_location", table_name="document_warehouse_item_copies")
    op.drop_index("ix_doc_wh_copy_revision_compliance", table_name="document_warehouse_item_copies")
    op.drop_index("ix_doc_wh_copy_record_status", table_name="document_warehouse_item_copies")
    op.drop_table("document_warehouse_item_copies")

    op.drop_index("ix_doc_wh_location_parent", table_name="document_warehouse_locations")
    op.drop_table("document_warehouse_locations")

    op.drop_index("ix_doc_wh_identifier_record", table_name="document_warehouse_identifiers")
    op.drop_table("document_warehouse_identifiers")

    op.drop_index("ix_doc_wh_binary_version", table_name="document_warehouse_binary_objects")
    op.drop_table("document_warehouse_binary_objects")

    op.drop_index("ix_doc_wh_version_tenant_effective", table_name="document_warehouse_content_versions")
    op.drop_index("ix_doc_wh_version_record_status", table_name="document_warehouse_content_versions")
    op.drop_table("document_warehouse_content_versions")

    if _postgres():
        op.execute(sa.text("DROP INDEX IF EXISTS ix_doc_wh_record_search_fts"))
    op.drop_index("ix_doc_wh_record_tenant_title", table_name="document_warehouse_content_records")
    op.drop_index("ix_doc_wh_record_tenant_type_status", table_name="document_warehouse_content_records")
    op.drop_table("document_warehouse_content_records")
