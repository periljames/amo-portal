"""Runtime route and migration contracts for enterprise QMS/DMS integration.

These checks deliberately inspect the assembled FastAPI application, not just
source imports. They do not replace database-backed authorization or browser
acceptance.
"""
from __future__ import annotations

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.routing import APIRoute

from amodb.main import app


QUALITY_PREFIX = "/api/maintenance/{amo_code}/quality"


@pytest.mark.parametrize(("method", "path"), [
    ("GET", QUALITY_PREFIX + "/management-review/meetings"),
    ("GET", "/platform/tenants/{tenant_id}/storage-quota"),
    ("POST", "/platform/tenants/{tenant_id}/storage-quota"),
    ("POST", "/platform/tenants/{tenant_id}/storage-quota/reconcile"),
    ("POST", "/platform/tenants/{tenant_id}/storage-quota/verify-objects"),
    ("POST", QUALITY_PREFIX + "/management-review/meetings/{meeting_id}/approve"),
    ("POST", QUALITY_PREFIX + "/management-review/meetings/{meeting_id}/actions/{action_id}/verify"),
    ("GET", QUALITY_PREFIX + "/risk/governance/matrix"),
    ("POST", QUALITY_PREFIX + "/risk/governance/records/{kind}/{risk_id}/accept"),
    ("GET", QUALITY_PREFIX + "/equipment-calibration/governance/eligibility"),
    ("POST", QUALITY_PREFIX + "/equipment-calibration/governance/assets/{asset_id}/return-to-service"),
    ("POST", QUALITY_PREFIX + "/external-interface/governance/records/{kind}/{record_id}/submit"),
    ("POST", QUALITY_PREFIX + "/external-interface/governance/records/{kind}/{record_id}/close"),
    ("POST", QUALITY_PREFIX + "/system/governance/processes/{process_id}/approve"),
    ("POST", QUALITY_PREFIX + "/system/governance/processes/{process_id}/reviews/{review_id}/verify"),
    ("POST", QUALITY_PREFIX + "/manual-impact/manuals/{manual_id}/revisions/{revision_id}/assign"),
    ("GET", "/doc-control/workspace/t/{tenant_slug}/microsoft365/connection"),
    ("POST", "/doc-control/workspace/t/{tenant_slug}/documents/{manual_id}/microsoft365/import"),
    ("GET", "/doc-control/microsoft365/oauth/callback"),
    ("GET", "/manuals/t/{tenant_slug}/{manual_id}/rev/{revision_id}/layout-status"),
    ("POST", "/manuals/t/{tenant_slug}/{manual_id}/rev/{revision_id}/layout-verify"),
])
def test_governed_endpoint_has_exactly_one_application_owner(method: str, path: str) -> None:
    owners = [
        route for route in app.routes
        if isinstance(route, APIRoute)
        and route.path == path
        and method in (route.methods or ())
    ]
    assert len(owners) == 1, f"{method} {path}: expected one registered owner, got {len(owners)}"


def test_qms_dms_migration_chain_is_reachable_and_ordered() -> None:
    script = ScriptDirectory.from_config(Config("amodb/alembic.ini"))
    parents = {
        "plat_20261016_storage_bytes": "quality_261003_evidence_context",
        "plat_261026_merge_heads": ("extprov_261019_oversight", "plat_20261016_storage_bytes"),
        "venspera_quality_261029_merge": ("plat_261026_merge_heads", "quality_car_feedback_261027"),
        "docx_fidelity_261028": "venspera_quality_261029_merge",
        "doc_m365_261028": "docx_fidelity_261028",
        "docctl_261009_favorites": "doc_m365_261028",
        "quality_process_review_261111": "docctl_261009_favorites",
        "dms_training_link_261111": "quality_process_review_261111",
        "qms_equipment_serial_261112": "dms_training_link_261111",
    }
    for revision, expected_parent in parents.items():
        node = script.get_revision(revision)
        assert node is not None, f"Missing enterprise migration {revision}"
        assert node.down_revision == expected_parent, f"Unexpected ancestor for {revision}"

    reachable = {
        revision.revision
        for revision in script.walk_revisions(base="base", head="heads")
    }
    assert set(parents).issubset(reachable), "The final Alembic heads must include the enterprise DMS/QMS chain"
