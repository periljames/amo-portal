from datetime import datetime, timedelta, timezone

from amodb.apps.reliability.router import router
from amodb.apps.reliability.services import _reliability_freshness


def test_router_exposes_one_canonical_reliability_surface():
    paths = {route.path for route in router.routes}
    assert "/reliability/workbench" in paths
    assert "/reliability/events" in paths
    assert "/reliability/events/{event_id:int}" in paths
    assert "/reliability/alerts" in paths
    assert "/reliability/alerts/{alert_id:int}" in paths
    assert "/reliability/fracas/cases" in paths
    assert "/reliability/fracas/cases/{case_id:int}" in paths
    assert "/reliability/fracas/cases/{case_id:int}/actions" in paths
    assert "/reliability/engine-trends/fleet-status" in paths
    assert all("/v2" not in route_path for route_path in paths)
    assert "/reliability/fracas/{fracas_case_id}/actions" not in paths


def test_freshness_never_marks_missing_data_current():
    now = datetime(2026, 8, 3, tzinfo=timezone.utc)
    missing = _reliability_freshness(source="Missing", latest=None, now=now)
    stale = _reliability_freshness(source="Stale", latest=now - timedelta(days=8), now=now)
    current = _reliability_freshness(source="Current", latest=now - timedelta(days=1), now=now)
    assert missing.status == "MISSING"
    assert stale.status == "STALE"
    assert current.status == "CURRENT"
