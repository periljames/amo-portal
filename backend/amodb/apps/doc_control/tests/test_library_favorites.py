from datetime import datetime, timezone
from types import SimpleNamespace

from amodb.apps.doc_control import workspace_library_discovery_router as routes


def test_favorite_toggle_preserves_reader_bookmarks_and_open_history(monkeypatch):
    opened_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
    progress = SimpleNamespace(
        manual_id="manual-1", revision_id="revision-1", is_favorite=False,
        bookmark_label="Calibration procedure", bookmarks_json=[{"page": 12}],
        last_opened_at=opened_at, last_page_number=12,
    )
    manual = SimpleNamespace(id="manual-1", current_published_rev_id="revision-1")
    revision = SimpleNamespace(id="revision-1")

    class Query:
        def __init__(self, rows): self.rows = rows
        def filter(self, *args): return self
        def all(self): return self.rows
        def first(self): return self.rows[0] if self.rows else None

    class DB:
        def query(self, entity):
            return Query({
                routes.manual_models.Manual: [manual],
                routes.manual_models.ManualRevision: [revision],
                routes.manual_models.ManualReaderProgress: [progress],
            }[entity])
        def commit(self): pass

    monkeypatch.setattr(routes, "resolve_tenant", lambda *args: SimpleNamespace(id="tenant-1"))
    monkeypatch.setattr(routes, "get_profile", lambda *args: None)
    monkeypatch.setattr(routes, "can_read_manual", lambda *args: True)
    monkeypatch.setattr(routes, "audit", lambda *args: None)
    for favorite in [True, False]:
        response = routes.set_library_favorite(
            tenant_slug="tenant-1", manual_id=manual.id,
            payload=routes.LibraryFavoriteIn(favorite=favorite), request=None,
            db=DB(), current_user=SimpleNamespace(id="reader-1"),
        )
        assert response["favorite"] is favorite and progress.is_favorite is favorite
        assert progress.bookmark_label == "Calibration procedure"
        assert progress.bookmarks_json == [{"page": 12}]
        assert progress.last_opened_at == opened_at and progress.last_page_number == 12
