from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

TARGET_REVISION = "workforce_20260721_complete"
ROSTER_PARENT = "phase2_14a_20260615"
PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _run_alembic(*args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "amodb/alembic.ini", *args],
        cwd=PROJECT_ROOT,
        check=True,
    )


def _load_metadata() -> None:
    from amodb.main import app  # noqa: F401
    from amodb.database import Base  # noqa: F401


def _create_current_database_baseline(engine: sa.Engine) -> None:
    from amodb.database import Base

    Base.metadata.create_all(engine)


def _stamp_converged_parents(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    _run_alembic("stamp", "qual_20260705_merge_heads")


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _unique_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {
        str(constraint["name"])
        for constraint in inspector.get_unique_constraints(table_name)
        if constraint.get("name")
    }


def _foreign_key_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {
        str(foreign_key["name"])
        for foreign_key in inspector.get_foreign_keys(table_name)
        if foreign_key.get("name")
    }


def _version_rows(engine: sa.Engine) -> set[str]:
    with engine.connect() as connection:
        return {
            str(revision)
            for revision in connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalars()
        }


def _verify_workforce_schema(engine: sa.Engine) -> None:
    inspector = inspect(engine)
    required_tables = {
        "shift_templates",
        "roster_periods",
        "roster_versions",
        "roster_assignments",
        "roster_rules",
        "roster_validation_findings",
        "roster_rule_exceptions",
        "roster_publication_acknowledgements",
        "roster_demand_requirements",
        "roster_task_assignment_links",
        "roster_command_receipts",
        "roster_planner_preferences",
        "employee_availability_events",
        "employment_contracts",
        "leave_types",
        "leave_balances",
        "leave_requests",
        "leave_approvals",
        "work_patterns",
        "work_pattern_days",
        "employee_work_pattern_assignments",
        "attendance_events",
        "timesheets",
        "timesheet_lines",
        "overtime_requests",
        "overtime_approvals",
        "roster_actual_variances",
        "workforce_permission_grants",
        "training_event_time_windows",
        "workforce_notification_preferences",
    }
    assert not (required_tables - set(inspector.get_table_names()))
    assert {
        "source_version_id",
        "amendment_type",
        "amendment_reason",
        "effective_from",
        "publication_correlation_key",
    } <= _column_names(inspector, "roster_versions")
    assert {"source_reference_id", "state_revision"} <= _column_names(
        inspector, "roster_assignments"
    )
    assert "uq_roster_assignments_source_ref" in _unique_names(
        inspector, "roster_assignments"
    )
    assert "ix_roster_assignments_user_window_active" in _index_names(
        inspector, "roster_assignments"
    )
    assert "uq_workforce_permission_scope" in _unique_names(
        inspector, "workforce_permission_grants"
    )
    assert "fk_roster_task_link_task_assignment" in _foreign_key_names(
        inspector, "roster_task_assignment_links"
    )


def _verify_precreate_idempotency(engine: sa.Engine) -> None:
    inspector = inspect(engine)
    assert "roster_rules" in inspector.get_table_names()
    assert "ix_roster_rules_scope" not in _index_names(inspector, "roster_rules")
    assert "ix_wr_roster_rules_scope" in _index_names(inspector, "roster_rules")


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

    _run_alembic("upgrade", TARGET_REVISION)
    _verify_workforce_schema(engine)
    _verify_precreate_idempotency(engine)
    _verify_redundant_phase2_overlap_repair(engine)


if __name__ == "__main__":
    main()
