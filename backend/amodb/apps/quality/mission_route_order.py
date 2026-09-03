from __future__ import annotations

from .canonical_router import router
from .route_ordering import promote_route_family


def _is_mission_route(route_item: object) -> bool:
    path = str(getattr(route_item, "path", ""))
    return "/quality/missions" in path or "/qms/missions" in path


promote_route_family(router, predicate=_is_mission_route, label="QMS missions")
