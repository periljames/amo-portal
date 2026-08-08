from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from amodb.apps.doc_control import knowledge_assistant_router as assistant


def _source(source_id: str = "section:rev:sec") -> dict:
    return {
        "id": source_id,
        "code": "QAM",
        "title": "Quality Assurance Manual",
        "heading": "Controlled forms",
        "page_number": 51,
        "snippet": "Use QAM 51 for the inspection record.",
    }


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[5]


def test_provider_is_off_by_default_and_never_calls_external_network(monkeypatch) -> None:
    monkeypatch.delenv("DOCUMENT_AI_PROVIDER", raising=False)
    monkeypatch.delenv("DOCUMENT_AI_ALLOW_EXTERNAL", raising=False)
    monkeypatch.setattr(
        assistant.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network called")),
    )

    answer, citations, warning = assistant._openai_synthesis("Where is QAM 51?", [_source()])

    assert answer is None
    assert citations == []
    assert warning is None


def test_external_provider_request_is_server_side_non_storing_and_citation_limited(monkeypatch) -> None:
    captured: dict = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            content = json.dumps(
                {
                    "answer": "Open QAM 51 and verify the controlled form.",
                    "source_ids": ["section:rev:sec", "invented"],
                }
            )
            return json.dumps(
                {"output": [{"type": "message", "content": [{"type": "output_text", "text": content}]}]}
            ).encode()

    def fake_open(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode())
        return FakeResponse()

    monkeypatch.setenv("DOCUMENT_AI_PROVIDER", "openai")
    monkeypatch.setenv("DOCUMENT_AI_ALLOW_EXTERNAL", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    monkeypatch.setenv("DOCUMENT_AI_MODEL", "configured-model")
    monkeypatch.setattr(assistant.urllib.request, "urlopen", fake_open)

    answer, citations, warning = assistant._openai_synthesis("Where is QAM 51?", [_source()])

    assert answer == "Open QAM 51 and verify the controlled form."
    assert citations == ["section:rev:sec"]
    assert warning is None
    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["timeout"] == 12
    assert captured["body"]["store"] is False
    assert captured["body"]["model"] == "configured-model"
    assert captured["body"]["text"]["format"]["type"] == "json_schema"
    assert "test-only-key" not in json.dumps(captured["body"])


def test_navigation_url_carries_precise_page_and_anchor() -> None:
    tenant = SimpleNamespace(slug="safarilink")
    url = assistant._reader_url(tenant, "manual-1", "revision-2", page=51, anchor="qam-51")
    assert url == "/maintenance/SAFARILINK/publications/manual-1/rev/revision-2/read?page=51&anchor=qam-51"


def test_results_are_ranked_and_deduplicated_by_revision_location() -> None:
    first = {**_source("low"), "revision_id": "r1", "section_id": "s1", "score": 5}
    stronger = {**_source("high"), "revision_id": "r1", "section_id": "s1", "score": 50}
    other = {**_source("other"), "revision_id": "r2", "section_id": "s2", "score": 30}

    result = assistant._deduplicate([first, stronger, other], 10)

    assert [row["id"] for row in result] == ["high", "other"]
    assert [row["rank"] for row in result] == [1, 2]


def test_route_contract_filters_access_before_retrieval_and_audits_only_query_hash() -> None:
    source = Path(assistant.__file__).read_text(encoding="utf-8")
    assert "if can_read_manual(user, profiles.get(manual.id))" in source
    assert "manual.current_published_rev_id" in source
    assert "not current_effective and not is_control_user(user)" in source
    assert 'event_name="documentation.assisted_search"' in source
    assert '"query_sha256": _query_hash(request_payload.query)' in source
    assert '"query_text"' not in source
    assert '"controlled_source_is_authoritative": True' in source
    assert '"store": False' in source
    assert "https://api.openai.com/v1/responses" in source


def test_assistant_route_precedes_compatibility_workspace_routes() -> None:
    from amodb.main import app

    path = "/doc-control/workspace/t/{tenant_slug}/knowledge/assist"
    matching = [route for route in app.routes if getattr(route, "path", "") == path]
    assert matching, path
    assert matching[0].endpoint.__module__ == "amodb.apps.doc_control.knowledge_assistant_router"


def test_postgresql_search_migration_is_online_safe_and_reversible() -> None:
    migration = (
        _repository_root()
        / "backend/amodb/alembic/versions/document_control_20260729_ai_assisted_search.py"
    )
    source = migration.read_text(encoding="utf-8")
    assert "USING GIN" in source
    assert "to_tsvector('simple'" in source
    assert "document_control_20260729_knowledge_graph" in source
    assert "autocommit_block" in source
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS" in source
    assert "DROP INDEX CONCURRENTLY IF EXISTS" in source


def test_frontend_assistant_remains_contextual_and_not_permanent_dms_chrome() -> None:
    root = _repository_root() / "frontend/src"
    service = (root / "services/documentationAssistant.ts").read_text(encoding="utf-8")
    panel = (root / "pages/manuals/DocumentationAssistantPanel.tsx").read_text(encoding="utf-8")
    reader = (root / "pages/manuals/ManualReaderPage.tsx").read_text(encoding="utf-8")
    shell = (root / "pages/documentControl/DocumentControlShell.tsx").read_text(encoding="utf-8")

    assert "/doc-control/workspace/t/${tenantPath(tenant)}/knowledge/assist" in service
    assert "controlled_source_is_authoritative" in service
    assert "amo:publication-navigate" in panel
    assert "The controlled source remains authoritative" in panel
    # Assisted search remains available in the document-reading context, but it
    # must not turn every DMS workspace into an always-mounted chat surface.
    assert "DocumentationAssistantPanel" in reader
    assert "PublicationAssistedNavigationBridge" in reader
    assert "DocumentationAssistantPanel" not in shell
    assert "OPENAI_API_KEY" not in service + panel + reader + shell


def test_direct_and_assisted_reader_navigation_share_one_precise_contract() -> None:
    bridge = (
        _repository_root()
        / "frontend/src/pages/manuals/PublicationAssistedNavigationBridge.tsx"
    ).read_text(encoding="utf-8")
    viewer = (
        _repository_root()
        / "frontend/src/pages/manuals/PublicationPdfLayoutViewer.tsx"
    ).read_text(encoding="utf-8")
    core = (
        _repository_root()
        / "frontend/src/pages/manuals/PdfReaderCoreV2.tsx"
    ).read_text(encoding="utf-8")

    assert 'searchParams.get("page")' in bridge
    assert 'searchParams.get("anchor")' in bridge
    assert 'window.addEventListener("amo:publication-navigate"' in bridge
    assert '.pdf-engine-page[data-page-number=' in bridge
    assert "data-page-number={page}" in core
    assert "jump(navigationRequest.page)" in core
    assert "PdfReaderCore" in viewer
    assert "<PdfDocument" not in viewer
