from __future__ import annotations

from amodb.main import app


def test_main_application_mounts_workforce_and_rostering_routes():
    paths = {route.path for route in app.routes}
    assert "/workforce/employment-contracts" in paths
    assert "/workforce/leave-requests" in paths
    assert "/rostering/dashboard" in paths
    assert "/rostering/versions/{version_id}/publish" in paths


def test_main_application_has_only_one_copy_of_each_new_route():
    paths = [route.path for route in app.routes]
    for required in (
        "/workforce/employment-contracts",
        "/workforce/leave-requests",
        "/rostering/dashboard",
        "/rostering/planning-board",
    ):
        assert paths.count(required) == 1
