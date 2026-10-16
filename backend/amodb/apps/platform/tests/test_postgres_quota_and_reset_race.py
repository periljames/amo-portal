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
from amodb.apps.accounts.models import AMO, Department, User, PasswordResetToken
from amodb.apps.platform import storage_quota_service as quota
from amodb.apps.platform.storage_quota_models import (
    TenantStorageQuota, TenantStorageReservation, TenantStorageObject, TenantStorageLedgerEvent,
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
        AMO.__table__, Department.__table__, User.__table__,
        PasswordResetToken.__table__, TenantStorageQuota.__table__,
        TenantStorageReservation.__table__, TenantStorageObject.__table__,
        TenantStorageLedgerEvent.__table__,
    ]
    Base.metadata.create_all(scoped, tables=tables)
    try:
        yield scoped, schema
    finally:
        scoped.dispose()
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def test_two_worker_reservations_cannot_exceed_quota(postgres_schema):
    engine, _ = postgres_schema
    with Session(engine) as db:
        db.add(AMO(id="pg-tenant", amo_code="PG_QUOTA", name="Concurrent Quota", login_slug="pg-quota"))
        db.commit()
        quota.allocate(db, tenant_id="pg-tenant", quota_bytes=100, actor_id=None, reason="Approved contract")
        db.commit()
    barrier = threading.Barrier(2)

    def worker(number):
        barrier.wait(timeout=10)
        with Session(engine) as db:
            try:
                with db.begin():
                    quota.reserve(db, tenant_id="pg-tenant",
                                  object_key=f"uploads/worker-{number}.pdf",
                                  size_bytes=80, idempotency_key=f"worker-{number}")
                    time.sleep(0.1)
                return True
            except ValueError as exc:
                assert "quota exceeded" in str(exc).lower()
                return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(worker, (1, 2)))
    assert sorted(results) == [False, True]
    with Session(engine) as db:
        account = quota.read_quota(db, "pg-tenant")
        assert account["reserved_bytes"] == 80
        assert account["used_bytes"] == 0
        assert account["remaining_bytes"] == 20


def test_password_reset_one_use_conditional_update_under_postgres(postgres_schema):
    """Tests the indexed conditional one-use gate with independent transactions."""
    from datetime import datetime, timedelta, timezone
    from amodb.apps.accounts import services as account_services
    engine, _ = postgres_schema
    with Session(engine) as db:
        db.add(AMO(id="pg-auth", amo_code="PG_AUTH", name="Concurrent Auth", login_slug="pg-auth"))
        db.add(User(
            id="pg-user", amo_id="pg-auth", staff_code="PG1",
            email="pg-user@example.test", first_name="Test", last_name="User",
            full_name="Test User", hashed_password="unusable",
        ))
        db.flush()
        token = "reset-token-from-independent-workers"
        digest = account_services._indexed_reset_digest(token)
        db.add(PasswordResetToken(
            id="pg-reset", user_id="pg-user", token_hash=digest,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        ))
        db.commit()
    barrier = threading.Barrier(2)

    def worker(number):
        barrier.wait(timeout=10)
        with Session(engine) as db:
            with db.begin():
                affected = (db.query(PasswordResetToken)
                    .filter(PasswordResetToken.id == "pg-reset", PasswordResetToken.used_at.is_(None),
                            PasswordResetToken.expires_at > datetime.now(timezone.utc))
                    .update({"used_at": datetime.now(timezone.utc)}, synchronize_session=False))
                time.sleep(0.05)
            return affected

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(worker, (1, 2)))
    assert sorted(results) == [0, 1]
