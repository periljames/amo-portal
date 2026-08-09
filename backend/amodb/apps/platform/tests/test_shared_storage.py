from __future__ import annotations

import io
import os
import time
from pathlib import Path

import pytest

from amodb import storage


def test_local_backend_round_trip_and_delete(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AMO_STORAGE_BACKEND", "local")
    monkeypatch.setenv("AMO_STORAGE_LOCAL_ROOT", str(tmp_path / "uploads"))
    monkeypatch.setenv("AMO_STORAGE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("AMO_REQUIRE_SHARED_STORAGE", raising=False)

    stored = storage.put_stream(io.BytesIO(b"aviation-control-plane"), key="tenant-a/docs/test.txt", content_type="text/plain")
    assert stored.backend == "local"
    assert stored.key == "tenant-a/docs/test.txt"
    assert stored.size_bytes == len(b"aviation-control-plane")
    assert storage.exists(stored.uri)
    assert storage.materialize(stored.uri).read_bytes() == b"aviation-control-plane"

    storage.delete(stored.uri)
    assert not storage.exists(stored.uri)


def test_horizontal_mode_rejects_local_storage(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AMO_STORAGE_BACKEND", "local")
    monkeypatch.setenv("AMO_STORAGE_LOCAL_ROOT", str(tmp_path / "uploads"))
    monkeypatch.setenv("AMO_REQUIRE_SHARED_STORAGE", "true")
    with pytest.raises(RuntimeError, match="requires AMO_STORAGE_BACKEND=s3"):
        storage.validate_storage_configuration()


def test_s3_mode_requires_bucket(monkeypatch):
    monkeypatch.setenv("AMO_STORAGE_BACKEND", "s3")
    monkeypatch.delenv("AMO_STORAGE_S3_BUCKET", raising=False)
    with pytest.raises(RuntimeError, match="AMO_STORAGE_S3_BUCKET"):
        storage.validate_storage_configuration()


def test_keys_are_normalised_without_path_traversal():
    assert storage.normalise_key("tenant/../unsafe/../../document.pdf") == "tenant/unsafe/document.pdf"
    assert storage.normalise_key("tenant\\folder\\document.pdf") == "tenant/folder/document.pdf"


def test_ephemeral_cache_prunes_old_entries(monkeypatch, tmp_path: Path):
    root = tmp_path / "cache"
    root.mkdir()
    monkeypatch.setenv("AMO_STORAGE_CACHE_DIR", str(root))
    monkeypatch.setenv("AMO_STORAGE_CACHE_MAX_BYTES", str(64 * 1024 * 1024))
    monkeypatch.setenv("AMO_STORAGE_CACHE_MAX_AGE_SEC", "300")

    stale = root / "stale.pdf"
    fresh = root / "fresh.pdf"
    staged = root / "amo-upload-active"
    stale.write_bytes(b"old")
    fresh.write_bytes(b"new")
    staged.write_bytes(b"in-flight")
    old = time.time() - 600
    os.utime(stale, (old, old))

    storage.cleanup_cache(force=True)
    assert not stale.exists()
    assert fresh.exists()
    assert staged.exists(), "active upload staging files must never be evicted"
