from __future__ import annotations

from types import SimpleNamespace

from amodb.apps.doc_control.knowledge_assistant_router import DocumentationAssistRequest
from amodb.apps.doc_control.knowledge_assistant_runtime_guard import audit_assist_safely
from amodb.apps.manuals.models import ManualAIHookEvent


class _CollectingSession:
    def __init__(self) -> None:
        self.rows: list[ManualAIHookEvent] = []

    def add(self, row: ManualAIHookEvent) -> None:
        self.rows.append(row)


def test_assisted_search_audit_uses_only_mapped_event_fields() -> None:
    session = _CollectingSession()
    context = SimpleNamespace(
        tenant=SimpleNamespace(id="tenant-1"),
        manuals={"manual-1": SimpleNamespace(id="manual-1")},
        revisions={
            "revision-1": SimpleNamespace(id="revision-1", manual_id="manual-1"),
        },
    )
    payload = DocumentationAssistRequest(query="DMS-CI-MOM", mode="SEARCH")
    current_user = SimpleNamespace(id="user-1", contact_id="contact-1")

    audit_assist_safely(
        session,
        context=context,
        current_user=current_user,
        request_payload=payload,
        provider_mode="DETERMINISTIC",
        source_ids=["document:manual-1:revision-1"],
        warning=None,
    )

    assert len(session.rows) == 1
    event = session.rows[0]
    assert event.tenant_id == "tenant-1"
    assert event.revision_id == "revision-1"
    assert event.event_name == "documentation.assisted_search"
    assert event.payload_json["manual_id"] == "manual-1"
    assert event.payload_json["actor_id"] == "user-1"
    assert event.payload_json["actor_contact_id"] == "contact-1"
    assert event.payload_json["source_ids"] == ["document:manual-1:revision-1"]


def test_assisted_search_without_authorised_sources_does_not_emit_synthetic_event() -> None:
    session = _CollectingSession()
    context = SimpleNamespace(
        tenant=SimpleNamespace(id="tenant-1"),
        manuals={},
        revisions={},
    )

    audit_assist_safely(
        session,
        context=context,
        current_user=SimpleNamespace(id="user-1", contact_id=None),
        request_payload=DocumentationAssistRequest(query="unknown document", mode="SEARCH"),
        provider_mode="DETERMINISTIC",
        source_ids=[],
        warning=None,
    )

    assert session.rows == []
