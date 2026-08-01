from __future__ import annotations

from amodb.apps.quality.canonical_router import router as canonical_router
from amodb.apps.quality.dashboard_v2 import DASHBOARD_V2_CONTRACT, _build_action_queue


def test_operational_dashboard_route_is_registered() -> None:
    paths = {str(getattr(route, "path", "")) for route in canonical_router.routes}
    assert "/api/maintenance/{amo_code}/quality/dashboard-v2" in paths
    assert DASHBOARD_V2_CONTRACT == "qms-operational-dashboard.v2"


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
