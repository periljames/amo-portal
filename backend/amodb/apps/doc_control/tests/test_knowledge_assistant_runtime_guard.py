from __future__ import annotations

from types import SimpleNamespace

from amodb.apps.accounts import models as account_models
from amodb.apps.doc_control import knowledge_assistant_runtime_guard as guard
from amodb.apps.doc_control.knowledge_assistant_router import DocumentationAssistRequest
from amodb.apps.manuals import models as manual_models


class RecordingSession:
    def __init__(self) -> None:
        self.added: list[manual_models.ManualAIHookEvent] = []

    def add(self, value: manual_models.ManualAIHookEvent) -> None:
        self.added.append(value)


class ActorSession:
    def __init__(self, actor) -> None:
        self.actor = actor

    def get(self, model, key):
        assert model is account_models.User
        assert str(key) == str(self.actor.id)
        return self.actor


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


def test_tenant_actor_must_match_ai_tenant_scope() -> None:
    actor = SimpleNamespace(
        id="user-1",
        is_active=True,
        is_superuser=False,
        amo_id="tenant-a",
    )
    allowed, warning = guard._actor_tenant_ai_access(
        ActorSession(actor),
        tenant_id="tenant-b",
        user_id="user-1",
    )
    assert allowed is False
    assert warning and "does not match" in warning


def test_platform_actor_requires_active_support_session(monkeypatch) -> None:
    access = lambda *args, **kwargs: (_ for _ in ()).throw(
        PermissionError("Cross-tenant AI data access requires an active governed platform support session")
    )
    monkeypatch.setattr(guard.ai_access, "require_tenant_data_access", access)
    allowed, warning = guard._actor_tenant_ai_access(
        object(),
        tenant_id="tenant-a",
        user_id="platform-1",
    )
    assert allowed is False
    assert warning and "support session" in warning


def test_platform_actor_with_exact_support_session_can_reach_tenant_ai(monkeypatch) -> None:
    monkeypatch.setattr(
        guard.ai_access,
        "require_tenant_data_access",
        lambda *args, **kwargs: "support-1",
    )
    allowed, warning = guard._actor_tenant_ai_access(
        object(),
        tenant_id="tenant-a",
        user_id="platform-1",
    )
    assert allowed is True
    assert warning is None


def test_cross_tenant_document_synthesis_never_calls_provider(monkeypatch) -> None:
    actor = SimpleNamespace(
        id="user-1",
        is_active=True,
        is_superuser=False,
        amo_id="tenant-a",
    )
    provider_called = False

    def fail_if_called(*args, **kwargs):
        nonlocal provider_called
        provider_called = True
        raise AssertionError("Provider must not be called for a mismatched tenant actor")

    monkeypatch.setattr(guard.ai_gateway, "run_ai", fail_if_called)
    answer, citations, warning = guard._governed_synthesis(
        ActorSession(actor),
        "tenant-b",
        "user-1",
        "Show me the controlled procedure",
        [
            {
                "id": "section:revision-1:section-1",
                "code": "MPM",
                "title": "Maintenance Procedures Manual",
                "heading": "Quality",
                "page_number": 12,
                "snippet": "Tenant B controlled text must never leave the portal in this case.",
            }
        ],
    )
    assert provider_called is False
    assert answer is None
    assert citations == []
    assert warning and "Deterministic results" in warning
