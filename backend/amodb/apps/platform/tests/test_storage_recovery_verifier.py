"""Object storage recovery checks must reject remote drift and foreign receipts."""
from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

from amodb.apps.platform import storage_quota_models
from amodb.scripts import verify_tenant_object_recovery as verifier


def _receipt(uri="s3://managed/prefix/evidence/tenant-1/one.pdf", data=b"retained evidence"):
    return SimpleNamespace(
        id="object-a", object_key="evidence/tenant-1/one.pdf", storage_uri=uri,
        size_bytes=len(data), checksum_sha256=hashlib.sha256(data).hexdigest(),
    )


def test_physical_verifier_checks_managed_uri_before_remote_request(monkeypatch):
    monkeypatch.setattr(verifier.storage, "expected_s3_uri",
                        lambda key: "s3://managed/prefix/" + key)
    monkeypatch.setattr(verifier.storage, "retained_object_size",
                        lambda uri: pytest.fail("Foreign object must not be accessed"))
    with pytest.raises(ValueError, match="Receipt URI"):
        verifier.verify_retained_object(_receipt("s3://foreign/evidence/tenant-1/one.pdf"),
                                        restore_bytes=False)


def test_physical_verifier_detects_missing_bytes(monkeypatch):
    monkeypatch.setattr(verifier.storage, "expected_s3_uri",
                        lambda key: "s3://managed/prefix/" + key)
    monkeypatch.setattr(verifier.storage, "retained_object_size", lambda uri: 1)
    with pytest.raises(IOError, match="Physical object size"):
        verifier.verify_retained_object(_receipt(), restore_bytes=False)


def test_recovery_proof_forces_fresh_sha256_download(monkeypatch, tmp_path):
    content = b"retained evidence"
    remote = tmp_path / "fresh-node-copy"
    remote.write_bytes(content)
    flags = []
    monkeypatch.setattr(verifier.storage, "expected_s3_uri",
                        lambda key: "s3://managed/prefix/" + key)
    def recover(uri, *, expected_sha256, force_download):
        flags.append((expected_sha256, force_download))
        return remote
    monkeypatch.setattr(verifier.storage, "materialize", recover)
    verifier.verify_retained_object(_receipt(data=content), restore_bytes=True)
    assert flags == [(hashlib.sha256(content).hexdigest(), True)]
    remote.write_bytes(b"tampered content")
    with pytest.raises(IOError, match="Freshly restored content"):
        verifier.verify_retained_object(_receipt(data=content), restore_bytes=True)


def test_exact_five_decimal_tb_allocation():
    assert storage_quota_models.DEFAULT_PAID_QUOTA_BYTES == 5_000_000_000_000
