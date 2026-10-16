from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from amodb.apps.doc_control import knowledge_artifact_transactions as custody
from amodb.apps.doc_control import knowledge_records_router as records


def test_rolled_back_generated_record_deletes_retained_s3_artifact(monkeypatch):
    from amodb import storage as shared_storage
    session = SimpleNamespace(info={})
    calls = []
    monkeypatch.setattr(shared_storage, "delete", lambda uri: calls.append(uri))
    uri = "s3://retained-assets/documentation-generated-records/tenant/record.pdf"
    custody._track_pending_artifact(session, uri)
    assert uri in session.info[custody._PENDING_ARTIFACTS_KEY]
    custody._cleanup_pending_artifacts(session)
    assert calls == [uri]
    assert custody._PENDING_ARTIFACTS_KEY not in session.info


def test_retained_documentation_integrity_verified_on_another_worker(monkeypatch, tmp_path):
    from amodb import storage as shared_storage
    content = b"%PDF-1.7\nretained documentation record"
    expected = hashlib.sha256(content).hexdigest()
    path = tmp_path / "worker-b-record.pdf"
    path.write_bytes(content)
    seen = []
    monkeypatch.setattr(shared_storage, "materialize",
        lambda uri, *, expected_sha256=None: seen.append((uri, expected_sha256)) or path)
    row = SimpleNamespace(artifact_storage_path="s3://remote/documentation/record.pdf",
                          artifact_sha256=expected)
    integrity = records._integrity(row)
    assert integrity["status"] == "VERIFIED"
    assert integrity["size_bytes"] == len(content)
    assert seen == [(row.artifact_storage_path, expected)]


def test_mismatched_object_is_not_reported_as_verified(monkeypatch, tmp_path):
    from amodb import storage as shared_storage
    expected = hashlib.sha256(b"intact source").hexdigest()
    def tampered(*args, **kwargs):
        raise IOError("Checksum mismatch")
    monkeypatch.setattr(shared_storage, "materialize", tampered)
    row = SimpleNamespace(artifact_storage_path="s3://remote/documentation/record.pdf",
                          artifact_sha256=expected)
    result = records._integrity(row)
    assert result["status"] == "MISMATCH"
