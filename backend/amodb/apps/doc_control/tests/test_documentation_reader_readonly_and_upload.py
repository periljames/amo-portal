from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from amodb.apps.doc_control import domain_models
from amodb.apps.doc_control import governance_models as gm
from amodb.apps.doc_control import knowledge_models as km
from amodb.apps.doc_control.knowledge_tree_reader import (
    read_only_hierarchy_payload,
    read_only_node_connections,
)
from amodb.apps.manuals import models as manual_models


class _FakeQuery:
    def __init__(self, *, rows=None, first=None):
        self._rows = list(rows or [])
        self._first = first

    def filter(self, *_criteria):
        return self

    def order_by(self, *_criteria):
        return self

    def limit(self, _value):
        return self

    def count(self):
        return len(self._rows)

    def all(self):
        return list(self._rows)

    def first(self):
        return self._first


class _ReadOnlyDb:
    def __init__(
        self,
        *,
        nodes,
        manuals,
        revision,
        execution_profiles=None,
        governed_relationships=None,
        references=None,
        records=None,
    ):
        self.nodes = nodes
        self.manuals = manuals
        self.revision = revision
        self.execution_profiles = list(execution_profiles or [])
        self.governed_relationships = list(governed_relationships or [])
        self.references = list(references or [])
        self.records = list(records or [])

    def query(self, entity):
        if entity is km.DocumentationNode:
            return _FakeQuery(rows=self.nodes)
        if entity is manual_models.Manual:
            return _FakeQuery(rows=self.manuals)
        if entity is domain_models.DocumentControlProfile:
            return _FakeQuery(rows=[])
        if entity is km.DocumentationExecutionProfile:
            return _FakeQuery(rows=self.execution_profiles)
        if entity is manual_models.ManualRevision:
            return _FakeQuery(rows=[self.revision])
        if entity is gm.DocumentGovernedRelationship:
            return _FakeQuery(rows=self.governed_relationships)
        if entity is km.DocumentationReference:
            return _FakeQuery(rows=self.references)
        if entity is km.DocumentationRecord:
            return _FakeQuery(rows=self.records)
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
        manual_id="manual-1",
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


def test_node_connections_return_reader_lineage_and_submitters_own_records() -> None:
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
        metadata_json={},
    )
    form_node = SimpleNamespace(
        id="form-node",
        parent_id="root",
        node_type="FORM",
        code="QF-01",
        title="Quality inspection form",
        path="/doc-root/qf-01",
        depth=1,
        order_index=1,
        manual_id="form-manual",
        status="ACTIVE",
        metadata_json={},
    )
    related_node = SimpleNamespace(
        id="procedure-node",
        parent_id="root",
        node_type="PROCEDURE",
        code="QP-01",
        title="Quality inspection procedure",
        path="/doc-root/qp-01",
        depth=1,
        order_index=2,
        manual_id="procedure-manual",
        status="ACTIVE",
        metadata_json={},
    )
    series_node = SimpleNamespace(
        id="series-node",
        parent_id="root",
        node_type="RECORD_SERIES",
        code="QR-01",
        title="Quality inspection records",
        path="/doc-root/qr-01",
        depth=1,
        order_index=3,
        manual_id=None,
        status="ACTIVE",
        metadata_json={},
    )
    manuals = [
        SimpleNamespace(
            id="form-manual",
            tenant_id="tenant-db",
            manual_type="FORM",
            status="ACTIVE",
            current_published_rev_id="revision-1",
        ),
        SimpleNamespace(
            id="procedure-manual",
            tenant_id="tenant-db",
            manual_type="PROCEDURE",
            status="ACTIVE",
            current_published_rev_id=None,
        ),
    ]
    revision = SimpleNamespace(
        id="revision-1",
        manual_id="form-manual",
        rev_number="1",
        source_type_enum=manual_models.ManualSourceType.PDF,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    execution = SimpleNamespace(
        id="execution-1",
        manual_id="form-manual",
        execution_type="PDF_ACROFORM",
        submission_mode="FILL_AND_SUBMIT",
        record_series_node_id="series-node",
        retention_years=7,
        naming_pattern="{code}-{date}-{sequence}",
        allow_download=True,
        allow_save_draft=True,
        requires_signature=False,
        requires_review=True,
        schema_json={},
        access_scope_json={},
        metadata_json={},
        version=1,
    )
    relationship = SimpleNamespace(
        id="relationship-1",
        relationship_type="IMPLEMENTS",
        relationship_source="MANUAL",
        resolution_status="CONFIRMED",
        source_manual_id="form-manual",
        target_manual_id="procedure-manual",
        exact_token="QP-01",
        exact_quote="Complete QP-01",
        page_number=2,
        section_label="2.1",
        confidence_percent=100,
        updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    reference = SimpleNamespace(
        id="reference-1",
        relationship_type="USES_FORM",
        status="VERIFIED",
        source_manual_id="procedure-manual",
        target_manual_id="form-manual",
        raw_token="QF-01",
        source_quote="Use QF-01",
        source_page_number=3,
        confidence_percent=98,
        updated_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )
    record = SimpleNamespace(
        id="record-1",
        record_number="QF-01-20260104-000001",
        status="PENDING_REVIEW",
        artifact_filename="inspection.pdf",
        template_manual_id="form-manual",
        record_series_node_id="series-node",
        submitted_by_user_id="reader-1",
        submitted_at=datetime(2026, 1, 4, tzinfo=timezone.utc),
        retention_years=7,
    )
    db = _ReadOnlyDb(
        nodes=[root, form_node, related_node, series_node],
        manuals=manuals,
        revision=revision,
        execution_profiles=[execution],
        governed_relationships=[relationship],
        references=[reference],
        records=[record],
    )
    user = SimpleNamespace(
        id="reader-1",
        role="USER",
        department=None,
        is_superuser=False,
        is_amo_admin=False,
    )

    payload = read_only_node_connections(
        db,
        manual_tenant=SimpleNamespace(id="tenant-db", amo_id="amo-1", slug="tenant"),
        user=user,
        node_id="form-node",
    )

    assert payload is not None
    assert [item["id"] for item in payload["breadcrumbs"]] == ["root", "form-node"]
    assert payload["record_series"]["id"] == "series-node"
    assert [item["id"] for item in payload["workflow_nodes"]] == ["series-node"]
    assert payload["governed_relationships"][0]["related_node"]["id"] == "procedure-node"
    assert payload["detected_references"][0]["direction"] == "INCOMING"
    assert payload["records"]["scope"] == "OWN"
    assert payload["records"]["items"][0]["download_url"] == "/manuals/t/tenant/records/record-1/artifact.pdf"

    procedure_payload = read_only_node_connections(
        db,
        manual_tenant=SimpleNamespace(id="tenant-db", amo_id="amo-1", slug="tenant"),
        user=user,
        node_id="procedure-node",
    )
    assert procedure_payload is not None
    assert {item["id"] for item in procedure_payload["workflow_nodes"]} == {
        "form-node",
        "series-node",
    }
    assert procedure_payload["records"]["total"] == 1


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
