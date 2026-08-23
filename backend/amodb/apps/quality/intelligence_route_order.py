from __future__ import annotations

from fastapi import APIRouter

from .canonical_router import router


def _is_intelligence_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return "/quality/intelligence" in path or "/qms/intelligence" in path


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _promote(api_router: APIRouter) -> None:
    routes = [item for item in api_router.routes if _is_intelligence_route(item)]
    if not routes:
        raise RuntimeError("QMS Intelligence routes were not registered")
    remaining = [item for item in api_router.routes if not _is_intelligence_route(item)]
    catchall_index = next((index for index, item in enumerate(remaining) if _is_generic_catchall(item)), len(remaining))
    api_router.routes[:] = [*remaining[:catchall_index], *routes, *remaining[catchall_index:]]


_promote(router)
