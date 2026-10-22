"""Add tenant-scoped, versioned RCA documents and corrective action records.

Revision ID: quality_car_rca_261022
Revises: extprov_261019_oversight
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "quality_car_rca_261022"
down_revision = "extprov_261019_oversight"
branch_labels = None
depends_on = None

TABLES = (
    "quality_car_rca_documents", "quality_car_rca_revisions",
    "quality_car_rca_actions", "quality_car_rca_mutations",
)


def _scoped_columns():
    return (
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("car_id", UUID(as_uuid=True), sa.ForeignKey("quality_cars.id", ondelete="CASCADE"), nullable=False),
    )


def _enable_rls(name):
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(sa.text('ALTER TABLE "' + name + '" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text('ALTER TABLE "' + name + '" FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(
        'CREATE POLICY ' + name + '_amo_isolation ON "' + name + '" '
        "USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), '')) "
        "WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))"
    ))


def upgrade():
    op.create_table("quality_car_rca_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True), *_scoped_columns(),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("draft", sa.JSON(), nullable=False),
        sa.Column("submitted_revision", sa.Integer()),
        sa.Column("submitted_snapshot", sa.JSON()),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("amo_id", "car_id", name="uq_quality_car_rca_document"),
        sa.CheckConstraint("revision >= 0", name="ck_quality_car_rca_revision_nonnegative"))
    op.create_index("ix_quality_car_rca_doc_lookup", "quality_car_rca_documents", ["amo_id", "car_id"])
    op.create_table("quality_car_rca_revisions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True), *_scoped_columns(),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("quality_car_rca_documents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("actor_kind", sa.String(16), nullable=False),
        sa.Column("actor_ref", sa.String(255)),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "revision", name="uq_quality_car_rca_revision_sequence"))
    op.create_index("ix_quality_car_rca_revision_history", "quality_car_rca_revisions", ["amo_id", "car_id", "created_at"])
    op.create_table("quality_car_rca_actions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True), *_scoped_columns(),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("cause_node_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_references", sa.JSON(), nullable=False),
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("external_owner_name", sa.String(255)),
        sa.Column("target_date", sa.Date()),
        sa.Column("priority", sa.String(12), nullable=False, server_default="MEDIUM"),
        sa.Column("state", sa.String(24), nullable=False, server_default="PROPOSED"),
        sa.Column("completion_note", sa.Text()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("quality_review_note", sa.Text()),
        sa.Column("reviewed_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("amo_id", "car_id", "sequence_no", name="uq_quality_car_rca_action_number"),
        sa.CheckConstraint("kind IN ('CORRECTIVE','PREVENTIVE','CONTAINMENT')", name="ck_quality_car_rca_action_kind"),
        sa.CheckConstraint("state IN ('PROPOSED','ACCEPTED','IN_PROGRESS','SUBMITTED','VERIFIED','REJECTED','CANCELLED')", name="ck_quality_car_rca_action_state"),
        sa.CheckConstraint("priority IN ('LOW','MEDIUM','HIGH','CRITICAL')", name="ck_quality_car_rca_action_priority"))
    op.create_index("ix_quality_car_rca_action_due", "quality_car_rca_actions", ["amo_id", "state", "target_date"])
    op.create_table("quality_car_rca_mutations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True), *_scoped_columns(),
        sa.Column("mutation_key", sa.String(100), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("result_revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("amo_id", "car_id", "mutation_key", name="uq_quality_car_rca_mutation_key"))
    op.create_index("ix_quality_car_rca_mutations", "quality_car_rca_mutations", ["amo_id", "car_id", "created_at"])
    for table in TABLES:
        _enable_rls(table)


def downgrade():
    # Downgrade refuses destruction of any retained RCA evidence.
    for table in TABLES:
        if op.get_bind().execute(sa.text('SELECT COUNT(*) FROM "' + table + '"')).scalar():
            raise RuntimeError("Cannot downgrade: governed RCA evidence exists in " + table)
    for table in reversed(TABLES):
        op.drop_table(table)
