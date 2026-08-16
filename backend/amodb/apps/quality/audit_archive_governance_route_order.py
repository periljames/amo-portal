from __future__ import annotations

from fastapi import APIRouter

from . import audit_archive_governance_models as _audit_archive_governance_models  # noqa: F401
from . import audit_archive_governance_router
from .canonical_router import legacy_router, router


def _is_archive_governance_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return (
        "/audit-retention-policy" in path
        or ("/audits/" in path and "/archive-governance" in path)
        or ("/audits/" in path and "/archive-manifests" in path)
        or ("/audits/" in path and "/legal-holds/" in path)
    ) and ("/quality/" in path or "/qms/" in path)


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _register(api_router: APIRouter) -> None:
    if not any(_is_archive_governance_route(item) for item in api_router.routes):
        api_router.include_router(audit_archive_governance_router.router)


def _promote(api_router: APIRouter) -> None:
    routes = [item for item in api_router.routes if _is_archive_governance_route(item)]
    if not routes:
        raise RuntimeError("QMS audit archive governance routes were not registered")
    remaining = [item for item in api_router.routes if not _is_archive_governance_route(item)]
    catchall_index = next((index for index, item in enumerate(remaining) if _is_generic_catchall(item)), len(remaining))
    api_router.routes[:] = [*remaining[:catchall_index], *routes, *remaining[catchall_index:]]


for api_router in (router, legacy_router):
    _register(api_router)
    _promote(api_router)
