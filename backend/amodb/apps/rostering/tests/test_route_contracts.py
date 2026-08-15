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
        ("PATCH", "/workforce/work-pattern-assignments/{assignment_id}"),
        ("DELETE", "/workforce/work-pattern-assignments/{assignment_id}"),
        ("POST", "/workforce/leave-requests"),
        ("GET", "/workforce/leave-requests/export"),
        ("POST", "/workforce/attendance-events"),
        ("GET", "/workforce/attendance-events/export"),
        ("POST", "/workforce/timesheets/generate"),
        ("GET", "/workforce/payroll-export"),
        ("GET", "/workforce/hr/dashboard"),
        ("GET", "/workforce/hr/work-patterns"),
        ("POST", "/workforce/hr/work-pattern-assignments"),
    }
    assert required.issubset(routes)
    assert not any(path.startswith("/rostering/workforce/") for _, path in routes)


def test_roster_setup_and_automation_routes_are_registered():
    routes = route_methods()
    required = {
        ("GET", "/rostering/setup/readiness"),
        ("GET", "/rostering/automation-policy"),
        ("PATCH", "/rostering/automation-policy"),
        ("POST", "/rostering/automation/preview"),
        ("POST", "/rostering/automation/run"),
        ("GET", "/rostering/automation/runs"),
    }
    assert required.issubset(routes)


def test_complete_roster_lifecycle_and_planner_routes_exist():
    routes = route_methods()
    required = {
        ("GET", "/rostering/dashboard"),
        ("GET", "/rostering/planning-board"),
        ("GET", "/rostering/my-roster"),
        ("GET", "/rostering/commitments"),
        ("POST", "/rostering/periods/{period_id}/versions"),
        ("POST", "/rostering/versions/{version_id}/assignments/bulk"),
        ("POST", "/rostering/versions/{version_id}/generate-from-pattern"),
        ("GET", "/rostering/versions/{version_id}/coverage-recommendations"),
        ("POST", "/rostering/versions/{version_id}/coverage-recommendations/apply"),
        ("DELETE", "/rostering/demand-requirements/{requirement_id}"),
        ("DELETE", "/rostering/assignments/{assignment_id}/task-links/{link_id}"),
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
