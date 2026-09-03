from __future__ import annotations

from .canonical_router import router
from .route_ordering import promote_route_family


def _is_excellence_route(route_item: object) -> bool:
    return "/excellence/" in str(getattr(route_item, "path", ""))


promote_route_family(router, predicate=_is_excellence_route, label="QMS excellence")
