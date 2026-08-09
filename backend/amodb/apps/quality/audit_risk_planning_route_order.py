from __future__ import annotations

from fastapi import APIRouter

from . import audit_risk_planning_router
from .canonical_router import legacy_router, router


def _is_risk_planning_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return path.endswith("/audit-programmes/risk-context")


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _register(api_router: APIRouter) -> None:
    if not any(_is_risk_planning_route(item) for item in api_router.routes):
        api_router.include_router(audit_risk_planning_router.router)


def _promote(api_router: APIRouter) -> None:
    routes = [item for item in api_router.routes if _is_risk_planning_route(item)]
    if not routes:
        raise RuntimeError("QMS risk planning context route was not registered")
    remaining = [item for item in api_router.routes if not _is_risk_planning_route(item)]
    catchall_index = next((index for index, item in enumerate(remaining) if _is_generic_catchall(item)), len(remaining))
    api_router.routes[:] = [*remaining[:catchall_index], *routes, *remaining[catchall_index:]]


for api_router in (router, legacy_router):
    _register(api_router)
    _promote(api_router)

from . import audit_programme_occurrence_route_order as _audit_programme_occurrence_route_order  # noqa: F401,E402
