"""add explicit audit scope management fields

Revision ID: qual_20260704_scopes
Revises: qual_20260627_wf_close
Create Date: 2026-07-04
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "qual_20260704_scopes"
down_revision: Union[str, Sequence[str], None] = "qual_20260627_wf_close"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _has_fk(table_name: str, constraint_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return constraint_name in {fk.get("name") for fk in inspector.get_foreign_keys(table_name)}


def _column_type_name(table_name: str, column_name: str) -> str | None:
    """Return a stable SQLAlchemy type name for guarded cross-branch FKs."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return None
    for column in inspector.get_columns(table_name):
        if column.get("name") == column_name:
            return column.get("type").__class__.__name__.lower()
    return None


def _scope_fk_compatible(child_table: str) -> bool:
    """Only create the FK when both sides are the canonical UUID shape.

    Historical clean installs can encounter an artifact-shaped
    ``qms_audit_scopes`` table with a VARCHAR primary key before the separate
    scope-reference repair branch replaces it with the canonical UUID table.
    Creating the FK in that intermediate state is invalid PostgreSQL DDL. The
    later convergence migration adds any missing FK after both branches have
    completed.
    """
    child_type = _column_type_name(child_table, "audit_scope_id")
    parent_type = _column_type_name("qms_audit_scopes", "id")
    return child_type == "uuid" and parent_type == "uuid"


def upgrade() -> None:
    if _has_table("qms_audits"):
        if not _has_column("qms_audits", "audit_scope_id"):
            op.add_column("qms_audits", sa.Column("audit_scope_id", sa.UUID(), nullable=True))
        if not _has_column("qms_audits", "audit_scope_code"):
            op.add_column("qms_audits", sa.Column("audit_scope_code", sa.String(length=16), nullable=True))
        op.create_index("ix_qms_audits_audit_scope_id", "qms_audits", ["audit_scope_id"], unique=False, if_not_exists=True)
        op.create_index("ix_qms_audits_audit_scope_code", "qms_audits", ["audit_scope_code"], unique=False, if_not_exists=True)
        # Historical clean installs reach this revision before the separate
        # reference-family migration creates the canonical UUID scope table.
        # Add the FK only when the actual database types are compatible.
        if (
            _has_table("qms_audit_scopes")
            and _scope_fk_compatible("qms_audits")
            and not _has_fk("qms_audits", "fk_qms_audits_audit_scope")
        ):
            op.create_foreign_key(
                "fk_qms_audits_audit_scope",
                "qms_audits",
                "qms_audit_scopes",
                ["audit_scope_id"],
                ["id"],
                ondelete="SET NULL",
            )

    if _has_table("qms_audit_schedules"):
        if not _has_column("qms_audit_schedules", "audit_scope_id"):
            op.add_column("qms_audit_schedules", sa.Column("audit_scope_id", sa.UUID(), nullable=True))
        if not _has_column("qms_audit_schedules", "audit_scope_code"):
            op.add_column("qms_audit_schedules", sa.Column("audit_scope_code", sa.String(length=16), nullable=True))
        op.create_index("ix_qms_audit_schedules_audit_scope_id", "qms_audit_schedules", ["audit_scope_id"], unique=False, if_not_exists=True)
        op.create_index("ix_qms_audit_schedules_audit_scope_code", "qms_audit_schedules", ["audit_scope_code"], unique=False, if_not_exists=True)
        if (
            _has_table("qms_audit_scopes")
            and _scope_fk_compatible("qms_audit_schedules")
            and not _has_fk("qms_audit_schedules", "fk_qms_audit_schedules_audit_scope")
        ):
            op.create_foreign_key(
                "fk_qms_audit_schedules_audit_scope",
                "qms_audit_schedules",
                "qms_audit_scopes",
                ["audit_scope_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    if _has_table("qms_audit_schedules"):
        if _has_fk("qms_audit_schedules", "fk_qms_audit_schedules_audit_scope"):
            op.drop_constraint("fk_qms_audit_schedules_audit_scope", "qms_audit_schedules", type_="foreignkey")
        op.drop_index("ix_qms_audit_schedules_audit_scope_code", table_name="qms_audit_schedules", if_exists=True)
        op.drop_index("ix_qms_audit_schedules_audit_scope_id", table_name="qms_audit_schedules", if_exists=True)
        if _has_column("qms_audit_schedules", "audit_scope_code"):
            op.drop_column("qms_audit_schedules", "audit_scope_code")
        if _has_column("qms_audit_schedules", "audit_scope_id"):
            op.drop_column("qms_audit_schedules", "audit_scope_id")

    if _has_table("qms_audits"):
        if _has_fk("qms_audits", "fk_qms_audits_audit_scope"):
            op.drop_constraint("fk_qms_audits_audit_scope", "qms_audits", type_="foreignkey")
        op.drop_index("ix_qms_audits_audit_scope_code", table_name="qms_audits", if_exists=True)
        op.drop_index("ix_qms_audits_audit_scope_id", table_name="qms_audits", if_exists=True)
        if _has_column("qms_audits", "audit_scope_code"):
            op.drop_column("qms_audits", "audit_scope_code")
        if _has_column("qms_audits", "audit_scope_id"):
            op.drop_column("qms_audits", "audit_scope_id")
