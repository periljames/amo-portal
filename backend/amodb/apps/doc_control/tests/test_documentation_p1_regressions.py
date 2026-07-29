from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from amodb.apps.doc_control import knowledge_hardening
from amodb.apps.doc_control.knowledge_artifact_transactions import (
    _cleanup_pending_artifacts,
    _track_pending_artifact,
)
from amodb.apps.doc_control.knowledge_hardening import (
    _filter_hierarchy_items,
    _hierarchy_override_detected,
    _new_record_number,
    _restore_verified_resolution,
    _verified_resolution_snapshot,
)
from amodb.apps.manuals import models as manual_models
from amodb.main import app


def test_verified_reference_resolution_is_restored_after_reindex_diagnostics() -> None:
    verified_at = object()
    row = SimpleNamespace(
        relationship_type="USES_FORM",
        resolution_policy="PINNED_REVISION",
        target_manual_id="manual-selected",
        target_revision_id="revision-selected",
        target_section_id="section-selected",
        verified_by_user_id="controller-1",
        verified_at=verified_at,
        status="OUTDATED",
        confidence_percent=20,
    )
    snapshot = _verified_resolution_snapshot(row)
    assert snapshot is not None

    row.relationship_type = "REFERENCES"
    row.resolution_policy = "CURRENT_EFFECTIVE"
    row.target_manual_id = "alias-candidate"
    row.target_revision_id = "alias-revision"
    row.target_section_id = None
    row.status = "AUTO_RESOLVED"
    _restore_verified_resolution(row, snapshot)

    assert row.relationship_type == "USES_FORM"
    assert row.resolution_policy == "PINNED_REVISION"
    assert row.target_manual_id == "manual-selected"
    assert row.target_revision_id == "revision-selected"
    assert row.target_section_id == "section-selected"
    assert row.verified_by_user_id == "controller-1"
    assert row.verified_at is verified_at
    assert row.status == "VERIFIED"
    assert row.confidence_percent == 100


def test_record_numbers_are_collision_resistant_under_concurrent_allocation() -> None:
    with ThreadPoolExecutor(max_workers=16) as pool:
        values = list(pool.map(lambda _: _new_record_number("QAM 51", date_token="20260729"), range(1000)))
    assert len(values) == len(set(values))
    assert all(value.startswith("QAM51-20260729-") for value in values)


def test_new_artifact_is_removed_when_record_flush_fails(tmp_path, monkeypatch) -> None:
    class FailingDb:
        def add(self, _row):
            return None

        def flush(self):
            raise RuntimeError("forced persistence failure")

    monkeypatch.setattr(knowledge_hardening.knowledge_service, "RECORD_ROOT", tmp_path)
    revision = SimpleNamespace(
        id="revision-1",
        rev_number="1",
        status_enum=manual_models.ManualRevisionStatus.PUBLISHED,
        immutable_locked=True,
    )
    profile = SimpleNamespace(
        record_series_node_id="series-1",
        requires_review=False,
        retention_years=7,
        execution_type="DOWNLOAD_AND_UPLOAD",
    )
    with pytest.raises(RuntimeError, match="forced persistence failure"):
        knowledge_hardening._create_documentation_record_hardened(
            FailingDb(),
            manual_tenant=SimpleNamespace(amo_id="amo-1", slug="tenant"),
            template=SimpleNamespace(id="manual-1", code="QAM 51"),
            revision=revision,
            profile=profile,
            actor_id="user-1",
            filename="completed.pdf",
            content=b"%PDF-1.7\nrecord",
            source_reference_id=None,
            payload={},
        )
    assert not list(tmp_path.rglob("*.pdf"))


def test_pending_artifact_is_removed_when_outer_transaction_rolls_back(tmp_path) -> None:
    path = tmp_path / "pending.pdf"
    path.write_bytes(b"%PDF-1.7\nrecord")
    session = SimpleNamespace(info={})
    _track_pending_artifact(session, str(path))

    _cleanup_pending_artifacts(session)

    assert not path.exists()
    assert session.info == {}


def test_reconciliation_detects_controller_governed_hierarchy_changes() -> None:
    row = SimpleNamespace(
        code="QWI-01",
        title="Governed work instruction",
        node_type="WORK_INSTRUCTION",
        parent_id="controller-parent",
        order_index=17,
    )
    assert _hierarchy_override_detected(
        row,
        code="QWI-01",
        title="Governed work instruction",
        node_type="PROCEDURE",
        parent=SimpleNamespace(id="heuristic-parent"),
        order_index=1,
    )


def test_reader_hierarchy_omits_restricted_nodes_records_and_descendants() -> None:
    items = [
        {"id": "root", "parent_id": None, "manual_id": None, "node_type": "ROOT", "metadata": {}},
        {"id": "group", "parent_id": "root", "manual_id": None, "node_type": "MANAGEMENT_SYSTEM", "metadata": {}},
        {"id": "public", "parent_id": "group", "manual_id": "manual-public", "node_type": "MANUAL", "metadata": {}},
        {"id": "restricted", "parent_id": "group", "manual_id": "manual-secret", "node_type": "MANUAL", "metadata": {}},
        {"id": "secret-child", "parent_id": "restricted", "manual_id": None, "node_type": "RECORD_SERIES", "metadata": {}},
        {"id": "secret-series", "parent_id": "group", "manual_id": None, "node_type": "RECORD_SERIES", "metadata": {"template_manual_id": "manual-secret"}},
    ]
    visible = _filter_hierarchy_items(items, {"manual-public"})
    visible_ids = {item["id"] for item in visible}
    assert visible_ids == {"root", "group", "public"}


def test_access_filtered_tree_routes_precede_legacy_tree_handlers() -> None:
    routes = [route for route in app.routes if getattr(route, "path", None)]
    for path in (
        "/doc-control/workspace/t/{tenant_slug}/knowledge/tree",
        "/manuals/t/{tenant_slug}/knowledge-tree",
    ):
        matching = [route for route in routes if route.path == path]
        assert len(matching) >= 2
        assert matching[0].endpoint.__module__.endswith("knowledge_access_router")
