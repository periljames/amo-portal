from __future__ import annotations

from . import audit_risk_planning_router
from .audit_programme_route_order import _promote_audit_programme_routes
from .canonical_router import router


if not any(
    str(getattr(item, "path", "")).endswith("/audit-programmes/risk-context")
    for item in router.routes
):
    router.include_router(audit_risk_planning_router.router)

_promote_audit_programme_routes(router)

from . import audit_programme_occurrence_route_order as _audit_programme_occurrence_route_order  # noqa: E402,F401
