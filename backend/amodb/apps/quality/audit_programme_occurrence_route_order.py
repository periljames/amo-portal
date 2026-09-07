from __future__ import annotations

from . import audit_programme_occurrence_router
from .audit_programme_route_order import _promote_audit_programme_routes
from .canonical_router import router


def _is_occurrence_route(route_item: object) -> bool:
    path = str(getattr(route_item, "path", ""))
    return path.endswith("/occurrence-links") or "/occurrences/{occurrence_type}" in path


if not any(_is_occurrence_route(item) for item in router.routes):
    router.include_router(audit_programme_occurrence_router.router)

_promote_audit_programme_routes(router)
