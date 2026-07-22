"""complete workforce-integrated duty rostering

Revision ID: workforce_20260721_complete
Revises: workforce_20260721_precreate
Create Date: 2026-07-21

The revision graph is import-safe: importing this module never loads the
application package and never requires DATABASE_URL. Application metadata is
loaded only while an actual upgrade is executing against a configured database.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from importlib import import_module
from typing import Any, Iterable
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "workforce_20260721_complete"
down_revision = "workforce_20260721_precreate"
branch_labels = None
depends_on = None

UTC = timezone.utc

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

ROSTER_COLUMNS: dict[str, list[sa.Column[Any]]] = {
    "shift_templates": [
        sa.Column("color_token", sa.String(length=64), nullable=True),
        sa.Column("icon_name", sa.String(length=64), nullable=True),
    ],
    "roster_periods": [
        sa.Column("timezone_name", sa.String(length=64), nullable=True),
    ],
    "roster_versions": [
        sa.Column("source_version_id", sa.String(length=36), nullable=True),
        sa.Column("amendment_type", sa.String(length=32), nullable=True),
        sa.Column("amendment_reason", sa.Text(), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("state_revision", sa.Integer(), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validation_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("publication_correlation_key", sa.String(length=128), nullable=True),
    ],
    "roster_assignments": [
        sa.Column("department_id", sa.String(length=36), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("source_reference_id", sa.String(length=128), nullable=True),
        sa.Column("team_code", sa.String(length=64), nullable=True),
        sa.Column("location_label", sa.String(length=128), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("state_revision", sa.Integer(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_user_id", sa.String(length=36), nullable=True),
    ],
    "roster_validation_findings": [
        sa.Column("rule_id", sa.String(length=36), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("overridable", sa.Boolean(), nullable=True),
        sa.Column("overridden_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("overridden_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
    ],
    "roster_publication_acknowledgements": [
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("delivery_status", sa.String(length=32), nullable=True),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=True),
    ],
}

FOREIGN_KEYS = [
    ("roster_versions", "fk_roster_versions_source_version", ["source_version_id"], "roster_versions", ["id"], "SET NULL"),
    ("roster_assignments", "fk_roster_assignments_department", ["department_id"], "departments", ["id"], "SET NULL"),
    ("roster_assignments", "fk_roster_assignments_deleted_by", ["deleted_by_user_id"], "users", ["id"], "SET NULL"),
    ("roster_validation_findings", "fk_roster_validation_rule", ["rule_id"], "roster_rules", ["id"], "SET NULL"),
    ("roster_validation_findings", "fk_roster_validation_overridden_by", ["overridden_by_user_id"], "users", ["id"], "SET NULL"),
]

INDEXES = [
    ("shift_templates", "ix_shift_templates_color_token", ["color_token"], False),
    ("roster_versions", "ix_roster_versions_source_version_id", ["source_version_id"], False),
    ("roster_versions", "ix_roster_versions_amendment_type", ["amendment_type"], False),
    ("roster_versions", "ix_roster_versions_idempotency_key", ["idempotency_key"], False),
    ("roster_versions", "ix_roster_versions_publication_correlation", ["publication_correlation_key"], False),
    ("roster_versions", "uq_roster_version_idempotency", ["amo_id", "idempotency_key"], True),
    ("roster_assignments", "ix_roster_assignments_department_time", ["department_id", "starts_at", "ends_at"], False),
    ("roster_assignments", "ix_roster_assignments_source_reference", ["version_id", "source", "source_reference_id"], False),
    ("roster_assignments", "ix_roster_assignments_deleted_at", ["deleted_at"], False),
    ("roster_assignments", "uq_roster_assignment_source_reference", ["version_id", "source", "source_reference_id"], True),
    ("roster_validation_findings", "ix_roster_validation_rule", ["rule_id", "resolved"], False),
    ("roster_publication_acknowledgements", "ix_roster_ack_idempotency_key", ["idempotency_key"], False),
    ("roster_publication_acknowledgements", "uq_roster_ack_idempotency", ["amo_id", "idempotency_key"], True),
]


def _application_metadata() -> sa.MetaData:
    """Load schema metadata only during a real migration execution."""
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


def _column_names(bind, table_name: str) -> set[str]:
    inspector = inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def _index_names(bind, table_name: str) -> set[str]:
    inspector = inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {str(index["name"]) for index in inspector.get_indexes(table_name) if index.get("name")}


def _fk_names(bind, table_name: str) -> set[str]:
    inspector = inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {str(fk["name"]) for fk in inspector.get_foreign_keys(table_name) if fk.get("name")}


def _add_columns(bind) -> None:
    for table_name, columns in ROSTER_COLUMNS.items():
        existing = _column_names(bind, table_name)
        for column in columns:
            if column.name not in existing:
                op.add_column(table_name, column)


def _create_metadata_tables(bind) -> None:
    metadata = _application_metadata()
    for table_name in NEW_TABLES:
        table = metadata.tables.get(table_name)
        if table is None:
            raise RuntimeError(f"Migration metadata table missing: {table_name}")
        table.create(bind=bind, checkfirst=True)


def _create_foreign_keys(bind) -> None:
    if bind.dialect.name == "sqlite":
        return
    for table_name, constraint_name, local_columns, remote_table, remote_columns, ondelete in FOREIGN_KEYS:
        if constraint_name in _fk_names(bind, table_name):
            continue
        op.create_foreign_key(
            constraint_name,
            table_name,
            remote_table,
            local_columns,
            remote_columns,
            ondelete=ondelete,
        )


def _create_indexes(bind) -> None:
    for table_name, name, columns, unique in INDEXES:
        if name not in _index_names(bind, table_name):
            op.create_index(name, table_name, columns, unique=unique)


def _execute_best_effort(bind, postgres_sql: str, sqlite_sql: str | None = None) -> None:
    try:
        if bind.dialect.name == "sqlite" and sqlite_sql:
            bind.execute(text(sqlite_sql))
        else:
            bind.execute(text(postgres_sql))
    except Exception:
        return


def _backfill_existing_rows(bind) -> None:
    _execute_best_effort(
        bind,
        """
        UPDATE roster_periods rp
        SET timezone_name = COALESCE(NULLIF(a.time_zone, ''), 'UTC')
        FROM amos a
        WHERE rp.amo_id = a.id AND (rp.timezone_name IS NULL OR rp.timezone_name = '')
        """,
        """
        UPDATE roster_periods
        SET timezone_name = COALESCE(
            (SELECT NULLIF(amos.time_zone, '') FROM amos WHERE amos.id = roster_periods.amo_id),
            'UTC'
        )
        WHERE timezone_name IS NULL OR timezone_name = ''
        """,
    )
    bind.execute(text("UPDATE roster_periods SET timezone_name = 'UTC' WHERE timezone_name IS NULL OR timezone_name = ''"))
    bind.execute(text("UPDATE roster_versions SET state_revision = 1 WHERE state_revision IS NULL OR state_revision < 1"))
    bind.execute(text("UPDATE roster_assignments SET state_revision = 1 WHERE state_revision IS NULL OR state_revision < 1"))
    bind.execute(text("UPDATE roster_assignments SET source = 'MANUAL' WHERE source IS NULL OR source = ''"))
    bind.execute(text("UPDATE roster_validation_findings SET overridable = false WHERE overridable IS NULL"))
    bind.execute(text("UPDATE roster_validation_findings SET sort_order = 100 WHERE sort_order IS NULL"))
    bind.execute(text("UPDATE roster_publication_acknowledgements SET delivery_status = 'ACKNOWLEDGED' WHERE delivery_status IS NULL OR delivery_status = ''"))
    bind.execute(text("UPDATE roster_publication_acknowledgements SET viewed_at = acknowledged_at WHERE viewed_at IS NULL"))
    _execute_best_effort(
        bind,
        """
        UPDATE roster_assignments ra
        SET department_id = u.department_id
        FROM users u
        WHERE ra.user_id = u.id AND ra.department_id IS NULL
        """,
        """
        UPDATE roster_assignments
        SET department_id = (SELECT users.department_id FROM users WHERE users.id = roster_assignments.user_id)
        WHERE department_id IS NULL
        """,
    )


def _set_not_null_defaults(bind) -> None:
    if bind.dialect.name == "sqlite":
        return
    op.alter_column("roster_periods", "timezone_name", existing_type=sa.String(length=64), nullable=False, server_default="UTC")
    op.alter_column("roster_versions", "state_revision", existing_type=sa.Integer(), nullable=False, server_default="1")
    op.alter_column("roster_assignments", "source", existing_type=sa.String(length=32), nullable=False, server_default="MANUAL")
    op.alter_column("roster_assignments", "state_revision", existing_type=sa.Integer(), nullable=False, server_default="1")
    op.alter_column("roster_validation_findings", "overridable", existing_type=sa.Boolean(), nullable=False, server_default=sa.text("false"))
    op.alter_column("roster_validation_findings", "sort_order", existing_type=sa.Integer(), nullable=False, server_default="100")
    op.alter_column("roster_publication_acknowledgements", "delivery_status", existing_type=sa.String(length=32), nullable=False, server_default="PENDING")


def _first(mapping: dict[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        value = mapping.get(name)
        if value is not None and value != "":
            return value
    return None


def _as_aware(value: Any, *, end_of_day: bool = False) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        local_time = time.max if end_of_day else time.min
        return datetime.combine(value, local_time, tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except Exception:
        return None


def _availability_type(raw: Any) -> str:
    value = str(getattr(raw, "value", raw) or "UNAVAILABLE").strip().upper().replace(" ", "_")
    aliases = {
        "LEAVE": "ANNUAL_LEAVE",
        "ANNUAL": "ANNUAL_LEAVE",
        "SICK": "SICK_LEAVE",
        "UNAVAIL": "UNAVAILABLE",
        "OUT_OF_OFFICE": "UNAVAILABLE",
    }
    value = aliases.get(value, value)
    allowed = {
        "AVAILABLE",
        "UNAVAILABLE",
        "ANNUAL_LEAVE",
        "SICK_LEAVE",
        "COMPASSIONATE_LEAVE",
        "MATERNITY_LEAVE",
        "PATERNITY_LEAVE",
        "STUDY_LEAVE",
        "UNPAID_LEAVE",
        "TRAINING",
        "TRAVEL",
        "SUSPENDED",
        "OTHER",
    }
    return value if value in allowed else "OTHER"


def _migrate_legacy_availability(bind) -> None:
    inspector = inspect(bind)
    if not inspector.has_table("user_availability") or not inspector.has_table("employee_availability_events"):
        return
    rows = bind.execute(text("SELECT * FROM user_availability")).mappings().all()
    target = sa.table(
        "employee_availability_events",
        sa.column("id"),
        sa.column("amo_id"),
        sa.column("user_id"),
        sa.column("availability_type"),
        sa.column("starts_at"),
        sa.column("ends_at"),
        sa.column("blocking"),
        sa.column("provisional"),
        sa.column("source_type"),
        sa.column("source_id"),
        sa.column("reason"),
        sa.column("metadata_json"),
        sa.column("created_by_user_id"),
        sa.column("updated_by_user_id"),
        sa.column("created_at"),
        sa.column("updated_at"),
    )
    existing_sources = {
        (str(row[0]), str(row[1]))
        for row in bind.execute(
            text(
                "SELECT source_type, source_id FROM employee_availability_events "
                "WHERE source_type = 'LEGACY_QUALITY_AVAILABILITY'"
            )
        ).fetchall()
    }
    inserts: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        mapping = dict(row)
        amo_id = _first(mapping, ("amo_id", "tenant_id"))
        user_id = _first(mapping, ("user_id", "person_id", "employee_user_id"))
        starts_at = _as_aware(_first(mapping, ("starts_at", "start_at", "effective_from", "valid_from", "start_date", "from_date")))
        ends_at = _as_aware(_first(mapping, ("ends_at", "end_at", "effective_to", "valid_to", "end_date", "to_date")), end_of_day=True)
        if starts_at and not ends_at:
            ends_at = starts_at + timedelta(days=1)
        if not amo_id or not user_id or not starts_at or not ends_at or ends_at <= starts_at:
            continue
        legacy_id = str(_first(mapping, ("id", "availability_id")) or index)
        source_key = ("LEGACY_QUALITY_AVAILABILITY", legacy_id)
        if source_key in existing_sources:
            continue
        inserts.append({
            "id": str(uuid4()),
            "amo_id": str(amo_id),
            "user_id": str(user_id),
            "availability_type": _availability_type(_first(mapping, ("availability_type", "status", "type", "kind"))),
            "starts_at": starts_at,
            "ends_at": ends_at,
            "blocking": bool(_first(mapping, ("blocking", "is_blocking")) if _first(mapping, ("blocking", "is_blocking")) is not None else True),
            "provisional": bool(_first(mapping, ("provisional", "is_provisional")) or False),
            "source_type": "LEGACY_QUALITY_AVAILABILITY",
            "source_id": legacy_id,
            "reason": str(_first(mapping, ("reason", "notes", "description")) or "Migrated from quality.user_availability"),
            "metadata_json": {"legacy_table": "user_availability", "legacy_id": legacy_id},
            "created_by_user_id": _first(mapping, ("created_by_user_id", "created_by")),
            "updated_by_user_id": _first(mapping, ("updated_by_user_id", "updated_by")),
            "created_at": _as_aware(_first(mapping, ("created_at",))) or datetime.now(UTC),
            "updated_at": _as_aware(_first(mapping, ("updated_at",))) or datetime.now(UTC),
        })
    if inserts:
        bind.execute(target.insert(), inserts)


def upgrade() -> None:
    bind = op.get_bind()
    _add_columns(bind)
    _create_metadata_tables(bind)
    _create_foreign_keys(bind)
    _create_indexes(bind)
    _backfill_existing_rows(bind)
    _set_not_null_defaults(bind)
    _migrate_legacy_availability(bind)


def downgrade() -> None:
    bind = op.get_bind()

    # Drop references from pre-existing tables before dropping their targets.
    if bind.dialect.name != "sqlite":
        for table_name, constraint_name, _local, _remote_table, _remote, _ondelete in reversed(FOREIGN_KEYS):
            if constraint_name in _fk_names(bind, table_name):
                op.drop_constraint(constraint_name, table_name, type_="foreignkey")

    for table_name, name, _columns, _unique in reversed(INDEXES):
        if name in _index_names(bind, table_name):
            op.drop_index(name, table_name=table_name)

    for table_name in reversed(NEW_TABLES):
        if inspect(bind).has_table(table_name):
            op.drop_table(table_name)

    for table_name, columns in reversed(list(ROSTER_COLUMNS.items())):
        existing = _column_names(bind, table_name)
        for column in reversed(columns):
            if column.name in existing:
                op.drop_column(table_name, column.name)
