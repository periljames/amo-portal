"""S3 tenant quota and retained CAR evidence regression contracts.

These exercise the real storage adapter rather than relying on source-text
assertions. Neither public, staff nor control-loop attachments may bypass
quota reservations in a shared-storage deployment.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb import storage
from amodb.apps.quality import car_rca_storage
from amodb.apps.platform import storage_quota_upload, storage_quota_service


def test_car_evidence_upload_uses_exact_tenant_reservation(monkeypatch, tmp_path):
    car_id = uuid4()
    blob = tmp_path / "evidence.pdf"
    blob.write_bytes(b"approved-evidence")
    db = object()
    recorded = []

    monkeypatch.setattr(storage, "shared_storage_enabled", lambda: True)

    def write_quota(session, *, tenant_id, key, path, content_type):
        recorded.append((session, tenant_id, key, path, content_type))
        return SimpleNamespace(uri=f"s3://controlled/{key}")

    monkeypatch.setattr(storage_quota_upload, "put_local_file", write_quota)
    uri = car_rca_storage.store_car_file(
        blob, amo_id="tenant-A", car_id=car_id,
        content_type="application/pdf", db=db,
    )
    assert uri == f"s3://controlled/tenants/tenant-A/qms/cars/{car_id}/attachments/evidence.pdf"
    assert recorded == [(
        db, "tenant-A",
        f"tenants/tenant-A/qms/cars/{car_id}/attachments/evidence.pdf",
        blob, "application/pdf",
    )]


def test_shared_car_upload_without_quota_session_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "shared_storage_enabled", lambda: True)
    blob = tmp_path / "evidence.pdf"
    blob.write_bytes(b"not free")
    with pytest.raises(HTTPException) as failed:
        car_rca_storage.store_car_file(blob, amo_id="tenant-A", car_id=uuid4(), content_type=None)
    assert failed.value.status_code == 503


def test_car_quota_rejection_is_not_masked_as_storage_outage(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "shared_storage_enabled", lambda: True)
    blob = tmp_path / "evidence.pdf"
    blob.write_bytes(b"not free")
    def blocked(*args, **kwargs):
        raise HTTPException(status_code=413, detail="Tenant storage quota exceeded")
    monkeypatch.setattr(storage_quota_upload, "put_local_file", blocked)
    with pytest.raises(HTTPException) as failed:
        car_rca_storage.store_car_file(blob, amo_id="tenant-A", car_id=uuid4(), content_type=None, db=object())
    assert failed.value.status_code == 413


def test_s3_car_deletion_releases_bytes_after_physical_delete(monkeypatch):
    car_id = uuid4()
    amo_id = "tenant-A"
    key = f"tenants/{amo_id}/qms/cars/{car_id}/attachments/evidence.pdf"
    uri = f"s3://controlled/{key}"
    db = object()
    order = []
    monkeypatch.setattr(storage, "expected_s3_uri", lambda value: f"s3://controlled/{value}")
    monkeypatch.setattr(storage, "delete", lambda value: order.append(("physical", value)))
    monkeypatch.setattr(storage_quota_service, "recorded_delete",
                        lambda session, *, tenant_id, object_key: order.append(("ledger", session, tenant_id, object_key)))

    car_rca_storage.delete_unretained_car_file(uri, car_id=car_id, amo_id=amo_id, db=db)
    assert order == [("physical", uri), ("ledger", db, amo_id, key)]


def test_s3_car_deletion_rejects_cross_tenant_before_storage_access(monkeypatch):
    car_id = uuid4()
    key = f"tenants/tenant-B/qms/cars/{car_id}/attachments/evidence.pdf"
    monkeypatch.setattr(storage, "expected_s3_uri", lambda value: f"s3://controlled/{value}")
    monkeypatch.setattr(storage, "delete", lambda uri: pytest.fail("Cross-tenant evidence must never be touched"))
    with pytest.raises(HTTPException) as denied:
        car_rca_storage.delete_unretained_car_file(f"s3://controlled/{key}", car_id=car_id, amo_id="tenant-A", db=object())
    assert denied.value.status_code == 403


def test_failed_s3_deletion_does_not_refund_quota(monkeypatch):
    car_id = uuid4()
    key = f"tenants/tenant-A/qms/cars/{car_id}/attachments/evidence.pdf"
    monkeypatch.setattr(storage, "expected_s3_uri", lambda value: f"s3://controlled/{value}")
    def unavailable(uri):
        raise OSError("No storage service")
    monkeypatch.setattr(storage, "delete", unavailable)
    monkeypatch.setattr(storage_quota_service, "recorded_delete",
                        lambda *args, **kwargs: pytest.fail("Cannot refund unremoved bytes"))
    with pytest.raises(HTTPException) as failed:
        car_rca_storage.delete_unretained_car_file(f"s3://controlled/{key}", car_id=car_id, amo_id="tenant-A", db=object())
    assert failed.value.status_code == 503
