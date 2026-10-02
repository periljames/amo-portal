from __future__ import annotations

from fastapi.routing import APIRoute

from amodb.apps.quality.canonical_router import router as canonical_router
import amodb.apps.quality  # noqa: F401  # ensure route-order modules are installed


def _matching(method: str, suffix: str) -> list[tuple[int, APIRoute]]:
    rows: list[tuple[int, APIRoute]] = []
    for index, route in enumerate(canonical_router.routes):
        if not isinstance(route, APIRoute):
            continue
        if method not in set(route.methods or ()):
            continue
        if str(route.path).endswith(suffix):
            rows.append((index, route))
    return rows


def _generic_post_index() -> int:
    for index, route in enumerate(canonical_router.routes):
        if not isinstance(route, APIRoute):
            continue
        if "POST" in set(route.methods or ()) and str(route.path).endswith("/{module}/{record_id}/{action}"):
            return index
    raise AssertionError("generic Quality workflow route is missing")


def _generic_get_index() -> int:
    for index, route in enumerate(canonical_router.routes):
        if not isinstance(route, APIRoute):
            continue
        if "GET" in set(route.methods or ()) and str(route.path).endswith("/{module_path:path}"):
            return index
    raise AssertionError("generic Quality read route is missing")


def test_authoritative_car_review_precedes_generic_workflow_action() -> None:
    matches = _matching("POST", "/cars/{car_id}/review")
    assert matches, "canonical CAR review route is missing"
    exact_index, route = matches[0]
    assert route.endpoint.__name__ == "review_car_response"
    assert exact_index < _generic_post_index()


def test_audit_personnel_options_precedes_generic_quality_reader() -> None:
    matches = _matching("GET", "/audits/personnel/options")
    assert matches, "canonical audit personnel options route is missing"
    exact_index, route = matches[0]
    assert route.endpoint.__name__ == "list_audit_personnel_options"
    assert exact_index < _generic_get_index()
