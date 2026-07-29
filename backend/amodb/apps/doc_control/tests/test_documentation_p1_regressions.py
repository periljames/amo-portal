from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from amodb.apps.doc_control import knowledge_hardening
from amodb.apps.doc_control.knowledge_artifact_transactions import (
    _cleanup_if_outer_transaction_ended,
    _cleanup_pending_artifacts,
    _finalize_outer_commit,
    _mark_outer_commit_intent,
    _track_pending_artifact,
)
from amodb.apps.doc_control.knowledge_hardening import (
    _filter_hierarchy_items,
    _hierarchy_override_detected,
    _new_record_number,
    _restore_verified_resolution,
    _verified_resolution_snapshot,
)
from amodb.apps.doc_control.knowledge_hierarchy_identity import (
    _ensure_node_with_stable_manual_less_identity,
    _select_stable_manual_less_node,
)
from amodb.apps.doc_control.knowledge_resolution_router import (
    _revision_is_approved_immutable,
)
from amodb.apps.doc_control.knowledge_signature_guard import (
    _create_documentation_record_signature_guarded,
)
from amodb.apps.manuals import models as manual_models
from amodb.apps.manuals.knowledge_reader_access_router import (
    _enforce_reference_source_access,
)
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


def test_pending_artifact_is_removed_when_session_close_ends_outer_transaction(tmp_path) -> None:
    path = tmp_path / "implicit-close.pdf"
    path.write_bytes(b"%PDF-1.7\nrecord")
    session = SimpleNamespace(info={})
    _track_pending_artifact(session, str(path))

    _cleanup_if_outer_transaction_ended(session, SimpleNamespace(parent=None))

    assert not path.exists()
    assert session.info == {}


def test_nested_transaction_end_does_not_remove_pending_outer_artifact(tmp_path) -> None:
    path = tmp_path / "nested.pdf"
    path.write_bytes(b"%PDF-1.7\nrecord")
    session = SimpleNamespace(info={})
    _track_pending_artifact(session, str(path))

    _cleanup_if_outer_transaction_ended(session, SimpleNamespace(parent=object()))

    assert path.exists()


def test_savepoint_commit_does_not_finalize_outer_artifact_custody(tmp_path) -> None:
    path = tmp_path / "savepoint-commit.pdf"
    path.write_bytes(b"%PDF-1.7\nrecord")
    session = SimpleNamespace(info={}, in_nested_transaction=lambda: True)
    _track_pending_artifact(session, str(path))

    _mark_outer_commit_intent(session)
    _finalize_outer_commit(session)
    _cleanup_if_outer_transaction_ended(session, SimpleNamespace(parent=object()))

    assert path.exists()
    assert session.info.get("documentation_pending_artifact_paths")


def test_savepoint_rollback_does_not_delete_outer_artifact(tmp_path) -> None:
    path = tmp_path / "savepoint-rollback.pdf"
    path.write_bytes(b"%PDF-1.7\nrecord")
    session = SimpleNamespace(info={})
    _track_pending_artifact(session, str(path))

    _cleanup_if_outer_transaction_ended(session, SimpleNamespace(parent=object()))

    assert path.exists()


def test_successful_outer_commit_finalizes_without_deleting_artifact(tmp_path) -> None:
    path = tmp_path / "outer-commit.pdf"
    path.write_bytes(b"%PDF-1.7\nrecord")
    session = SimpleNamespace(info={}, in_nested_transaction=lambda: False)
    _track_pending_artifact(session, str(path))

    _mark_outer_commit_intent(session)
    _finalize_outer_commit(session)
    _cleanup_if_outer_transaction_ended(session, SimpleNamespace(parent=None))

    assert path.exists()
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


def test_renamed_record_series_is_selected_by_stable_template_relationship() -> None:
    renamed = SimpleNamespace(
        id="series-1",
        manual_id=None,
        code="CONTROLLER-RENAMED-SERIES",
        metadata_json={"template_manual_id": "manual-1", "hierarchy_management": "GOVERNED"},
    )
    unrelated = SimpleNamespace(
        id="series-2",
        manual_id=None,
        code="REC-OTHER",
        metadata_json={"template_manual_id": "manual-2"},
    )
    selected = _select_stable_manual_less_node(
        [unrelated, renamed],
        node_type="RECORD_SERIES",
        metadata={"template_manual_id": "manual-1"},
    )
    assert selected is renamed


def test_reconciliation_reuses_renamed_record_series_instead_of_allocating_duplicate() -> None:
    renamed = SimpleNamespace(
        id="series-1",
        manual_id=None,
        code="CONTROLLER-RENAMED-SERIES",
        metadata_json={"template_manual_id": "manual-1"},
    )

    class FakeQuery:
        def filter(self, *_criteria):
            return self

        def all(self):
            return [renamed]

    class FakeDb:
        def query(self, _model):
            return FakeQuery()

    result = _ensure_node_with_stable_manual_less_identity(
        FakeDb(),
        tenant_id="amo-1",
        code="REC-QAM-51",
        title="QAM 51 completed records",
        node_type="RECORD_SERIES",
        parent=SimpleNamespace(id="records-group"),
        manual_id=None,
        order_index=1,
        metadata={"template_manual_id": "manual-1", "source_node_id": "node-1"},
        actor_id="controller-1",
    )

    assert result is renamed
    assert result.code == "CONTROLLER-RENAMED-SERIES"
    assert result.metadata_json["hierarchy_management"] == "GOVERNED"
    assert result.metadata_json["source_node_id"] == "node-1"


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


def test_restricted_reference_source_is_rejected_even_when_target_is_readable() -> None:
    source = SimpleNamespace(id="source-manual")
    restricted_profile = SimpleNamespace(restricted_flag=True, access_scope_json={})

    class FakeQuery:
        def __init__(self, result):
            self.result = result

        def filter(self, *_criteria):
            return self

        def first(self):
            return self.result

    class FakeDb:
        def __init__(self):
            self.results = iter((source, restricted_profile))

        def query(self, _model):
            return FakeQuery(next(self.results))

    user = SimpleNamespace(
        id="ordinary-user",
        role="USER",
        department=None,
        is_superuser=False,
        is_amo_admin=False,
    )
    with pytest.raises(HTTPException) as caught:
        _enforce_reference_source_access(
            FakeDb(),
            tenant=SimpleNamespace(id="tenant-db", amo_id="amo-1"),
            reference=SimpleNamespace(source_manual_id=source.id),
            user=user,
        )
    assert caught.value.status_code == 403


@pytest.mark.parametrize(
    ("status", "immutable", "expected"),
    [
        (manual_models.ManualRevisionStatus.PUBLISHED, True, True),
        (manual_models.ManualRevisionStatus.PUBLISHED, False, False),
        (manual_models.ManualRevisionStatus.DRAFT, True, False),
    ],
)
def test_only_published_immutable_revisions_can_be_verified(status, immutable, expected) -> None:
    revision = SimpleNamespace(status_enum=status, immutable_locked=immutable)
    assert _revision_is_approved_immutable(revision) is expected


def test_signature_required_record_workflow_fails_closed() -> None:
    with pytest.raises(HTTPException) as caught:
        _create_documentation_record_signature_guarded(
            SimpleNamespace(),
            profile=SimpleNamespace(requires_signature=True),
            manual_tenant=SimpleNamespace(),
            template=SimpleNamespace(),
            revision=SimpleNamespace(),
            actor_id="user-1",
            filename="unsigned.pdf",
            content=b"%PDF-1.7\nunsigned",
            source_reference_id=None,
            payload={},
        )
    assert caught.value.status_code == 409
    assert "validated digital signature" in caught.value.detail


def test_precedence_routes_enforce_hardened_contracts() -> None:
    routes = [route for route in app.routes if getattr(route, "path", None)]
    expected_modules = {
        "/doc-control/workspace/t/{tenant_slug}/knowledge/tree": "knowledge_access_router",
        "/manuals/t/{tenant_slug}/knowledge-tree": "knowledge_access_router",
        "/manuals/t/{tenant_slug}/linked-resources/{reference_id}": "knowledge_reader_access_router",
        "/manuals/t/{tenant_slug}/linked-resources/{reference_id}/submit": "knowledge_reader_access_router",
        "/doc-control/workspace/t/{tenant_slug}/knowledge/references/{reference_id}/resolve": "knowledge_resolution_router",
    }
    for path, module_suffix in expected_modules.items():
        matching = [route for route in routes if route.path == path]
        assert len(matching) >= 2
        assert matching[0].endpoint.__module__.endswith(module_suffix)
