from __future__ import annotations

from . import audit_risk_planning_router
from .canonical_router import router
from .route_ordering import promote_route_family


def _is_audit_programme_route(route_item: object) -> bool:
    path = str(getattr(route_item, "path", ""))
    return "/quality/audit-programmes" in path or "/qms/audit-programmes" in path


if not any(
    str(getattr(item, "path", "")).endswith("/audit-programmes/risk-context")
    for item in router.routes
):
    router.include_router(audit_risk_planning_router.router)

promote_route_family(router, predicate=_is_audit_programme_route, label="QMS audit programme")

from . import audit_programme_occurrence_route_order as _audit_programme_occurrence_route_order  # noqa: E402,F401
