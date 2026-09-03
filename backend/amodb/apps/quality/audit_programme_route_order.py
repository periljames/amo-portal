from __future__ import annotations

from .canonical_router import router
from .route_ordering import promote_route_family


def _is_audit_programme_route(route_item: object) -> bool:
    path = str(getattr(route_item, "path", ""))
    return "/quality/audit-programmes" in path or "/qms/audit-programmes" in path


promote_route_family(router, predicate=_is_audit_programme_route, label="QMS audit programme")
