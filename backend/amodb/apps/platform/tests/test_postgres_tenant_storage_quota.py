"""Real PostgreSQL concurrency proof for tenant storage quota reservations.

A separate schema is used so the test never modifies a deployed tenant.
"""
from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from amodb.database import Base
from amodb.apps.accounts.models import AMO, AMOAsset, Department, User
from amodb.apps.platform import storage_quota_service as quota
from amodb.apps.platform.storage_quota_models import (
    TenantStorageQuota, TenantStorageReservation, TenantStorageObject,
    TenantStorageLedgerEvent,
)

DSN = os.getenv("STORAGE_QUOTA_POSTGRES_TEST_DSN", "")
pytestmark = pytest.mark.skipif(not DSN, reason="Requires a dedicated PostgreSQL CI database")


@pytest.fixture()
def postgres_schema():
    engine = create_engine(DSN, pool_size=5, max_overflow=2)
    schema = "quota_accept_" + uuid4().hex[:12]
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = engine.execution_options(schema_translate_map={None: schema})
    tables = [
        AMO.__table__, Department.__table__, User.__table__, AMOAsset.__table__,
        TenantStorageQuota.__table__, TenantStorageReservation.__table__,
        TenantStorageObject.__table__, TenantStorageLedgerEvent.__table__,
    ]
    try:
        Base.metadata.create_all(scoped, tables=tables)
        yield scoped
    finally:
        scoped.dispose()
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def test_independent_writers_cannot_overbook_tenant_quota(postgres_schema):
    engine = postgres_schema
    with Session(engine) as db:
        db.add(AMO(id="pg-tenant", amo_code="PG_QUOTA", name="Concurrent Quota", login_slug="pg-quota"))
        db.commit()
        quota.allocate(db, tenant_id="pg-tenant", quota_bytes=100,
                       actor_id=None, reason="Approved test allocation")
        db.commit()

    barrier = threading.Barrier(2)

    def writer(number):
        barrier.wait(timeout=15)
        with Session(engine) as db:
            try:
                with db.begin():
                    quota.reserve(
                        db, tenant_id="pg-tenant",
                        object_key=f"uploads/worker-{number}.pdf",
                        size_bytes=80, idempotency_key=f"worker-{number}",
                    )
                    time.sleep(0.1)
                return True
            except ValueError as exc:
                assert "quota exceeded" in str(exc).lower()
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(writer, (1, 2)))
    assert sorted(results) == [False, True]
    with Session(engine) as db:
        account = quota.read_quota(db, "pg-tenant")
        assert account["reserved_bytes"] == 80
        assert account["used_bytes"] == 0
        assert account["remaining_bytes"] == 20
