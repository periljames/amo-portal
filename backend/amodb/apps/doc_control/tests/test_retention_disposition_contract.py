from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "amodb" / "apps" / "doc_control"
MIGRATIONS = ROOT / "amodb" / "alembic" / "versions"
FRONTEND = ROOT.parent / "frontend" / "src" / "pages" / "documentControl"
SERVICES = ROOT.parent / "frontend" / "src" / "services"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_retention_ledger_is_tenant_document_source_and_approver_scoped() -> None:
    model = _text(APP / "retention_models.py")
    migration = _text(MIGRATIONS / "docctl_20260812_retention_disposition.py")
    approver_migration = _text(MIGRATIONS / "docctl_20260812_retention_approver.py")
    assert 'ForeignKey("amos.id"' in model
    assert 'ForeignKey("manuals.id"' in model
    assert 'ForeignKey("manual_revisions.id"' in model
    assert 'ForeignKey("document_evidence_assets.id"' in model
    assert "approver_user_id" in model
    assert "ix_document_retention_approver" in model
    assert "uq_document_retention_source" in model
    assert 'down_revision = "docctl_20260812_reminder_deliveries"' in migration
    assert 'down_revision = "docctl_20260812_retention_disposition"' in approver_migration
    assert 'sa.Column("approver_user_id"' in approver_migration


def test_retention_workflow_never_hard_deletes_controlled_history() -> None:
    source = _text(APP / "workspace_retention_router.py")
    assert "@router.delete(" not in source.lower()
    assert '"controlled_history_deleted": False' in source
    assert 'row.status = "DISPOSED"' in source
    assert "certificate_evidence_asset_id" in source
    assert "validate_evidence_references" in source


def test_accountability_override_precedes_base_retention_routes() -> None:
    router = _text(APP / "router.py")
    assert "workspace_retention_accountability_router" in router
    assert router.index("workspace_retention_accountability_router,") < router.index("workspace_retention_router,")


def test_legal_hold_clears_pending_disposition_authority() -> None:
    source = _text(APP / "workspace_retention_accountability_router.py")
    assert "require_decision_approver(current_user)" in source
    assert 'row.status = "HOLD"' in source
    assert "row.approver_user_id = None" in source
    assert "row.approved_by_user_id = None" in source
    assert 'if row.legal_hold or row.status == "HOLD":' in source


def test_disposition_request_requires_named_authorized_non_requester_approver() -> None:
    source = _text(APP / "workspace_retention_accountability_router.py")
    assert "class RetentionRequestWithApprover" in source
    assert "approver_user_id: str" in source
    assert "is_decision_approver(user)" in source
    assert "Disposition requester cannot be the assigned approver" in source
    assert "RETENTION_APPROVER_INVALID" in source
    assert "row.approver_user_id = approver.id" in source


def test_decision_is_bound_to_assigned_approver_and_separation_of_duties() -> None:
    source = _text(APP / "workspace_retention_accountability_router.py")
    assert "RETENTION_APPROVER_ASSIGNMENT_REQUIRED" in source
    assert "Only the assigned disposition approver may record this decision" in source
    assert "RETENTION_SEPARATION_OF_DUTIES_REQUIRED" in source
    base = _text(APP / "workspace_retention_router.py")
    assert 'if row.status != "APPROVED":' in base
    assert 'evidence=[{"asset_id": payload.certificate_evidence_asset_id}]' in base
    assert 'raise HTTPException(status_code=422, detail="Disposition certificate evidence is required")' in base


def test_retention_work_is_notified_and_attributed_only_to_named_users() -> None:
    source = _text(APP / "workspace_retention_accountability_router.py")
    assert 'kind="DOCUMENT_CONTROL_RETENTION"' in source
    assert 'event="REQUESTED"' in source
    assert 'event="APPROVED" if approved else "REJECTED"' in source
    assert "def retention_work(" in source
    assert '"RETENTION_APPROVAL" if approval else "RETENTION_EXECUTION"' in source
    assert "DocumentRetentionDisposition.approver_user_id == current_user.id" in source
    assert "DocumentRetentionDisposition.requested_by_user_id == current_user.id" in source
    assert '"limit": 100' in source


def test_retention_source_catalogue_prevents_raw_source_id_entry() -> None:
    source = _text(APP / "workspace_retention_sources_router.py")
    actions = _text(FRONTEND / "DocumentControlRetentionActions.tsx")
    client = _text(SERVICES / "documentControlRetention.ts")
    assert "def retention_sources(" in source
    assert "tenant.amo_id" in source
    assert "manual.id" in source
    assert '"per_type_limit": 500' in source
    assert "getDocumentRetentionSources" in actions
    assert "Generated controlled record" in actions
    assert "Only records returned by the tenant-scoped server catalogue can be selected" in actions
    assert "/retention-sources" in client


def test_frontend_exposes_retention_as_an_accountable_operating_workflow() -> None:
    actions = _text(FRONTEND / "DocumentControlRetentionActions.tsx")
    record_actions = _text(FRONTEND / "DocumentControlRecordActions.tsx")
    client = _text(SERVICES / "documentControlRetention.ts")
    assert "Govern retention" in actions
    assert "Place legal hold" in actions
    assert "Request disposition" in actions
    assert "Approve disposition" in actions
    assert "Record disposition with evidence" in actions
    assert "detail.capabilities.approve" in actions
    assert "listDocumentRetentionApprovers" in actions
    assert "Assigned disposition approver" in actions
    assert 'params.get("retention")' in actions
    assert "DISPOSITION_CERTIFICATE" in actions
    assert "DocumentControlRetentionActions" in record_actions
    assert 'title="Retention & disposition"' in record_actions
    assert "/retention-approvers" in client
    assert "approver_user_id: approverUserId" in client
    assert "/request-disposition" in client
    assert "/decision" in client
    assert "/dispose" in client


def test_retention_work_is_merged_into_document_control_home() -> None:
    service = _text(SERVICES / "documentControlHome.ts")
    page = _text(FRONTEND / "DocumentGovernanceDashboardPage.tsx")
    assert "listDocumentRetentionWork" in service
    assert '"RETENTION_APPROVAL"' in service
    assert '"RETENTION_EXECUTION"' in service
    assert "Retention approval" in page
    assert "Retention execution" in page
    assert "retention/disposition action attributable to you" in page
