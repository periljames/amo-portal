"""Real S3-compatible two-node storage acceptance (MinIO on CI).

Tests durable bytes, cross-node retrieval, checksum tampering and deletion.
"""
from __future__ import annotations

import hashlib
import os

import pytest


@pytest.mark.skipif(not os.getenv("STORAGE_MINIO_ACCEPTANCE"), reason="Requires real MinIO on CI")
def test_real_s3_two_node_upload_restore_integrity_and_delete(monkeypatch, tmp_path):
    import boto3
    from amodb import storage

    bucket = os.environ["AMO_STORAGE_S3_BUCKET"]
    client = boto3.client(
        "s3",
        endpoint_url=os.environ["AMO_STORAGE_S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("AMO_STORAGE_S3_REGION") or "us-east-1",
    )
    try:
        client.create_bucket(Bucket=bucket)
    except client.exceptions.BucketAlreadyOwnedByYou:
        pass

    content = b"retained quality audit source" * 10000
    source = tmp_path / "source.pdf"
    source.write_bytes(content)
    checksum = hashlib.sha256(content).hexdigest()
    monkeypatch.setenv("AMO_STORAGE_CACHE_DIR", str(tmp_path / "node-a"))
    stored = storage.put_file(
        source, key="tenant-A/quality/reports/verified.pdf", content_type="application/pdf",
    )
    assert stored.uri.startswith(f"s3://{bucket}/")
    assert stored.size_bytes == len(content)
    assert storage.exists(stored.uri)

    # A second API worker has a completely separate local disk/cache.
    monkeypatch.setenv("AMO_STORAGE_CACHE_DIR", str(tmp_path / "node-b"))
    restored = storage.materialize(stored.uri, expected_sha256=checksum)
    assert restored.read_bytes() == content
    assert restored != source
    assert restored.is_relative_to(tmp_path / "node-b")

    # Tampering with the backing object must never serve corrupted content.
    key = stored.uri.split(f"s3://{bucket}/", 1)[1]
    client.put_object(Bucket=bucket, Key=key, Body=b"tampered")
    monkeypatch.setenv("AMO_STORAGE_CACHE_DIR", str(tmp_path / "node-c"))
    with pytest.raises(IOError, match="checksum"):
        storage.materialize(stored.uri, expected_sha256=checksum)

    # Restore from original retained source and verify on a fresh worker.
    client.put_object(Bucket=bucket, Key=key, Body=content)
    monkeypatch.setenv("AMO_STORAGE_CACHE_DIR", str(tmp_path / "node-d"))
    assert storage.materialize(stored.uri, expected_sha256=checksum).read_bytes() == content
    storage.delete(stored.uri)
    assert not storage.exists(stored.uri)

def test_managed_s3_delete_never_touches_foreign_buckets_or_prefixes(monkeypatch, tmp_path):
    from amodb import storage

    monkeypatch.setenv("AMO_STORAGE_S3_BUCKET", "managed")
    monkeypatch.setenv("AMO_STORAGE_S3_PREFIX", "amo-portal")
    monkeypatch.setenv("AMO_STORAGE_CACHE_DIR", str(tmp_path))
    deleted = []

    class Client:
        def delete_object(self, *, Bucket, Key):
            deleted.append((Bucket, Key))

    monkeypatch.setattr(storage, "_client", lambda: Client())
    with pytest.raises(ValueError, match="outside"):
        storage.delete("s3://foreign/amo-portal/tenant/file.pdf")
    with pytest.raises(ValueError, match="outside"):
        storage.delete("s3://managed/unrelated/tenant/file.pdf")
    assert deleted == []
    storage.delete("s3://managed/amo-portal/tenant/file.pdf")
    assert deleted == [("managed", "amo-portal/tenant/file.pdf")]


