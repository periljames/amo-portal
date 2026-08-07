from __future__ import annotations

from types import SimpleNamespace

from amodb.apps.aircraft_architecture.content_packs import (
    backend_currentness,
    backend_currentness_hardening,
)


class FakeDb:
    def __init__(self, mapping):
        self.mapping = mapping

    def get(self, model, row_id):
        return self.mapping.get((model.__name__, row_id))


def test_published_baseline_is_review_required_when_active_tr_is_missing(monkeypatch):
    publication = SimpleNamespace(id="pub-1", publication_code="PSM-1-84-7P")
    publication_revision = SimpleNamespace(
        id="pubrev-52",
        publication_id="pub-1",
        publication=publication,
    )
    source = SimpleNamespace(
        id="source-base",
        publication_revision_id="pubrev-52",
        temporary_revision_id=None,
    )
    persisted_revision = SimpleNamespace(id="content-r1", sources=[source])
    active_tr = SimpleNamespace(id="tr-1", temporary_revision_code="TR-01")
    original = backend_currentness.ContentPackCurrentnessRead(
        pack={
            "id": "pack-1",
            "code": "DHC8_400_TEST",
            "manufacturer": "De Havilland Canada",
            "family": "DHC-8",
            "series": "400",
            "description": "test",
            "status": "ACTIVE",
            "created_at": "2026-08-07T00:00:00Z",
        },
        published_revision={
            "id": "content-r1",
            "pack_id": "pack-1",
            "revision_code": "R1",
            "status": "PUBLISHED",
            "change_summary": None,
            "content_hash": "a" * 64,
            "created_at": "2026-08-07T00:00:00Z",
            "published_at": "2026-08-07T00:00:00Z",
        },
        status="CURRENT",
        source_states=[],
    )
    monkeypatch.setattr(
        backend_currentness_hardening,
        "_ORIGINAL",
        lambda db, *, pack: original,
    )
    monkeypatch.setattr(
        backend_currentness_hardening.governance,
        "governed_publication_currentness",
        lambda db, *, publication: SimpleNamespace(
            active_temporary_revisions=[active_tr],
            current_revision=SimpleNamespace(id="pubrev-52"),
        ),
    )
    db = FakeDb(
        {
            ("AircraftContentPackRevision", "content-r1"): persisted_revision,
            ("AircraftOemPublicationRevision", "pubrev-52"): publication_revision,
            ("AircraftOemPublication", "pub-1"): publication,
        }
    )

    result = backend_currentness_hardening.content_pack_currentness(
        db,
        pack=SimpleNamespace(id="pack-1"),
    )

    assert result.status == "SOURCE_REVIEW_REQUIRED"
    assert result.source_states[-1].status == "MISSING_ACTIVE_TEMPORARY_REVISION"
    assert result.source_states[-1].temporary_revision_id == "tr-1"
