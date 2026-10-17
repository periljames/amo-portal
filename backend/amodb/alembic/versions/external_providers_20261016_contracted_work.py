"""Phase 7: governed outbound contracted maintenance, distinct from commercial Procurement.

All four registers are tenant-isolated. Technical events are append-only and neither
supplier submission nor a PO can independently create a maintenance release.
"""
from alembic import op
import sqlalchemy as sa

revision = "extprov_261016_work"
down_revision = "extprov_261016_proc"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("external_contracted_work",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("procurement_suppliers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("provider_id", sa.String(36), sa.ForeignKey("external_tenant_providers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("work_number", sa.String(80), nullable=False),
        sa.Column("work_type", sa.String(24), nullable=False),
        sa.Column("work_title", sa.String(255), nullable=False),
        sa.Column("function", sa.String(255), nullable=False),
        sa.Column("scope_text", sa.Text(), nullable=False),
        sa.Column("site_code", sa.String(64), nullable=False),
        sa.Column("scope_id", sa.Integer(), sa.ForeignKey("procurement_supplier_approval_scopes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contract_id", sa.String(36), sa.ForeignKey("quality_external_provider_contracts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("purchase_order_id", sa.Integer(), sa.ForeignKey("procurement_purchase_orders.id", ondelete="RESTRICT")),
        sa.Column("internal_work_reference", sa.String(128)),
        sa.Column("technical_coordinator_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("asset_kind", sa.String(32), nullable=False),
        sa.Column("registration", sa.String(40)),
        sa.Column("part_number", sa.String(90)),
        sa.Column("serial_number", sa.String(90)),
        sa.Column("asset_description", sa.String(255)),
        sa.Column("defect", sa.Text(), nullable=False),
        sa.Column("data_reference", sa.String(255), nullable=False),
        sa.Column("data_revision", sa.String(80), nullable=False),
        sa.Column("inspections_json", sa.JSON(), nullable=False),
        sa.Column("required_release", sa.String(255), nullable=False),
        sa.Column("requirements_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(48), nullable=False, server_default="DRAFT"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("technical_review_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("technical_review_at", sa.DateTime(timezone=True)),
        sa.Column("quality_checked_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("quality_checked_at", sa.DateTime(timezone=True)),
        sa.Column("authorized_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("authorized_at", sa.DateTime(timezone=True)),
        sa.Column("accepted_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("closure_reason", sa.Text()),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("amo_id", "work_number", name="uq_external_work_number"),
        sa.CheckConstraint("version > 0", name="ck_external_work_version"),
        sa.CheckConstraint("work_type IN ('BASE','LINE','WORKSHOP','SPECIALISED')", name="ck_external_work_type"),
        sa.CheckConstraint("asset_kind IN ('AIRCRAFT','ENGINE','COMPONENT','PROPELLER','APU','SERVICE')", name="ck_external_work_asset"),
    )
    op.create_index("ix_external_work_scope", "external_contracted_work", ["amo_id", "supplier_id", "status"])
    op.create_table("external_contracted_work_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("work_id", sa.String(36), sa.ForeignKey("external_contracted_work.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("actor_identity_id", sa.String(36), sa.ForeignKey("external_identities.id", ondelete="RESTRICT")),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("from_state", sa.String(48)),
        sa.Column("to_state", sa.String(48)),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("amo_id", "work_id", "idempotency_key", name="uq_external_work_event_retry"),
    )
    op.create_index("ix_external_work_events", "external_contracted_work_events", ["amo_id", "work_id", "created_at"])
    op.create_table("external_contracted_additional_work",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("work_id", sa.String(36), sa.ForeignKey("external_contracted_work.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("technical_data", sa.Text()),
        sa.Column("commercial_reference", sa.String(128)),
        sa.Column("operator_approval_reference", sa.String(128)),
        sa.Column("authority_approval_reference", sa.String(128)),
        sa.Column("state", sa.String(24), nullable=False, server_default="REQUESTED"),
        sa.Column("requested_by_identity_id", sa.String(36), sa.ForeignKey("external_identities.id", ondelete="RESTRICT")),
        sa.Column("reviewed_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("decision_reason", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("state IN ('REQUESTED','APPROVED','REJECTED','WITHDRAWN')", name="ck_external_additional_state"),
    )
    op.create_table("external_contracted_custody",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("work_id", sa.String(36), sa.ForeignKey("external_contracted_work.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("item_type", sa.String(32), nullable=False),
        sa.Column("part_number", sa.String(96)),
        sa.Column("serial_batch", sa.String(128)),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("uom", sa.String(24), nullable=False),
        sa.Column("condition", sa.String(255)),
        sa.Column("stores_reference", sa.String(128)),
        sa.Column("state", sa.String(24), nullable=False, server_default="REGISTERED"),
        sa.Column("discrepancy", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_external_custody_qty"),
        sa.CheckConstraint("state IN ('REGISTERED','DISPATCHED','RECEIVED_BY_PROVIDER','CONSUMED','RETURNED','DISCREPANCY','RECONCILED')", name="ck_external_custody_state"),
    )
    # A release or generic test-report attachment does not establish that each
    # required inspection/test/hold point was reviewed against its own evidence.
    op.create_table("external_contracted_inspection_checks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("work_id", sa.String(36), sa.ForeignKey("external_contracted_work.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("criterion_index", sa.Integer(), nullable=False),
        sa.Column("criterion", sa.Text(), nullable=False),
        sa.Column("result", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("submission_id", sa.String(36), sa.ForeignKey("external_partner_evidence_submissions.id", ondelete="RESTRICT")),
        sa.Column("review_reason", sa.Text()),
        sa.Column("reviewed_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("amo_id","work_id","criterion_index", name="uq_external_work_inspection_index"),
        sa.CheckConstraint("criterion_index >= 0", name="ck_external_inspection_index"),
        sa.CheckConstraint("result IN ('PENDING','ACCEPTED','REJECTED')", name="ck_external_inspection_result"),
    )
    op.create_index("ix_ext_work_inspection", "external_contracted_inspection_checks", ["amo_id","work_id","result"])
    op.create_table("external_contracted_evidence_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("work_id", sa.String(36), sa.ForeignKey("external_contracted_work.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_submission_id", sa.String(36), sa.ForeignKey("external_partner_evidence_submissions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("linked_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("amo_id","work_id","source_submission_id", name="uq_external_work_evidence"),
    )
    with op.batch_alter_table("external_partner_evidence_submissions") as batch:
        batch.drop_constraint("ck_ext_partner_upload_relation", type_="check")
        batch.create_check_constraint("ck_ext_partner_upload_relation",
            "related_kind IN ('PROVIDER','CONTRACT','ASSIGNMENT','RFQ','PO','SHIPMENT','CONTRACTED_WORK')")
    if op.get_bind().dialect.name == "postgresql":
        for table in ("external_contracted_work","external_contracted_work_events","external_contracted_additional_work","external_contracted_custody","external_contracted_inspection_checks","external_contracted_evidence_links"):
            op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
            op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
            op.execute(sa.text(f"""CREATE POLICY "{table}_tenant" ON "{table}"
              USING (amo_id = NULLIF(current_setting('app.tenant_id', true), ''))
              WITH CHECK (amo_id = NULLIF(current_setting('app.tenant_id', true), ''))"""))
        op.execute("""CREATE FUNCTION external_contracted_event_immutable() RETURNS trigger
          LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'Contracted work history is immutable';
          END; $$""")
        op.execute("""CREATE TRIGGER external_contracted_event_no_edit
          BEFORE UPDATE OR DELETE ON external_contracted_work_events
          FOR EACH ROW EXECUTE FUNCTION external_contracted_event_immutable()""")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS external_contracted_event_no_edit ON external_contracted_work_events")
        op.execute("DROP FUNCTION IF EXISTS external_contracted_event_immutable()")
    with op.batch_alter_table("external_partner_evidence_submissions") as batch:
        batch.drop_constraint("ck_ext_partner_upload_relation", type_="check")
        batch.create_check_constraint("ck_ext_partner_upload_relation",
            "related_kind IN ('PROVIDER','CONTRACT','ASSIGNMENT','RFQ','PO','SHIPMENT')")
    for table in ("external_contracted_evidence_links","external_contracted_inspection_checks","external_contracted_custody","external_contracted_additional_work",
                  "external_contracted_work_events","external_contracted_work"):
        op.drop_table(table)
