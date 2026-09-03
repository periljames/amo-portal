from __future__ import annotations

from .canonical_router import router
from .route_ordering import promote_route_family


def _is_planner_route(route_item: object) -> bool:
    path = str(getattr(route_item, "path", ""))
    return "/integrations/calendar" in path or (
        "/audit-programmes/" in path and path.endswith("/schedule")
    )


promote_route_family(router, predicate=_is_planner_route, label="QMS planner")
