from __future__ import annotations

from pathlib import Path

from amodb.apps.doc_control.governance_models import (
    DocumentAnnotation,
    DocumentGovernanceBackfillItem,
    DocumentGovernanceBackfillRun,
    DocumentGovernedRelationship,
    DocumentLocation,
    DocumentResponsibilityAssignment,
)
from amodb.apps.doc_control.governance_router import router


def test_governance_routes_are_explicit_and_tenant_scoped() -> None:
    paths = {route.path for route in router.routes}
    assert "/workspace/t/{tenant_slug}/governance/dashboard" in paths
    assert "/workspace/t/{tenant_slug}/governance/library" in paths
    assert "/workspace/t/{tenant_slug}/documents/{manual_id}/governance" in paths
    assert "/workspace/t/{tenant_slug}/governance/backfill/{run_id}/resume" in paths


def test_core_governance_relations_are_normalized_tables() -> None:
    assert DocumentResponsibilityAssignment.__table__.name == "document_responsibility_assignments"
    assert DocumentLocation.__table__.name == "document_locations"
    assert DocumentGovernedRelationship.__table__.name == "document_governed_relationships"
    assert DocumentAnnotation.__table__.name == "document_annotations"
    assert DocumentGovernanceBackfillRun.__table__.name == "document_governance_backfill_runs"
    assert DocumentGovernanceBackfillItem.__table__.name == "document_governance_backfill_items"


def test_migration_is_on_the_current_governance_head_and_has_safe_downgrade() -> None:
    source = Path("amodb/alembic/versions/docgov_20260806_governance.py").read_text(encoding="utf-8")
    assert 'down_revision: Union[str, Sequence[str], None] = "workforce_20260806_governance"' in source
    assert "def upgrade()" in source
    assert "def downgrade()" in source
    assert "document_responsibility_assignments" in source
    assert "document_governed_relationships" in source
    assert "document_annotations" in source


def test_demo_fixture_covers_required_relationship_and_ownership_states() -> None:
    import json

    fixture = json.loads(Path("amodb/apps/doc_control/tests/fixtures/document_governance_demo.json").read_text(encoding="utf-8"))
    statuses = {row["status"] for row in fixture["relationships"]}
    assert {"CONFIRMED", "MATCH_PROPOSED", "REJECTED"}.issubset(statuses)
    assert any(row["source"] == "INHERITED" for row in fixture["responsibilities"])
    assert any(row.get("effective_to") for row in fixture["responsibilities"])
    assert sum(1 for row in fixture["relationships"] if row["type"] == "HAS_FORM") == 2
    assert any(row["type"] == "GENERATES_RECORD" for row in fixture["relationships"])
    assert any(row["type"] == "LINKED_REGULATION" for row in fixture["relationships"])


def test_detected_reference_review_is_tenant_scoped_and_human_governed() -> None:
    source = Path(__file__).resolve().parents[1] / "governance_router.py"
    text = source.read_text(encoding="utf-8")
    assert '/governance/references/{reference_id}/decision' in text
    assert 'Resolve the target document and revision before confirmation' in text
    assert 'published immutable revision in this tenant' in text
    assert 'document.governance.reference_decided' in text
