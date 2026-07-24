from __future__ import annotations

from hashlib import sha1
from importlib import import_module

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "workforce_20260721_precreate"
down_revision = ("qual_20260705_merge_heads", "phase2_14a_20260615")
branch_labels = None
depends_on = None

NEW_TABLES = (
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
)

# This historical precreate revision deliberately reads current ORM metadata so it
# can repair incomplete legacy installations. Newer migrations can therefore add
# relationships to these tables that did not exist when this revision shipped.
# Such foreign keys must be created by their owning later migration, not treated
# as a failure while replaying this older revision on a clean database.
FUTURE_MANAGED_FOREIGN_KEYS = {
    ("roster_rules", ("rule_set_id",), "roster_rule_sets", ("id",)),
}


def _load_metadata() -> sa.MetaData:
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


def _application_metadata() -> sa.MetaData:
    return _load_metadata()


def _bounded_identifier(value: str, *, max_length: int = 63) -> str:
    if len(value) <= max_length:
        return value
    digest = sha1(value.encode("utf-8")).hexdigest()[:8]
    return f"{value[: max_length - len(digest) - 1]}_{digest}"


def _bounded_constraint_name(value: str) -> str:
    return _bounded_identifier(value)


def _available_index_name(bind, desired_name: str, table_name: str) -> str | None:
    inspector = inspect(bind)
    existing = {
        str(row["name"])
        for existing_table in inspector.get_table_names()
        for row in inspector.get_indexes(existing_table)
        if row.get("name")
    }
    if desired_name not in existing:
        return desired_name
    if desired_name in {
        str(row["name"])
        for row in inspector.get_indexes(table_name)
        if row.get("name")
    }:
        return None
    return _bounded_identifier(f"{desired_name}__{table_name}")


def _create_tables_without_indexes(bind, metadata: sa.MetaData) -> None:
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    for table_name in NEW_TABLES:
        table = metadata.tables[table_name]
        if table_name in existing_tables:
            continue

        # PostgreSQL uses the same schema-level relation namespace for indexes and
        # UNIQUE-constraint backing indexes. Temporarily omit UNIQUE constraints
        # from CREATE TABLE so a legacy collision can be resolved with the same
        # bounded, table-specific naming policy used for normal indexes below.
        unique_constraints = [
            constraint
            for constraint in list(table.constraints)
            if isinstance(constraint, sa.UniqueConstraint)
        ]
        for constraint in unique_constraints:
            table.constraints.remove(constraint)
        try:
            bind.execute(sa.schema.CreateTable(table, include_foreign_key_constraints=[]))
        finally:
            for constraint in unique_constraints:
                table.append_constraint(constraint)
        existing_tables.add(table_name)


def _fk_signature(
    local_columns: list[str],
    remote_table: str,
    remote_columns: list[str],
) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
    return (tuple(local_columns), remote_table, tuple(remote_columns))


def _existing_fk_signatures(
    bind,
    table_name: str,
) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    return {
        _fk_signature(
            [str(column) for column in (foreign_key.get("constrained_columns") or ())],
            str(foreign_key.get("referred_table") or ""),
            [str(column) for column in (foreign_key.get("referred_columns") or ())],
        )
        for foreign_key in inspect(bind).get_foreign_keys(table_name)
    }


def _existing_fk_names(bind, table_name: str) -> set[str]:
    return {
        str(foreign_key["name"])
        for foreign_key in inspect(bind).get_foreign_keys(table_name)
        if foreign_key.get("name")
    }


def _constraint_name(
    constraint: sa.ForeignKeyConstraint,
    table_name: str,
    local_columns: list[str],
    remote_table: str,
) -> str:
    explicit = str(constraint.name or "").strip()
    if explicit:
        return _bounded_constraint_name(explicit)
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
                future_signature = (
                    table_name,
                    tuple(local_columns),
                    remote_table,
                    tuple(remote_columns),
                )
                if future_signature in FUTURE_MANAGED_FOREIGN_KEYS:
                    continue
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


def _create_unique_constraints_safely(bind, metadata: sa.MetaData) -> None:
    for table_name in NEW_TABLES:
        table = metadata.tables[table_name]
        constraints = sorted(
            (
                constraint
                for constraint in table.constraints
                if isinstance(constraint, sa.UniqueConstraint)
            ),
            key=lambda item: str(item.name or ""),
        )
        for constraint in constraints:
            columns = [str(column.name) for column in constraint.columns]
            if not columns:
                raise RuntimeError(f"Unique constraint without columns on {table_name}")
            desired_name = str(constraint.name or "").strip() or _bounded_identifier(
                f"uq_{table_name}_{'_'.join(columns)}"
            )
            actual_name = _available_index_name(bind, desired_name, table_name)
            if actual_name is None:
                continue
            op.create_index(actual_name, table_name, columns, unique=True)


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
    _create_unique_constraints_safely(bind, metadata)
    _create_indexes_safely(bind, metadata)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(NEW_TABLES):
        if inspect(bind).has_table(table_name):
            op.drop_table(table_name)
