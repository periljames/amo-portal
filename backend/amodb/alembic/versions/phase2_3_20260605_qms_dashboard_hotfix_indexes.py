"""phase2.3 qms dashboard hotfix indexes

Revision ID: phase2_3_20260605
Revises: phase2_2_20260605
Create Date: 2026-06-05
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "phase2_3_20260605"
down_revision = "phase2_2_20260605"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    if _is_postgresql():
        return bool(bind.execute(sa.text("SELECT to_regclass(:name)"), {"name": f"public.{table_name}"}).scalar())
    return table_name in sa.inspect(bind).get_table_names()


def _index_exists(index_name: str) -> bool:
    bind = op.get_bind()
    if _is_postgresql():
        return bool(
            bind.execute(
                sa.text(
                    """
                    SELECT 1
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                      AND indexname = :index_name
                    """
                ),
                {"index_name": index_name},
            ).first()
        )
    for table in sa.inspect(bind).get_table_names():
        if any(idx.get("name") == index_name for idx in sa.inspect(bind).get_indexes(table)):
            return True
    return False


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str], where: str | None = None) -> None:
    if not _table_exists(table_name) or _index_exists(index_name):
        return
    kwargs = {}
    if where and _is_postgresql():
        kwargs["postgresql_where"] = sa.text(where)
    op.create_index(index_name, table_name, columns, **kwargs)


def upgrade() -> None:
    _create_index_if_missing(
        "ix_qms_audits_dashboard_open_partial",
        "qms_audits",
        ["amo_id"],
        "status <> 'CLOSED'",
    )
    _create_index_if_missing(
        "ix_qms_audits_dashboard_in_progress_partial",
        "qms_audits",
        ["amo_id"],
        "status = 'IN_PROGRESS'",
    )
    _create_index_if_missing(
        "ix_qms_audits_dashboard_due_partial",
        "qms_audits",
        ["amo_id", "planned_start"],
        "planned_start IS NOT NULL AND status <> 'CLOSED'",
    )
    _create_index_if_missing(
        "ix_quality_cars_dashboard_open_partial",
        "quality_cars",
        ["amo_id"],
        "status NOT IN ('CLOSED', 'CANCELLED')",
    )
    _create_index_if_missing(
        "ix_quality_cars_dashboard_due_partial",
        "quality_cars",
        ["amo_id", "due_date"],
        "due_date IS NOT NULL AND status NOT IN ('CLOSED', 'CANCELLED')",
    )
    _create_index_if_missing(
        "ix_qms_findings_dashboard_open_partial",
        "qms_audit_findings",
        ["amo_id"],
        "closed_at IS NULL",
    )
    _create_index_if_missing(
        "ix_training_records_dashboard_expired_partial",
        "training_records",
        ["amo_id", "valid_until"],
        "valid_until IS NOT NULL",
    )
    if _is_postgresql():
        # Refresh planner statistics after adding dashboard-specific indexes.
        for table_name in ("qms_audits", "quality_cars", "qms_audit_findings", "training_records"):
            if _table_exists(table_name):
                op.execute(sa.text(f"ANALYZE {table_name}"))


def downgrade() -> None:
    for index_name, table_name in [
        ("ix_training_records_dashboard_expired_partial", "training_records"),
        ("ix_qms_findings_dashboard_open_partial", "qms_audit_findings"),
        ("ix_quality_cars_dashboard_due_partial", "quality_cars"),
        ("ix_quality_cars_dashboard_open_partial", "quality_cars"),
        ("ix_qms_audits_dashboard_due_partial", "qms_audits"),
        ("ix_qms_audits_dashboard_in_progress_partial", "qms_audits"),
        ("ix_qms_audits_dashboard_open_partial", "qms_audits"),
    ]:
        if _table_exists(table_name) and _index_exists(index_name):
            op.drop_index(index_name, table_name=table_name)
