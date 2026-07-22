"""Finalize deferred indexes and Quality tenant normalization after branch convergence.

Revision ID: saas_20260722_finalize_idx
Revises: saas_20260722_control_plane
Create Date: 2026-07-22

Historical migrations on parallel branches intentionally skip tables that do
not exist yet. This finalizer runs after the SaaS/Quality chain has converged,
re-applies deferred indexes, and recalculates Quality ``amo_id`` backfills from
the final schema rather than preserving stale early-migration issue rows.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from alembic import op
import sqlalchemy as sa


revision = "saas_20260722_finalize_idx"
down_revision = "saas_20260722_control_plane"
branch_labels = None
depends_on = None


INDEXES: tuple[tuple[str, str, tuple[object, ...], tuple[str, ...]], ...] = (
    (
        "ix_work_orders_amo_aircraft_created",
        "work_orders",
        ("amo_id", "aircraft_serial_number", sa.text("created_at DESC")),
        ("amo_id", "aircraft_serial_number", "created_at"),
    ),
    (
        "ix_task_cards_amo_workorder_status",
        "task_cards",
        ("amo_id", "work_order_id", "status"),
        ("amo_id", "work_order_id", "status"),
    ),
    (
        "ix_audit_events_amo_time_desc",
        "audit_events",
        ("amo_id", sa.text("occurred_at DESC")),
        ("amo_id", "occurred_at"),
    ),
    (
        "ix_config_events_amo_aircraft_date_desc",
        "aircraft_configuration_events",
        ("amo_id", "aircraft_serial_number", sa.text("occurred_at DESC")),
        ("amo_id", "aircraft_serial_number", "occurred_at"),
    ),
    (
        "ix_part_movement_amo_aircraft_date",
        "part_movement_ledger",
        ("amo_id", "aircraft_serial_number", sa.text("event_date DESC")),
        ("amo_id", "aircraft_serial_number", "event_date"),
    ),
)

QUALITY_TABLES = (
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


def _index_names(table_name: str) -> set[str]:
    inspector = _inspector()
    if not inspector.has_table(table_name):
        return set()
    return {
        str(index.get("name"))
        for index in inspector.get_indexes(table_name)
        if index.get("name")
    }


def _constraint_names(table_name: str) -> set[str]:
    inspector = _inspector()
    if not inspector.has_table(table_name):
        return set()
    names = {
        str(item.get("name"))
        for item in inspector.get_unique_constraints(table_name)
        if item.get("name")
    }
    names.update(
        str(item.get("name"))
        for item in inspector.get_foreign_keys(table_name)
        if item.get("name")
    )
    return names


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


def _execute_if_columns(required: Mapping[str, Iterable[str]], sql: str) -> None:
    if all(_has_columns(table_name, columns) for table_name, columns in required.items()):
        op.get_bind().execute(sa.text(sql))


def _ensure_issue_table() -> None:
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


def _ensure_amo_column(table_name: str) -> None:
    if not _has_table(table_name):
        return
    if "amo_id" not in _columns(table_name):
        op.add_column(table_name, sa.Column("amo_id", sa.String(length=36), nullable=True))


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


def _set_user_triggers(table_name: str, enabled: bool) -> None:
    if not _has_table(table_name):
        return
    state = "ENABLE" if enabled else "DISABLE"
    op.execute(sa.text(f'ALTER TABLE "{table_name}" {state} TRIGGER USER'))


def _backfill_quality_tenants() -> None:
    for table_name in QUALITY_TABLES:
        _ensure_amo_column(table_name)

    protected_tables = [table_name for table_name in QUALITY_TABLES if _has_table(table_name)]
    try:
        for table_name in protected_tables:
            _set_user_triggers(table_name, False)

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
    finally:
        for table_name in protected_tables:
            _set_user_triggers(table_name, True)

    _ensure_issue_table()
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM quality_tenant_backfill_issues WHERE table_name = ANY(:table_names)"),
        {"table_names": list(QUALITY_TABLES)},
    )

    for table_name in QUALITY_TABLES:
        if not _has_columns(table_name, ("id", "amo_id")):
            continue
        bind.execute(
            sa.text(
                f"""
                INSERT INTO quality_tenant_backfill_issues (table_name, row_id, reason)
                SELECT :table_name, CAST(id AS TEXT), 'amo_id unresolved after branch convergence'
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

    unresolved = int(
        bind.execute(
            sa.text("SELECT COUNT(*) FROM quality_tenant_backfill_issues WHERE table_name = ANY(:table_names)"),
            {"table_names": list(QUALITY_TABLES)},
        ).scalar()
        or 0
    )
    if unresolved == 0:
        for table_name in QUALITY_TABLES:
            if not _has_columns(table_name, ("amo_id",)):
                continue
            column = next(item for item in _inspector().get_columns(table_name) if item["name"] == "amo_id")
            if bool(column.get("nullable", True)):
                op.alter_column(table_name, "amo_id", existing_type=column["type"], nullable=False)


def upgrade() -> None:
    inspector = _inspector()
    for name, table_name, expressions, required_columns in INDEXES:
        if not _has_columns(table_name, required_columns):
            continue
        if name in _index_names(table_name):
            continue
        op.create_index(name, table_name, list(expressions))
        inspector = _inspector()

    _backfill_quality_tenants()


def downgrade() -> None:
    for name, table_name, _expressions, _required_columns in reversed(INDEXES):
        if name in _index_names(table_name):
            op.drop_index(name, table_name=table_name)
