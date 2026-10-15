from __future__ import annotations

import hashlib
import importlib

import pytest
from fastapi import HTTPException

vault = importlib.import_module("amodb.apps.doc_control.workspace_records_vault_router")


def test_retained_object_can_be_materialized_from_a_second_worker(monkeypatch, tmp_path):
    bytes_value = b"regulatory-maintenance-record"
    replicated_file = tmp_path / "record.pdf"
    replicated_file.write_bytes(bytes_value)
    calls = []
    monkeypatch.setattr(
        vault.shared_storage,
        "materialize",
        lambda uri: calls.append(uri) or replicated_file,
    )
    uri = "s3://retained-vault/document-record-vault/tenant-01/record.pdf"
    resolved = vault._materialize_record_file(
        uri, expected_sha256=hashlib.sha256(bytes_value).hexdigest(),
    )
    assert resolved.read_bytes() == bytes_value
    assert calls == [uri]


def test_tampered_retained_object_is_blocked(monkeypatch, tmp_path):
    altered = tmp_path / "altered.pdf"
    altered.write_bytes(b"modified")
    monkeypatch.setattr(vault.shared_storage, "materialize", lambda _: altered)
    with pytest.raises(HTTPException) as error:
        vault._materialize_record_file(
            "s3://retained-vault/record.pdf",
            expected_sha256=hashlib.sha256(b"original").hexdigest(),
        )
    assert error.value.status_code == 409
