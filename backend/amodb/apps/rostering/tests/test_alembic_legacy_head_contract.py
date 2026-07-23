from __future__ import annotations

from pathlib import Path


VERSIONS = Path(__file__).resolve().parents[3] / "alembic" / "versions"
PRECREATE = VERSIONS / "workforce_20260721_precreate_tables.py"


def test_workforce_precreate_history_is_not_rewritten() -> None:
    source = PRECREATE.read_text(encoding="utf-8")
    assert 'down_revision = "qual_20260705_merge_heads"' in source
    assert 'down_revision = ("qual_20260705_merge_heads", "phase2_14a_20260615")' not in source
