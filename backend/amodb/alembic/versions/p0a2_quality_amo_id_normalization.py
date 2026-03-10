"""P0 quality amo_id normalization

Revision ID: p0a2_quality_amo_id_normalization
Revises: p0a1_authz_core_tables
Create Date: 2026-03-09 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "p0a2_quality_amo_id_normalization"
down_revision = "p0a1_authz_core_tables"
branch_labels = None
depends_on = None

TABLES = [
    "qms_documents",
    "qms_document_revisions",
    "qms_document_distributions",
    "qms_audits",
    "qms_audit_findings",
    "quality_cars",
    "qms_notifications",
]


def _add_amo_column_if_missing(table_name: str) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns(table_name)}
    if "amo_id" not in cols:
        op.add_column(table_name, sa.Column("amo_id", sa.String(length=36), nullable=True))


def upgrade() -> None:
    bind = op.get_bind()
    for t in TABLES:
        _add_amo_column_if_missing(t)

    bind.execute(sa.text("""UPDATE qms_documents d SET amo_id = u.amo_id FROM users u WHERE d.amo_id IS NULL AND d.created_by_user_id = u.id"""))
    bind.execute(sa.text("""UPDATE qms_documents d SET amo_id = u.amo_id FROM users u WHERE d.amo_id IS NULL AND d.owner_user_id = u.id"""))
    bind.execute(sa.text("""UPDATE qms_document_revisions r SET amo_id = d.amo_id FROM qms_documents d WHERE r.amo_id IS NULL AND r.document_id = d.id"""))
    bind.execute(sa.text("""UPDATE qms_document_distributions x SET amo_id = d.amo_id FROM qms_documents d WHERE x.amo_id IS NULL AND x.document_id = d.id"""))
    bind.execute(sa.text("""UPDATE qms_audits a SET amo_id = u.amo_id FROM users u WHERE a.amo_id IS NULL AND a.created_by_user_id = u.id"""))
    bind.execute(sa.text("""UPDATE qms_audit_findings f SET amo_id = a.amo_id FROM qms_audits a WHERE f.amo_id IS NULL AND f.audit_id = a.id"""))
    bind.execute(sa.text("""UPDATE quality_cars c SET amo_id = u.amo_id FROM users u WHERE c.amo_id IS NULL AND c.requested_by_user_id = u.id"""))
    bind.execute(sa.text("""UPDATE quality_cars c SET amo_id = f.amo_id FROM qms_audit_findings f WHERE c.amo_id IS NULL AND c.finding_id = f.id"""))
    bind.execute(sa.text("""UPDATE qms_notifications n SET amo_id = u.amo_id FROM users u WHERE n.amo_id IS NULL AND n.user_id = u.id"""))

    op.create_table(
        "quality_tenant_backfill_issues",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("table_name", sa.String(length=64), nullable=False),
        sa.Column("row_id", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    for t in TABLES:
        bind.execute(
            sa.text(
                f"""
                INSERT INTO quality_tenant_backfill_issues (table_name, row_id, reason)
                SELECT :table_name, CAST(id AS TEXT), 'amo_id unresolved during P0 normalization'
                FROM {t}
                WHERE amo_id IS NULL
                """
            ),
            {"table_name": t},
        )

    for t in TABLES:
        op.create_foreign_key(f"fk_{t}_amo_id_amos", t, "amos", ["amo_id"], ["id"], ondelete="CASCADE")
        op.create_index(f"ix_{t}_amo_id", t, ["amo_id"])

    op.drop_constraint("uq_qms_doc_code", "qms_documents", type_="unique")
    op.create_unique_constraint("uq_qms_doc_code_per_amo", "qms_documents", ["amo_id", "domain", "doc_type", "doc_code"])

    op.drop_constraint("uq_qms_audit_ref", "qms_audits", type_="unique")
    op.create_unique_constraint("uq_qms_audit_ref_per_amo", "qms_audits", ["amo_id", "domain", "audit_ref"])

    unresolved = bind.execute(sa.text("SELECT COUNT(*) FROM quality_tenant_backfill_issues")).scalar() or 0
    if unresolved == 0:
        for t in TABLES:
            op.alter_column(t, "amo_id", nullable=False)


def downgrade() -> None:
    op.drop_constraint("uq_qms_doc_code_per_amo", "qms_documents", type_="unique")
    op.create_unique_constraint("uq_qms_doc_code", "qms_documents", ["domain", "doc_type", "doc_code"])
    op.drop_constraint("uq_qms_audit_ref_per_amo", "qms_audits", type_="unique")
    op.create_unique_constraint("uq_qms_audit_ref", "qms_audits", ["domain", "audit_ref"])

    for t in TABLES:
        try:
            op.drop_index(f"ix_{t}_amo_id", table_name=t)
        except Exception:
            pass
        try:
            op.drop_constraint(f"fk_{t}_amo_id_amos", t, type_="foreignkey")
        except Exception:
            pass

    op.drop_table("quality_tenant_backfill_issues")
