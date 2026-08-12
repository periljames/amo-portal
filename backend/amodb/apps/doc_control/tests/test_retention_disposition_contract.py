from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "amodb" / "apps" / "doc_control"
MIGRATIONS = ROOT / "amodb" / "alembic" / "versions"
FRONTEND = ROOT.parent / "frontend" / "src" / "pages" / "documentControl"
SERVICES = ROOT.parent / "frontend" / "src" / "services"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_retention_ledger_is_tenant_document_and_source_scoped() -> None:
    model = _text(APP / "retention_models.py")
    migration = _text(MIGRATIONS / "docctl_20260812_retention_disposition.py")
    assert 'ForeignKey("amos.id"' in model
    assert 'ForeignKey("manuals.id"' in model
    assert 'ForeignKey("manual_revisions.id"' in model
    assert 'ForeignKey("document_evidence_assets.id"' in model
    assert "uq_document_retention_source" in model
    assert 'down_revision = "docctl_20260812_reminder_deliveries"' in migration
    assert '"document_retention_dispositions"' in migration


def test_retention_workflow_never_hard_deletes_controlled_history() -> None:
    source = _text(APP / "workspace_retention_router.py")
    assert "@router.delete(" not in source.lower()
    assert '"controlled_history_deleted": False' in source
    assert 'row.status = "DISPOSED"' in source
    assert "certificate_evidence_asset_id" in source
    assert "validate_evidence_references" in source


def test_legal_hold_blocks_or_cancels_disposition_progression() -> None:
    source = _text(APP / "workspace_retention_router.py")
    assert 'if payload.legal_hold:' in source
    assert 'row.status = "HOLD"' in source
    assert 'row.approved_by_user_id = None' in source
    assert 'if row.legal_hold or row.status == "HOLD":' in source
    assert 'raise HTTPException(status_code=409, detail="Disposition is blocked by legal hold")' in source


def test_disposition_requires_independent_approval_and_certificate_evidence() -> None:
    source = _text(APP / "workspace_retention_router.py")
    assert "require_decision_approver(current_user)" in source
    assert "RETENTION_SEPARATION_OF_DUTIES_REQUIRED" in source
    assert 'if row.status != "APPROVED":' in source
    assert 'evidence=[{"asset_id": payload.certificate_evidence_asset_id}]' in source
    assert 'raise HTTPException(status_code=422, detail="Disposition certificate evidence is required")' in source


def test_sources_are_governed_without_raw_document_or_evidence_ids() -> None:
    source = _text(APP / "workspace_retention_router.py")
    assert 'if payload.source_type == "DOCUMENT":' in source
    assert 'if payload.source_type == "REVISION":' in source
    assert 'if payload.source_type == "EVIDENCE_ASSET":' in source
    assert 'if generated_model is None:' in source
    assert "generated_model.tenant_id == tenant.amo_id" in source
    assert "generated_model.manual_id == manual.id" in source


def test_frontend_exposes_retention_as_an_operating_workflow() -> None:
    actions = _text(FRONTEND / "DocumentControlRetentionActions.tsx")
    record_actions = _text(FRONTEND / "DocumentControlRecordActions.tsx")
    client = _text(SERVICES / "documentControlRetention.ts")
    assert "Govern retention" in actions
    assert "Place legal hold" in actions
    assert "Request disposition" in actions
    assert "Approve disposition" in actions
    assert "Record disposition with evidence" in actions
    assert "detail.capabilities.approve" in actions
    assert "DISPOSITION_CERTIFICATE" in actions
    assert "DocumentControlRetentionActions" in record_actions
    assert 'title="Retention & disposition"' in record_actions
    assert "/request-disposition" in client
    assert "/decision" in client
    assert "/dispose" in client
