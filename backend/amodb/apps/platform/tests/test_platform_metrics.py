from amodb.apps.platform.metrics import live_summary, record_route_metric


def test_route_metrics_summary_contains_throughput_fields():
    record_route_metric(method="GET", route="/platform/test", status_code=200, duration_ms=25.0, tenant_id=None, actor_user_id="u1", is_platform_route=True)
    summary = live_summary(minutes=60)
    assert "requests_last_60m" in summary
    assert "requests_per_minute" in summary
    assert "p95_latency_ms" in summary
    assert summary["requests_last_60m"] >= 1
