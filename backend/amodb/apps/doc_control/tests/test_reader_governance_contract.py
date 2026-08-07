from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from amodb.apps.doc_control.reader_governance_compare import compare_revisions, migration_proposal
from amodb.apps.doc_control.reader_governance_evidence import stable_json_sha
from amodb.apps.doc_control.reader_governance_models import DocumentAnnotationMigration, DocumentEvidenceSnapshot
from amodb.apps.doc_control.reader_governance_router import router
from amodb.apps.manuals import models as manual_models


def test_reader_governance_routes_are_version_scoped() -> None:
    paths = {route.path for route in router.routes}
    required = {
        "/workspace/t/{tenant_slug}/reader/documents/{manual_id}/revisions/{revision_id}/manifest",
        "/workspace/t/{tenant_slug}/reader/documents/{manual_id}/revisions/{revision_id}/annotations",
        "/workspace/t/{tenant_slug}/reader/documents/{manual_id}/revisions/{revision_id}/annotations/{annotation_id}",
        "/workspace/t/{tenant_slug}/reader/documents/{manual_id}/revisions/{revision_id}/evidence",
        "/workspace/t/{tenant_slug}/reader/documents/{manual_id}/revisions/{revision_id}/evidence/snapshots",
        "/workspace/t/{tenant_slug}/reader/documents/{manual_id}/revisions/{revision_id}/evidence/snapshots/{snapshot_id}",
        "/workspace/t/{tenant_slug}/reader/documents/{manual_id}/compare",
        "/workspace/t/{tenant_slug}/reader/documents/{manual_id}/annotation-migrations/prepare",
        "/workspace/t/{tenant_slug}/reader/documents/{manual_id}/annotation-migrations",
        "/workspace/t/{tenant_slug}/reader/documents/{manual_id}/annotation-migrations/{migration_id}",
    }
    assert not (required - paths), required - paths


def test_reader_governance_uses_normalized_evidence_tables() -> None:
    assert DocumentAnnotationMigration.__table__.name == "document_annotation_migrations"
    assert DocumentEvidenceSnapshot.__table__.name == "document_evidence_snapshots"


def test_reader_governance_migration_follows_merged_alembic_head() -> None:
    merge = Path("amodb/alembic/versions/docgov_merge_20260807.py").read_text(encoding="utf-8")
    reader = Path("amodb/alembic/versions/docgov_20260807_reader_governance.py").read_text(encoding="utf-8")
    assert '"docgov_20260806_governance"' in merge
    assert '"merge_20260806_aircraft_workforce"' in merge
    assert 'down_revision: Union[str, Sequence[str], None] = "docgov_merge_20260807"' in reader
    heads = Path("amodb/alembic/versions/docgov_merge_20260807_heads.py").read_text(encoding="utf-8")
    assert '"docgov_20260807_reader_governance"' in heads
    assert '"aircraft_arch_20260806_usage_hsi"' in heads
    assert "document_annotation_migrations" in reader
    assert "document_evidence_snapshots" in reader


def test_evidence_hash_is_stable_across_key_order() -> None:
    left = {"revision": {"id": "r1", "sha": "abc"}, "items": [2, 1]}
    right = {"items": [2, 1], "revision": {"sha": "abc", "id": "r1"}}
    assert stable_json_sha(left) == stable_json_sha(right)
    assert stable_json_sha(left) != stable_json_sha({"revision": {"id": "r2"}, "items": [2, 1]})


class _Query:
    def __init__(self, values):
        self.values = values

    def filter(self, *_criteria):
        return self

    def order_by(self, *_criteria):
        return self

    def all(self):
        return list(self.values)

    def first(self):
        return self.values[0] if self.values else None


class _SequenceDb:
    def __init__(self, responses):
        self.responses = iter(responses)

    def query(self, _model):
        return _Query(next(self.responses))


def test_revision_compare_marks_exact_anchor_content_as_unchanged() -> None:
    source_section = SimpleNamespace(id="s1", anchor_slug="scope", heading="1. Scope", order_index=1)
    target_section = SimpleNamespace(id="t1", anchor_slug="scope", heading="1. Scope", order_index=1)
    source_block = SimpleNamespace(section_id="s1", order_index=1, change_hash="same")
    target_block = SimpleNamespace(section_id="t1", order_index=1, change_hash="same")
    db = _SequenceDb([[source_section], [source_block], [target_section], [target_block]])
    result = compare_revisions(db, SimpleNamespace(id="rev-old"), SimpleNamespace(id="rev-new"))
    assert result["summary"] == {"UNCHANGED": 1}
    assert result["section_map"]["s1"]["status"] == "EXACT"
    assert result["section_map"]["s1"]["confidence_percent"] == 100


def test_annotation_migration_requires_review_when_only_page_survives() -> None:
    location = SimpleNamespace(
        id="loc-1",
        page_number=12,
        section_id=None,
        location_type="PAGE",
        exact_quote=None,
        prefix_context=None,
        suffix_context=None,
        normalized_rects_json=[],
    )
    proposal = migration_proposal(_SequenceDb([[location]]), SimpleNamespace(location_id="loc-1"), {"section_map": {}})
    assert proposal["strategy"] == "REVIEW_REQUIRED"
    assert proposal["confidence_percent"] == 40
    assert proposal["location"]["page_number"] == 12


def test_reader_api_fails_closed_on_checksum_and_human_review() -> None:
    text = (Path(__file__).resolve().parents[1] / "reader_governance_router.py").read_text(encoding="utf-8")
    assert "expected_source_sha256" in text
    assert "source revision changed or has no matching checksum" in text
    assert "Unresolved migrations cannot be accepted" in text
    assert 'payload.decision == "REJECT"' in text
    assert "Shared, controlled-evidence and finding annotations require Document Control privileges" in text
