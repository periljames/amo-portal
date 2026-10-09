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
          "external_provider_capabilities", "external_provider_source_links")

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
                               name="assignment_valid"))
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
            sa.ForeignKeyConstraint(["site_id"], ["external_provider_sites.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["evidence_id"], ["quality_external_provider_evidence.id"], ondelete="SET NULL"))
    _create("external_provider_source_links",
            sa.Column("source_system", sa.String(80), nullable=False),
            sa.Column("source_identifier", sa.String(255), nullable=False),
            sa.Column("source_row", sa.Integer()),
            sa.Column("source_digest", sa.String(64)),
            sa.Column("imported_at", sa.DateTime(timezone=True)),
            extra=(sa.UniqueConstraint("amo_id", "source_system", "source_identifier",
                                       name="uq_external_provider_source_identity"),))

def downgrade():
    for name in reversed(TABLES):
        if op.get_bind().dialect.name == "postgresql":
            op.execute(sa.text(f'DROP POLICY IF EXISTS "{name}_tenant" ON "{name}"'))
        op.drop_index(f"ix_{name}_supplier", table_name=name)
        op.drop_table(name)
    op.drop_constraint("uq_procurement_supplier_tenant_identity", "procurement_suppliers", type_="unique")
