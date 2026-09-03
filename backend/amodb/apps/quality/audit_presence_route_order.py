from __future__ import annotations

from fastapi import APIRouter

from . import audit_presence_models as _audit_presence_models  # noqa: F401
from . import audit_presence_router
from .canonical_router import router
from .router import public_router as quality_public_router

# Presence routes must be promoted ahead of the canonical catch-all.


def _is_presence_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return (
        "/presence" in path
        and ("/audits/" in path or "/audit-access/" in path)
        and ("/quality/" in path or "/qms/" in path)
    )


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _register_and_promote(api_router: APIRouter) -> None:
    if not any(
        "/presence" in str(getattr(item, "path", "")) and "/audits/" in str(getattr(item, "path", ""))
        for item in api_router.routes
    ):
        api_router.include_router(audit_presence_router.router)

    routes = [item for item in api_router.routes if _is_presence_route(item)]
    if not routes:
        raise RuntimeError("QMS audit presence routes were not registered")
    remaining = [item for item in api_router.routes if not _is_presence_route(item)]
    catchall_index = next(
        (index for index, item in enumerate(remaining) if _is_generic_catchall(item)),
        len(remaining),
    )
    api_router.routes[:] = [*remaining[:catchall_index], *routes, *remaining[catchall_index:]]


for _api_router in (router,):
    _register_and_promote(_api_router)

if not any(
    "/quality/audit-access/presence/heartbeat" in str(getattr(item, "path", ""))
    for item in quality_public_router.routes
):
    quality_public_router.include_router(audit_presence_router.public_router)
