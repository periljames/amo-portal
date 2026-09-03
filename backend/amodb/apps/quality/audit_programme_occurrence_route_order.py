from __future__ import annotations

from . import audit_programme_occurrence_router
from .canonical_router import router
from .route_ordering import promote_route_family


def _is_audit_programme_route(route_item: object) -> bool:
    path = str(getattr(route_item, "path", ""))
    return "/quality/audit-programmes" in path or "/qms/audit-programmes" in path


def _is_occurrence_route(route_item: object) -> bool:
    path = str(getattr(route_item, "path", ""))
    return path.endswith("/occurrence-links") or "/occurrences/{occurrence_type}" in path


if not any(_is_occurrence_route(item) for item in router.routes):
    router.include_router(audit_programme_occurrence_router.router)

promote_route_family(router, predicate=_is_audit_programme_route, label="QMS audit programme")
