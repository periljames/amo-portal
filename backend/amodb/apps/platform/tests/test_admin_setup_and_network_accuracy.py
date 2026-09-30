from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from amodb.apps.platform import network_diagnostics, saas_provider_setup, saas_services
from amodb.jobs import platform_monitor


def test_openai_guided_setup_uses_backend_model_allowlists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_DEFAULT_MODEL", "chat-default")
    monkeypatch.setenv("OPENAI_LIGHTWEIGHT_MODEL", "chat-light")
    monkeypatch.setenv("OPENAI_PREMIUM_MODEL", "chat-premium")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "embed-default")
    monkeypatch.setenv("AI_ALLOWED_CHAT_MODELS", "chat-default,chat-light,chat-premium")
    monkeypatch.setenv("AI_ALLOWED_EMBEDDING_MODELS", "embed-default,embed-large")

    setup = saas_provider_setup.provider_setup_schema("openai")
    fields = {field["name"]: field for field in setup["fields"]}

    assert fields["api_key"]["control"] == "password"
    assert fields["api_key"]["required"] is True
    assert fields["default_model"]["default"] == "chat-default"
    assert [item["value"] for item in fields["default_model"]["options"]] == [
        "chat-default", "chat-light", "chat-premium"
    ]
    assert [item["value"] for item in fields["embedding_model"]["options"]] == [
        "embed-default", "embed-large"
    ]
    assert fields["api_base_url"]["advanced"] is True


def test_provider_partial_config_update_preserves_hidden_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    row = SimpleNamespace(
        id="provider-1",
        provider="openai",
        tenant_id=None,
        status="CONFIGURED",
        config_json={"api_base_url": "https://proxy.example.com", "project": "project-1"},
        encrypted_secret="encrypted",
        secret_fingerprint="fingerprint",
        configured_at=None,
        updated_by=None,
    )
    db = MagicMock()
    monkeypatch.setattr(saas_services, "get_provider_credential", lambda *args, **kwargs: row)
    monkeypatch.setattr(saas_services, "provider_payload", lambda value: dict(value.config_json))
    monkeypatch.setattr(saas_services.saas_secrets, "decrypt_secret", lambda value: {"api_key": "stored"})

    payload = saas_services.upsert_provider_credential(
        db,
        provider="openai",
        payload={"config": {"default_model": "gpt-5-mini"}, "enabled": True},
        actor_user_id="root-1",
    )

    assert payload == {
        "api_base_url": "https://proxy.example.com",
        "project": "project-1",
        "default_model": "gpt-5-mini",
    }


@pytest.mark.parametrize("host", ["http://speed.cloudflare.com", "localhost", "127.0.0.1", "10.0.0.4", "speed.cloudflare.com/path"])
def test_speedtest_host_rejects_unsafe_targets(host: str) -> None:
    with pytest.raises(ValueError):
        network_diagnostics._validated_host(host)


def test_speedtest_host_accepts_public_https_target() -> None:
    assert network_diagnostics._validated_host("https://speed.cloudflare.com") == "speed.cloudflare.com"


def test_speedtest_http_transfer_uses_provider_compatible_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    requests = []

    class FakeResponse:
        headers = {"cf-ray": "test-NBO"}

        def __init__(self) -> None:
            self._chunks = [b"abc", b""]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self, _size: int) -> bytes:
            return self._chunks.pop(0)

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(network_diagnostics.urllib.request, "urlopen", fake_urlopen)

    received, headers = network_diagnostics._http_transfer(
        "https://speed.cloudflare.com/__down?bytes=3"
    )
    assert received == 3
    assert headers["cf-ray"] == "test-NBO"
    download_request = requests[-1][0]
    assert download_request.get_method() == "GET"
    assert download_request.get_header("Accept") == "*/*"
    assert download_request.get_header("User-agent") == network_diagnostics.HTTP_USER_AGENT
    assert download_request.get_header("Content-type") is None

    network_diagnostics._http_transfer(
        "https://speed.cloudflare.com/__up",
        payload=b"abc",
    )
    upload_request = requests[-1][0]
    assert upload_request.get_method() == "POST"
    assert upload_request.get_header("Content-type") == "application/octet-stream"


def test_stability_requires_a_settled_sample_window() -> None:
    assert network_diagnostics._is_stable([100, 102, 99, 101]) is True
    assert network_diagnostics._is_stable([100, 160, 90, 145]) is False
    assert network_diagnostics._is_stable([100, 101, 99]) is False


def test_scheduled_network_cycle_persists_provider_rejection_and_continues_database_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = MagicMock()
    internet = {
        "ok": False,
        "download_bps": None,
        "error": "HTTP Error 403: Forbidden",
        "details": {"failure_kind": "provider_rejected", "http_status": 403},
    }
    database = {"ok": True, "latency_ms": 2.5}
    persisted: list[tuple[str, dict]] = []

    monkeypatch.setattr(platform_monitor, "WriteSessionLocal", lambda: db)
    monkeypatch.setattr(platform_monitor.network_diagnostics, "run_internet_speedtest", lambda: internet)
    monkeypatch.setattr(platform_monitor.network_diagnostics, "run_database_throughput", lambda value: database)
    monkeypatch.setattr(
        platform_monitor.network_diagnostics,
        "persist_probe",
        lambda value, *, scenario, source, data: persisted.append((scenario, data)),
    )
    monkeypatch.setattr(platform_monitor.network_diagnostics, "prune", lambda value, *, days: 0)
    monkeypatch.setattr(platform_monitor, "_touch_heartbeat", lambda *args, **kwargs: None)

    result = platform_monitor.run_network_probes_once(prune_days=30)

    assert result == {
        "internet_download_mbps": 0.0,
        "internet_ok": False,
        "database_latency_ms": 2.5,
    }
    assert persisted == [
        ("server_internet", internet),
        ("server_database", database),
    ]
    db.commit.assert_called()
    db.close.assert_called_once()
