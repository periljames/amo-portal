"""External provider identity extensions; no Quality approval is created here.

Revision ID: extprov_261009_foundation
Revises: quality_261003_evidence_context
"""
from alembic import op
import sqlalchemy as sa

revision = "extprov_261009_foundation"
down_revision = "quality_261003_evidence_context"
branch_labels = None
depends_on = None

TABLES = ("external_provider_roles", "external_provider_sites", "external_provider_contacts",
          "external_provider_capabilities", "external_provider_source_links",
          "external_provider_certificates", "external_provider_relationships",
          "external_provider_account_links", "external_provider_scope_links",
          "external_provider_change_events")

def _common():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["amo_id", "supplier_id"],
                                ["procurement_suppliers.amo_id", "procurement_suppliers.id"],
                                ondelete="RESTRICT"),
        sa.CheckConstraint("version > 0", name="version_positive"),
    ]

def _create(name, *columns, extra=()):
    op.create_table(name, *_common(), *columns, *extra)
    op.create_index(f"ix_{name}_supplier", name, ["amo_id", "supplier_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text(f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{name}" FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f"""CREATE POLICY "{name}_tenant" ON "{name}"
            USING (amo_id = NULLIF(current_setting('app.tenant_id', true), ''))
            WITH CHECK (amo_id = NULLIF(current_setting('app.tenant_id', true), ''))"""))

def upgrade():
    # Existing supplier IDs are globally primary keyed, but composite uniqueness
    # is needed to enforce tenant-matched references at the database boundary.
    op.create_unique_constraint("uq_procurement_supplier_tenant_identity",
                                "procurement_suppliers", ["amo_id", "id"])
    _create("external_provider_roles",
            sa.Column("role_code", sa.String(64), nullable=False),
            sa.Column("notes", sa.Text()),
            extra=(sa.UniqueConstraint("amo_id", "supplier_id", "role_code",
                                       name="uq_external_provider_role"),))
    _create("external_provider_sites",
            sa.Column("site_code", sa.String(64), nullable=False),
            sa.Column("site_name", sa.String(255), nullable=False),
            sa.Column("country", sa.String(80)),
            sa.Column("address", sa.Text()),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
            extra=(sa.UniqueConstraint("amo_id", "supplier_id", "id", name="uq_ext_site_tenant_ref"),
                   sa.UniqueConstraint("amo_id", "supplier_id", "site_code",
                                       name="uq_external_provider_site"),))
    _create("external_provider_contacts",
            sa.Column("contact_name", sa.String(255), nullable=False),
            sa.Column("email", sa.String(255)),
            sa.Column("phone", sa.String(80)),
            sa.Column("assignment", sa.String(32), nullable=False),
            sa.Column("site_id", sa.String(36)),
            sa.ForeignKeyConstraint(["amo_id", "supplier_id", "site_id"],
                                    ["external_provider_sites.amo_id", "external_provider_sites.supplier_id", "external_provider_sites.id"]),
            sa.CheckConstraint("assignment IN ('COMMERCIAL','TECHNICAL','QUALITY','OTHER')",
                               name="assignment_valid"),
            extra=(sa.UniqueConstraint("amo_id", "supplier_id", "id", name="uq_ext_contact_tenant_ref"),))
    op.create_unique_constraint("uq_ext_qms_evidence_tenant_identity",
                                "quality_external_provider_evidence", ["amo_id", "supplier_id", "id"])
    _create("external_provider_capabilities",
            sa.Column("site_id", sa.String(36)),
            sa.Column("capability_type", sa.String(64), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("manufacturer", sa.String(255)),
            sa.Column("product_family", sa.String(255)),
            sa.Column("rating", sa.String(255)),
            sa.Column("limitations", sa.Text()),
            sa.Column("regulatory_authority", sa.String(128)),
            sa.Column("certificate_number", sa.String(128)),
            sa.Column("valid_until", sa.Date()),
            sa.Column("evidence_id", sa.String(36)),
            sa.ForeignKeyConstraint(["amo_id", "supplier_id", "site_id"],
                                    ["external_provider_sites.amo_id", "external_provider_sites.supplier_id", "external_provider_sites.id"]),
            sa.ForeignKeyConstraint(["amo_id", "supplier_id", "evidence_id"],
                                    ["quality_external_provider_evidence.amo_id",
                                     "quality_external_provider_evidence.supplier_id",
                                     "quality_external_provider_evidence.id"]))
    _create("external_provider_source_links",
            sa.Column("source_system", sa.String(80), nullable=False),
            sa.Column("source_identifier", sa.String(255), nullable=False),
            sa.Column("source_row", sa.Integer()),
            sa.Column("source_digest", sa.String(64)),
            sa.Column("imported_at", sa.DateTime(timezone=True)),
            extra=(sa.UniqueConstraint("amo_id", "source_system", "source_identifier",
                                       name="uq_external_provider_source_identity"),))

    _create("external_provider_certificates",
            sa.Column("certificate_type", sa.String(80), nullable=False),
            sa.Column("certificate_number", sa.String(160), nullable=False),
            sa.Column("issuing_authority", sa.String(160)),
            sa.Column("jurisdiction", sa.String(80)),
            sa.Column("approval_rating", sa.String(255)),
            sa.Column("limitations", sa.Text()),
            sa.Column("valid_from", sa.Date()),
            sa.Column("valid_until", sa.Date()),
            sa.Column("verification_state", sa.String(20), nullable=False, server_default="UNVERIFIED"),
            sa.Column("verified_by_user_id", sa.String(36)),
            sa.Column("verified_at", sa.DateTime(timezone=True)),
            sa.Column("evidence_id", sa.String(36)),
            sa.CheckConstraint("verification_state IN ('UNVERIFIED','VERIFIED','REJECTED','SUPERSEDED')",
                               name="ck_ext_provider_certificate_verification"),
            sa.CheckConstraint("valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from",
                               name="ck_ext_provider_certificate_validity"),
            sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["amo_id", "supplier_id", "evidence_id"],
                                    ["quality_external_provider_evidence.amo_id",
                                     "quality_external_provider_evidence.supplier_id",
                                     "quality_external_provider_evidence.id"]),
            extra=(sa.UniqueConstraint("amo_id", "supplier_id", "certificate_type",
                                       "certificate_number", name="uq_ext_provider_certificate"),))
    op.create_unique_constraint("uq_ext_contract_tenant_identity",
                                "quality_external_provider_contracts", ["amo_id", "supplier_id", "id"])
    op.create_unique_constraint("uq_ext_supplier_scope_tenant_identity",
                                "procurement_supplier_approval_scopes", ["amo_id", "supplier_id", "id"])
    op.create_unique_constraint("uq_ext_user_tenant_identity", "users", ["amo_id", "id"])
    _create("external_provider_relationships",
            sa.Column("parent_supplier_id", sa.Integer(), nullable=False),
            sa.Column("contract_id", sa.String(36)),
            sa.Column("relationship_kind", sa.String(32), nullable=False),
            sa.Column("function_scope", sa.Text(), nullable=False),
            sa.Column("consent_state", sa.String(24), nullable=False, server_default="PENDING"),
            sa.Column("consent_evidence_id", sa.String(36)),
            sa.Column("consent_issued_at", sa.DateTime(timezone=True)),
            sa.Column("consent_expires_on", sa.Date()),
            sa.CheckConstraint("parent_supplier_id <> supplier_id",
                               name="ck_ext_provider_distinct_relatives"),
            sa.CheckConstraint("relationship_kind IN ('PARENT','FURTHER_SUBCONTRACTOR','AFFILIATE')",
                               name="ck_ext_provider_relation_kind"),
            sa.CheckConstraint("consent_state IN ('PENDING','VERIFIED','REVOKED')",
                               name="ck_ext_provider_relation_consent"),
            sa.ForeignKeyConstraint(["amo_id", "parent_supplier_id"],
                                    ["procurement_suppliers.amo_id", "procurement_suppliers.id"]),
            sa.ForeignKeyConstraint(["amo_id", "parent_supplier_id", "contract_id"],
                                    ["quality_external_provider_contracts.amo_id",
                                     "quality_external_provider_contracts.supplier_id",
                                     "quality_external_provider_contracts.id"]),
            sa.ForeignKeyConstraint(["amo_id", "parent_supplier_id", "consent_evidence_id"],
                                    ["quality_external_provider_evidence.amo_id",
                                     "quality_external_provider_evidence.supplier_id",
                                     "quality_external_provider_evidence.id"]),
            extra=(sa.UniqueConstraint("amo_id", "supplier_id", "parent_supplier_id",
                                       "relationship_kind", name="uq_ext_provider_relation"),))
    _create("external_provider_account_links",
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("contact_id", sa.String(36)),
            sa.Column("account_state", sa.String(24), nullable=False, server_default="PENDING"),
            sa.Column("requested_scopes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("authorized_by_user_id", sa.String(36)),
            sa.Column("authorized_at", sa.DateTime(timezone=True)),
            sa.CheckConstraint("account_state IN ('PENDING','VERIFIED','REVOKED')",
                               name="ck_ext_provider_account_state"),
            sa.ForeignKeyConstraint(["amo_id", "user_id"], ["users.amo_id", "users.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["authorized_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["amo_id", "supplier_id", "contact_id"],
                                    ["external_provider_contacts.amo_id", "external_provider_contacts.supplier_id",
                                     "external_provider_contacts.id"]),
            extra=(sa.UniqueConstraint("amo_id", "supplier_id", "user_id",
                                       name="uq_ext_provider_account_link"),))
    _create("external_provider_scope_links",
            sa.Column("approval_scope_id", sa.Integer(), nullable=False),
            sa.Column("site_id", sa.String(36)),
            sa.Column("contracted_function", sa.String(128)),
            sa.Column("service_category", sa.String(128)),
            sa.Column("product_family", sa.String(128)),
            sa.ForeignKeyConstraint(["amo_id", "supplier_id", "approval_scope_id"],
                                    ["procurement_supplier_approval_scopes.amo_id",
                                     "procurement_supplier_approval_scopes.supplier_id",
                                     "procurement_supplier_approval_scopes.id"]),
            sa.ForeignKeyConstraint(["amo_id", "supplier_id", "site_id"],
                                    ["external_provider_sites.amo_id", "external_provider_sites.supplier_id",
                                     "external_provider_sites.id"]),
            extra=(sa.UniqueConstraint("amo_id", "supplier_id", "approval_scope_id", "site_id",
                                       name="uq_ext_provider_scope_link"),))
    _create("external_provider_change_events",
            sa.Column("event_type", sa.String(100), nullable=False),
            sa.Column("actor_user_id", sa.String(36)),
            sa.Column("source_system", sa.String(80), nullable=False),
            sa.Column("source_identifier", sa.String(255)),
            sa.Column("before_json", sa.JSON()),
            sa.Column("after_json", sa.JSON(), nullable=False),
            sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"))
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("""CREATE FUNCTION external_provider_prevent_event_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $
            BEGIN RAISE EXCEPTION 'External provider event provenance is immutable'; END $"""))
        op.execute(sa.text("""CREATE TRIGGER trg_external_provider_events_immutable
            BEFORE UPDATE OR DELETE ON external_provider_change_events
            FOR EACH ROW EXECUTE FUNCTION external_provider_prevent_event_mutation()"""))

    op.create_table("external_provider_import_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("mapping_json", sa.JSON(), nullable=False),
        sa.Column("import_kind", sa.String(20), nullable=False, server_default="SUPPLIERS"),
        sa.Column("mapping_digest", sa.String(64), nullable=False),
        sa.Column("source_sheet", sa.String(128)),
        sa.Column("status", sa.String(20), nullable=False, server_default="STAGED"),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("committed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("amo_id", "id", name="uq_ext_import_batch_tenant_id"),
        sa.UniqueConstraint("amo_id", "source_sha256", "import_kind", "mapping_digest",
                            name="uq_ext_import_tenant_file"),
        sa.CheckConstraint("import_kind IN ('SUPPLIERS','CONTRACTS')", name="ck_ext_import_kind"),
        sa.CheckConstraint("status IN ('STAGED','COMMITTED','ROLLED_BACK','SUPERSEDED')", name="ck_ext_import_status"),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"))
    op.create_index("ix_ext_import_batches_tenant", "external_provider_import_batches", ["amo_id", "status"])
    op.create_table("external_provider_import_rows",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), nullable=False),
        sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("sheet_name", sa.String(128), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("raw_json", sa.JSON(), nullable=False),
        sa.Column("normalized_json", sa.JSON(), nullable=False),
        sa.Column("diagnostics_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="READY"),
        sa.Column("supplier_id", sa.Integer()),
        sa.Column("contract_id", sa.String(36)),
        sa.CheckConstraint("status IN ('READY','ERROR','CREATED','ROLLED_BACK')", name="ck_ext_import_row_state"),
        sa.ForeignKeyConstraint(["amo_id", "supplier_id", "contract_id"],
                                ["quality_external_provider_contracts.amo_id",
                                 "quality_external_provider_contracts.supplier_id",
                                 "quality_external_provider_contracts.id"]),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["amo_id", "batch_id"],
                                ["external_provider_import_batches.amo_id", "external_provider_import_batches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["amo_id", "supplier_id"],
                                ["procurement_suppliers.amo_id", "procurement_suppliers.id"]),
        sa.UniqueConstraint("batch_id", "sheet_name", "row_number", name="uq_ext_import_source_row"))
    op.create_index("ix_ext_import_rows_batch", "external_provider_import_rows", ["amo_id", "batch_id"])
    if op.get_bind().dialect.name == "postgresql":
        for name in ("external_provider_import_batches", "external_provider_import_rows"):
            op.execute(sa.text(f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY'))
            op.execute(sa.text(f'ALTER TABLE "{name}" FORCE ROW LEVEL SECURITY'))
            op.execute(sa.text(f"""CREATE POLICY "{name}_tenant" ON "{name}"
                USING (amo_id = NULLIF(current_setting('app.tenant_id', true), ''))
                WITH CHECK (amo_id = NULLIF(current_setting('app.tenant_id', true), ''))"""))

def downgrade():

    for name in ("external_provider_import_rows", "external_provider_import_batches"):
        if op.get_bind().dialect.name == "postgresql":
            op.execute(sa.text(f'DROP POLICY IF EXISTS "{name}_tenant" ON "{name}"'))
        op.drop_table(name)
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_external_provider_events_immutable ON external_provider_change_events"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS external_provider_prevent_event_mutation()"))
    for name in reversed(TABLES):
        if op.get_bind().dialect.name == "postgresql":
            op.execute(sa.text(f'DROP POLICY IF EXISTS "{name}_tenant" ON "{name}"'))
        op.drop_index(f"ix_{name}_supplier", table_name=name)
        op.drop_table(name)
    op.drop_constraint("uq_ext_user_tenant_identity", "users", type_="unique")
    op.drop_constraint("uq_ext_contract_tenant_identity",
                       "quality_external_provider_contracts", type_="unique")
    op.drop_constraint("uq_ext_supplier_scope_tenant_identity",
                       "procurement_supplier_approval_scopes", type_="unique")
    op.drop_constraint("uq_ext_qms_evidence_tenant_identity",
                       "quality_external_provider_evidence", type_="unique")
    op.drop_constraint("uq_procurement_supplier_tenant_identity", "procurement_suppliers", type_="unique")
