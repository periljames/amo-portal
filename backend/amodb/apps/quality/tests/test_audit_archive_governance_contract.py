from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest
from pydantic import ValidationError

import amodb.apps.quality.audit_archive_package_router as package_router
from amodb.apps.quality.audit_archive_governance_router import RetentionPolicyCreate, _canonical_hash
from amodb.apps.quality.audit_archive_package_router import _render_package


def test_retention_duration_is_explicit_policy_not_application_default() -> None:
    with pytest.raises(ValidationError):
        RetentionPolicyCreate(
            retention_class="AUDIT_STANDARD",
            retention_start_event="FOLLOW_UP_COMPLETE",
            duration_days=None,
            indefinite=False,
            governing_basis="Approved organisational record retention schedule.",
            disposition_mode="PRESERVE_METADATA_DELETE_PACKAGE",
        )

    finite = RetentionPolicyCreate(
        retention_class="AUDIT_STANDARD",
        retention_start_event="FOLLOW_UP_COMPLETE",
        duration_days=2555,
        indefinite=False,
        governing_basis="Approved organisational record retention schedule revision 7.",
        disposition_mode="PRESERVE_METADATA_DELETE_PACKAGE",
    )
    assert finite.duration_days == 2555

    indefinite = RetentionPolicyCreate(
        retention_class="AUDIT_PERMANENT",
        retention_start_event="EXECUTION_CLOSED",
        duration_days=None,
        indefinite=True,
        governing_basis="Approved permanent-retention decision for this record class.",
        disposition_mode="NO_DISPOSITION",
    )
    assert indefinite.indefinite is True


def test_indefinite_policy_cannot_enable_disposition() -> None:
    with pytest.raises(ValidationError):
        RetentionPolicyCreate(
            retention_class="AUDIT_PERMANENT",
            retention_start_event="FOLLOW_UP_COMPLETE",
            indefinite=True,
            governing_basis="Approved permanent-retention decision for this record class.",
            disposition_mode="TRANSFER_PACKAGE",
        )


def test_archive_package_is_deterministic_and_contains_required_indexes(tmp_path: Path, monkeypatch) -> None:
    evidence_content = b"governed fieldwork evidence\n"
    evidence_file = tmp_path / "evidence.txt"
    evidence_file.write_bytes(evidence_content)
    evidence_sha = hashlib.sha256(evidence_content).hexdigest()
    monkeypatch.setattr(package_router, "resolve_audit_evidence", lambda _ref: evidence_file)

    inventory = [
        {
            "item_type": "AUDIT",
            "authoritative_record_id": "audit-1",
            "revision_ref": None,
            "source_system": "QUALITY",
            "content_hash": "a" * 64,
            "retention_role": "AUDIT_IDENTITY_SCOPE_CRITERIA",
            "metadata": {"scope": "Approved scope", "criteria": "Approved criteria"},
        },
        {
            "item_type": "REPORT_REVISION",
            "authoritative_record_id": "report-1",
            "revision_ref": "1",
            "source_system": "QUALITY_REPORT_GOVERNANCE",
            "content_hash": "b" * 64,
            "retention_role": "AUDIT_REPORT_HISTORY",
            "metadata": {"status": "ISSUED"},
        },
        {
            "item_type": "EVIDENCE_ARTIFACT",
            "authoritative_record_id": "evidence-1",
            "revision_ref": None,
            "source_system": "QUALITY_AUDIT_EVIDENCE",
            "content_hash": evidence_sha,
            "retention_role": "FIELDWORK_EVIDENCE",
            "metadata": {
                "file_ref": "tenant-1/audit-1/item-1/evidence.txt",
                "filename": "evidence.txt",
                "content_type": "text/plain",
                "size_bytes": len(evidence_content),
            },
        },
    ]
    manifest = {
        "manifest_id": "manifest-1",
        "tenant_id": "tenant-1",
        "audit_id": "audit-1",
        "audit_ref": "QAR-MO-26-021",
        "manifest_version": 1,
        "items": inventory,
    }
    manifest_sha = _canonical_hash(manifest)
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    first_size, first_sha = _render_package(first, manifest_payload=manifest, manifest_sha256=manifest_sha, inventory=inventory, timeline=[])
    second_size, second_sha = _render_package(second, manifest_payload=manifest, manifest_sha256=manifest_sha, inventory=inventory, timeline=[])

    assert first_size == second_size
    assert first_sha == second_sha
    with zipfile.ZipFile(first) as archive:
        names = set(archive.namelist())
        assert {
            "manifest.json",
            "scope-criteria.json",
            "preparation/index.json",
            "checklist/index.json",
            "evidence/index.json",
            "evidence/files/evidence-1/evidence.txt",
            "findings/index.json",
            "report/index.json",
            "signatures/index.json",
            "closing-meeting/index.json",
            "cars/index.json",
            "timeline.json",
        } <= names
        assert archive.read("evidence/files/evidence-1/evidence.txt") == evidence_content


def test_archive_package_rejects_evidence_hash_mismatch(tmp_path: Path, monkeypatch) -> None:
    evidence_file = tmp_path / "evidence.txt"
    evidence_file.write_bytes(b"changed evidence")
    monkeypatch.setattr(package_router, "resolve_audit_evidence", lambda _ref: evidence_file)
    inventory = [
        {
            "item_type": "EVIDENCE_ARTIFACT",
            "authoritative_record_id": "evidence-1",
            "revision_ref": None,
            "source_system": "QUALITY_AUDIT_EVIDENCE",
            "content_hash": "0" * 64,
            "retention_role": "FIELDWORK_EVIDENCE",
            "metadata": {
                "file_ref": "tenant-1/audit-1/item-1/evidence.txt",
                "filename": "evidence.txt",
                "size_bytes": evidence_file.stat().st_size,
            },
        }
    ]
    manifest = {"manifest_id": "manifest-1", "items": inventory}
    with pytest.raises(Exception) as exc:
        _render_package(
            tmp_path / "bad.zip",
            manifest_payload=manifest,
            manifest_sha256=_canonical_hash(manifest),
            inventory=inventory,
            timeline=[],
        )
    assert "SHA-256" in str(exc.value)
