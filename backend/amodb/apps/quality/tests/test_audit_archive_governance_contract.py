from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from pydantic import ValidationError

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


def test_archive_package_is_deterministic_and_contains_required_indexes(tmp_path: Path) -> None:
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
            "findings/index.json",
            "report/index.json",
            "signatures/index.json",
            "closing-meeting/index.json",
            "cars/index.json",
            "timeline.json",
        } <= names
