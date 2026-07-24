from types import SimpleNamespace
import zipfile

import pytest
from fastapi import HTTPException

from amodb.apps.quality import router
from amodb.apps.quality import audit_file_controls as controls
from amodb.apps.quality.schemas import QMSAuditOut


def _post_routes(path: str):
    return [
        route
        for route in router.routes
        if str(getattr(route, "path", "")) == path
        and "POST" in (getattr(route, "methods", None) or set())
    ]


def test_controlled_checklist_upload_route_replaces_legacy_handler_once():
    routes = _post_routes("/quality/audits/{audit_id}/checklist")
    assert len(routes) == 1
    assert getattr(routes[0], "response_model", None) is QMSAuditOut
    assert getattr(routes[0], "endpoint", None) is controls.upload_controlled_audit_checklist


def test_pdf_signature_validation_accepts_pdf_and_rejects_extension_spoof(tmp_path):
    valid_pdf = tmp_path / "checklist.pdf"
    valid_pdf.write_bytes(b"%PDF-1.7\n% test form\n")
    controls._validate_checklist_signature(valid_pdf, ".pdf")

    spoofed_pdf = tmp_path / "spoofed.pdf"
    spoofed_pdf.write_bytes(b"not a pdf")
    with pytest.raises(HTTPException) as exc_info:
        controls._validate_checklist_signature(spoofed_pdf, ".pdf")
    assert exc_info.value.status_code == 415


def test_docx_signature_validation_requires_a_word_package(tmp_path):
    valid_docx = tmp_path / "checklist.docx"
    with zipfile.ZipFile(valid_docx, "w") as package:
        package.writestr("[Content_Types].xml", "<Types />")
        package.writestr("word/document.xml", "<document />")
    controls._validate_checklist_signature(valid_docx, ".docx")

    generic_zip = tmp_path / "generic.docx"
    with zipfile.ZipFile(generic_zip, "w") as package:
        package.writestr("notes.txt", "not a Word document")
    with pytest.raises(HTTPException) as exc_info:
        controls._validate_checklist_signature(generic_zip, ".docx")
    assert exc_info.value.status_code == 415


def test_existing_checklist_cleanup_is_confined_to_approved_storage(monkeypatch, tmp_path):
    approved_root = tmp_path / "approved"
    approved_root.mkdir()
    approved_file = approved_root / "audit" / "checklist.pdf"
    approved_file.parent.mkdir()
    approved_file.write_bytes(b"%PDF-1.7")
    outside_file = tmp_path / "outside.pdf"
    outside_file.write_bytes(b"%PDF-1.7")

    monkeypatch.setattr(controls, "AUDIT_CHECKLIST_DIR", approved_root)
    assert controls._approved_existing_checklist_path(approved_file) == approved_file.resolve()
    assert controls._approved_existing_checklist_path(outside_file) is None


def test_checklist_editor_requires_quality_admin_or_assigned_audit_team(monkeypatch):
    audit = SimpleNamespace(
        lead_auditor_user_id="lead",
        observer_auditor_user_id="observer",
        assistant_auditor_user_id="assistant",
    )

    monkeypatch.setattr(controls, "_is_quality_admin", lambda user: bool(getattr(user, "is_amo_admin", False)))
    controls._require_checklist_editor(SimpleNamespace(id="admin", is_amo_admin=True), audit)
    controls._require_checklist_editor(SimpleNamespace(id="observer", is_amo_admin=False), audit)

    with pytest.raises(HTTPException) as exc_info:
        controls._require_checklist_editor(SimpleNamespace(id="unassigned", is_amo_admin=False), audit)
    assert exc_info.value.status_code == 403
    assert "assigned audit team" in str(exc_info.value.detail)
