from __future__ import annotations

from fastapi import APIRouter

from . import audit_presence_models as _audit_presence_models  # noqa: F401
from . import audit_presence_router
from .canonical_router import router
from .router import public_router as quality_public_router


def _is_presence_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return "/audits/" in path and "/presence" in path and "/quality/" in path


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _register(api_router: APIRouter) -> None:
    if not any(_is_presence_route(item) for item in api_router.routes):
        api_router.include_router(audit_presence_router.router)


def _promote(api_router: APIRouter) -> None:
    routes = [item for item in api_router.routes if _is_presence_route(item)]
    if not routes:
        raise RuntimeError("QMS audit presence routes were not registered")
    remaining = [item for item in api_router.routes if not _is_presence_route(item)]
    catchall_index = next((index for index, item in enumerate(remaining) if _is_generic_catchall(item)), len(remaining))
    api_router.routes[:] = [*remaining[:catchall_index], *routes, *remaining[catchall_index:]]


_register(router)
_promote(router)

if not any("/quality/audit-access/presence/heartbeat" in str(getattr(item, "path", "")) for item in quality_public_router.routes):
    quality_public_router.include_router(audit_presence_router.public_router)
