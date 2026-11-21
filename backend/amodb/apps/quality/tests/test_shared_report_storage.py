"""Tenant-scoped generated QMS audit report storage read-back contracts."""
from __future__ import annotations

import hashlib
import pytest
from fastapi import HTTPException

from amodb.apps.quality import audit_report_composition as reports


def test_generated_report_from_shared_storage_is_checksum_verified(monkeypatch, tmp_path):
    data = b"%PDF-1.7\nretained generated audit report"
    path = tmp_path / "report.pdf"
    path.write_bytes(data)
    calls = []
    monkeypatch.setattr(reports.shared_storage, "materialize", lambda uri: calls.append(uri) or path)
    uri = "s3://managed/audits/tenant-a/report.pdf"
    result = reports.resolve_report_artifact(uri, expected_sha256=hashlib.sha256(data).hexdigest())
    assert result == path
    assert calls == [uri]


def test_generated_report_mismatched_checksum_never_served(monkeypatch, tmp_path):
    path = tmp_path / "cached-report.pdf"
    path.write_bytes(b"tampered")
    monkeypatch.setattr(reports.shared_storage, "materialize", lambda uri: path)
    with pytest.raises(HTTPException) as denied:
        reports.resolve_report_artifact(
            "s3://managed/audits/tenant-a/report.pdf",
            expected_sha256=hashlib.sha256(b"original").hexdigest(),
        )
    assert denied.value.status_code == 409


def test_generated_report_missing_remote_storage_fails_closed(monkeypatch):
    def unavailable(uri):
        raise FileNotFoundError("not present")
    monkeypatch.setattr(reports.shared_storage, "materialize", unavailable)
    with pytest.raises(HTTPException) as denied:
        reports.resolve_report_artifact("s3://managed/audits/tenant-a/report.pdf")
    assert denied.value.status_code == 404
