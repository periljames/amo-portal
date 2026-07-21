from __future__ import annotations

from amodb.apps.rostering.application_router import router


def route_methods():
    return {
        (method, route.path)
        for route in router.routes
        for method in (getattr(route, "methods", None) or set())
    }


def test_canonical_workforce_routes_are_registered_as_siblings():
    routes = route_methods()
    required = {
        ("GET", "/workforce/permissions/current"),
        ("GET", "/workforce/employment-contracts"),
        ("POST", "/workforce/work-patterns"),
        ("POST", "/workforce/leave-requests"),
        ("POST", "/workforce/attendance-events"),
        ("POST", "/workforce/timesheets/generate"),
        ("GET", "/workforce/payroll-export"),
    }
    assert required.issubset(routes)
    assert not any(path.startswith("/rostering/workforce/") for _, path in routes)


def test_complete_roster_lifecycle_and_planner_routes_exist():
    routes = route_methods()
    required = {
        ("GET", "/rostering/dashboard"),
        ("GET", "/rostering/planning-board"),
        ("GET", "/rostering/my-roster"),
        ("POST", "/rostering/periods/{period_id}/versions"),
        ("POST", "/rostering/versions/{version_id}/assignments/bulk"),
        ("POST", "/rostering/versions/{version_id}/generate-from-pattern"),
        ("POST", "/rostering/versions/{version_id}/validate"),
        ("POST", "/rostering/versions/{version_id}/submit"),
        ("POST", "/rostering/versions/{version_id}/approve"),
        ("POST", "/rostering/versions/{version_id}/publish"),
        ("POST", "/rostering/versions/{version_id}/acknowledge"),
        ("POST", "/rostering/findings/{finding_id}/override"),
        ("GET", "/rostering/reports/export"),
    }
    assert required.issubset(routes)


def test_no_duplicate_method_path_contracts():
    pairs = [
        (method, route.path)
        for route in router.routes
        for method in (getattr(route, "methods", None) or set())
    ]
    duplicates = {pair for pair in pairs if pairs.count(pair) > 1}
    # PUT compatibility aliases intentionally share business handlers but do
    # not duplicate the same HTTP method/path pair.
    assert duplicates == set()
