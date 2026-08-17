"""Real PostgreSQL concurrency, idempotency and reconnect tests.

Run with TEST_DATABASE_URL=postgresql://amo_test:amo_test@localhost:55432/amo_resilience_test.
"""
from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL or not URL.startswith("postgresql"), reason="TEST_DATABASE_URL PostgreSQL is required")


@pytest.fixture()
def engine():
    value = create_engine(URL, pool_pre_ping=True, pool_size=4, max_overflow=0)
    schema = f"resilience_{uuid.uuid4().hex[:12]}"
    with value.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET search_path TO "{schema}"'))
        connection.execute(text("CREATE TABLE commands (key text PRIMARY KEY, payload text NOT NULL)"))
        connection.execute(text("CREATE TABLE items (id integer PRIMARY KEY, status text NOT NULL DEFAULT 'PENDING')"))
        connection.execute(text("INSERT INTO items(id) SELECT generate_series(1, 100)"))
    yield value, schema
    with value.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    value.dispose()


def test_atomic_idempotency_under_concurrency(engine):
    value, schema = engine

    def insert() -> int:
        with value.begin() as connection:
            connection.execute(text(f'SET search_path TO "{schema}"'))
            return connection.execute(text(
                "INSERT INTO commands(key,payload) VALUES ('same-key','one') "
                "ON CONFLICT (key) DO NOTHING RETURNING 1"
            )).scalar() or 0

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(lambda _: insert(), range(100)))
    assert sum(results) == 1


def test_skip_locked_claims_are_disjoint(engine):
    value, schema = engine

    def claim(worker: str) -> set[int]:
        with value.begin() as connection:
            connection.execute(text(f'SET search_path TO "{schema}"'))
            rows = connection.execute(text(
                "WITH picked AS (SELECT id FROM items WHERE status='PENDING' ORDER BY id "
                "FOR UPDATE SKIP LOCKED LIMIT 25) UPDATE items SET status=:worker "
                "FROM picked WHERE items.id=picked.id RETURNING items.id"
            ), {"worker": worker}).scalars().all()
            return set(rows)

    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(claim, ["w1", "w2", "w3", "w4"]))
    assert len(set().union(*claims)) == 100
    assert sum(len(group) for group in claims) == 100


def test_pool_reconnects_after_terminated_connection(engine):
    value, _schema = engine
    victim = value.connect()
    pid = victim.execute(text("SELECT pg_backend_pid()" )).scalar_one()
    with value.begin() as killer:
        assert killer.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid}).scalar_one()
    with pytest.raises(DBAPIError):
        victim.execute(text("SELECT 1"))
    victim.close()
    with value.connect() as recovered:
        assert recovered.execute(text("SELECT 1")).scalar_one() == 1
