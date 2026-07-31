from datetime import datetime, timedelta, timezone

from amodb.apps.platform import metrics


def _network_stub(minutes: int) -> dict:
    return {
        "scope": "host_interfaces",
        "window_minutes": minutes,
        "current_total_bytes_per_second": 0.0,
        "peak_total_bytes_per_second": 0.0,
        "series": [],
    }


def _reset_buckets() -> None:
    with metrics._LOCK:
        metrics._BUCKETS.clear()
        metrics._PERSISTED_CACHE.update({"at": 0.0, "minutes": 0, "rows": []})


def test_route_metrics_summary_contains_real_trend_and_bandwidth_fields(monkeypatch):
    _reset_buckets()
    monkeypatch.setattr(metrics, "_persisted_rows", lambda _minutes: [])
    monkeypatch.setattr(metrics, "_network_summary", _network_stub)
    monkeypatch.setattr(metrics, "_schedule_auto_flush", lambda: None)

    metrics.record_route_metric(
        method="GET",
        route="/platform/test",
        status_code=200,
        duration_ms=25.0,
        tenant_id=None,
        actor_user_id="u1",
        is_platform_route=True,
    )
    summary = metrics.live_summary(minutes=60)

    assert "requests_last_60m" in summary
    assert "requests_per_minute" in summary
    assert "p95_latency_ms" in summary
    assert summary["requests_last_60m"] >= 1
    assert len(summary["trend_series"]) == 60
    assert summary["trend_series"][-1]["requests"] >= 1
    assert summary["current_requests_per_minute"] >= 1
    assert summary["peak_requests_per_minute"] >= summary["current_requests_per_minute"]

    bandwidth = summary["bandwidth"]
    assert bandwidth["scope"] == "host_interfaces"
    assert "current_total_bytes_per_second" in bandwidth
    assert "peak_total_bytes_per_second" in bandwidth
    assert isinstance(bandwidth["series"], list)


def test_persisted_traffic_remains_in_global_latency_percentiles(monkeypatch):
    _reset_buckets()
    now = metrics._bucket_start()
    persisted = [{
        "bucket_start": now,
        "method": "GET",
        "route": "/platform/persisted",
        "tenant_id": None,
        "is_platform_route": True,
        "request_count": 100,
        "success_count": 100,
        "client_error_count": 0,
        "server_error_count": 0,
        "timeout_count": 0,
        "total_duration_ms": 100_000.0,
        "avg_latency_ms": 1_000.0,
        "p95_latency_ms": 2_000.0,
        "p99_latency_ms": 3_000.0,
        "samples": [],
        "source": "persisted",
    }]
    monkeypatch.setattr(metrics, "_persisted_rows", lambda _minutes: persisted)
    monkeypatch.setattr(metrics, "_network_summary", _network_stub)
    monkeypatch.setattr(metrics, "_schedule_auto_flush", lambda: None)

    metrics.record_route_metric(
        method="GET",
        route="/platform/live",
        status_code=200,
        duration_ms=10.0,
        is_platform_route=True,
    )
    summary = metrics.live_summary(minutes=60)

    assert summary["p95_latency_ms"] > 1_900
    assert summary["p99_latency_ms"] > 2_900
    assert summary["requests_in_window"] == 101


def test_timeout_is_a_failure_classification_not_a_second_error(monkeypatch):
    _reset_buckets()
    monkeypatch.setattr(metrics, "_persisted_rows", lambda _minutes: [])
    monkeypatch.setattr(metrics, "_network_summary", _network_stub)
    monkeypatch.setattr(metrics, "_schedule_auto_flush", lambda: None)

    metrics.record_route_metric(
        method="GET",
        route="/platform/timeout",
        status_code=503,
        duration_ms=2_000.0,
        is_platform_route=True,
        timeout=True,
    )
    summary = metrics.live_summary(minutes=60)

    assert summary["failure_count"] == 1
    assert summary["timeout_count"] == 1
    assert summary["error_rate"] == 1.0
    assert summary["trend_series"][-1]["error_rate"] == 1.0


def test_completed_buckets_are_drained_for_api_process_persistence():
    _reset_buckets()
    current = metrics._bucket_start()
    previous = current - timedelta(minutes=1)
    old_key = (previous, "GET", "/platform/old", None, True)
    current_key = (current, "GET", "/platform/current", None, True)
    with metrics._LOCK:
        metrics._BUCKETS[old_key] = {**metrics._new_bucket_row(), "request_count": 2}
        metrics._BUCKETS[current_key] = {**metrics._new_bucket_row(), "request_count": 1}

    payload = metrics._drain_route_metrics(include_current=False)

    assert old_key in payload
    assert current_key not in payload
    with metrics._LOCK:
        assert current_key in metrics._BUCKETS
    _reset_buckets()


def test_auto_flush_runs_inside_the_api_worker_process(monkeypatch):
    started: list[str] = []

    class ThreadStub:
        def __init__(self, *, target, name, daemon):
            assert target is metrics._auto_flush_worker
            assert daemon is True
            self.name = name

        def start(self):
            started.append(self.name)

    monkeypatch.setattr(metrics.threading, "Thread", ThreadStub)
    monkeypatch.setattr(metrics.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(metrics, "_AUTO_FLUSH_INTERVAL_SECONDS", 5.0)
    monkeypatch.setattr(metrics, "_LAST_AUTO_FLUSH_AT", 0.0)
    monkeypatch.setattr(metrics, "_AUTO_FLUSH_IN_FLIGHT", False)

    metrics._schedule_auto_flush()

    assert started == ["platform-metrics-flush"]
    assert metrics._AUTO_FLUSH_IN_FLIGHT is True
