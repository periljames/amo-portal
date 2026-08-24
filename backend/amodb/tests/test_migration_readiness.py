"""Focused regression coverage for ancestry-aware /healthz migration readiness."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("ALLOW_SQLITE_FOR_TESTS", "1")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("DATABASE_WRITE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("AMODB_SKIP_MODEL_IMPORTS", "1")

sys.path.append(str(Path(__file__).resolve().parents[2]))

from amodb import main as portal_main  # noqa: E402


class _FakeRevision:
    def __init__(self, revision: str) -> None:
        self.revision = revision


class _FakeScript:
    """Minimal Alembic ScriptDirectory stand-in for readiness unit tests."""

    def __init__(self, lineages: dict[str, list[str]]) -> None:
        # lineages[head] = revisions from tip toward base (iterate_revisions order).
        self._lineages = {head: list(chain) for head, chain in lineages.items()}
        self._known = {revision for chain in self._lineages.values() for revision in chain}

    def get_heads(self) -> list[str]:
        return list(self._lineages.keys())

    def get_revision(self, revision: str) -> _FakeRevision:
        if revision not in self._known:
            raise KeyError(f"No such revision '{revision}'")
        return _FakeRevision(revision)

    def iterate_revisions(self, upper: str, lower: str):
        del lower  # readiness always walks to base
        if upper not in self._lineages:
            raise ValueError(f"Unknown upper revision '{upper}'")
        for revision in self._lineages[upper]:
            yield _FakeRevision(revision)


def _dual_branch_script() -> _FakeScript:
    # Two independent module branches sharing no tip:
    #   anc_a -> mid_a -> head_a
    #   anc_b -> head_b
    return _FakeScript(
        {
            "head_a": ["head_a", "mid_a", "anc_a"],
            "head_b": ["head_b", "anc_b"],
        }
    )


def test_revision_applied_when_expected_is_exact_db_head() -> None:
    script = _dual_branch_script()
    assert portal_main._revision_applied_in_database(script, "head_a", {"head_a", "head_b"}) is True


def test_revision_applied_when_expected_is_ancestor_of_db_head() -> None:
    script = _dual_branch_script()
    assert portal_main._revision_applied_in_database(script, "anc_a", {"head_a", "head_b"}) is True
    assert portal_main._revision_applied_in_database(script, "mid_a", {"head_a"}) is True


def test_revision_not_applied_when_expected_is_unrelated() -> None:
    script = _dual_branch_script()
    assert portal_main._revision_applied_in_database(script, "anc_a", {"head_b"}) is False
    assert portal_main._revision_applied_in_database(script, "head_a", {"head_b"}) is False


def test_revision_not_applied_for_unknown_expected_revision() -> None:
    script = _dual_branch_script()
    assert (
        portal_main._revision_applied_in_database(
            script,
            "does_not_exist_in_graph",
            {"head_a", "head_b"},
        )
        is False
    )


def _force_fresh_readiness_cache() -> None:
    portal_main._readiness_migration_cache.update(
        {"checked_at": 0.0, "ready": False, "detail": "Not checked"}
    )


def _patch_readiness_deps(monkeypatch, script: _FakeScript, database_heads: set[str]) -> None:
    class _Result:
        def fetchall(self):
            return [(revision,) for revision in sorted(database_heads)]

    class _Session:
        def execute(self, *_args, **_kwargs):
            return _Result()

    monkeypatch.setattr(portal_main, "WriteSessionLocal", lambda: _Session())
    monkeypatch.setattr(portal_main, "close_session_safely", lambda _db: None)
    monkeypatch.setattr(portal_main, "Config", lambda *_a, **_k: object())
    monkeypatch.setattr(
        portal_main.ScriptDirectory,
        "from_config",
        classmethod(lambda cls, _cfg: script),
    )
    _force_fresh_readiness_cache()


def test_migration_readiness_exact_db_head(monkeypatch) -> None:
    script = _dual_branch_script()
    _patch_readiness_deps(monkeypatch, script, {"head_a", "head_b"})
    monkeypatch.setenv("DATABASE_EXPECTED_ALEMBIC_HEADS", "head_a")

    ready, detail = portal_main._migration_readiness()
    assert ready is True
    assert detail is None


def test_migration_readiness_ancestor_of_applied_head(monkeypatch) -> None:
    script = _dual_branch_script()
    _patch_readiness_deps(monkeypatch, script, {"head_a", "head_b"})
    monkeypatch.setenv("DATABASE_EXPECTED_ALEMBIC_HEADS", "anc_a,anc_b")

    ready, detail = portal_main._migration_readiness()
    assert ready is True
    assert detail is None


def test_migration_readiness_missing_non_ancestor(monkeypatch) -> None:
    script = _dual_branch_script()
    _patch_readiness_deps(monkeypatch, script, {"head_b"})
    monkeypatch.setenv("DATABASE_EXPECTED_ALEMBIC_HEADS", "head_a")

    ready, detail = portal_main._migration_readiness()
    assert ready is False
    assert detail is not None
    assert "head_a" in detail
    assert "head_b" in detail


def test_migration_readiness_unknown_expected_is_not_false_ready(monkeypatch) -> None:
    script = _dual_branch_script()
    _patch_readiness_deps(monkeypatch, script, {"head_a", "head_b"})
    monkeypatch.setenv("DATABASE_EXPECTED_ALEMBIC_HEADS", "bogus_revision_xyz")

    ready, detail = portal_main._migration_readiness()
    assert ready is False
    assert detail is not None
    assert "bogus_revision_xyz" in detail
    assert "do not include required heads" in detail


def test_migration_readiness_multi_branch_each_expected_satisfied(monkeypatch) -> None:
    script = _dual_branch_script()
    _patch_readiness_deps(monkeypatch, script, {"head_a", "head_b"})
    monkeypatch.setenv("DATABASE_EXPECTED_ALEMBIC_HEADS", "mid_a,anc_b")

    ready, detail = portal_main._migration_readiness()
    assert ready is True
    assert detail is None


def test_migration_readiness_empty_database_heads_not_ready(monkeypatch) -> None:
    script = _dual_branch_script()
    _patch_readiness_deps(monkeypatch, script, set())
    monkeypatch.setenv("DATABASE_EXPECTED_ALEMBIC_HEADS", "head_a")

    ready, detail = portal_main._migration_readiness()
    assert ready is False
    assert detail is not None
