from __future__ import annotations

from fastapi import APIRouter

from .canonical_router import router


def _is_guard_route(route_item) -> bool:
    endpoint = getattr(route_item, "endpoint", None)
    return bool(endpoint and getattr(endpoint, "__module__", "") == "amodb.apps.quality.planner_assignment_guard_router")


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _signature(route_item) -> tuple[str, frozenset[str]]:
    return (
        str(getattr(route_item, "path", "")),
        frozenset(getattr(route_item, "methods", None) or ()),
    )


def _promote(api_router: APIRouter) -> None:
    guard_routes = [item for item in api_router.routes if _is_guard_route(item)]
    if not guard_routes:
        raise RuntimeError("QMS governed planner assignment routes were not registered")
    guard_signatures = {_signature(item) for item in guard_routes}
    remaining = [
        item
        for item in api_router.routes
        if not _is_guard_route(item) and _signature(item) not in guard_signatures
    ]
    catchall_index = next(
        (index for index, item in enumerate(remaining) if _is_generic_catchall(item)),
        len(remaining),
    )
    api_router.routes[:] = [*remaining[:catchall_index], *guard_routes, *remaining[catchall_index:]]


_promote(router)
