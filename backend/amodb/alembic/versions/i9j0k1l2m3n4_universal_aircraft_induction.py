"""replace legacy aircraft importer with universal induction

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-08-05 08:10:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "i9j0k1l2m3n4"
down_revision = "h8i9j0k1l2m3"
branch_labels = None
depends_on = None


def _timestamps():
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _drop_if_exists(table_name: str) -> None:
    bind = op.get_bind()
    if inspect(bind).has_table(table_name):
        op.drop_table(table_name)


def upgrade() -> None:
    op.create_table(
        "aircraft_families",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("manufacturer", sa.String(160), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        *_timestamps(),
        sa.UniqueConstraint("code", name="uq_aircraft_family_code"),
    )
    op.create_index("ix_aircraft_family_manufacturer", "aircraft_families", ["manufacturer", "status"])

    op.create_table(
        "aircraft_types",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("family_id", sa.String(36), sa.ForeignKey("aircraft_families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type_code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("type_certificate_number", sa.String(128)),
        sa.Column("authority", sa.String(32)),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        *_timestamps(),
        sa.UniqueConstraint("family_id", "type_code", name="uq_aircraft_type_family_code"),
    )
    op.create_index("ix_aircraft_type_tc", "aircraft_types", ["type_certificate_number", "authority"])

    op.create_table(
        "aircraft_variants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("aircraft_type_id", sa.String(36), sa.ForeignKey("aircraft_types.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_code", sa.String(64), nullable=False),
        sa.Column("model_code", sa.String(64), nullable=False),
        sa.Column("marketing_name", sa.String(160)),
        sa.Column("description", sa.Text()),
        sa.Column("serial_effectivity_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("engine_options_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("propeller_options_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("apu_options_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        *_timestamps(),
        sa.UniqueConstraint("aircraft_type_id", "variant_code", name="uq_aircraft_variant_type_code"),
    )
    op.create_index("ix_aircraft_variant_model_code", "aircraft_variants", ["model_code"])

    op.create_table(
        "aircraft_type_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("variant_id", sa.String(36), sa.ForeignKey("aircraft_variants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code", sa.String(96), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False, server_default="GLOBAL"),
        sa.Column("owner_amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE")),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        *_timestamps(),
        sa.UniqueConstraint("code", name="uq_aircraft_type_template_code"),
    )
    op.create_index("ix_aircraft_type_template_scope", "aircraft_type_templates", ["visibility", "owner_amo_id", "status"])

    op.create_table(
        "aircraft_type_template_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("template_id", sa.String(36), sa.ForeignKey("aircraft_type_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision_code", sa.String(48), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("effective_date", sa.Date()),
        sa.Column("source_reference", sa.String(255)),
        sa.Column("source_hash", sa.String(64)),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("release_notes", sa.Text()),
        sa.Column("approved_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        *_timestamps(),
        sa.UniqueConstraint("template_id", "revision_code", name="uq_aircraft_type_template_revision"),
    )
    op.create_index("ix_aircraft_type_revision_status", "aircraft_type_template_revisions", ["template_id", "status", "effective_date"])
    op.create_index("ix_aircraft_type_revision_content_hash", "aircraft_type_template_revisions", ["content_hash"])

    op.create_table(
        "aircraft_template_source_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("template_revision_id", sa.String(36), sa.ForeignKey("aircraft_type_template_revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_type", sa.String(32), nullable=False),
        sa.Column("reference", sa.String(160), nullable=False),
        sa.Column("document_revision", sa.String(64)),
        sa.Column("issue_date", sa.Date()),
        sa.Column("authority", sa.String(32)),
        sa.Column("source_uri", sa.String(512)),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("notes", sa.Text()),
        sa.UniqueConstraint("template_revision_id", "document_type", "reference", "document_revision", name="uq_aircraft_template_source_document"),
    )
    op.create_index("ix_template_source_revision", "aircraft_template_source_documents", ["template_revision_id", "document_type"])

    op.create_table(
        "aircraft_template_configuration_nodes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("template_revision_id", sa.String(36), sa.ForeignKey("aircraft_type_template_revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_key", sa.String(128), nullable=False),
        sa.Column("parent_node_key", sa.String(128)),
        sa.Column("node_type", sa.String(32), nullable=False),
        sa.Column("position_code", sa.String(64)),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("ata_chapter", sa.String(20)),
        sa.Column("minimum_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("maximum_quantity", sa.Integer()),
        sa.Column("allowable_parts_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("counter_rules_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("effectivity_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("sequence_no", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("template_revision_id", "node_key", name="uq_aircraft_template_config_node"),
        sa.CheckConstraint("minimum_quantity >= 0", name="ck_aircraft_template_node_min_qty"),
        sa.CheckConstraint("maximum_quantity IS NULL OR maximum_quantity >= minimum_quantity", name="ck_aircraft_template_node_qty_order"),
    )
    op.create_index("ix_template_config_revision_parent", "aircraft_template_configuration_nodes", ["template_revision_id", "parent_node_key", "sequence_no"])

    op.create_table(
        "aircraft_template_requirements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("template_revision_id", sa.String(36), sa.ForeignKey("aircraft_type_template_revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requirement_key", sa.String(128), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("ata_chapter", sa.String(20)),
        sa.Column("task_code", sa.String(96), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("governing_logic", sa.String(32), nullable=False, server_default="WHICHEVER_FIRST"),
        sa.Column("interval_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("threshold_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("effectivity_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("source_reference", sa.String(255)),
        sa.Column("source_document_id", sa.String(36), sa.ForeignKey("aircraft_template_source_documents.id", ondelete="SET NULL")),
        sa.Column("mandatory", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sequence_no", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("template_revision_id", "requirement_key", name="uq_aircraft_template_requirement"),
    )
    op.create_index("ix_template_requirement_revision_ata", "aircraft_template_requirements", ["template_revision_id", "ata_chapter", "category"])

    op.create_table(
        "aircraft_import_mapping_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE")),
        sa.Column("scope", sa.String(16), nullable=False, server_default="TENANT"),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_version", sa.String(64)),
        sa.Column("dataset", sa.String(32), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("header_signature_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("mapping_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("transformations_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("defaults_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("validation_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        *_timestamps(),
        sa.UniqueConstraint("scope", "amo_id", "name", "version", name="uq_aircraft_import_mapping_profile"),
    )
    op.create_index("ix_import_mapping_fingerprint", "aircraft_import_mapping_profiles", ["dataset", "fingerprint", "status"])
    op.create_index("ix_import_mapping_source", "aircraft_import_mapping_profiles", ["source_system", "source_version", "dataset"])

    op.create_table(
        "tenant_maintenance_programs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_id", sa.String(36), sa.ForeignKey("aircraft_variants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code", sa.String(96), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("authority", sa.String(32)),
        sa.Column("approval_reference", sa.String(160)),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        *_timestamps(),
        sa.UniqueConstraint("amo_id", "code", name="uq_tenant_maintenance_program_code"),
    )
    op.create_index("ix_tenant_program_variant", "tenant_maintenance_programs", ["amo_id", "variant_id", "status"])

    op.create_table(
        "tenant_maintenance_program_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("program_id", sa.String(36), sa.ForeignKey("tenant_maintenance_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("base_template_revision_id", sa.String(36), sa.ForeignKey("aircraft_type_template_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("revision_code", sa.String(48), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("effective_date", sa.Date()),
        sa.Column("approval_reference", sa.String(160)),
        sa.Column("approval_date", sa.Date()),
        sa.Column("notes", sa.Text()),
        sa.Column("approved_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        *_timestamps(),
        sa.UniqueConstraint("program_id", "revision_code", name="uq_tenant_program_revision"),
    )
    op.create_index("ix_tenant_program_revision_status", "tenant_maintenance_program_revisions", ["program_id", "status", "effective_date"])

    op.create_table(
        "tenant_program_overrides",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("program_revision_id", sa.String(36), sa.ForeignKey("tenant_maintenance_program_revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requirement_key", sa.String(128), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("patch_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("effectivity_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("authority_reference", sa.String(160)),
        sa.UniqueConstraint("program_revision_id", "requirement_key", name="uq_tenant_program_override"),
    )
    op.create_index("ix_tenant_program_override_action", "tenant_program_overrides", ["program_revision_id", "action"])

    op.create_table(
        "aircraft_inductions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("induction_ref", sa.String(96), nullable=False),
        sa.Column("serial_number", sa.String(50), nullable=False),
        sa.Column("registration", sa.String(20), nullable=False),
        sa.Column("variant_id", sa.String(36), sa.ForeignKey("aircraft_variants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("template_revision_id", sa.String(36), sa.ForeignKey("aircraft_type_template_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("program_revision_id", sa.String(36), sa.ForeignKey("tenant_maintenance_program_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="DRAFT"),
        sa.Column("source_system", sa.String(64)),
        sa.Column("source_reference", sa.String(255)),
        sa.Column("source_hash", sa.String(64)),
        sa.Column("current_step", sa.String(32), nullable=False, server_default="IDENTIFY"),
        sa.Column("counts_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("validation_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("activation_manifest_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.UniqueConstraint("amo_id", "induction_ref", name="uq_aircraft_induction_ref"),
    )
    op.create_index("ix_aircraft_induction_status", "aircraft_inductions", ["amo_id", "status", "created_at"])
    op.create_index("ix_aircraft_induction_aircraft", "aircraft_inductions", ["amo_id", "serial_number", "registration"])

    op.create_table(
        "aircraft_induction_datasets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("induction_id", sa.String(36), sa.ForeignKey("aircraft_inductions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset", sa.String(32), nullable=False),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("source_sheet", sa.String(160)),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("mapping_profile_id", sa.String(36), sa.ForeignKey("aircraft_import_mapping_profiles.id", ondelete="SET NULL")),
        sa.Column("headers_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="STAGED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("induction_id", "dataset", "source_name", "source_sheet", name="uq_aircraft_induction_dataset"),
    )
    op.create_index("ix_aircraft_induction_dataset_status", "aircraft_induction_datasets", ["induction_id", "status"])

    op.create_table(
        "aircraft_induction_rows",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("aircraft_induction_datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("source_json", sa.JSON(), nullable=False),
        sa.Column("normalized_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("status", sa.String(20), nullable=False, server_default="STAGED"),
        sa.Column("errors_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("warnings_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("decision", sa.String(20)),
        sa.Column("final_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("decided_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("dataset_id", "row_number", name="uq_aircraft_induction_row"),
    )
    op.create_index("ix_aircraft_induction_row_status", "aircraft_induction_rows", ["dataset_id", "status", "row_number"])

    op.create_table(
        "aircraft_applicability_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("induction_id", sa.String(36), sa.ForeignKey("aircraft_inductions.id", ondelete="SET NULL")),
        sa.Column("aircraft_serial_number", sa.String(50), nullable=False),
        sa.Column("template_revision_id", sa.String(36), sa.ForeignKey("aircraft_type_template_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("program_revision_id", sa.String(36), sa.ForeignKey("tenant_maintenance_program_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("configuration_hash", sa.String(64), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("context_json", sa.JSON(), nullable=False),
        sa.Column("applicable_requirements_json", sa.JSON(), nullable=False),
        sa.Column("excluded_requirements_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_aircraft_applicability_aircraft", "aircraft_applicability_snapshots", ["amo_id", "aircraft_serial_number", "created_at"])
    op.create_index("ix_aircraft_applicability_hash", "aircraft_applicability_snapshots", ["snapshot_hash"])

    op.create_table(
        "aircraft_template_bindings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aircraft_serial_number", sa.String(50), sa.ForeignKey("aircraft.serial_number", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_id", sa.String(36), sa.ForeignKey("aircraft_variants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("template_revision_id", sa.String(36), sa.ForeignKey("aircraft_type_template_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("program_revision_id", sa.String(36), sa.ForeignKey("tenant_maintenance_program_revisions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("applicability_snapshot_id", sa.String(36), sa.ForeignKey("aircraft_applicability_snapshots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("activated_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_aircraft_template_binding_active", "aircraft_template_bindings", ["amo_id", "aircraft_serial_number", "status"])
    op.create_index(
        "uq_aircraft_template_binding_one_active",
        "aircraft_template_bindings",
        ["amo_id", "aircraft_serial_number"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "aircraft_induction_counter_baselines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("induction_id", sa.String(36), sa.ForeignKey("aircraft_inductions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("counter_code", sa.String(48), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("value", sa.Numeric(18, 4), nullable=False),
        sa.Column("effective_date", sa.Date()),
        sa.Column("source_reference", sa.String(255)),
        sa.UniqueConstraint("induction_id", "counter_code", name="uq_induction_counter_baseline"),
        sa.CheckConstraint("value >= 0", name="ck_induction_counter_baseline_nonnegative"),
    )

    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("aircraft_import_templates"):
        bind.execute(sa.text("""
            INSERT INTO aircraft_import_mapping_profiles (
                id, amo_id, scope, name, version, source_system, source_version,
                dataset, fingerprint, header_signature_json, mapping_json,
                transformations_json, defaults_json, validation_json, status,
                created_by_user_id, created_at, updated_at
            )
            SELECT
                'legacy-map-' || id::text,
                NULL,
                'GLOBAL',
                name,
                1,
                'LEGACY_IMPORTER',
                NULL,
                CASE WHEN lower(COALESCE(template_type, 'aircraft')) = 'component' THEN 'COMPONENTS' ELSE 'AIRCRAFT_MASTER' END,
                md5(COALESCE(template_type, '') || ':' || COALESCE(name, '') || ':' || id::text),
                '[]'::json,
                COALESCE(column_mapping, '{}'::json),
                '{}'::json,
                COALESCE(default_values, '{}'::json),
                json_build_object(
                    'migrated_from', 'aircraft_import_templates',
                    'legacy_aircraft_template', aircraft_template,
                    'legacy_model_code', model_code,
                    'legacy_operator_code', operator_code
                ),
                'ACTIVE',
                NULL,
                created_at,
                updated_at
            FROM aircraft_import_templates
        """))

    for table_name in (
        "aircraft_import_reconciliation_logs",
        "aircraft_import_snapshots",
        "aircraft_import_preview_rows",
        "aircraft_import_preview_sessions",
        "aircraft_import_templates",
    ):
        _drop_if_exists(table_name)


def downgrade() -> None:
    op.create_table(
        "aircraft_import_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("template_type", sa.String(32), nullable=False, server_default="aircraft"),
        sa.Column("aircraft_template", sa.String(50)),
        sa.Column("model_code", sa.String(32)),
        sa.Column("operator_code", sa.String(5)),
        sa.Column("column_mapping", sa.JSON()),
        sa.Column("default_values", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("template_type", "name", name="uq_aircraft_import_template_type_name"),
    )

    for table_name in (
        "aircraft_induction_counter_baselines",
        "aircraft_template_bindings",
        "aircraft_applicability_snapshots",
        "aircraft_induction_rows",
        "aircraft_induction_datasets",
        "aircraft_inductions",
        "tenant_program_overrides",
        "tenant_maintenance_program_revisions",
        "tenant_maintenance_programs",
        "aircraft_import_mapping_profiles",
        "aircraft_template_requirements",
        "aircraft_template_configuration_nodes",
        "aircraft_template_source_documents",
        "aircraft_type_template_revisions",
        "aircraft_type_templates",
        "aircraft_variants",
        "aircraft_types",
        "aircraft_families",
    ):
        _drop_if_exists(table_name)
