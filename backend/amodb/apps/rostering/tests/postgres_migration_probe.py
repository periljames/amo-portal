from __future__ import annotations

import os
import subprocess
from importlib import import_module

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from amodb.database import Base


NEW_TABLES = {
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
}

QUALITY_PARENT = "qual_20260705_merge_heads"
ROSTER_PARENT = "phase2_14a_20260615"
TARGET_REVISION = "workforce_20260721_complete"


def _load_metadata() -> None:
    for module_name in (
        "amodb.apps.accounts.models",
        "amodb.apps.foundations.models",
        "amodb.apps.training.models",
        "amodb.apps.work.models",
        "amodb.apps.rostering.models",
        "amodb.apps.workforce.models",
    ):
        import_module(module_name)


def _create_current_database_baseline(engine: sa.Engine) -> None:
    """Create the existing tables required by the Workforce revisions."""
    baseline = sa.MetaData()
    manual = {
        "amos": [
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("time_zone", sa.String(64)),
        ],
        "departments": [sa.Column("id", sa.String(36), primary_key=True)],
        "users": [
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("department_id", sa.String(36)),
        ],
        "base_stations": [sa.Column("id", sa.String(36), primary_key=True)],
        "shift_templates": [
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("amo_id", sa.String(36)),
        ],
        "roster_periods": [
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("amo_id", sa.String(36)),
        ],
        "roster_versions": [
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("amo_id", sa.String(36)),
        ],
        "roster_assignments": [
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("amo_id", sa.String(36)),
            sa.Column("version_id", sa.String(36)),
            sa.Column("user_id", sa.String(36)),
            sa.Column("starts_at", sa.DateTime(timezone=True)),
            sa.Column("ends_at", sa.DateTime(timezone=True)),
        ],
        "roster_validation_findings": [
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("amo_id", sa.String(36)),
            sa.Column("version_id", sa.String(36)),
            sa.Column("user_id", sa.String(36)),
            sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        ],
        "roster_publication_acknowledgements": [
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("amo_id", sa.String(36)),
            sa.Column("version_id", sa.String(36)),
            sa.Column("user_id", sa.String(36)),
            sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        ],
    }
    for table_name, columns in manual.items():
        sa.Table(table_name, baseline, *columns)

    referenced: dict[str, dict[str, sa.Column]] = {}
    for table_name in NEW_TABLES:
        table = Base.metadata.tables[table_name]
        for foreign_key in table.foreign_keys:
            target = foreign_key.column
            target_table = target.table.name
            if target_table in NEW_TABLES or target_table in manual:
                continue
            referenced.setdefault(target_table, {})[target.name] = target

    for table_name, columns in referenced.items():
        sa.Table(
            table_name,
            baseline,
            *[
                sa.Column(
                    column_name,
                    source_column.type,
                    primary_key=bool(source_column.primary_key or column_name == "id"),
                )
                for column_name, source_column in columns.items()
            ],
        )

    baseline.create_all(engine)


def _run_alembic(*arguments: str) -> None:
    subprocess.run(
        ["alembic", "-c", "amodb/alembic.ini", *arguments],
        check=True,
        env=os.environ.copy(),
    )


def _stamp_converged_parents(engine: sa.Engine) -> None:
    _run_alembic("stamp", QUALITY_PARENT)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO alembic_version (version_num) VALUES (:revision) "
                "ON CONFLICT (version_num) DO NOTHING"
            ),
            {"revision": ROSTER_PARENT},
        )


def _metadata_fk_signatures(table: sa.Table) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    return {
        (
            tuple(str(element.parent.name) for element in constraint.elements),
            constraint.referred_table.name,
            tuple(str(element.column.name) for element in constraint.elements),
        )
        for constraint in table.foreign_key_constraints
    }


def _database_fk_signatures(
    inspector: sa.Inspector,
    table_name: str,
) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    return {
        (
            tuple(str(column) for column in (foreign_key.get("constrained_columns") or ())),
            str(foreign_key.get("referred_table") or ""),
            tuple(str(column) for column in (foreign_key.get("referred_columns") or ())),
        )
        for foreign_key in inspector.get_foreign_keys(table_name)
    }


def _version_rows(engine: sa.Engine) -> set[str]:
    with engine.connect() as connection:
        return {
            str(revision)
            for revision in connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalars()
        }


def _verify_redundant_phase2_overlap_repair(engine: sa.Engine) -> None:
    """Reproduce the released overlapping-head state and run real Alembic commands."""
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO alembic_version (version_num) VALUES (:revision) "
                "ON CONFLICT (version_num) DO NOTHING"
            ),
            {"revision": ROSTER_PARENT},
        )

    assert _version_rows(engine) == {TARGET_REVISION, ROSTER_PARENT}
    _run_alembic("upgrade", TARGET_REVISION)
    assert _version_rows(engine) == {TARGET_REVISION}

    script = ScriptDirectory.from_config(Config("amodb/alembic.ini"))
    expected_heads = set(script.get_heads())
    assert "rostering_20260724_governance" in expected_heads

    # Reproduce the exact `upgrade heads` overlap at a fully-stamped installation:
    # all legitimate heads plus the now-redundant historical Phase 2 marker.
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM alembic_version"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            [{"revision": revision} for revision in sorted(expected_heads | {ROSTER_PARENT})],
        )

    _run_alembic("upgrade", "heads")
    assert _version_rows(engine) == expected_heads


def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_engine(database_url)
    _load_metadata()
    _create_current_database_baseline(engine)
    _stamp_converged_parents(engine)

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE migration_collision_probe (id integer)"))
        connection.execute(text("CREATE INDEX ix_roster_rules_scope ON migration_collision_probe (id)"))
        connection.execute(text("CREATE INDEX ix_roster_rules_amo_active ON migration_collision_probe (id)"))
        connection.execute(text("CREATE INDEX uq_roster_rules_amo_code ON migration_collision_probe (id)"))

    _run_alembic("upgrade", TARGET_REVISION)

    inspector = inspect(engine)
    with engine.connect() as connection:
        revision = connection.execute(
            text(
                "SELECT version_num FROM alembic_version "
                "WHERE version_num = :revision"
            ),
            {"revision": TARGET_REVISION},
        ).scalar_one()
        roster_table = connection.execute(
            text("SELECT to_regclass('public.roster_rules')")
        ).scalar_one()
        indexes = set(
            connection.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'public' AND tablename = 'roster_rules'"
                )
            ).scalars()
        )

    assert revision == TARGET_REVISION
    assert roster_table == "roster_rules"
    assert "ix_wr_roster_rules_scope" in indexes
    assert any(
        name.startswith("ix_roster_rules_amo_active__roster_rules")
        for name in indexes
    ), indexes
    assert any(
        name.startswith("uq_roster_rules_amo_code__roster_rules")
        for name in indexes
    ), indexes

    shift_columns = {column["name"] for column in inspector.get_columns("shift_templates")}
    assert {"color_token", "icon_name"}.issubset(shift_columns), shift_columns

    missing_foreign_keys: dict[str, list[tuple[tuple[str, ...], str, tuple[str, ...]]]] = {}
    for table_name in sorted(NEW_TABLES):
        expected = _metadata_fk_signatures(Base.metadata.tables[table_name])
        actual = _database_fk_signatures(inspector, table_name)
        missing = sorted(expected - actual)
        if missing:
            missing_foreign_keys[table_name] = missing
    assert missing_foreign_keys == {}, missing_foreign_keys

    _verify_redundant_phase2_overlap_repair(engine)


if __name__ == "__main__":
    main()
