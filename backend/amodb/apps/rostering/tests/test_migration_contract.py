from __future__ import annotations

import ast
from pathlib import Path


MIGRATION = Path(__file__).resolve().parents[3] / "alembic" / "versions" / "workforce_20260721_complete_rostering.py"
PRECREATE = Path(__file__).resolve().parents[3] / "alembic" / "versions" / "workforce_20260721_precreate_tables.py"


def assignment_value(module: ast.Module, name: str):
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"Missing migration variable: {name}")


def test_migration_descends_from_quality_and_core_rostering_heads():
    module = ast.parse(MIGRATION.read_text(encoding="utf-8"))
    assert assignment_value(module, "revision") == "workforce_20260721_complete"
    assert assignment_value(module, "down_revision") == "workforce_20260721_precreate"

    predecessor = ast.parse(PRECREATE.read_text(encoding="utf-8"))
    assert assignment_value(predecessor, "revision") == "workforce_20260721_precreate"
    assert assignment_value(predecessor, "down_revision") == (
        "qual_20260705_merge_heads",
        "phase2_14a_20260615",
    )


def test_migration_revision_graph_is_import_safe_without_database_url():
    for path in (PRECREATE, MIGRATION):
        module = ast.parse(path.read_text(encoding="utf-8"))
        top_level_application_imports: list[str] = []
        for node in module.body:
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("amodb"):
                top_level_application_imports.append(node.module)
            elif isinstance(node, ast.Import):
                top_level_application_imports.extend(alias.name for alias in node.names if alias.name.startswith("amodb"))
        assert top_level_application_imports == []


def test_migration_creates_required_workforce_and_roster_tables():
    source = MIGRATION.read_text(encoding="utf-8")
    precreate_source = PRECREATE.read_text(encoding="utf-8")
    required = {
        "employment_contracts",
        "work_patterns",
        "employee_work_pattern_assignments",
        "leave_requests",
        "employee_availability_events",
        "attendance_events",
        "timesheets",
        "workforce_permission_grants",
        "roster_rules",
        "roster_rule_exceptions",
        "roster_demand_requirements",
        "roster_command_receipts",
    }
    missing = sorted(
        name
        for name in required
        if f'"{name}"' not in source and f'"{name}"' not in precreate_source
    )
    assert missing == []
    assert "_restore_deferred_foreign_keys" in precreate_source


def test_historical_phase1_migration_is_not_revised():
    historical = Path(__file__).resolve().parents[3] / "alembic" / "versions" / "phase1_20260604_core_rostering.py"
    assert historical.exists()
    assert "Revision ID: phase1_20260604" in historical.read_text(encoding="utf-8")
