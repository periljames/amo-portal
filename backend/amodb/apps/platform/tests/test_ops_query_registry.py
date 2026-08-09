from __future__ import annotations

import time

import pytest

from amodb.apps.platform import ops_query_registry as registry


def setup_function():
    registry._CACHE.clear()
    registry._LAST_GOOD.clear()


def test_registry_never_contains_tenant_or_user_cardinality():
    forbidden = {"tenant_id", "user_id", "email", "document_id", "work_order_id", "authorization", "token"}
    assert registry.QUERY_REGISTRY
    for name, spec in registry.QUERY_REGISTRY.items():
        expression = spec.expression.lower()
        assert not any(value in expression for value in forbidden), (name, expression)
        assert spec.max_samples <= 2000
        assert spec.timeout_seconds <= 2.0
        assert spec.cache_ttl_seconds > 0


def test_historical_ranges_are_server_controlled(monkeypatch):
    captured = {}

    def fake_request(path, params, *, timeout):
        captured.update({"path": path, "params": params, "timeout": timeout})
        return {"status": "success", "data": {"result": [{"metric": {"instance": "node-a:9100"}, "values": [[1, "10"], [2, "11"]]}]}}

    monkeypatch.setattr(registry, "_request", fake_request)
    result = registry.query_range("host_cpu_utilization", "30d", end_epoch=2_000_000_000)

    assert captured["path"] == "/api/v1/query_range"
    assert captured["params"]["step"] >= 7200
    assert result["max_samples"] <= 2000
    assert result["series"][0]["labels"]["instance"] == "node-a:9100"


def test_arbitrary_promql_is_rejected():
    with pytest.raises(KeyError):
        registry.query_instant('up or vector(1)')
    with pytest.raises(ValueError):
        registry.query_range("host_cpu_utilization", "365d")


def test_query_failure_serves_last_known_snapshot(monkeypatch):
    calls = 0

    def fake_request(path, params, *, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"status": "success", "data": {"result": [{"metric": {"instance": "node-a"}, "value": [time.time(), "42"]}]}}
        raise TimeoutError("prometheus unavailable")

    monkeypatch.setattr(registry, "_request", fake_request)
    first = registry.query_instant("host_load_1m")
    assert first["available"] is True
    assert first["stale"] is False

    registry._CACHE.clear()
    second = registry.query_instant("host_load_1m")
    assert second["available"] is True
    assert second["stale"] is True
    assert "prometheus unavailable" in second["error"]
