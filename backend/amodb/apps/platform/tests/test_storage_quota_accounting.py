from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from amodb.database import Base
from amodb.apps.accounts.models import AMO, AMOAsset, Department, User
from amodb.apps.platform import storage_quota_service as quota
from amodb.apps.platform.storage_quota_models import (
    DEFAULT_PAID_QUOTA_BYTES, TenantStorageLedgerEvent,
    TenantStorageObject, TenantStorageQuota, TenantStorageReservation,
)


@pytest.fixture()
def storage_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[
        AMO.__table__, Department.__table__, User.__table__, AMOAsset.__table__,
        TenantStorageQuota.__table__, TenantStorageReservation.__table__,
        TenantStorageObject.__table__, TenantStorageLedgerEvent.__table__,
    ])
    with Session(engine) as db:
        db.add(AMO(id="tenant-1", name="Quota Test Tenant", amo_code="QT-1", login_slug="quota-1"))
        db.add(AMO(id="tenant-2", name="Quota Test Tenant 2", amo_code="QT-2", login_slug="quota-2"))
        db.commit()
        yield db
    engine.dispose()


def test_decimal_five_terabytes_is_not_binary_tebibytes():
    assert DEFAULT_PAID_QUOTA_BYTES == 5_000_000_000_000
    assert DEFAULT_PAID_QUOTA_BYTES != 5 * (1024 ** 4)


def test_new_tenant_has_no_unapproved_allowance(storage_db):
    state = quota.read_quota(storage_db, "tenant-1")
    assert state["quota_bytes"] == 0
    with pytest.raises(ValueError, match="no activated"):
        quota.reserve(storage_db, tenant_id="tenant-1", object_key="one/file.pdf",
                      size_bytes=10, idempotency_key="id-a")


def test_reservation_is_idempotent_and_blocks_overbooking(storage_db):
    quota.allocate(storage_db, tenant_id="tenant-1", quota_bytes=100, actor_id=None, reason="Approved limit")
    first = quota.reserve(storage_db, tenant_id="tenant-1", object_key="one/file.pdf",
                          size_bytes=80, idempotency_key="id-a")
    storage_db.commit()
    second = quota.reserve(storage_db, tenant_id="tenant-1", object_key="one/file.pdf",
                           size_bytes=80, idempotency_key="id-a")
    assert first.id == second.id
    with pytest.raises(ValueError, match="exceeded"):
        quota.reserve(storage_db, tenant_id="tenant-1", object_key="two/file.pdf",
                      size_bytes=21, idempotency_key="id-b")
    with pytest.raises(ValueError, match="different content"):
        quota.reserve(storage_db, tenant_id="tenant-1", object_key="other.pdf",
                      size_bytes=80, idempotency_key="id-a")
    assert quota.read_quota(storage_db, "tenant-1")["reserved_bytes"] == 80
    with pytest.raises(ValueError, match="already exists"):
        quota.reserve(storage_db, tenant_id="tenant-1",
                      object_key="one//file.pdf", size_bytes=1,
                      idempotency_key="aliased-key")


def test_finalize_and_delete_have_exact_balances(storage_db):
    quota.allocate(storage_db, tenant_id="tenant-1", quota_bytes=100, actor_id=None, reason="Contract")
    r = quota.reserve(storage_db, tenant_id="tenant-1", object_key="one/file.pdf",
                      size_bytes=99, idempotency_key="one")
    storage_db.commit()
    digest = hashlib.sha256(b"x").hexdigest()
    obj = quota.finalize(storage_db, tenant_id="tenant-1", reservation_id=r.id,
                         storage_uri="s3://test/one/file.pdf", checksum_sha256=digest)
    storage_db.commit()
    assert quota.read_quota(storage_db, "tenant-1")["used_bytes"] == 99
    assert quota.read_quota(storage_db, "tenant-1")["reserved_bytes"] == 0
    repeated = quota.finalize(storage_db, tenant_id="tenant-1", reservation_id=r.id,
                              storage_uri="s3://test/one/file.pdf", checksum_sha256=digest)
    assert repeated.id == obj.id
    assert quota.recorded_delete(storage_db, tenant_id="tenant-1", object_key="one/file.pdf")
    assert not quota.recorded_delete(storage_db, tenant_id="tenant-1", object_key="one/file.pdf")
    assert quota.read_quota(storage_db, "tenant-1")["used_bytes"] == 0
    with pytest.raises(ValueError, match="already exists"):
        quota.reserve(storage_db, tenant_id="tenant-1",
                      object_key="one/file.pdf", size_bytes=1,
                      idempotency_key="new-operation-after-delete")


def test_finalization_rejects_foreign_s3_bucket_and_key(storage_db, monkeypatch):
    monkeypatch.setenv("AMO_STORAGE_BACKEND", "s3")
    monkeypatch.setenv("AMO_STORAGE_S3_BUCKET", "tenant-storage")
    monkeypatch.setenv("AMO_STORAGE_S3_PREFIX", "amo-portal")
    quota.allocate(storage_db, tenant_id="tenant-1", quota_bytes=100,
                   actor_id=None, reason="Approved storage")
    reservation = quota.reserve(storage_db, tenant_id="tenant-1",
                                object_key="evidence/tenant-1/report.pdf",
                                size_bytes=12, idempotency_key="foreign-uri")
    digest = hashlib.sha256(b"verified").hexdigest()

    for uri in (
        "s3://foreign-bucket/amo-portal/evidence/tenant-1/report.pdf",
        "s3://tenant-storage/amo-portal/evidence/tenant-2/report.pdf",
        "s3://tenant-storage/evidence/tenant-1/report.pdf",
    ):
        with pytest.raises(ValueError, match="does not match"):
            quota.finalize(storage_db, tenant_id="tenant-1", reservation_id=reservation.id,
                           storage_uri=uri, checksum_sha256=digest)
        assert quota.read_quota(storage_db, "tenant-1")["reserved_bytes"] == 12

    receipt = quota.finalize(storage_db, tenant_id="tenant-1",
                             reservation_id=reservation.id,
                             storage_uri="s3://tenant-storage/amo-portal/evidence/tenant-1/report.pdf",
                             checksum_sha256=digest)
    assert receipt.size_bytes == 12
    assert quota.read_quota(storage_db, "tenant-1")["used_bytes"] == 12


def test_cancel_and_tenant_boundaries(storage_db):
    quota.allocate(storage_db, tenant_id="tenant-1", quota_bytes=10, actor_id=None, reason="Contract")
    quota.allocate(storage_db, tenant_id="tenant-2", quota_bytes=5, actor_id=None, reason="Contract")
    r = quota.reserve(storage_db, tenant_id="tenant-1", object_key="one/file.pdf",
                      size_bytes=9, idempotency_key="one")
    with pytest.raises(ValueError, match="not found"):
        quota.cancel(storage_db, tenant_id="tenant-2", reservation_id=r.id)
    quota.cancel(storage_db, tenant_id="tenant-1", reservation_id=r.id)
    assert quota.read_quota(storage_db, "tenant-1")["reserved_bytes"] == 0
    assert quota.read_quota(storage_db, "tenant-2")["reserved_bytes"] == 0


def test_reconciliation_detects_drift_and_denies_further_writes(storage_db):
    quota.allocate(storage_db, tenant_id="tenant-1", quota_bytes=100, actor_id=None, reason="Contract")
    quota.reserve(storage_db, tenant_id="tenant-1", object_key="one/file.pdf",
                  size_bytes=20, idempotency_key="one")
    storage_db.commit()
    storage_db.get(TenantStorageQuota, "tenant-1").reserved_bytes = 5
    storage_db.commit()
    result = quota.reconcile(storage_db, tenant_id="tenant-1")
    assert result["drift"]
    with pytest.raises(ValueError, match="reconciliation required"):
        quota.reserve(storage_db, tenant_id="tenant-1", object_key="two.pdf",
                      size_bytes=1, idempotency_key="two")
    assert quota.reconcile(storage_db, tenant_id="tenant-1")["drift"]


def test_allocation_cannot_shrink_below_active_usage(storage_db):
    quota.allocate(storage_db, tenant_id="tenant-1", quota_bytes=100, actor_id=None, reason="Contract")
    quota.reserve(storage_db, tenant_id="tenant-1", object_key="a.pdf",
                  size_bytes=50, idempotency_key="a")
    with pytest.raises(ValueError, match="cannot fall below"):
        quota.allocate(storage_db, tenant_id="tenant-1", quota_bytes=49,
                       actor_id=None, reason="Downgrade")


def test_finalized_upload_replay_returns_receipt_without_rewriting_object(storage_db):
    from amodb.apps.platform import storage_quota_upload
    from fastapi import HTTPException

    quota.allocate(storage_db, tenant_id="tenant-1", quota_bytes=100,
                   actor_id=None, reason="Contract")
    reservation = quota.reserve(storage_db, tenant_id="tenant-1",
                                object_key="uploads/immutable.pdf",
                                size_bytes=5, idempotency_key="same-operation")
    digest = hashlib.sha256(b"first").hexdigest()
    quota.finalize(storage_db, tenant_id="tenant-1",
                   reservation_id=reservation.id,
                   storage_uri="s3://test/uploads/immutable.pdf",
                   checksum_sha256=digest)
    storage_db.commit()

    same_operation = quota.reserve(storage_db, tenant_id="tenant-1",
                                   object_key="uploads/immutable.pdf",
                                   size_bytes=5, idempotency_key="same-operation")
    retained = storage_quota_upload._finalized_replay(
        storage_db, same_operation, digest=digest,
    )
    assert retained.uri == "s3://test/uploads/immutable.pdf"
    assert retained.size_bytes == 5
    assert quota.read_quota(storage_db, "tenant-1")["used_bytes"] == 5

    # A retry with the same operation id but different bytes is not allowed
    # to overwrite the object already committed to the ledger.
    with pytest.raises(HTTPException) as exc:
        storage_quota_upload._finalized_replay(
            storage_db, same_operation, digest=hashlib.sha256(b"other").hexdigest(),
        )
    assert exc.value.status_code == 409
    assert quota.read_quota(storage_db, "tenant-1")["used_bytes"] == 5


def test_upload_paths_must_keep_physical_tenant_namespace_separate():
    from fastapi import HTTPException
    from amodb.apps.platform.storage_quota_upload import _tenant_scoped_key

    assert _tenant_scoped_key("tenant-1", "evidence/tenant-1/report.pdf") == "evidence/tenant-1/report.pdf"
    assert _tenant_scoped_key("tenant-1", "evidence//tenant-1/report.pdf") == "evidence/tenant-1/report.pdf"
    with pytest.raises(HTTPException) as exc:
        _tenant_scoped_key("tenant-1", "evidence/tenant-2/report.pdf")
    assert exc.value.status_code == 403
