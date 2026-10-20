"""Guard FastAPI dependency identity so shared engines do not double-checkout."""

from __future__ import annotations

from amodb import database as database_module


def test_shared_engine_aliases_read_dependency_to_write() -> None:
    """Local single-DB deployments must share one dependency callable.

    FastAPI caches Depends() by callable identity. Distinct get_read_db /
    get_write_db generators previously checked out two pooled connections per
    authenticated request and exhausted the pool under QMS page fan-out.
    """
    # A shared URL must share the engine/dependency. Configured read replicas
    # must retain an independent engine rather than invalidating this contract.
    if database_module.READ_DB_URL == database_module.WRITE_DB_URL:
        assert database_module.get_read_db is database_module.get_write_db
    else:
        assert database_module.get_read_db is database_module._get_read_db_separate
        assert database_module.get_read_db is not database_module.get_write_db
    # Other integration tests may replace the module's engine attribute with
    # isolated SQLite test engines. FastAPI caches by dependency callable
    # identity, not the current identity of a mutable engine attribute.
    assert database_module.get_db is database_module.get_write_db


def test_pool_timeout_defaults_allow_brief_wait() -> None:
    assert database_module.POOL_TIMEOUT >= 10
