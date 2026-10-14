"""Partner-facing review proposals, receipts, evidence and attributable notifications.

Revision ID: extprov_261012_partner
Revises: extprov_261012_identity
"""
from alembic import op
import sqlalchemy as sa

revision = "extprov_261012_partner"
down_revision = "extprov_261012_identity"
branch_labels = None
depends_on = None

_TABLES = (
    "external_partner_change_requests",
    "external_partner_contract_receipts",
    "external_partner_evidence_submissions",
    "external_partner_notifications",
)

def _tenant_columns():
    return [
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("amo_id",sa.String(36),nullable=False),
        sa.Column("tenant_provider_id",sa.String(36),nullable=False),
        sa.Column("identity_id",sa.String(36),sa.ForeignKey("external_identities.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["amo_id","tenant_provider_id"],
            ["external_tenant_providers.amo_id","external_tenant_providers.id"],ondelete="RESTRICT"),
    ]

def upgrade():
    op.create_table("external_partner_change_requests",*_tenant_columns(),
        sa.Column("category",sa.String(32),nullable=False),
        sa.Column("proposed_json",sa.JSON(),nullable=False),
        sa.Column("reason",sa.Text(),nullable=False),
        sa.Column("status",sa.String(24),nullable=False,server_default="PENDING"),
        sa.Column("source_version",sa.Integer()),
        sa.Column("review_note",sa.Text()),
        sa.Column("reviewed_by_user_id",sa.String(36),sa.ForeignKey("users.id",ondelete="SET NULL")),
        sa.Column("reviewed_at",sa.DateTime(timezone=True)),
        sa.Column("version",sa.Integer(),nullable=False,server_default="1"),
        sa.CheckConstraint("category IN ('IDENTITY','CONTACT','SITE','CAPABILITY','BANKING','RENEWAL')",name="ck_ext_partner_change_category"),
        sa.CheckConstraint("status IN ('PENDING','UNDER_REVIEW','ACCEPTED','REJECTED','WITHDRAWN')",name="ck_ext_partner_change_state"),
        sa.CheckConstraint("version > 0",name="ck_ext_partner_change_version"))
    op.create_index("ix_ext_partner_change_provider","external_partner_change_requests",
        ["amo_id","tenant_provider_id","status","created_at"])

    op.create_table("external_partner_contract_receipts",*_tenant_columns(),
        sa.Column("contract_id",sa.String(36),nullable=False),
        sa.Column("supplier_id",sa.Integer(),nullable=False),
        sa.Column("contract_version",sa.Integer(),nullable=False),
        sa.Column("document_revision",sa.String(64)),
        sa.Column("acknowledgement",sa.String(24),nullable=False),
        sa.Column("note",sa.Text()),
        sa.ForeignKeyConstraint(["amo_id","supplier_id","contract_id"],
            ["quality_external_provider_contracts.amo_id","quality_external_provider_contracts.supplier_id","quality_external_provider_contracts.id"],ondelete="RESTRICT"),
        sa.UniqueConstraint("amo_id","tenant_provider_id","identity_id","contract_id","contract_version",
            name="uq_ext_partner_contract_receipt"),
        sa.CheckConstraint("acknowledgement IN ('RECEIVED','REQUEST_CLARIFICATION')",name="ck_ext_partner_contract_ack"))
    op.create_index("ix_ext_partner_contract_receipts","external_partner_contract_receipts",
        ["amo_id","tenant_provider_id","contract_id"])

    op.create_table("external_partner_evidence_submissions",*_tenant_columns(),
        sa.Column("evidence_type",sa.String(48),nullable=False),
        sa.Column("related_kind",sa.String(32),nullable=False),
        sa.Column("related_id",sa.String(64)),
        sa.Column("filename",sa.String(255),nullable=False),
        sa.Column("content_type",sa.String(100),nullable=False),
        sa.Column("object_uri",sa.Text(),nullable=False),
        sa.Column("sha256",sa.String(64),nullable=False),
        sa.Column("size_bytes",sa.BigInteger(),nullable=False),
        sa.Column("status",sa.String(24),nullable=False,server_default="PENDING_REVIEW"),
        sa.Column("review_note",sa.Text()),
        sa.Column("reviewed_by_user_id",sa.String(36),sa.ForeignKey("users.id",ondelete="SET NULL")),
        sa.Column("reviewed_at",sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('PENDING_REVIEW','ACCEPTED','REJECTED','WITHDRAWN')",name="ck_ext_partner_upload_state"),
        sa.CheckConstraint("related_kind IN ('PROVIDER','CONTRACT','ASSIGNMENT')",name="ck_ext_partner_upload_relation"),
        sa.CheckConstraint("size_bytes BETWEEN 1 AND 20971520",name="ck_ext_partner_upload_limit"))
    op.create_index("ix_ext_partner_evidence_provider","external_partner_evidence_submissions",
        ["amo_id","tenant_provider_id","created_at"])

    op.create_table("external_partner_notifications",
        sa.Column("id",sa.String(36),primary_key=True),
        sa.Column("amo_id",sa.String(36),nullable=False),
        sa.Column("tenant_provider_id",sa.String(36),nullable=False),
        sa.Column("identity_id",sa.String(36),sa.ForeignKey("external_identities.id",ondelete="RESTRICT"),nullable=False),
        sa.Column("category",sa.String(32),nullable=False),
        sa.Column("title",sa.String(200),nullable=False),
        sa.Column("message",sa.Text(),nullable=False),
        sa.Column("resource_kind",sa.String(32)),
        sa.Column("resource_id",sa.String(64)),
        sa.Column("read_at",sa.DateTime(timezone=True)),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["amo_id","tenant_provider_id"],
            ["external_tenant_providers.amo_id","external_tenant_providers.id"],ondelete="RESTRICT"))
    op.create_index("ix_ext_partner_notifications_identity","external_partner_notifications",
        ["amo_id","tenant_provider_id","identity_id","read_at","created_at"])

    if op.get_bind().dialect.name == "postgresql":
        for name in _TABLES:
            op.execute(sa.text(f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY'))
            op.execute(sa.text(f'ALTER TABLE "{name}" FORCE ROW LEVEL SECURITY'))
            # The external request sets app.external_provider_id; internal Quality
            # review has no provider context and remains scoped by tenant+role.
            # RLS therefore protects cross-provider access even if a future
            # read-projection query accidentally omits its supplier predicate.
            provider_guard = """(
                tenant_provider_id = NULLIF(current_setting('app.external_provider_id',true),'')
                OR current_setting('app.external_provider_id',true) = '__INTERNAL_QUALITY_REVIEW__'
            )"""
            op.execute(sa.text(f"""CREATE POLICY "{name}_tenant" ON "{name}"
                USING (amo_id = NULLIF(current_setting('app.tenant_id',true),'') AND {provider_guard})
                WITH CHECK (amo_id = NULLIF(current_setting('app.tenant_id',true),'') AND {provider_guard})"""))

def downgrade():
    for name in reversed(_TABLES):
        op.drop_table(name)
