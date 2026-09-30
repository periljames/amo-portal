from __future__ import annotations

from datetime import datetime, timezone
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
        "internet_download_mbps": None,
        "internet_ok": False,
        "internet_error": "HTTP Error 403: Forbidden",
        "internet_failure_kind": "provider_rejected",
        "database_latency_ms": 2.5,
    }
    assert persisted == [
        ("server_internet", internet),
        ("server_database", database),
    ]
    db.commit.assert_called()
    db.close.assert_called_once()


def _adaptive_row(
    *,
    download_bps: float = 100_000_000.0,
    latency_ms: float = 20.0,
    anomalous: bool = False,
    ok: bool = True,
):
    return SimpleNamespace(
        download_bps=download_bps,
        latency_ms=latency_ms,
        ok=ok,
        details_json={"adaptive": {"anomalous": anomalous}},
    )


def test_adaptive_network_policy_backs_off_to_two_hours_when_deeply_stable() -> None:
    previous = [
        _adaptive_row(download_bps=100_000_000.0 + (index % 3) * 500_000.0, latency_ms=20.0 + (index % 2))
        for index in range(20)
    ]
    current = {
        "ok": True,
        "download_bps": 100_500_000.0,
        "latency_ms": 20.5,
        "details": {"sample_kind": "sentinel"},
    }

    policy = platform_monitor._adaptive_network_policy(current, previous)

    assert policy["state"] == "deep_stable"
    assert policy["next_delay_seconds"] == 7200.0
    assert policy["anomalous"] is False
    assert policy["ema_span"] == 20


def test_adaptive_network_policy_escalates_to_one_minute_on_real_deviation() -> None:
    previous = [_adaptive_row() for _ in range(10)]
    current = {
        "ok": True,
        "download_bps": 50_000_000.0,
        "latency_ms": 20.0,
        "details": {"sample_kind": "sentinel"},
    }

    policy = platform_monitor._adaptive_network_policy(current, previous)

    assert policy["state"] == "investigating"
    assert policy["next_delay_seconds"] == 60.0
    assert policy["anomalous"] is True
    assert "download_drop" in policy["reasons"]
    assert policy["confirmed_anomaly"] is False


def test_adaptive_network_policy_requires_consecutive_anomalies_before_heavy_confirmation() -> None:
    previous = [_adaptive_row(download_bps=50_000_000.0, anomalous=True)] + [
        _adaptive_row() for _ in range(9)
    ]
    current = {
        "ok": True,
        "download_bps": 50_000_000.0,
        "latency_ms": 20.0,
        "details": {"sample_kind": "sentinel"},
    }

    policy = platform_monitor._adaptive_network_policy(current, previous)

    assert policy["anomalous"] is True
    assert policy["confirmed_anomaly"] is True


def test_provider_rejection_backs_off_without_marking_network_slow() -> None:
    previous = [_adaptive_row() for _ in range(10)]
    current = {
        "ok": False,
        "download_bps": None,
        "latency_ms": None,
        "details": {"sample_kind": "sentinel", "failure_kind": "provider_rejected"},
    }

    policy = platform_monitor._adaptive_network_policy(current, previous)

    assert policy["state"] == "provider_unavailable"
    assert policy["next_delay_seconds"] == 3600.0
    assert policy["provider_unavailable"] is True
    assert policy["anomalous"] is False
    assert policy["confirmed_anomaly"] is False


def test_adaptive_probe_bootstraps_full_measurement_without_repeating_bulk_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = MagicMock()
    previous_query = MagicMock()
    previous_query.filter.return_value = previous_query
    previous_query.order_by.return_value = previous_query
    previous_query.limit.return_value = previous_query
    previous_query.all.return_value = []

    full_query = MagicMock()
    full_query.filter.return_value = full_query
    full_query.order_by.return_value = full_query
    full_query.limit.return_value = full_query
    full_query.all.return_value = []
    db.query.side_effect = [previous_query, full_query]

    sentinel = {
        "ok": True,
        "download_bps": 80_000_000.0,
        "latency_ms": 18.0,
        "details": {"sample_kind": "sentinel"},
    }
    database_sentinel = {
        "ok": True,
        "latency_ms": 2.0,
        "details": {"sample_kind": "sentinel"},
    }
    full_internet = {
        "ok": True,
        "download_bps": 90_000_000.0,
        "details": {"sample_kind": "full"},
    }
    full_database = {
        "ok": True,
        "latency_ms": 1.5,
        "details": {"sample_kind": "full"},
    }
    persisted: list[tuple[str, str, dict]] = []

    monkeypatch.setattr(platform_monitor, "WriteSessionLocal", lambda: db)
    monkeypatch.setattr(platform_monitor, "_touch_heartbeat", lambda *args, **kwargs: None)
    monkeypatch.setattr(platform_monitor.network_diagnostics, "run_internet_sentinel", lambda: sentinel)
    monkeypatch.setattr(platform_monitor.network_diagnostics, "run_database_latency_probe", lambda value: database_sentinel)
    monkeypatch.setattr(platform_monitor.network_diagnostics, "run_internet_speedtest", lambda: full_internet)
    monkeypatch.setattr(platform_monitor.network_diagnostics, "run_database_throughput", lambda value: full_database)
    monkeypatch.setattr(platform_monitor.network_diagnostics, "prune", lambda value, *, days: 0)
    monkeypatch.setattr(
        platform_monitor.network_diagnostics,
        "persist_probe",
        lambda value, *, scenario, source, data: persisted.append((scenario, source, data)),
    )

    result = platform_monitor.run_adaptive_network_probe_once(prune_days=30)

    assert result is not None
    assert result["full_probe_ran"] is True
    assert result["full_probe_reason"] == "bootstrap"
    assert result["adaptive_state"] == "recovery"
    assert result["next_delay_seconds"] == 900.0
    assert [item[:2] for item in persisted] == [
        ("server_internet", "scheduled_light"),
        ("server_database", "scheduled_light"),
        ("server_internet", "scheduled_full"),
        ("server_database", "scheduled_full"),
    ]


def test_adaptive_probe_does_not_escalate_provider_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = MagicMock()
    previous_query = MagicMock()
    previous_query.filter.return_value = previous_query
    previous_query.order_by.return_value = previous_query
    previous_query.limit.return_value = previous_query
    previous_query.all.return_value = []

    full_query = MagicMock()
    full_query.filter.return_value = full_query
    full_query.order_by.return_value = full_query
    full_query.limit.return_value = full_query
    full_query.all.return_value = []
    db.query.side_effect = [previous_query, full_query]

    sentinel = {
        "ok": False,
        "download_bps": None,
        "latency_ms": None,
        "error": "HTTP Error 403: Forbidden",
        "details": {"sample_kind": "sentinel", "failure_kind": "provider_rejected"},
    }
    database_sentinel = {
        "ok": True,
        "latency_ms": 2.0,
        "details": {"sample_kind": "sentinel"},
    }

    monkeypatch.setattr(platform_monitor, "WriteSessionLocal", lambda: db)
    monkeypatch.setattr(platform_monitor, "_touch_heartbeat", lambda *args, **kwargs: None)
    monkeypatch.setattr(platform_monitor.network_diagnostics, "run_internet_sentinel", lambda: sentinel)
    monkeypatch.setattr(platform_monitor.network_diagnostics, "run_database_latency_probe", lambda value: database_sentinel)
    monkeypatch.setattr(platform_monitor.network_diagnostics, "run_internet_speedtest", MagicMock())
    monkeypatch.setattr(platform_monitor.network_diagnostics, "run_database_throughput", MagicMock())
    monkeypatch.setattr(platform_monitor.network_diagnostics, "persist_probe", lambda *args, **kwargs: None)

    result = platform_monitor.run_adaptive_network_probe_once(prune_days=30)

    assert result is not None
    assert result["adaptive_state"] == "provider_unavailable"
    assert result["next_delay_seconds"] == 3600.0
    assert result["full_probe_ran"] is False
    platform_monitor.network_diagnostics.run_internet_speedtest.assert_not_called()
    platform_monitor.network_diagnostics.run_database_throughput.assert_not_called()


def test_network_history_excludes_sentinels_from_throughput_aggregates() -> None:
    now = datetime.now(timezone.utc)
    sentinel = SimpleNamespace(
        captured_at=now,
        scenario="server_internet",
        source="scheduled_light",
        target="speed.cloudflare.com",
        ok=True,
        latency_ms=20.0,
        jitter_ms=1.0,
        download_bps=10_000_000.0,
        upload_bps=None,
        error=None,
        details_json={"sample_kind": "sentinel"},
    )
    full = SimpleNamespace(
        captured_at=now,
        scenario="server_internet",
        source="scheduled_full",
        target="speed.cloudflare.com",
        ok=True,
        latency_ms=21.0,
        jitter_ms=1.5,
        download_bps=100_000_000.0,
        upload_bps=50_000_000.0,
        error=None,
        details_json={"sample_kind": "full"},
    )
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = [sentinel, full]
    db = MagicMock()
    db.query.return_value = query

    payload = network_diagnostics.history(
        db,
        window="24h",
        scenario="server_internet",
        sla_download_mbps=80.0,
    )

    history = payload["scenarios"]["server_internet"]
    assert history["download_mbps"]["avg"] == 100.0
    assert history["upload_mbps"]["avg"] == 50.0
    assert history["download_mbps"]["samples"] == 1
    assert history["sentinel_samples"] == 1
    assert history["full_samples"] == 1
    assert history["sla_breaches"] == 0
