"""Guard FastAPI dependency identity so shared engines do not double-checkout."""

from __future__ import annotations

from amodb import database as database_module


def test_shared_engine_aliases_read_dependency_to_write() -> None:
    """Local single-DB deployments must share one dependency callable.

    FastAPI caches Depends() by callable identity. Distinct get_read_db /
    get_write_db generators previously checked out two pooled connections per
    authenticated request and exhausted the pool under QMS page fan-out.
    """
    assert database_module.read_engine is database_module.write_engine
    assert database_module.get_read_db is database_module.get_write_db
    assert database_module.get_db is database_module.get_write_db


def test_pool_timeout_defaults_allow_brief_wait() -> None:
    assert database_module.POOL_TIMEOUT >= 10
