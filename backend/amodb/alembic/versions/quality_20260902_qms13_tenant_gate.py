"""Close the QMS-01..13 tenant-isolation schema gap.

Revision ID: quality_260902_qms13_gate
Revises: procurement_260820_supplier_gov, quality_260823_hybrid_programme
Create Date: 2026-09-02

Manual change requests predated tenant normalization and could therefore be
listed, updated, and counted across AMOs.  Make the tenant key authoritative,
backfill only from the attributable creator, and fail the deployment if any
historical row cannot be assigned without guessing.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "quality_260902_qms13_gate"
down_revision = (
    "procurement_260820_supplier_gov",
    "quality_260823_hybrid_programme",
)
branch_labels = None
depends_on = None


TABLE = "qms_manual_change_requests"
TENANT_FK = "fk_qms_manual_change_requests_amo_id_amos"
TENANT_POLICY = "qms_manual_change_requests_tenant_isolation"


def _inspector():
    return sa.inspect(op.get_bind())


def _columns() -> set[str]:
    return {column["name"] for column in _inspector().get_columns(TABLE)}


def _indexes() -> set[str]:
    return {index["name"] for index in _inspector().get_indexes(TABLE)}


def _foreign_keys() -> set[str]:
    return {
        foreign_key["name"]
        for foreign_key in _inspector().get_foreign_keys(TABLE)
        if foreign_key.get("name")
    }


def upgrade() -> None:
    bind = op.get_bind()
    if not _inspector().has_table(TABLE):
        raise RuntimeError(f"Required Quality table {TABLE} is missing; repair the migration baseline before deployment")

    if "amo_id" not in _columns():
        op.add_column(TABLE, sa.Column("amo_id", sa.String(length=36), nullable=True))

    if bind.dialect.name == "postgresql":
        op.execute(sa.text(
            """
            UPDATE qms_manual_change_requests request
            SET amo_id = creator.amo_id
            FROM users creator
            WHERE request.amo_id IS NULL
              AND request.created_by_user_id = creator.id
            """
        ))
    else:
        op.execute(sa.text(
            """
            UPDATE qms_manual_change_requests
            SET amo_id = (
                SELECT users.amo_id
                FROM users
                WHERE users.id = qms_manual_change_requests.created_by_user_id
            )
            WHERE amo_id IS NULL
            """
        ))

    unscoped = int(bind.execute(sa.text(
        "SELECT COUNT(*) FROM qms_manual_change_requests WHERE amo_id IS NULL"
    )).scalar() or 0)
    if unscoped:
        raise RuntimeError(
            f"Cannot safely tenant-scope {unscoped} manual change request row(s) without an attributable creator; "
            "remediate those rows before rerunning Alembic"
        )

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(TABLE) as batch:
            if TENANT_FK not in _foreign_keys():
                batch.create_foreign_key(TENANT_FK, "amos", ["amo_id"], ["id"], ondelete="CASCADE")
            batch.alter_column("amo_id", existing_type=sa.String(length=36), nullable=False)
    else:
        if TENANT_FK not in _foreign_keys():
            op.create_foreign_key(TENANT_FK, TABLE, "amos", ["amo_id"], ["id"], ondelete="CASCADE")
        op.alter_column(TABLE, "amo_id", existing_type=sa.String(length=36), nullable=False)

    indexes = _indexes()
    for obsolete in ("ix_qms_cr_domain_status", "ix_qms_cr_submitted_at"):
        if obsolete in indexes:
            op.drop_index(obsolete, table_name=TABLE)
    indexes = _indexes()
    if "ix_qms_manual_change_requests_amo_id" not in indexes:
        op.create_index("ix_qms_manual_change_requests_amo_id", TABLE, ["amo_id"])
    if "ix_qms_cr_amo_domain_status" not in indexes:
        op.create_index("ix_qms_cr_amo_domain_status", TABLE, ["amo_id", "domain", "status"])
    if "ix_qms_cr_amo_submitted_at" not in indexes:
        op.create_index("ix_qms_cr_amo_submitted_at", TABLE, ["amo_id", "submitted_at"])

    if bind.dialect.name == "postgresql":
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" ENABLE ROW LEVEL SECURITY'))
        policy_exists = bool(bind.execute(sa.text(
            """
            SELECT 1 FROM pg_policies
            WHERE schemaname = current_schema()
              AND tablename = :table_name
              AND policyname = :policy_name
            """
        ), {"table_name": TABLE, "policy_name": TENANT_POLICY}).first())
        if not policy_exists:
            op.execute(sa.text(f'''
                CREATE POLICY "{TENANT_POLICY}" ON "{TABLE}"
                USING (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
                WITH CHECK (amo_id::text = NULLIF(current_setting('app.tenant_id', true), ''))
            '''))


def downgrade() -> None:
    bind = op.get_bind()
    if not _inspector().has_table(TABLE) or "amo_id" not in _columns():
        return

    if bind.dialect.name == "postgresql":
        op.execute(sa.text(f'DROP POLICY IF EXISTS "{TENANT_POLICY}" ON "{TABLE}"'))
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" DISABLE ROW LEVEL SECURITY'))

    indexes = _indexes()
    for index_name in (
        "ix_qms_cr_amo_submitted_at",
        "ix_qms_cr_amo_domain_status",
        "ix_qms_manual_change_requests_amo_id",
    ):
        if index_name in indexes:
            op.drop_index(index_name, table_name=TABLE)
    if "ix_qms_cr_domain_status" not in _indexes():
        op.create_index("ix_qms_cr_domain_status", TABLE, ["domain", "status"])
    if "ix_qms_cr_submitted_at" not in _indexes():
        op.create_index("ix_qms_cr_submitted_at", TABLE, ["submitted_at"])

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(TABLE) as batch:
            if TENANT_FK in _foreign_keys():
                batch.drop_constraint(TENANT_FK, type_="foreignkey")
            batch.drop_column("amo_id")
    else:
        if TENANT_FK in _foreign_keys():
            op.drop_constraint(TENANT_FK, TABLE, type_="foreignkey")
        op.drop_column(TABLE, "amo_id")
