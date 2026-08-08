from __future__ import annotations

from amodb.apps.doc_control.knowledge_service import _ensure_node


class _EmptyQuery:
    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return None


class _FlushGuardSession:
    def __init__(self) -> None:
        self.row = None
        self.flush_count = 0

    def query(self, _model):
        return _EmptyQuery()

    def add(self, row) -> None:
        self.row = row

    def flush(self) -> None:
        self.flush_count += 1
        assert self.row is not None
        assert self.row.id
        assert self.row.path
        assert self.row.path.startswith("/doc-root~")
        assert self.row.depth == 0


def test_new_hierarchy_node_has_materialized_path_before_first_flush() -> None:
    db = _FlushGuardSession()

    row = _ensure_node(
        db,
        tenant_id="00000000-0000-4000-8000-000000000001",
        code="DOC-ROOT",
        title="Controlled documented information",
        node_type="ROOT",
        parent=None,
    )

    assert db.flush_count == 1
    assert row is db.row
    assert row.path.startswith("/doc-root~")
    assert row.depth == 0
