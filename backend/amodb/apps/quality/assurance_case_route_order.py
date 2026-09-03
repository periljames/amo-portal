from __future__ import annotations

from .canonical_router import router
from .route_ordering import promote_route_family


def _is_assurance_case_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return "/quality/assurance-cases" in path or "/qms/assurance-cases" in path


promote_route_family(router, predicate=_is_assurance_case_route, label="QMS assurance cases")
