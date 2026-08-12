from __future__ import annotations

from types import SimpleNamespace

from amodb.apps.doc_control import knowledge_assistant_runtime_guard as guard
from amodb.apps.doc_control.knowledge_assistant_router import DocumentationAssistRequest
from amodb.apps.manuals import models as manual_models


class RecordingSession:
    def __init__(self) -> None:
        self.added: list[manual_models.ManualAIHookEvent] = []

    def add(self, value: manual_models.ManualAIHookEvent) -> None:
        self.added.append(value)


def test_audit_assist_uses_declared_event_columns_and_retains_manual_context() -> None:
    db = RecordingSession()
    context = SimpleNamespace(
        tenant=SimpleNamespace(id="tenant-1"),
        manuals={"manual-1": SimpleNamespace(id="manual-1")},
        revisions={"revision-1": SimpleNamespace(manual_id="manual-1")},
    )
    current_user = SimpleNamespace(id="user-1", contact_id="contact-1")
    request = DocumentationAssistRequest(
        query="Where is the controlled procedure?",
        mode="ASSIST",
        manual_id="manual-1",
        revision_id="revision-1",
        page_number=12,
    )

    guard.audit_assist_safely(
        db,
        context=context,
        current_user=current_user,
        request_payload=request,
        provider_mode="DETERMINISTIC",
        source_ids=["section:revision-1:section-1"],
        warning=None,
    )

    assert len(db.added) == 1
    event = db.added[0]
    assert event.tenant_id == "tenant-1"
    assert event.revision_id == "revision-1"
    assert event.event_name == "documentation.assisted_search"
    assert event.payload_json["actor_id"] == "user-1"
    assert event.payload_json["manual_context_id"] == "manual-1"
    assert event.payload_json["source_manual_id"] == "manual-1"
    assert event.payload_json["source_ids"] == ["section:revision-1:section-1"]
    assert event.payload_json["scope"] == "DOCUMENT"

    declared_columns = set(manual_models.ManualAIHookEvent.__table__.columns.keys())
    assert "manual_id" not in declared_columns
    assert "actor_contact_id" not in declared_columns


def test_library_assist_scopes_events_to_each_returned_manual() -> None:
    db = RecordingSession()
    context = SimpleNamespace(
        tenant=SimpleNamespace(id="tenant-1"),
        manuals={
            "manual-1": SimpleNamespace(id="manual-1"),
            "manual-2": SimpleNamespace(id="manual-2"),
        },
        revisions={
            "revision-1": SimpleNamespace(manual_id="manual-1"),
            "revision-2": SimpleNamespace(manual_id="manual-2"),
        },
    )
    request = DocumentationAssistRequest(query="inspection procedure", mode="SEARCH")

    guard.audit_assist_safely(
        db,
        context=context,
        current_user=SimpleNamespace(id="user-1"),
        request_payload=request,
        provider_mode="DETERMINISTIC",
        source_ids=[
            "document:manual-1:revision-1",
            "section:revision-2:section-2",
        ],
        warning=None,
    )

    assert [event.payload_json["source_manual_id"] for event in db.added] == [
        "manual-1",
        "manual-2",
    ]
    assert all(
        event.payload_json["scope"] == "LIBRARY_RESULT_DOCUMENT" for event in db.added
    )


def test_no_result_assist_emits_no_synthetic_audit_event() -> None:
    db = RecordingSession()
    context = SimpleNamespace(
        tenant=SimpleNamespace(id="tenant-1"),
        manuals={"manual-1": SimpleNamespace(id="manual-1")},
        revisions={},
    )

    guard.audit_assist_safely(
        db,
        context=context,
        current_user=SimpleNamespace(id="user-1"),
        request_payload=DocumentationAssistRequest(query="no matching source", mode="SEARCH"),
        provider_mode="DETERMINISTIC",
        source_ids=[],
        warning=None,
    )

    assert db.added == []
