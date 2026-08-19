"""Add ephemeral audit collaboration presence.

Revision ID: quality_260817_audit_presence
Revises: quality_260817_evidence_artifacts
Create Date: 2026-08-17
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260817_audit_presence"
down_revision = "quality_260817_evidence_artifacts"
branch_labels = None
depends_on = None

TABLE = "quality_audit_presence"


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("amo_id", sa.String(length=36), nullable=False),
        sa.Column("audit_id", sa.Uuid(), nullable=False),
        sa.Column("actor_type", sa.String(length=24), nullable=False),
        sa.Column("actor_key", sa.String(length=96), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("participant_id", sa.String(length=36), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=128), nullable=True),
        sa.Column("route", sa.String(length=128), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["amo_id"], ["amos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["audit_id"], ["qms_audits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_id"], ["quality_audit_participants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("amo_id", "audit_id", "actor_key", name="uq_quality_audit_presence_actor"),
        sa.CheckConstraint("actor_type IN ('INTERNAL_USER','EXTERNAL_AUDITOR','AUDITEE_GUEST')", name="ck_quality_audit_presence_actor_type"),
        sa.CheckConstraint(
            "(actor_type = 'INTERNAL_USER' AND user_id IS NOT NULL AND participant_id IS NULL) OR "
            "(actor_type <> 'INTERNAL_USER' AND user_id IS NULL AND participant_id IS NOT NULL)",
            name="ck_quality_audit_presence_actor_identity",
        ),
    )
    op.create_index("ix_quality_audit_presence_live", TABLE, ["amo_id", "audit_id", "last_seen_at"])
    if _is_postgresql():
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f"""
            CREATE POLICY {TABLE}_amo_isolation
            ON "{TABLE}"
            USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
            WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
        """))


def downgrade() -> None:
    if _is_postgresql():
        op.execute(sa.text(f"DROP POLICY IF EXISTS {TABLE}_amo_isolation ON \"{TABLE}\""))
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" NO FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" DISABLE ROW LEVEL SECURITY'))
    op.drop_index("ix_quality_audit_presence_live", table_name=TABLE)
    op.drop_table(TABLE)
