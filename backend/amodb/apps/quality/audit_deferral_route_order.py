from __future__ import annotations

from fastapi import APIRouter

from . import audit_deferral_router
from .canonical_router import router


def _is_deferral_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return "/quality/audit-deferrals" in path or "/qms/audit-deferrals" in path


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _register(api_router: APIRouter) -> None:
    if not any(_is_deferral_route(item) for item in api_router.routes):
        api_router.include_router(audit_deferral_router.router)


def _promote(api_router: APIRouter) -> None:
    routes = [item for item in api_router.routes if _is_deferral_route(item)]
    if not routes:
        raise RuntimeError("QMS audit deferral routes were not registered")
    remaining = [item for item in api_router.routes if not _is_deferral_route(item)]
    catchall_index = next((index for index, item in enumerate(remaining) if _is_generic_catchall(item)), len(remaining))
    api_router.routes[:] = [*remaining[:catchall_index], *routes, *remaining[catchall_index:]]


for api_router in (router,):
    _register(api_router)
    _promote(api_router)

from . import audit_source_handoff_route_order as _audit_source_handoff_route_order  # noqa: F401,E402
