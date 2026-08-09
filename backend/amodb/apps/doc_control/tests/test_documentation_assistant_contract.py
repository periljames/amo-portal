from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from amodb.apps.doc_control import knowledge_assistant_router as assistant


def _source(source_id: str = "section:rev:sec") -> dict:
    return {
        "id": source_id,
        "type": "section",
        "manual_id": "manual-1",
        "revision_id": "revision-2",
        "section_id": "section-3",
        "title": "QAM 51",
        "content": "Controlled source content",
        "score": 10,
        "page": 51,
        "anchor": "qam-51",
    }


def test_external_provider_is_disabled_without_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOCUMENT_AI_ALLOW_EXTERNAL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")

    answer, citations, warning = assistant._openai_synthesis("Where is QAM 51?", [_source()])

    assert answer is None
    assert citations == []
    assert warning == "External AI synthesis is disabled. Controlled retrieval results remain authoritative."


def test_external_provider_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCUMENT_AI_ALLOW_EXTERNAL", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    answer, citations, warning = assistant._openai_synthesis("Where is QAM 51?", [_source()])

    assert answer is None
    assert citations == []
    assert warning == "External AI synthesis is unavailable because no provider key is configured."


def test_openai_synthesis_uses_configured_model_and_never_serializes_key(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            payload = {
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "answer": "Open QAM 51 and verify the controlled form.",
                                        "citations": ["section:rev:sec"],
                                    }
                                ),
                            }
                        ]
                    }
                ]
            }
            return json.dumps(payload).encode("utf-8")

    def fake_open(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

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
    assert url == "/maintenance/SAFARILINK/document-control/library/manual-1?tab=content&revision=revision-2&page=51&anchor=qam-51"


def test_results_are_ranked_and_deduplicated_by_revision_location() -> None:
    first = {**_source("low"), "revision_id": "r1", "section_id": "s1", "score": 5}
    stronger = {**_source("high"), "revision_id": "r1", "section_id": "s1", "score": 50}
    other = {**_source("other"), "revision_id": "r2", "section_id": "s2", "score": 30}

    result = assistant._deduplicate([first, stronger, other], 10)

    assert [row["id"] for row in result] == ["high", "other"]
    assert [row["rank"] for row in result] == [1, 2]


def test_route_contract_filters_access_before_retrieval_and_audits_only_query_hash() -> None:
    source = assistant.inspect.getsource(assistant.assist)
    access_index = source.index("_accessible_context")
    retrieval_index = source.index("_retrieve")
    assert access_index < retrieval_index
    assert "query_sha256" in source
    assert "query_text" not in source
    assert "query" not in source[source.index("ManualAIHookEvent"):]
