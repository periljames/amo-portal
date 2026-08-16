from __future__ import annotations

from fastapi import APIRouter

from . import audit_session_router
from .canonical_router import legacy_router, router


def _is_session_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return (
        ("/quality/audits/" in path and path.endswith("/session"))
        or ("/qms/audits/" in path and path.endswith("/session"))
    )


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _register(api_router: APIRouter) -> None:
    if not any(_is_session_route(item) for item in api_router.routes):
        api_router.include_router(audit_session_router.router)


def _promote(api_router: APIRouter) -> None:
    routes = [item for item in api_router.routes if _is_session_route(item)]
    if not routes:
        raise RuntimeError("QMS audit session routes were not registered")
    remaining = [item for item in api_router.routes if not _is_session_route(item)]
    catchall_index = next((index for index, item in enumerate(remaining) if _is_generic_catchall(item)), len(remaining))
    api_router.routes[:] = [*remaining[:catchall_index], *routes, *remaining[catchall_index:]]


for api_router in (router, legacy_router):
    _register(api_router)
    _promote(api_router)

# External participants and auditee released-data access are additive to the
# session projection. Loading here guarantees their ORM metadata and canonical
# routes exist without changing the historical central Quality bootstrap order.
from . import audit_external_access_route_order as _audit_external_access_route_order  # noqa: F401,E402
