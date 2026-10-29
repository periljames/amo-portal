from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import UploadFile

from amodb.apps.quality import audit_evidence_storage, audit_guest_document_storage


@pytest.mark.asyncio
@pytest.mark.parametrize("module,store,resolve,kwargs,content", [
    (audit_evidence_storage, audit_evidence_storage.store_audit_evidence,
     audit_evidence_storage.resolve_audit_evidence,
     {"amo_id": "tenant-a", "audit_id": "audit-1", "checklist_item_id": "item-1"},
     b"%PDF-1.7\nproof"),
    (audit_guest_document_storage, audit_guest_document_storage.store_guest_document,
     audit_guest_document_storage.resolve_guest_document,
     {"amo_id": "tenant-a", "audit_id": "audit-1", "request_id": "request-1"},
     b"%PDF-1.7\nguest"),
])
async def test_new_quality_evidence_is_shared_and_readable_on_another_worker(
    monkeypatch, tmp_path: Path, module, store, resolve, kwargs, content,
):
    monkeypatch.setattr(module.shared_storage, "shared_storage_enabled", lambda: True)
    monkeypatch.setattr(module.shared_storage, "cache_root", lambda: tmp_path)
    uploaded: dict[str, object] = {}
    from unittest.mock import MagicMock

    def put_file(source, *, key: str, content_type: str | None = None):
        assert Path(source).read_bytes() == content
        assert "tenant-a" in key
        uploaded["key"] = key
        return SimpleNamespace(uri="s3://test-bucket/" + key, size_bytes=len(content))

    from amodb.apps.platform import storage_quota_upload
    monkeypatch.setattr(storage_quota_upload, "put_local_file", lambda db, *, tenant_id, actor_id, path, key, content_type: put_file(path, key=key, content_type=content_type))
    saved = await store(
        UploadFile(io.BytesIO(content), filename="evidence.pdf", headers=None),
        db=MagicMock(),
        **kwargs,
    )
    assert saved.storage_ref == "s3://test-bucket/" + str(uploaded["key"])
    assert saved.size_bytes == len(content)
    assert not list(tmp_path.rglob("*.pdf")), "Temporary upload must not survive S3 transfer"

    replicated = tmp_path / "replica.pdf"
    replicated.write_bytes(content)
    monkeypatch.setattr(module.shared_storage, "materialize", lambda uri: replicated)
    assert resolve(saved.storage_ref).read_bytes() == content
