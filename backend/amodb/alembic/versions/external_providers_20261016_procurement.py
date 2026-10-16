"""Phase 6 supplier collaboration; no replacement of Procurement, Stores, QMS or Finance."""
from alembic import op
import sqlalchemy as sa

revision = "extprov_261016_proc"
down_revision = "extprov_261015_docs"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "external_procurement_quotes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("procurement_suppliers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("rfq_id", sa.Integer(), sa.ForeignKey("procurement_rfqs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("canonical_quote_id", sa.Integer(), sa.ForeignKey("procurement_quotes.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("external_reference", sa.String(128), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("previous_id", sa.String(36), sa.ForeignKey("external_procurement_quotes.id", ondelete="RESTRICT")),
        sa.Column("status", sa.String(20), nullable=False, server_default="SUBMITTED"),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("submitted_by_identity_id", sa.String(36), sa.ForeignKey("external_identities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("amo_id","supplier_id","rfq_id","external_reference","revision_no",name="uq_ext_proc_quote_revision"),
        sa.CheckConstraint("revision_no > 0",name="ck_ext_proc_revision"),
        sa.CheckConstraint("status IN ('SUBMITTED','WITHDRAWN','REPLACED')",name="ck_ext_proc_quote_state"),
    )
    op.create_index("ix_ext_proc_quote_supplier_rfq","external_procurement_quotes",["amo_id","supplier_id","rfq_id"])
    op.create_table(
        "external_procurement_shipments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("procurement_suppliers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("po_id", sa.Integer(), sa.ForeignKey("procurement_purchase_orders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("shipment_reference", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="ADVISED"),
        sa.Column("lines_json", sa.JSON(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("created_by_identity_id", sa.String(36), sa.ForeignKey("external_identities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("amo_id","supplier_id","po_id","shipment_reference",name="uq_ext_proc_shipment_reference"),
        sa.CheckConstraint("status IN ('ADVISED','CANCELLED')",name="ck_ext_proc_shipment_status"),
    )
    op.create_index("ix_ext_proc_shipment_po","external_procurement_shipments",["amo_id","supplier_id","po_id"])
    op.create_table(
        "external_procurement_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("procurement_suppliers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_identity_id", sa.String(36), sa.ForeignKey("external_identities.id", ondelete="RESTRICT")),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(48), nullable=False),
        sa.Column("message", sa.Text()),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("amo_id","supplier_id","idempotency_key",name="uq_ext_proc_event_retry"),
        sa.CheckConstraint("entity_type IN ('RFQ','QUOTE','PO','SHIPMENT','MATERIAL')",name="ck_ext_proc_event_entity"),
    )
    op.create_index("ix_ext_proc_event_entity","external_procurement_events",["amo_id","supplier_id","entity_type","entity_id","created_at"])
    with op.batch_alter_table("external_partner_evidence_submissions") as batch:
        batch.drop_constraint("ck_ext_partner_upload_relation", type_="check")
        batch.create_check_constraint("ck_ext_partner_upload_relation",
            "related_kind IN ('PROVIDER','CONTRACT','ASSIGNMENT','RFQ','PO','SHIPMENT')")
    if op.get_bind().dialect.name == "postgresql":
        for name in ("external_procurement_quotes","external_procurement_shipments","external_procurement_events"):
            op.execute(sa.text('ALTER TABLE "' + name + '" ENABLE ROW LEVEL SECURITY'))
            op.execute(sa.text('ALTER TABLE "' + name + '" FORCE ROW LEVEL SECURITY'))
            op.execute(sa.text('CREATE POLICY "' + name + '_tenant" ON "' + name +
                '" USING (amo_id = NULLIF(current_setting(' + "'app.tenant_id', true" + '), ' + "''" +
                ')) WITH CHECK (amo_id = NULLIF(current_setting(' + "'app.tenant_id', true" + '), ' + "''" + '))'))
        op.execute(sa.text("""
            CREATE FUNCTION external_procurement_event_immutable() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'Supplier transaction history is immutable'; END;
            $$;
        """))
        op.execute(sa.text("""
            CREATE TRIGGER external_procurement_event_no_edit
            BEFORE UPDATE OR DELETE ON external_procurement_events
            FOR EACH ROW EXECUTE FUNCTION external_procurement_event_immutable()
        """))

def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS external_procurement_event_no_edit ON external_procurement_events")
        op.execute("DROP FUNCTION IF EXISTS external_procurement_event_immutable()")
    with op.batch_alter_table("external_partner_evidence_submissions") as batch:
        batch.drop_constraint("ck_ext_partner_upload_relation", type_="check")
        batch.create_check_constraint("ck_ext_partner_upload_relation",
            "related_kind IN ('PROVIDER','CONTRACT','ASSIGNMENT')")
    op.drop_index("ix_ext_proc_event_entity",table_name="external_procurement_events")
    op.drop_table("external_procurement_events")
    op.drop_index("ix_ext_proc_shipment_po",table_name="external_procurement_shipments")
    op.drop_table("external_procurement_shipments")
    op.drop_index("ix_ext_proc_quote_supplier_rfq",table_name="external_procurement_quotes")
    op.drop_table("external_procurement_quotes")
