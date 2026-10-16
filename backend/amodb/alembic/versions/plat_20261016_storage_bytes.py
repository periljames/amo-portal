"""Add per-tenant BIGINT storage accounting and immutable object ledger.

Revision ID: plat_20261016_storage_bytes
Revises: quality_261003_evidence_context
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "plat_20261016_storage_bytes"
down_revision = "quality_261003_evidence_context"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tenant_storage_quotas",
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("quota_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("used_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("reserved_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("generation", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True)),
        sa.Column("integrity_state", sa.String(24), nullable=False, server_default="OK"),
        sa.CheckConstraint("quota_bytes >= 0 AND used_bytes >= 0 AND reserved_bytes >= 0", name="ck_tenant_storage_nonnegative"),
        sa.CheckConstraint("used_bytes + reserved_bytes <= quota_bytes", name="ck_tenant_storage_not_oversubscribed"),
    )
    op.create_table(
        "tenant_storage_reservations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False, server_default="RESERVED"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("finalized_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_tenant_storage_reservation_key"),
        sa.CheckConstraint("size_bytes > 0", name="ck_storage_reserved_positive"),
    )
    op.create_index("ix_storage_reservation_expire", "tenant_storage_reservations", ["state", "expires_at"])
    op.create_index("ix_storage_reservation_tenant", "tenant_storage_reservations", ["tenant_id"])
    op.create_table(
        "tenant_storage_objects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("state", sa.String(24), nullable=False, server_default="ACTIVE"),
        sa.Column("retained_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("reservation_id", sa.String(36), sa.ForeignKey("tenant_storage_reservations.id", ondelete="SET NULL")),
        sa.UniqueConstraint("tenant_id", "object_key", name="uq_tenant_storage_object_key"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_tenant_storage_object_nonnegative"),
    )
    op.create_index("ix_storage_objects_tenant", "tenant_storage_objects", ["tenant_id"])
    op.create_table(
        "tenant_storage_ledger_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("object_key", sa.Text()),
        sa.Column("delta_used_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("delta_reserved_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("quota_after_bytes", sa.BigInteger(), nullable=False),
        sa.Column("used_after_bytes", sa.BigInteger(), nullable=False),
        sa.Column("reserved_after_bytes", sa.BigInteger(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_storage_event_tenant_time", "tenant_storage_ledger_events", ["tenant_id", "created_at"])
    op.create_index("ix_storage_event_tenant", "tenant_storage_ledger_events", ["tenant_id"])

    if op.get_bind().dialect.name == "postgresql":
        for table in ("tenant_storage_quotas", "tenant_storage_reservations", "tenant_storage_objects", "tenant_storage_ledger_events"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(
                f"CREATE POLICY {table}_tenant_scope ON {table} USING "
                "(tenant_id = NULLIF(current_setting('app.tenant_id', true), '')) "
                "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), ''))"
            )


def downgrade():
    op.drop_table("tenant_storage_ledger_events")
    op.drop_table("tenant_storage_objects")
    op.drop_table("tenant_storage_reservations")
    op.drop_table("tenant_storage_quotas")
