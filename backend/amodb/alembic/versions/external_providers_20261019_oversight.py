"""Phase 9 immutable lifecycle history and provider oversight lookup indexes."""
from alembic import op
import sqlalchemy as sa

revision = "extprov_261019_oversight"
down_revision = "extprov_261018_alerts"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("external_provider_oversight_snapshots",
      sa.Column("id",sa.String(36),primary_key=True),
      sa.Column("amo_id",sa.String(36),nullable=False),
      sa.Column("supplier_id",sa.Integer(),nullable=False),
      sa.Column("actor_user_id",sa.String(36),sa.ForeignKey("users.id",ondelete="SET NULL")),
      sa.Column("action",sa.String(80),nullable=False),
      sa.Column("previous_status",sa.String(40)),
      sa.Column("current_status",sa.String(40),nullable=False),
      sa.Column("risk_level",sa.String(20),nullable=False),
      sa.Column("source_reference",sa.String(80)),
      sa.Column("occurred_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
      sa.ForeignKeyConstraint(["amo_id","supplier_id"],
         ["procurement_suppliers.amo_id","procurement_suppliers.id"],ondelete="RESTRICT"))
    op.create_index("ix_provider_snapshots_tenant_history","external_provider_oversight_snapshots",
                    ["amo_id","supplier_id","occurred_at"])
    op.create_index("ix_external_provider_contract_expiry",
       "quality_external_provider_contracts",["amo_id","status","expires_on"])
    op.create_index("ix_external_provider_certificate_expiry",
       "external_provider_certificates",["amo_id","verification_state","valid_until"])
    op.create_index("ix_external_provider_surveillance_due",
       "quality_provider_surveillance",["amo_id","supplier_id","due_on"])
    op.create_index("ix_external_provider_work_provider_state",
       "external_contracted_work",["amo_id","supplier_id","status","closed_at"])
    if op.get_bind().dialect.name=="postgresql":
        op.execute(sa.text("ALTER TABLE external_provider_oversight_snapshots ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text("ALTER TABLE external_provider_oversight_snapshots FORCE ROW LEVEL SECURITY"))
        condition="""amo_id=NULLIF(current_setting('app.tenant_id',true),'')
           AND (NULLIF(current_setting('app.external_provider_id',true),'') IS NULL
           OR current_setting('app.external_provider_id',true)='__INTERNAL_QUALITY_REVIEW__')"""
        op.execute(sa.text("CREATE POLICY ext_provider_snapshot_tenant ON external_provider_oversight_snapshots USING ("+condition+") WITH CHECK ("+condition+")"))
        op.execute(sa.text("""CREATE TRIGGER trg_ext_provider_snapshots_immutable
           BEFORE UPDATE OR DELETE ON external_provider_oversight_snapshots
           FOR EACH ROW EXECUTE FUNCTION external_provider_prevent_event_mutation()"""))

def downgrade():
    if op.get_bind().dialect.name=="postgresql":
        op.execute(sa.text("DROP TRIGGER IF EXISTS trg_ext_provider_snapshots_immutable ON external_provider_oversight_snapshots"))
    op.drop_index("ix_external_provider_work_provider_state",table_name="external_contracted_work")
    op.drop_index("ix_external_provider_surveillance_due",table_name="quality_provider_surveillance")
    op.drop_index("ix_external_provider_certificate_expiry",table_name="external_provider_certificates")
    op.drop_index("ix_external_provider_contract_expiry",table_name="quality_external_provider_contracts")
    op.drop_index("ix_provider_snapshots_tenant_history",table_name="external_provider_oversight_snapshots")
    op.drop_table("external_provider_oversight_snapshots")
