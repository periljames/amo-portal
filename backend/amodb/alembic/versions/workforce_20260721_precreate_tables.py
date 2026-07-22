"""Precreate workforce-integrated rostering tables safely.

Revision ID: workforce_20260721_precreate
Revises: qual_20260705_merge_heads, phase2_14a_20260615
Create Date: 2026-07-22

This predecessor isolates table creation from ORM-driven automatic index
creation. PostgreSQL relation names are schema-global, so indexes and backing
indexes of named unique constraints are created only after checking the whole
current schema. The revision explicitly converges the core rostering branch
before Workforce schema creation, then restores every deferred ORM foreign key
after all Workforce tables are available.
"""
from __future__ import annotations

from hashlib import sha1
from importlib import import_module
from typing import Any

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "workforce_20260721_precreate"
down_revision = ("qual_20260705_merge_heads", "phase2_14a_20260615")
branch_labels = None
depends_on = None

POSTGRES_IDENTIFIER_LIMIT = 63

NEW_TABLES = [
    "roster_rules",
    "roster_rule_exceptions",
    "roster_demand_requirements",
    "roster_command_receipts",
    "employment_contracts",
    "work_patterns",
    "work_pattern_days",
    "employee_work_pattern_assignments",
    "leave_types",
    "employee_leave_balances",
    "leave_requests",
    "leave_request_approvals",
    "employee_availability_events",
    "public_holiday_calendars",
    "public_holidays",
    "attendance_events",
    "timesheets",
    "timesheet_lines",
    "overtime_requests",
    "overtime_approvals",
    "roster_actual_variances",
    "workforce_permission_grants",
    "training_event_time_windows",
    "roster_planner_preferences",
    "workforce_notification_preferences",
]


def _application_metadata() -> sa.MetaData:
    """Load application metadata only during an actual migration run."""
    from amodb.database import Base

    for module_name in (
        "amodb.apps.accounts.models",
        "amodb.apps.foundations.models",
        "amodb.apps.training.models",
        "amodb.apps.work.models",
        "amodb.apps.rostering.models",
        "amodb.apps.workforce.models",
    ):
        import_module(module_name)
    return Base.metadata


def _relation_owner(bind, relation_name: str) -> dict[str, Any] | None:
    """Return the schema relation kind and owning table, when one exists."""
    if bind.dialect.name == "postgresql":
        row = bind.execute(
            text(
                """
                SELECT relation.relkind AS kind, owner.relname AS table_name
                FROM pg_class AS relation
                JOIN pg_namespace AS namespace
                  ON namespace.oid = relation.relnamespace
                LEFT JOIN pg_index AS index_record
                  ON index_record.indexrelid = relation.oid
                LEFT JOIN pg_class AS owner
                  ON owner.oid = index_record.indrelid
                WHERE namespace.nspname = current_schema()
                  AND relation.relname = :relation_name
                LIMIT 1
                """
            ),
            {"relation_name": relation_name},
        ).mappings().first()
        return dict(row) if row else None

    if bind.dialect.name == "sqlite":
        row = bind.execute(
            text(
                "SELECT type AS kind, tbl_name AS table_name "
                "FROM sqlite_master WHERE name = :relation_name LIMIT 1"
            ),
            {"relation_name": relation_name},
        ).mappings().first()
        return dict(row) if row else None

    inspector = inspect(bind)
    if relation_name in set(inspector.get_table_names()):
        return {"kind": "table", "table_name": relation_name}
    for table_name in inspector.get_table_names():
        for index in inspector.get_indexes(table_name):
            if index.get("name") == relation_name:
                return {"kind": "index", "table_name": table_name}
    return None


def _fallback_relation_name(desired_name: str, table_name: str, attempt: int) -> str:
    suffix = f"__{table_name}" if attempt == 1 else f"__{table_name}_{attempt}"
    available = max(1, POSTGRES_IDENTIFIER_LIMIT - len(suffix))
    return f"{desired_name[:available]}{suffix}"


def _available_relation_name(bind, desired_name: str, table_name: str) -> str:
    if _relation_owner(bind, desired_name) is None:
        return desired_name

    attempt = 1
    while True:
        fallback = _fallback_relation_name(desired_name, table_name, attempt)
        if _relation_owner(bind, fallback) is None:
            return fallback
        attempt += 1


def _available_index_name(bind, desired_name: str, table_name: str) -> str | None:
    owner = _relation_owner(bind, desired_name)
    if owner is None:
        return desired_name
    if owner.get("table_name") == table_name and owner.get("kind") in {"i", "I", "index"}:
        return None

    attempt = 1
    while True:
        fallback = _fallback_relation_name(desired_name, table_name, attempt)
        owner = _relation_owner(bind, fallback)
        if owner is None:
            return fallback
        if owner.get("table_name") == table_name and owner.get("kind") in {"i", "I", "index"}:
            return None
        attempt += 1


def _available_foreign_keys(bind, table: sa.Table) -> list[sa.ForeignKeyConstraint]:
    """Return FKs whose remote table can be resolved at table-create time."""
    inspector = inspect(bind)
    available_tables = set(inspector.get_table_names())
    included: list[sa.ForeignKeyConstraint] = []
    for constraint in table.foreign_key_constraints:
        remote_table = constraint.referred_table.name
        if remote_table == table.name or remote_table in available_tables:
            included.append(constraint)
    return included


def _create_table_with_safe_unique_names(bind, table: sa.Table) -> None:
    renamed: list[tuple[sa.UniqueConstraint, str]] = []
    for constraint in table.constraints:
        if not isinstance(constraint, sa.UniqueConstraint) or not constraint.name:
            continue
        desired_name = str(constraint.name)
        actual_name = _available_relation_name(bind, desired_name, table.name)
        if actual_name != desired_name:
            renamed.append((constraint, desired_name))
            constraint.name = actual_name

    try:
        bind.execute(
            sa.schema.CreateTable(
                table,
                include_foreign_key_constraints=_available_foreign_keys(bind, table),
            )
        )
    finally:
        for constraint, original_name in renamed:
            constraint.name = original_name


def _create_tables_without_indexes(bind, metadata: sa.MetaData) -> None:
    inspector = inspect(bind)
    for table_name in NEW_TABLES:
        table = metadata.tables.get(table_name)
        if table is None:
            raise RuntimeError(f"Migration metadata table missing: {table_name}")
        if not inspector.has_table(table_name):
            _create_table_with_safe_unique_names(bind, table)
            inspector = inspect(bind)


def _fk_signature(
    local_columns: list[str] | tuple[str, ...],
    remote_table: str,
    remote_columns: list[str] | tuple[str, ...],
) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
    return tuple(local_columns), remote_table, tuple(remote_columns)


def _existing_fk_signatures(bind, table_name: str) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    inspector = inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {
        _fk_signature(
            tuple(str(column) for column in (foreign_key.get("constrained_columns") or ())),
            str(foreign_key.get("referred_table") or ""),
            tuple(str(column) for column in (foreign_key.get("referred_columns") or ())),
        )
        for foreign_key in inspector.get_foreign_keys(table_name)
    }


def _existing_fk_names(bind, table_name: str) -> set[str]:
    inspector = inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {
        str(foreign_key["name"])
        for foreign_key in inspector.get_foreign_keys(table_name)
        if foreign_key.get("name")
    }


def _bounded_constraint_name(raw_name: str) -> str:
    if len(raw_name) <= POSTGRES_IDENTIFIER_LIMIT:
        return raw_name
    digest = sha1(raw_name.encode("utf-8")).hexdigest()[:8]
    return f"{raw_name[:POSTGRES_IDENTIFIER_LIMIT - 9]}_{digest}"


def _constraint_name(
    constraint: sa.ForeignKeyConstraint,
    table_name: str,
    local_columns: list[str],
    remote_table: str,
) -> str:
    if constraint.name:
        return _bounded_constraint_name(str(constraint.name))
    return _bounded_constraint_name(
        f"fk_{table_name}_{'_'.join(local_columns)}_{remote_table}"
    )


def _restore_deferred_foreign_keys(bind, metadata: sa.MetaData) -> None:
    if bind.dialect.name == "sqlite":
        return

    inspector = inspect(bind)
    available_tables = set(inspector.get_table_names())
    unresolved: list[str] = []

    for table_name in NEW_TABLES:
        table = metadata.tables[table_name]
        if table_name not in available_tables:
            unresolved.append(f"missing local table {table_name}")
            continue

        existing_signatures = _existing_fk_signatures(bind, table_name)
        existing_names = _existing_fk_names(bind, table_name)

        for constraint in sorted(
            table.foreign_key_constraints,
            key=lambda item: str(item.name or ""),
        ):
            elements = list(constraint.elements)
            local_columns = [str(element.parent.name) for element in elements]
            remote_table = constraint.referred_table.name
            remote_columns = [str(element.column.name) for element in elements]
            signature = _fk_signature(local_columns, remote_table, remote_columns)

            if signature in existing_signatures:
                continue
            if remote_table not in available_tables:
                unresolved.append(
                    f"{table_name}({','.join(local_columns)}) -> "
                    f"{remote_table}({','.join(remote_columns)})"
                )
                continue

            desired_name = _constraint_name(
                constraint,
                table_name,
                local_columns,
                remote_table,
            )
            actual_name = desired_name
            if actual_name in existing_names:
                digest = sha1(
                    f"{table_name}:{local_columns}:{remote_table}:{remote_columns}".encode("utf-8")
                ).hexdigest()[:8]
                actual_name = _bounded_constraint_name(f"{desired_name}_{digest}")

            first_element = elements[0]
            op.create_foreign_key(
                actual_name,
                table_name,
                remote_table,
                local_columns,
                remote_columns,
                ondelete=first_element.ondelete,
                onupdate=first_element.onupdate,
                deferrable=constraint.deferrable,
                initially=constraint.initially,
            )
            existing_signatures.add(signature)
            existing_names.add(actual_name)

    if unresolved:
        raise RuntimeError(
            "Deferred Workforce foreign keys could not be restored: "
            + "; ".join(sorted(unresolved))
        )


def _create_indexes_safely(bind, metadata: sa.MetaData) -> None:
    for table_name in NEW_TABLES:
        table = metadata.tables[table_name]
        for index in sorted(table.indexes, key=lambda item: str(item.name or "")):
            desired_name = str(index.name or "").strip()
            if not desired_name:
                raise RuntimeError(f"Unnamed index on migration table: {table_name}")
            columns = [str(column.name) for column in index.columns]
            if not columns:
                raise RuntimeError(f"Unsupported expression-only index: {desired_name}")
            actual_name = _available_index_name(bind, desired_name, table_name)
            if actual_name is None:
                continue
            op.create_index(actual_name, table_name, columns, unique=bool(index.unique))


def upgrade() -> None:
    bind = op.get_bind()
    metadata = _application_metadata()
    _create_tables_without_indexes(bind, metadata)
    _restore_deferred_foreign_keys(bind, metadata)
    _create_indexes_safely(bind, metadata)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(NEW_TABLES):
        if inspect(bind).has_table(table_name):
            op.drop_table(table_name)
