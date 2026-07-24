"""Converge audit-scope foreign keys after parallel Quality branches.

Revision ID: document_control_20260724_scope_fk
Revises: document_control_20260724_domain
Depends on: qual_20260704_scopes, qual_20260628_scope_fix
Create Date: 2026-07-24

The released Quality graph contains parallel branches that may create the audit
scope columns before the canonical UUID scope table is repaired. The earlier
migration now skips incompatible intermediate FK DDL; this convergence revision
runs only after both branches and restores the intended constraints.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "document_control_20260724_scope_fk"
down_revision = "document_control_20260724_domain"
branch_labels = None
depends_on = ("qual_20260704_scopes", "qual_20260628_scope_fix")


def _table_exists(bind, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _column_type(bind, table_name: str, column_name: str) -> str | None:
    if not _table_exists(bind, table_name):
        return None
    for column in sa.inspect(bind).get_columns(table_name):
        if column.get("name") == column_name:
            return column.get("type").__class__.__name__.lower()
    return None


def _constraint_exists(bind, table_name: str, constraint_name: str) -> bool:
    if not _table_exists(bind, table_name):
        return False
    return constraint_name in {
        str(foreign_key.get("name") or "")
        for foreign_key in sa.inspect(bind).get_foreign_keys(table_name)
    }


def _add_scope_fk(bind, table_name: str, constraint_name: str) -> None:
    if not _table_exists(bind, table_name) or not _table_exists(bind, "qms_audit_scopes"):
        return
    child_type = _column_type(bind, table_name, "audit_scope_id")
    parent_type = _column_type(bind, "qms_audit_scopes", "id")
    if child_type != "uuid" or parent_type != "uuid":
        raise RuntimeError(
            f"Cannot converge {constraint_name}: {table_name}.audit_scope_id={child_type!r}, "
            f"qms_audit_scopes.id={parent_type!r}. Run the Quality scope repair migrations first."
        )
    if _constraint_exists(bind, table_name, constraint_name):
        return

    orphan_count = int(
        bind.execute(
            text(
                f"""
                SELECT count(*)
                FROM {table_name} child
                LEFT JOIN qms_audit_scopes scope ON scope.id = child.audit_scope_id
                WHERE child.audit_scope_id IS NOT NULL
                  AND scope.id IS NULL
                """
            )
        ).scalar()
        or 0
    )
    if orphan_count:
        raise RuntimeError(
            f"Cannot create {constraint_name}: {orphan_count} orphaned audit_scope_id value(s) "
            f"exist in {table_name}. Repair the data before rerunning Alembic."
        )

    op.create_foreign_key(
        constraint_name,
        table_name,
        "qms_audit_scopes",
        ["audit_scope_id"],
        ["id"],
        ondelete="SET NULL",
    )


def upgrade() -> None:
    bind = op.get_bind()
    _add_scope_fk(bind, "qms_audits", "fk_qms_audits_audit_scope")
    _add_scope_fk(bind, "qms_audit_schedules", "fk_qms_audit_schedules_audit_scope")


def downgrade() -> None:
    # Non-destructive by design. These are canonical Quality integrity constraints
    # and may have existed before this convergence revision on upgraded databases.
    pass
