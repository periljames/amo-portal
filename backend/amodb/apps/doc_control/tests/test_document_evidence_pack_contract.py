from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "amodb" / "apps" / "doc_control"
FRONTEND = ROOT.parent / "frontend" / "src" / "pages" / "documentControl"
SERVICES = ROOT.parent / "frontend" / "src" / "services"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_pack_is_registered_and_controller_governed() -> None:
    source = _text(APP / "workspace_evidence_pack_router.py")
    router = _text(APP / "router.py")
    assert 'evidence-pack.zip' in source
    assert 'require_control_user(current_user)' in source
    assert 'require_manual_access(current_user, profile)' in source
    assert 'workspace_evidence_pack_router' in router
    assert 'router.include_router(\n    workspace_evidence_pack_router' in router


def test_pack_contains_complete_operating_lifecycle_datasets() -> None:
    source = _text(APP / "workspace_evidence_pack_router.py")
    for dataset in (
        '"change_requests"',
        '"workflows"',
        '"authority_submissions"',
        '"temporary_revisions"',
        '"distribution_campaigns"',
        '"distribution_recipients"',
        '"acknowledgements"',
        '"controlled_copies"',
        '"controlled_copy_events"',
        '"periodic_reviews"',
        '"external_sources"',
        '"external_revision_receipts"',
        '"applicability"',
        '"integration_links"',
    ):
        assert dataset in source
    assert '"data/audit_history.json"' in source
    assert '"data/evidence_assets.json"' in source
    assert '"data/revisions.json"' in source


def test_pack_verifies_all_retained_file_hashes_and_never_silently_truncates() -> None:
    source = _text(APP / "workspace_evidence_pack_router.py")
    assert 'EVIDENCE_PACK_CHECKSUM_MISMATCH' in source
    assert 'EVIDENCE_PACK_FILE_MISSING' in source
    assert 'EVIDENCE_PACK_TOO_LARGE' in source
    assert 'EVIDENCE_PACK_TOO_MANY_ATTACHMENTS' in source
    assert 'EVIDENCE_PACK_DATASET_TOO_LARGE' in source
    assert 'MAX_PACK_FILE_BYTES' in source
    assert 'MAX_PACK_ATTACHMENTS' in source
    assert 'MAX_PACK_ROWS_PER_DATASET' in source
    assert 'hashlib.sha256(content).hexdigest()' in source


def test_pack_manifest_and_server_response_are_integrity_identifiable() -> None:
    source = _text(APP / "workspace_evidence_pack_router.py")
    assert 'amo-portal.document-control-evidence-pack.v1' in source
    assert '"manifest.json"' in source
    assert '"X-Evidence-Pack-SHA256"' in source
    assert '"X-Evidence-Pack-Attachments"' in source
    assert 'document.evidence_pack.generated' in source
    assert 'pack_sha256' in source
    assert '"Cache-Control": "private, no-store"' in source


def test_pack_csv_neutralizes_spreadsheet_formulas() -> None:
    source = _text(APP / "workspace_evidence_pack_router.py")
    assert 'text_value.lstrip().startswith(("=", "+", "-", "@"))' in source
    assert 'text_value = "\'" + text_value' in source


def test_document_overview_exposes_one_click_evidence_pack_output() -> None:
    actions = _text(FRONTEND / "DocumentEvidencePackAction.tsx")
    record_actions = _text(FRONTEND / "DocumentControlRecordActions.tsx")
    client = _text(SERVICES / "documentControlEvidence.ts")
    assert 'downloadDocumentEvidencePack' in client
    assert 'evidence-pack.zip' in client
    assert 'x-evidence-pack-sha256' in client
    assert 'Download complete document evidence pack' in actions
    assert 'Latest revision only' in actions
    assert 'ZIP SHA-256' in actions
    assert 'DocumentEvidencePackAction' in record_actions
    assert 'title="Audit evidence pack"' in record_actions
