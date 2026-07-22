"""P0 Quality ``amo_id`` normalization with parallel-branch safety.

Revision ID: p0a2_quality_amo_id_norm
Revises: p0a1_authz_core_tables
Create Date: 2026-03-09 00:00:00.000000

The repository contains parallel Alembic branches. Some Quality tables may not
exist when this historical revision executes on a clean database. Every action
therefore operates only on tables and columns already present at this point.
The SaaS convergence migration repeats the normalization after all branches
have created their tables.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

from alembic import op
import sqlalchemy as sa


revision = "p0a2_quality_amo_id_norm"
down_revision = "p0a1_authz_core_tables"
branch_labels = None
depends_on = None

TABLES = (
    "qms_documents",
    "qms_document_revisions",
    "qms_document_distributions",
    "qms_audits",
    "qms_audit_findings",
    "quality_cars",
    "qms_notifications",
)


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return _inspector().has_table(table_name)


def _columns(table_name: str) -> set[str]:
    inspector = _inspector()
    if not inspector.has_table(table_name):
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def _has_columns(table_name: str, columns: Iterable[str]) -> bool:
    return set(columns).issubset(_columns(table_name))


def _constraint_names(table_name: str) -> set[str]:
    inspector = _inspector()
    if not inspector.has_table(table_name):
        return set()
    names = {
        str(item.get("name"))
        for item in inspector.get_unique_constraints(table_name)
        if item.get("name")
    }
    primary = inspector.get_pk_constraint(table_name).get("name")
    if primary:
        names.add(str(primary))
    names.update(
        str(item.get("name"))
        for item in inspector.get_foreign_keys(table_name)
        if item.get("name")
    )
    return names


def _index_names(table_name: str) -> set[str]:
    inspector = _inspector()
    if not inspector.has_table(table_name):
        return set()
    return {
        str(item.get("name"))
        for item in inspector.get_indexes(table_name)
        if item.get("name")
    }


def _foreign_key_exists(table_name: str, columns: Iterable[str], referred_table: str) -> bool:
    inspector = _inspector()
    if not inspector.has_table(table_name):
        return False
    expected = tuple(columns)
    return any(
        tuple(item.get("constrained_columns") or ()) == expected
        and str(item.get("referred_table") or "") == referred_table
        for item in inspector.get_foreign_keys(table_name)
    )


def _unique_exists(table_name: str, columns: Iterable[str]) -> bool:
    inspector = _inspector()
    if not inspector.has_table(table_name):
        return False
    expected = tuple(columns)
    if any(tuple(item.get("column_names") or ()) == expected for item in inspector.get_unique_constraints(table_name)):
        return True
    return any(
        bool(item.get("unique")) and tuple(item.get("column_names") or ()) == expected
        for item in inspector.get_indexes(table_name)
    )


def _add_amo_column_if_missing(table_name: str) -> bool:
    if not _has_table(table_name):
        return False
    if "amo_id" not in _columns(table_name):
        op.add_column(table_name, sa.Column("amo_id", sa.String(length=36), nullable=True))
    return True


def _execute_if_columns(required: Mapping[str, Iterable[str]], sql: str) -> None:
    if all(_has_columns(table_name, columns) for table_name, columns in required.items()):
        op.get_bind().execute(sa.text(sql))


def _ensure_backfill_issue_table() -> None:
    if _has_table("quality_tenant_backfill_issues"):
        return
    op.create_table(
        "quality_tenant_backfill_issues",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("table_name", sa.String(length=64), nullable=False),
        sa.Column("row_id", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def _ensure_amo_integrity(table_name: str) -> None:
    if not _has_columns(table_name, ("amo_id",)):
        return
    if _has_table("amos") and not _foreign_key_exists(table_name, ("amo_id",), "amos"):
        constraint_name = f"fk_{table_name}_amo_id_amos"
        if constraint_name not in _constraint_names(table_name):
            op.create_foreign_key(
                constraint_name,
                table_name,
                "amos",
                ["amo_id"],
                ["id"],
                ondelete="CASCADE",
            )
    index_name = f"ix_{table_name}_amo_id"
    if index_name not in _index_names(table_name):
        op.create_index(index_name, table_name, ["amo_id"])


def _replace_unique_if_supported(
    table_name: str,
    old_name: str,
    new_name: str,
    columns: tuple[str, ...],
) -> None:
    if not _has_columns(table_name, columns):
        return
    names = _constraint_names(table_name)
    if old_name in names:
        op.drop_constraint(old_name, table_name, type_="unique")
    if not _unique_exists(table_name, columns):
        op.create_unique_constraint(new_name, table_name, list(columns))


def upgrade() -> None:
    active_tables = [table_name for table_name in TABLES if _add_amo_column_if_missing(table_name)]

    _execute_if_columns(
        {"qms_documents": ("amo_id", "created_by_user_id"), "users": ("id", "amo_id")},
        "UPDATE qms_documents d SET amo_id = u.amo_id FROM users u "
        "WHERE d.amo_id IS NULL AND d.created_by_user_id = u.id",
    )
    _execute_if_columns(
        {"qms_documents": ("amo_id", "owner_user_id"), "users": ("id", "amo_id")},
        "UPDATE qms_documents d SET amo_id = u.amo_id FROM users u "
        "WHERE d.amo_id IS NULL AND d.owner_user_id = u.id",
    )
    _execute_if_columns(
        {"qms_document_revisions": ("amo_id", "document_id"), "qms_documents": ("id", "amo_id")},
        "UPDATE qms_document_revisions r SET amo_id = d.amo_id FROM qms_documents d "
        "WHERE r.amo_id IS NULL AND r.document_id = d.id",
    )
    _execute_if_columns(
        {"qms_document_distributions": ("amo_id", "document_id"), "qms_documents": ("id", "amo_id")},
        "UPDATE qms_document_distributions x SET amo_id = d.amo_id FROM qms_documents d "
        "WHERE x.amo_id IS NULL AND x.document_id = d.id",
    )
    _execute_if_columns(
        {"qms_audits": ("amo_id", "created_by_user_id"), "users": ("id", "amo_id")},
        "UPDATE qms_audits a SET amo_id = u.amo_id FROM users u "
        "WHERE a.amo_id IS NULL AND a.created_by_user_id = u.id",
    )
    _execute_if_columns(
        {"qms_audit_findings": ("amo_id", "audit_id"), "qms_audits": ("id", "amo_id")},
        "UPDATE qms_audit_findings f SET amo_id = a.amo_id FROM qms_audits a "
        "WHERE f.amo_id IS NULL AND f.audit_id = a.id",
    )
    _execute_if_columns(
        {"quality_cars": ("amo_id", "requested_by_user_id"), "users": ("id", "amo_id")},
        "UPDATE quality_cars c SET amo_id = u.amo_id FROM users u "
        "WHERE c.amo_id IS NULL AND c.requested_by_user_id = u.id",
    )
    _execute_if_columns(
        {"quality_cars": ("amo_id", "finding_id"), "qms_audit_findings": ("id", "amo_id")},
        "UPDATE quality_cars c SET amo_id = f.amo_id FROM qms_audit_findings f "
        "WHERE c.amo_id IS NULL AND c.finding_id = f.id",
    )
    _execute_if_columns(
        {"qms_notifications": ("amo_id", "user_id"), "users": ("id", "amo_id")},
        "UPDATE qms_notifications n SET amo_id = u.amo_id FROM users u "
        "WHERE n.amo_id IS NULL AND n.user_id = u.id",
    )

    _ensure_backfill_issue_table()
    bind = op.get_bind()
    for table_name in active_tables:
        if not _has_columns(table_name, ("id", "amo_id")):
            continue
        bind.execute(
            sa.text(
                f"""
                INSERT INTO quality_tenant_backfill_issues (table_name, row_id, reason)
                SELECT :table_name, CAST(id AS TEXT), 'amo_id unresolved during P0 normalization'
                FROM {table_name}
                WHERE amo_id IS NULL
                """
            ),
            {"table_name": table_name},
        )
        _ensure_amo_integrity(table_name)

    _replace_unique_if_supported(
        "qms_documents",
        "uq_qms_doc_code",
        "uq_qms_doc_code_per_amo",
        ("amo_id", "domain", "doc_type", "doc_code"),
    )
    _replace_unique_if_supported(
        "qms_audits",
        "uq_qms_audit_ref",
        "uq_qms_audit_ref_per_amo",
        ("amo_id", "domain", "audit_ref"),
    )

    unresolved = 0
    if _has_table("quality_tenant_backfill_issues"):
        unresolved = int(bind.execute(sa.text("SELECT COUNT(*) FROM quality_tenant_backfill_issues")).scalar() or 0)
    if unresolved == 0:
        for table_name in active_tables:
            if _has_columns(table_name, ("amo_id",)):
                op.alter_column(table_name, "amo_id", existing_type=sa.String(length=36), nullable=False)


def downgrade() -> None:
    for table_name, new_name, old_name, old_columns in (
        ("qms_documents", "uq_qms_doc_code_per_amo", "uq_qms_doc_code", ("domain", "doc_type", "doc_code")),
        ("qms_audits", "uq_qms_audit_ref_per_amo", "uq_qms_audit_ref", ("domain", "audit_ref")),
    ):
        names = _constraint_names(table_name)
        if new_name in names:
            op.drop_constraint(new_name, table_name, type_="unique")
        if _has_columns(table_name, old_columns) and not _unique_exists(table_name, old_columns):
            op.create_unique_constraint(old_name, table_name, list(old_columns))

    for table_name in TABLES:
        index_name = f"ix_{table_name}_amo_id"
        if index_name in _index_names(table_name):
            op.drop_index(index_name, table_name=table_name)
        constraint_name = f"fk_{table_name}_amo_id_amos"
        if constraint_name in _constraint_names(table_name):
            op.drop_constraint(constraint_name, table_name, type_="foreignkey")

    if _has_table("quality_tenant_backfill_issues"):
        op.drop_table("quality_tenant_backfill_issues")
