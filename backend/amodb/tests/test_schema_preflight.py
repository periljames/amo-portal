import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("DATABASE_WRITE_URL", "sqlite+pysqlite:///:memory:")
sys.path.append(str(Path(__file__).resolve().parents[2]))

from amodb import main  # noqa: E402


class _FakeResult:
    def __init__(self, versions):
        self._versions = versions

    def fetchall(self):
        return [(v,) for v in self._versions]


class _FakeSession:
    def __init__(self, versions):
        self._versions = versions

    def execute(self, _query):
        return _FakeResult(self._versions)

    def close(self):
        pass


class _FakeScript:
    def __init__(self, heads):
        self._heads = heads

    def get_heads(self):
        return self._heads


def test_schema_preflight_noop_when_not_strict(monkeypatch):
    monkeypatch.setenv("SCHEMA_STRICT", "0")
    main._enforce_schema_head_sync_if_configured()


def test_schema_preflight_raises_on_mismatch(monkeypatch):
    monkeypatch.setenv("SCHEMA_STRICT", "1")
    monkeypatch.setattr(main, "WriteSessionLocal", lambda: _FakeSession(["old_revision"]))
    monkeypatch.setattr(main.ScriptDirectory, "from_config", lambda _cfg: _FakeScript(["head_revision"]))

    with pytest.raises(RuntimeError):
        main._enforce_schema_head_sync_if_configured()


def test_schema_preflight_passes_on_match(monkeypatch):
    monkeypatch.setenv("SCHEMA_STRICT", "true")
    monkeypatch.setattr(main, "WriteSessionLocal", lambda: _FakeSession(["head_revision"]))
    monkeypatch.setattr(main.ScriptDirectory, "from_config", lambda _cfg: _FakeScript(["head_revision"]))

    main._enforce_schema_head_sync_if_configured()
