from __future__ import annotations

from amodb.main import app


def test_main_application_mounts_workforce_and_rostering_routes():
    paths = {route.path for route in app.routes}
    assert "/workforce/employment-contracts" in paths
    assert "/workforce/leave-requests" in paths
    assert "/rostering/dashboard" in paths
    assert "/rostering/versions/{version_id}/publish" in paths


def test_main_application_has_one_route_per_method_and_path():
    required_pairs = (
        ("GET", "/workforce/employment-contracts"),
        ("POST", "/workforce/employment-contracts"),
        ("GET", "/workforce/leave-requests"),
        ("POST", "/workforce/leave-requests"),
        ("GET", "/rostering/dashboard"),
        ("GET", "/rostering/planning-board"),
    )
    for method, path in required_pairs:
        matches = [
            route
            for route in app.routes
            if route.path == path and method in getattr(route, "methods", set())
        ]
        assert len(matches) == 1, f"Expected one {method} {path} route, found {len(matches)}"
