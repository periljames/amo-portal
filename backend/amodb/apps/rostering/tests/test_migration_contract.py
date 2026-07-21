from __future__ import annotations

import ast
from pathlib import Path


MIGRATION = Path(__file__).resolve().parents[3] / "alembic" / "versions" / "workforce_20260721_complete_rostering.py"


def assignment_value(module: ast.Module, name: str):
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"Missing migration variable: {name}")


def test_migration_descends_from_current_merge_head():
    module = ast.parse(MIGRATION.read_text(encoding="utf-8"))
    assert assignment_value(module, "revision") == "workforce_20260721_complete"
    assert assignment_value(module, "down_revision") == "qual_20260705_merge_heads"


def test_migration_creates_required_workforce_and_roster_tables():
    source = MIGRATION.read_text(encoding="utf-8")
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
    missing = sorted(name for name in required if f'"{name}"' not in source)
    assert missing == []


def test_historical_phase1_migration_is_not_revised():
    historical = Path(__file__).resolve().parents[3] / "alembic" / "versions" / "phase1_20260604_core_rostering.py"
    assert historical.exists()
    assert "Revision ID: phase1_20260604" in historical.read_text(encoding="utf-8")
