from __future__ import annotations

from fastapi import APIRouter

from . import audit_external_access_models as _audit_external_access_models  # noqa: F401
from . import audit_external_access_router
from . import audit_finding_release_status_router
from .canonical_router import legacy_router, router


def _is_external_access_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return (
        "/external-participants" in path
        or path.endswith("/finding-releases")
        or ("/findings/" in path and path.endswith("/release"))
    ) and ("/quality/" in path or "/qms/" in path)


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _register(api_router: APIRouter) -> None:
    if not any("/external-participants" in str(getattr(item, "path", "")) for item in api_router.routes):
        api_router.include_router(audit_external_access_router.router)
    if not any(str(getattr(item, "path", "")).endswith("/finding-releases") for item in api_router.routes):
        api_router.include_router(audit_finding_release_status_router.router)


def _promote(api_router: APIRouter) -> None:
    routes = [item for item in api_router.routes if _is_external_access_route(item)]
    if not routes:
        raise RuntimeError("QMS external audit access routes were not registered")
    remaining = [item for item in api_router.routes if not _is_external_access_route(item)]
    catchall_index = next((index for index, item in enumerate(remaining) if _is_generic_catchall(item)), len(remaining))
    api_router.routes[:] = [*remaining[:catchall_index], *routes, *remaining[catchall_index:]]


for api_router in (router, legacy_router):
    _register(api_router)
    _promote(api_router)
