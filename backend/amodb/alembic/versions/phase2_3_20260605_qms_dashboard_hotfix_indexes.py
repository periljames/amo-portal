"""Phase 2.3 QMS dashboard hotfix indexes.

Revision ID: phase2_3_20260605
Revises: phase2_2_20260605
Create Date: 2026-06-05

Partial-index predicates reference columns as well as index keys. Every key and
predicate column is therefore required before an index is created.
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


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def _index_exists(index_name: str) -> bool:
    bind = op.get_bind()
    if _is_postgresql():
        return bool(
            bind.execute(
                sa.text(
                    """
                    SELECT 1
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND indexname = :index_name
                    """
                ),
                {"index_name": index_name},
            ).first()
        )
    for table_name in sa.inspect(bind).get_table_names():
        if any(index.get("name") == index_name for index in sa.inspect(bind).get_indexes(table_name)):
            return True
    return False


def _create_index_if_missing(
    index_name: str,
    table_name: str,
    columns: list[str],
    predicate_columns: tuple[str, ...] = (),
    where: str | None = None,
) -> None:
    required = set(columns) | set(predicate_columns)
    if not required.issubset(_columns(table_name)) or _index_exists(index_name):
        return
    kwargs = {}
    if where and _is_postgresql():
        kwargs["postgresql_where"] = sa.text(where)
    op.create_index(index_name, table_name, columns, **kwargs)


def upgrade() -> None:
    specs = (
        ("ix_qms_audits_dashboard_open_partial", "qms_audits", ["amo_id"], ("status",), "status <> 'CLOSED'"),
        ("ix_qms_audits_dashboard_in_progress_partial", "qms_audits", ["amo_id"], ("status",), "status = 'IN_PROGRESS'"),
        ("ix_qms_audits_dashboard_due_partial", "qms_audits", ["amo_id", "planned_start"], ("status",), "planned_start IS NOT NULL AND status <> 'CLOSED'"),
        ("ix_quality_cars_dashboard_open_partial", "quality_cars", ["amo_id"], ("status",), "status NOT IN ('CLOSED', 'CANCELLED')"),
        ("ix_quality_cars_dashboard_due_partial", "quality_cars", ["amo_id", "due_date"], ("status",), "due_date IS NOT NULL AND status NOT IN ('CLOSED', 'CANCELLED')"),
        ("ix_qms_findings_dashboard_open_partial", "qms_audit_findings", ["amo_id"], ("closed_at",), "closed_at IS NULL"),
        ("ix_training_records_dashboard_expired_partial", "training_records", ["amo_id", "valid_until"], (), "valid_until IS NOT NULL"),
    )
    for index_name, table_name, columns, predicate_columns, where in specs:
        _create_index_if_missing(
            index_name,
            table_name,
            columns,
            predicate_columns,
            where,
        )

    if _is_postgresql():
        for table_name in ("qms_audits", "quality_cars", "qms_audit_findings", "training_records"):
            if _columns(table_name):
                op.execute(sa.text(f'ANALYZE "{table_name}"'))


def downgrade() -> None:
    for index_name, table_name in (
        ("ix_training_records_dashboard_expired_partial", "training_records"),
        ("ix_qms_findings_dashboard_open_partial", "qms_audit_findings"),
        ("ix_quality_cars_dashboard_due_partial", "quality_cars"),
        ("ix_quality_cars_dashboard_open_partial", "quality_cars"),
        ("ix_qms_audits_dashboard_due_partial", "qms_audits"),
        ("ix_qms_audits_dashboard_in_progress_partial", "qms_audits"),
        ("ix_qms_audits_dashboard_open_partial", "qms_audits"),
    ):
        if _index_exists(index_name):
            op.drop_index(index_name, table_name=table_name)
