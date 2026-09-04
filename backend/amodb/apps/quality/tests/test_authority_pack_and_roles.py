from __future__ import annotations

import hashlib
import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.quality import audit_authority_pack as authority_pack
from amodb.apps.quality.audit_authority_pack import build_authority_pack_zip
from amodb.apps.quality.audit_external_access_router import AUDITEE_ALLOWED
from amodb.apps.quality.router import _require_audit_fieldwork_write_access
from amodb.apps.quality.tenant_security import _QUALITY_ROLE_PERMISSIONS, _has_role_permission


def _user(role: str, user_id: str = "user-1"):
    return SimpleNamespace(
        id=user_id,
        role=role,
        amo_id="amo-1",
        is_active=True,
        is_superuser=False,
        is_platform_context=False,
        is_amo_admin=role == "AMO_ADMIN",
    )


def test_assigned_auditor_can_execute_but_unassigned_auditor_cannot() -> None:
    assigned = _user("AUDITOR", "lead-1")
    audit = SimpleNamespace(
        lead_auditor_user_id="lead-1",
        observer_auditor_user_id="observer-1",
        assistant_auditor_user_id="assistant-1",
    )
    assert _has_role_permission(assigned, "qms.audit.execute") is True
    assert _has_role_permission(assigned, "qms.audit.manage") is False
    _require_audit_fieldwork_write_access(assigned, audit)

    with pytest.raises(HTTPException) as exc:
        _require_audit_fieldwork_write_access(_user("AUDITOR", "other-1"), audit)
    assert exc.value.status_code == 403


def test_quality_officer_can_manage_car_follow_up_but_not_govern_or_close() -> None:
    officer = _user("QUALITY_OFFICER")
    assert _has_role_permission(officer, "qms.audit.execute") is True
    assert _has_role_permission(officer, "qms.audit.manage") is False
    assert _has_role_permission(officer, "qms.audit.notice.manage") is True
    assert _has_role_permission(officer, "qms.car.manage") is True
    assert _has_role_permission(officer, "qms.car.close") is False
    assert _has_role_permission(officer, "qms.reports.view") is True
    assert _has_role_permission(officer, "qms.training.manage") is False


def test_authority_attestation_is_accountable_executive_only() -> None:
    assert _has_role_permission(_user("ACCOUNTABLE_EXECUTIVE"), "qms.reports.attest_authority") is True
    assert _has_role_permission(_user("ACCOUNTABLE_EXECUTIVE"), "qms.reports.export") is True
    assert _has_role_permission(_user("ACCOUNTABLE_EXECUTIVE"), "qms.external.view") is True
    assert _has_role_permission(_user("ACCOUNTABLE_EXECUTIVE"), "qms.audit.manage") is False
    assert _has_role_permission(_user("QUALITY_MANAGER"), "qms.reports.attest_authority") is False
    assert _has_role_permission(_user("AMO_ADMIN"), "qms.reports.attest_authority") is False
    assert _has_role_permission(_user("QUALITY_MANAGER"), "qms.audit.notice.manage") is True
    assert _has_role_permission(_user("AMO_ADMIN"), "qms.audit.notice.manage") is True


def test_guest_allowlist_has_no_tenant_quality_capability() -> None:
    assert not any(permission.startswith("qms.") for permission in AUDITEE_ALLOWED)


class _Query:
    def __init__(self, value):
        self.value = value

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def with_for_update(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.value


class _PackDb:
    def __init__(self, values):
        self.values = iter(values)
        self.added = []

    def query(self, *_args, **_kwargs):
        return _Query(next(self.values))

    def add(self, value):
        self.added.append(value)

    def flush(self):
        return None


def _pack_rows(report_path: Path, *, attestation):
    audit_id = uuid.uuid4()
    report_bytes = report_path.read_bytes()
    report = SimpleNamespace(
        id="revision-1",
        amo_id="amo-1",
        audit_id=audit_id,
        revision_no=4,
        status="ISSUED",
        file_ref=str(report_path),
        filename="issued.pdf",
        sha256=hashlib.sha256(report_bytes).hexdigest(),
    )
    audit = SimpleNamespace(id=audit_id, audit_ref="QAR-AMO-004", deleted_at=None)
    signature = SimpleNamespace(ceremony_sha256="c" * 64, signed_at=datetime.now(timezone.utc))
    actor = SimpleNamespace(full_name="Accountable Executive", email="ae@example.test")
    return audit_id, report, [audit, report, attestation, None, signature, ("token-1",), actor]


def test_authority_pack_fails_closed_without_attestation(tmp_path: Path, monkeypatch) -> None:
    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir()
    report_path = legacy_root / "issued.pdf"
    report_path.write_bytes(b"%PDF-1.4\nissued report\n%%EOF")
    monkeypatch.setattr(authority_pack, "AUDIT_REPORT_DIR", legacy_root)
    monkeypatch.setattr("amodb.apps.quality.audit_report_composition._STORAGE_ROOT", tmp_path / "generated")
    audit_id, _report, values = _pack_rows(report_path, attestation=None)

    with pytest.raises(HTTPException) as exc:
        build_authority_pack_zip(_PackDb(values[:3]), "amo-1", audit_id, "ae-1")
    assert exc.value.status_code == 409
    assert "attestation" in str(exc.value.detail).lower()


def test_authority_pack_records_zip_hash_and_manifest(tmp_path: Path, monkeypatch) -> None:
    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir()
    report_path = legacy_root / "issued.pdf"
    report_path.write_bytes(b"%PDF-1.4\nissued report\n%%EOF")
    monkeypatch.setattr(authority_pack, "AUDIT_REPORT_DIR", legacy_root)
    generated_root = tmp_path / "generated"
    monkeypatch.setattr("amodb.apps.quality.audit_report_composition._STORAGE_ROOT", generated_root)
    attestation = SimpleNamespace(
        id="attestation-1",
        report_revision_id="revision-1",
        report_sha256=hashlib.sha256(report_path.read_bytes()).hexdigest(),
        rationale="Approved for Authority submission.",
        attested_by_user_id="ae-1",
        attested_at=datetime.now(timezone.utc),
        pack_filename=None,
        pack_content_type=None,
        pack_size_bytes=None,
        pack_sha256=None,
        pack_storage_ref=None,
        superseded_at=None,
    )
    audit_id, report, values = _pack_rows(report_path, attestation=attestation)
    attestation.report_sha256 = report.sha256

    result = build_authority_pack_zip(_PackDb(values), "amo-1", audit_id, "ae-1")
    pack_path = generated_root / result.pack_storage_ref
    assert result.pack_sha256 == hashlib.sha256(pack_path.read_bytes()).hexdigest()
    assert result.pack_content_type == "application/zip"
    with zipfile.ZipFile(pack_path) as archive:
        assert f"issued-report-r{report.revision_no}.pdf" in archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["audit_ref"] == "QAR-AMO-004"
    assert manifest["report_sha256"] == report.sha256
    assert manifest["verification_path_template"] == "/verify/{token}"
    assert manifest["attested_by"] == "Accountable Executive"


def test_permission_catalogue_contains_no_invented_authority_or_customer_role() -> None:
    assert "QUALITY_OFFICER" in _QUALITY_ROLE_PERMISSIONS
    assert not ({"AUTHORITY", "KCAA", "GCAA", "CUSTOMER", "SUPPLIER"} & set(_QUALITY_ROLE_PERMISSIONS))
