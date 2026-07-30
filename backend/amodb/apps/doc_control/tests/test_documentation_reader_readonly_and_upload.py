from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from amodb.apps.doc_control import domain_models
from amodb.apps.doc_control import knowledge_models as km
from amodb.apps.doc_control.knowledge_tree_reader import read_only_hierarchy_payload
from amodb.apps.manuals import models as manual_models


class _FakeQuery:
    def __init__(self, *, rows=None, first=None):
        self._rows = list(rows or [])
        self._first = first

    def filter(self, *_criteria):
        return self

    def order_by(self, *_criteria):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._first


class _ReadOnlyDb:
    def __init__(self, *, nodes, manuals, revision):
        self.nodes = nodes
        self.manuals = manuals
        self.revision = revision

    def query(self, entity):
        if entity is km.DocumentationNode:
            return _FakeQuery(rows=self.nodes)
        if entity is manual_models.Manual:
            return _FakeQuery(rows=self.manuals)
        if entity is domain_models.DocumentControlProfile:
            return _FakeQuery(rows=[])
        if entity is km.DocumentationExecutionProfile:
            return _FakeQuery(rows=[])
        if entity is manual_models.ManualRevision:
            return _FakeQuery(first=self.revision)
        raise AssertionError(f"Unexpected hierarchy query: {entity!r}")

    def add(self, _row):
        raise AssertionError("Hierarchy reads must not add rows")

    def flush(self):
        raise AssertionError("Hierarchy reads must not flush")

    def commit(self):
        raise AssertionError("Hierarchy reads must not commit")


def test_reader_hierarchy_serializes_existing_state_without_reconciliation() -> None:
    root = SimpleNamespace(
        id="root",
        parent_id=None,
        node_type="ROOT",
        code="DOC-ROOT",
        title="Documented information",
        path="/doc-root",
        depth=0,
        order_index=0,
        manual_id=None,
        status="ACTIVE",
        metadata_json={"system": True},
    )
    document = SimpleNamespace(
        id="node-1",
        parent_id="root",
        node_type="MANUAL",
        code="QAM",
        title="Quality Manual",
        path="/doc-root/qam",
        depth=1,
        order_index=1,
        manual_id="manual-1",
        status="ACTIVE",
        metadata_json={},
    )
    manual = SimpleNamespace(
        id="manual-1",
        tenant_id="tenant-db",
        manual_type="MANUAL",
        status="ACTIVE",
        current_published_rev_id="revision-1",
    )
    revision = SimpleNamespace(
        id="revision-1",
        rev_number="1",
        source_type_enum=manual_models.ManualSourceType.PDF,
        created_at=None,
    )
    db = _ReadOnlyDb(nodes=[root, document], manuals=[manual], revision=revision)
    user = SimpleNamespace(
        id="reader-1",
        role="USER",
        department=None,
        is_superuser=False,
        is_amo_admin=False,
    )

    payload = read_only_hierarchy_payload(
        db,
        manual_tenant=SimpleNamespace(id="tenant-db", amo_id="amo-1"),
        user=user,
    )

    assert payload["root_id"] == "root"
    assert [item["id"] for item in payload["items"]] == ["root", "node-1"]
    assert payload["items"][1]["document"]["latest_revision_id"] == "revision-1"
    assert payload["reference_health"] == {}


def test_hierarchy_get_routes_do_not_commit_or_reconcile() -> None:
    root = Path(__file__).resolve().parents[5]
    access_router = (root / "backend/amodb/apps/doc_control/knowledge_access_router.py").read_text(encoding="utf-8")
    assert "read_only_hierarchy_payload" in access_router
    assert "reconcile_documentation_hierarchy" not in access_router
    assert "db.commit()" not in access_router


def test_download_and_upload_mode_has_file_picker_and_submission_path() -> None:
    root = Path(__file__).resolve().parents[5]
    panel = (root / "frontend/src/pages/manuals/LinkedDocumentationPanel.tsx").read_text(encoding="utf-8")
    assert 'submission_mode === "DOWNLOAD_AND_UPLOAD"' in panel
    assert 'type="file"' in panel
    assert 'accept="application/pdf,.pdf"' in panel
    assert "Choose completed PDF" in panel
    assert "Submit flattened record" in panel
    assert 'output_mode: "FLATTENED_RECORD"' in panel
    assert "PDFium will flatten and verify" in panel
    assert "submitLinkedPdfResource" in panel
