from __future__ import annotations

from amodb.quality_main import OMITTED_OPERATIONAL_MODULES, PROFILE_MODULES, app


def test_quality_delivery_profile_exposes_required_route_families() -> None:
    paths = {route.path for route in app.routes}

    assert "/deployment-profile" in paths
    assert any(path.startswith("/quality") for path in paths)
    assert any(path.startswith("/api/maintenance/{amo_code}/quality") for path in paths)
    assert any(path.startswith("/api/maintenance/{amo_code}/qms") for path in paths)
    assert any(path.startswith("/accounts") for path in paths)
    assert any(path.startswith("/training") for path in paths)
    assert any(path.startswith("/notifications") for path in paths)
    assert any(path.startswith("/tasks") for path in paths)


def test_quality_delivery_profile_omits_unrelated_operational_routes() -> None:
    paths = {route.path for route in app.routes}
    blocked_prefixes = (
        "/fleet",
        "/work",
        "/crs",
        "/reliability",
        "/inventory",
        "/finance",
        "/billing",
        "/technical-records",
        "/rostering",
        "/workforce",
    )

    for prefix in blocked_prefixes:
        assert not any(path == prefix or path.startswith(f"{prefix}/") for path in paths), prefix


def test_quality_delivery_manifest_is_explicit() -> None:
    assert "quality" in PROFILE_MODULES
    assert "training" in PROFILE_MODULES
    assert "audit" in PROFILE_MODULES
    assert "notifications" in PROFILE_MODULES
    assert "tasks" in PROFILE_MODULES
    assert "reliability" in OMITTED_OPERATIONAL_MODULES
    assert "inventory" in OMITTED_OPERATIONAL_MODULES
    assert "finance" in OMITTED_OPERATIONAL_MODULES
