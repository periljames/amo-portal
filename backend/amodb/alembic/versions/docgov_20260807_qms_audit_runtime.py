"""Repair QMS audit runtime fields after QMS/Document Control convergence.

Revision ID: docgov_20260807_qms_audit_runtime
Revises: docgov_merge_20260807_qms
Create Date: 2026-08-07

The QMS planner ORM reads notification/auditee fields from ``qms_audits``.
The historical schedule migration created equivalent fields only on
``qms_audit_schedules``, leaving a clean Alembic upgrade incompatible with the
current QMSAudit model. This compatibility migration closes that gap without
rewriting existing audit data.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "docgov_20260807_qms_audit_runtime"
down_revision = "docgov_merge_20260807_qms"
branch_labels = None
depends_on = None


def _columns(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    columns = _columns(bind, "qms_audits")
    if not columns:
        return

    if "external_auditees_json" not in columns:
        op.add_column("qms_audits", sa.Column("external_auditees_json", sa.Text(), nullable=True))
    if "notify_auditors" not in columns:
        op.add_column(
            "qms_audits",
            sa.Column("notify_auditors", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    if "notify_auditees" not in columns:
        op.add_column(
            "qms_audits",
            sa.Column("notify_auditees", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    if "reminder_interval_days" not in columns:
        op.add_column(
            "qms_audits",
            sa.Column("reminder_interval_days", sa.Integer(), nullable=False, server_default=sa.text("7")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = _columns(bind, "qms_audits")
    for name in (
        "reminder_interval_days",
        "notify_auditees",
        "notify_auditors",
        "external_auditees_json",
    ):
        if name in columns:
            op.drop_column("qms_audits", name)
            columns.remove(name)
