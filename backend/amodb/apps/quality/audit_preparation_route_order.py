from __future__ import annotations

from fastapi import APIRouter

from .canonical_router import legacy_router, router


def _is_preparation_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return "/quality/audits/" in path and "/preparation-revisions" in path or "/qms/audits/" in path and "/preparation-revisions" in path


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _promote(api_router: APIRouter) -> None:
    routes = [item for item in api_router.routes if _is_preparation_route(item)]
    if not routes:
        raise RuntimeError("QMS audit preparation routes were not registered")
    remaining = [item for item in api_router.routes if not _is_preparation_route(item)]
    catchall_index = next((index for index, item in enumerate(remaining) if _is_generic_catchall(item)), len(remaining))
    api_router.routes[:] = [*remaining[:catchall_index], *routes, *remaining[catchall_index:]]


_promote(router)
_promote(legacy_router)
