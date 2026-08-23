from __future__ import annotations

from starlette.routing import Match

from amodb.apps.quality.canonical_router import router as canonical_router
from amodb.apps.quality.dashboard_v2 import (
    DASHBOARD_V2_CONTRACT,
    _build_action_queue,
    qms_operational_dashboard_v2,
)


def _first_matching_endpoint(api_router, path: str):
    scope = {
        "type": "http",
        "path": path,
        "root_path": "",
        "method": "GET",
        "scheme": "http",
        "query_string": b"",
        "headers": [],
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
    }
    for route in api_router.routes:
        match, _ = route.matches(scope)
        if match == Match.FULL:
            return getattr(route, "endpoint", None)
    return None


def test_operational_dashboard_route_is_registered() -> None:
    canonical_path = "/api/maintenance/SAF/quality/dashboard-v2"
    assert _first_matching_endpoint(canonical_router, canonical_path) is qms_operational_dashboard_v2
    assert DASHBOARD_V2_CONTRACT == "qms-operational-dashboard.v2"


def test_operational_dashboard_route_is_before_module_catchall() -> None:
    for api_router in (canonical_router,):
        dashboard_index = next(
            index
            for index, route in enumerate(api_router.routes)
            if getattr(route, "endpoint", None) is qms_operational_dashboard_v2
        )
        catchall_index = next(
            index
            for index, route in enumerate(api_router.routes)
            if str(getattr(route, "path", "")).endswith("/{module_path:path}")
            and "GET" in set(getattr(route, "methods", None) or ())
        )
        assert dashboard_index < catchall_index


def test_action_queue_is_ranked_and_bounded() -> None:
    queue = _build_action_queue(
        amo_code="SAF",
        counters={
            "overdue_cars": 4,
            "training_expired_records": 5,
            "cars_due_soon": 8,
            "audits_due_soon": 2,
            "open_findings": 9,
        },
        oldest_car_age=18,
        car_unassigned=1,
        oldest_training_age=12,
        finding_unassigned=0,
    )

    assert len(queue) == 5
    assert [item["id"] for item in queue[:2]] == ["overdue-cars", "expired-training"]
    assert queue[0]["oldest_age_days"] == 18
    assert queue[0]["owner_status"] == "partially_assigned"
    assert queue[0]["route"] == "/maintenance/SAF/quality/cars/overdue"


def test_action_queue_omits_zero_count_items() -> None:
    queue = _build_action_queue(
        amo_code="SAF",
        counters={"overdue_cars": 0, "training_expired_records": 0, "open_findings": 3},
        oldest_car_age=None,
        car_unassigned=None,
        oldest_training_age=None,
        finding_unassigned=3,
    )

    assert [item["id"] for item in queue] == ["open-findings"]
    assert queue[0]["owner_status"] == "unassigned"
