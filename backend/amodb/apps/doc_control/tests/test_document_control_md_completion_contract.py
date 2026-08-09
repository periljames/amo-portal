from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_library_discovery_is_permission_filtered_and_bounded() -> None:
    source = _source("workspace_library_discovery_router.py")
    assert 'pattern="^(all|my-documents|favorites|recently-opened|recently-revised|awaiting-my-review|external-technical-data|due-for-review|superseded|archived)$"' in source
    assert "per_page: int = Query(default=50, ge=1, le=100)" in source
    assert "if not controller:" in source
    assert "_scope_match" in source
    assert "ManualReaderProgress" in source
    assert "ManualBlock.text_plain.ilike" in source
    assert "DocumentationNode.metadata_json" in source
    assert ".offset((page - 1) * per_page).limit(per_page)" in source


def test_reports_catalogue_stays_controller_only_and_server_bounded() -> None:
    source = _source("workspace_reports_register_router.py")
    assert "require_control_user(current_user)" in source
    assert "per_page: int = Query(default=50, ge=1, le=100)" in source
    assert "_paginate(query, page, per_page)" in source
    for view in (
        "revisions",
        "lep",
        "distribution",
        "acknowledgements",
        "controlled-copies",
        "external-sources",
        "review-due",
        "temporary-revisions",
        "authority",
        "archive",
        "change-history",
        "retention",
    ):
        assert f'"{view}"' in source


def test_administration_is_backend_authoritative_and_audited() -> None:
    source = _source("workspace_administration_router.py")
    assert 'ADMIN_SETTINGS_KEY = "document_control_admin"' in source
    assert "DocControlSettings" in source
    assert "tenant.settings_json" in source
    assert "require_control_user(current_user)" in source
    assert '"document.administration.updated"' in source
    for policy in (
        "document_classes",
        "workflow_policy",
        "retention_classes",
        "indexing_policy",
        "integration_modules",
        "physical_copy_policy",
    ):
        assert policy in source


def test_external_revision_assessment_uses_existing_receipt_and_audit_evidence() -> None:
    source = _source("workspace_external_assessment_router.py")
    assert "ExternalRevisionReceipt" in source
    assert "NEW_REVISION_REQUIRES_ASSESSMENT" in source
    assert 'Literal["APPLICABLE", "PARTIAL", "NOT_APPLICABLE"]' in source
    assert '"APPLICABILITY_ASSESSMENT"' in source
    assert '"document.external_revision.assessed"' in source
    assert "affected_internal_documents" in source
    assert "DocumentGovernedRelationship" in source


def test_physical_copy_incidents_preserve_existing_copy_and_event_ledger() -> None:
    source = _source("workspace_copy_incident_router.py")
    assert 'Literal["DAMAGE", "LOSS"]' in source
    assert "DocumentControlledCopyEvent" in source
    assert 'row.status = "WITHDRAWN"' in source
    assert 'f"document.copy.{payload.incident_type.lower()}"' in source
    assert "evidence_json=list(payload.evidence)" in source
    assert "controlled-copy-custodians" in source
    assert "limit: int = Query(default=50, ge=1, le=100)" in source


def test_new_md_routes_are_mounted_before_compatibility_workspace_router() -> None:
    source = _source("router.py")
    required_mounts = [
        "workspace_reports_register_router",
        "workspace_administration_router",
        "workspace_external_assessment_router",
        "workspace_copy_incident_router",
        "workspace_library_discovery_router",
    ]
    compatibility_position = source.index("router.include_router(\n    workspace_router")
    for mount in required_mounts:
        assert mount in source
        assert source.index(f"router.include_router({mount}, prefix=\"/doc-control\")") < compatibility_position
