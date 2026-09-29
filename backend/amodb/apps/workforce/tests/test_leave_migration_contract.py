from __future__ import annotations

import ast
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "workforce_20260929_leave_governance.py"
)


def _assignment(module: ast.Module, name: str):
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"Missing migration variable: {name}")


def test_leave_governance_migration_extends_current_document_control_head():
    module = ast.parse(MIGRATION.read_text(encoding="utf-8"))

    assert _assignment(module, "revision") == "workforce_260929_leave_gov"
    assert _assignment(module, "down_revision") == "docctl_260926_record_index"


def test_leave_governance_migration_is_reachable_from_repository_heads():
    config = Config(str(Path(__file__).resolve().parents[3] / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    revision = script.get_revision("workforce_260929_leave_gov")

    assert revision is not None
    assert "workforce_260929_leave_gov" in set(script.get_heads())


def test_leave_governance_migration_repairs_columns_used_by_runtime_models():
    source = MIGRATION.read_text(encoding="utf-8")

    assert '"personnel_profiles"' in source
    assert '"gender"' in source
    assert '"leave_types"' in source
    assert '"eligible_gender"' in source
    assert "MATERNITY_LEAVE" in source
    assert "PATERNITY_LEAVE" in source
