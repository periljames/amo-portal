from __future__ import annotations

from .canonical_router import router
from .route_ordering import promote_route_family


def _is_people_route(route_item: object) -> bool:
    path = str(getattr(route_item, "path", ""))
    return "/quality/people" in path or "/qms/people" in path


promote_route_family(router, predicate=_is_people_route, label="QMS people and privileges")
