from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from amodb.apps.doc_control.workspace_evidence_router import (
    MAX_EVIDENCE_BYTES,
    _safe_filename,
    _validate_file_signature,
)


ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "amodb" / "apps" / "doc_control"
MIGRATIONS = ROOT / "amodb" / "alembic" / "versions"
FRONTEND = ROOT.parent / "frontend" / "src" / "pages" / "documentControl"
SERVICES = ROOT.parent / "frontend" / "src" / "services"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_evidence_model_and_migration_are_document_and_tenant_scoped() -> None:
    model = _text(APP / "evidence_models.py")
    migration = _text(MIGRATIONS / "docctl_20260812_evidence_assets.py")
    for token in (
        'tenant_id = Column(String(36), ForeignKey("amos.id"',
        'manual_id = Column(String(36), ForeignKey("manuals.id"',
        'revision_id = Column(String(36), ForeignKey("manual_revisions.id"',
        "sha256 = Column(String(64)",
        "storage_path = Column(Text",
        "uploaded_by_user_id",
    ):
        assert token in model
    assert 'down_revision = "docctl_ai_audit_260809"' in migration
    assert '"document_evidence_assets"' in migration
    assert 'ondelete="CASCADE"' in migration
    assert 'ondelete="SET NULL"' in migration


def test_evidence_routes_are_immutable_bounded_and_checksum_verified() -> None:
    source = _text(APP / "workspace_evidence_router.py")
    router = _text(APP / "router.py")
    assert MAX_EVIDENCE_BYTES == 25 * 1024 * 1024
    assert 'limit(200)' in source
    assert '"Cache-Control": "private, no-store"' in source
    assert 'hashlib.sha256(path.read_bytes()).hexdigest() != row.sha256' in source
    assert 'CONTROLLED_EVIDENCE_CHECKSUM_MISMATCH' in source
    assert '@router.delete(' not in source.lower()
    assert "workspace_evidence_router" in router
    assert "workspace_copy_evidence_router" in router


def test_browser_evidence_references_are_bound_to_same_tenant_and_document() -> None:
    source = _text(APP / "workspace_evidence_router.py")
    assert 'em.DocumentEvidenceAsset.tenant_id == tenant_id' in source
    assert 'em.DocumentEvidenceAsset.manual_id == manual_id' in source
    assert 'CONTROLLED_EVIDENCE_ASSET_REQUIRED' in source
    assert 'CONTROLLED_EVIDENCE_ASSET_INVALID' in source
    assert 'Browser clients may only submit ``asset_id`` references' in source


def test_assigned_reviewer_upload_is_narrower_than_controller_upload() -> None:
    source = _text(APP / "workspace_evidence_router.py")
    assert 'if is_control_user(user):' in source
    assert 'if category != "REVIEW" or not revision_id:' in source
    assert 'workflow_actions_for_user' in source
    assert '_REVIEW_UPLOAD_ACTIONS' in source


def test_workflow_authority_copy_and_external_routes_normalize_evidence_server_side() -> None:
    workflow = _text(APP / "workspace_workflow_review_router.py")
    authority = _text(APP / "workspace_authority_router.py")
    copy_guard = _text(APP / "workspace_copy_evidence_router.py")
    external = _text(APP / "workspace_external_router.py")
    assert 'validate_evidence_references' in workflow
    assert '_server_revision_evidence' in workflow
    assert 'CONTROLLED_REVISION_SOURCE' in workflow
    assert 'WAIVER_EVIDENCE_REQUIRED' in workflow
    assert 'validate_evidence_references' in authority
    assert '_merge_asset_evidence' in authority
    assert 'validate_evidence_references' in copy_guard
    assert 'validate_evidence_references' in external
    assert 'manual_id=source.manual_id' in external


def test_file_signature_allowlist_rejects_disguised_uploads() -> None:
    assert _validate_file_signature("proof.pdf", b"%PDF-1.7\n") == "application/pdf"
    assert _validate_file_signature("photo.png", b"\x89PNG\r\n\x1a\nrest") == "image/png"
    assert _safe_filename("../../audit/<approval>.pdf") == "_approval_.pdf"
    with pytest.raises(HTTPException) as bad_pdf:
        _validate_file_signature("proof.pdf", b"not really a pdf")
    assert bad_pdf.value.status_code == 422
    with pytest.raises(HTTPException) as unsupported:
        _validate_file_signature("malware.exe", b"MZ")
    assert unsupported.value.status_code == 415


def test_frontend_uses_picker_in_active_decision_and_external_source_surfaces() -> None:
    picker = _text(FRONTEND / "DocumentEvidencePicker.tsx")
    guarded = _text(FRONTEND / "DocumentControlLifecycleActionsGuarded.tsx")
    approver = _text(FRONTEND / "DocumentControlApproverLifecycleActions.tsx")
    reviewer = _text(FRONTEND / "DocumentControlReviewerLifecycleActions.tsx")
    external = _text(FRONTEND / "DocumentControlExternalSourceActions.tsx")
    record_actions = _text(FRONTEND / "DocumentControlRecordActions.tsx")
    client = _text(SERVICES / "documentControlEvidence.ts")
    assert "uploadDocumentEvidenceAsset" in picker
    assert "SHA-256" in picker
    assert "DocumentControlApproverLifecycleActions" in guarded
    assert 'props.activeView === "workflow" || props.activeView === "authority"' in guarded
    assert "DocumentEvidencePicker" in approver
    assert "DocumentEvidencePicker" in reviewer
    assert "Evidence asset IDs" not in approver
    assert "evidence-assets" in client
    assert "createExternalRevisionReceipt" in external
    assert "DocumentEvidencePicker" in external
    assert "checksum_sha256: primary?.sha256 || null" in external
    assert 'applicability_status: "PENDING"' in external
    assert "DocumentControlExternalSourceActions" in record_actions
    assert 'activeView="external"' not in record_actions
