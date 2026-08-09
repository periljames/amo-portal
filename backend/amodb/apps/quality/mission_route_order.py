from __future__ import annotations

from fastapi import APIRouter

from .canonical_router import legacy_router, router


def _is_mission_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return "/quality/missions" in path or "/qms/missions" in path


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _route_signature(route_item) -> tuple[str, frozenset[str]]:
    return (
        str(getattr(route_item, "path", "")),
        frozenset(getattr(route_item, "methods", None) or ()),
    )


def _promote_mission_routes(api_router: APIRouter) -> None:
    registered = [route_item for route_item in api_router.routes if _is_mission_route(route_item)]
    if not registered:
        raise RuntimeError("QMS Mission routes were not registered")

    selected_reversed = []
    seen: set[tuple[str, frozenset[str]]] = set()
    for route_item in reversed(registered):
        signature = _route_signature(route_item)
        if signature in seen:
            continue
        seen.add(signature)
        selected_reversed.append(route_item)
    mission_routes = list(reversed(selected_reversed))

    remaining = [route_item for route_item in api_router.routes if not _is_mission_route(route_item)]
    catchall_index = next(
        (index for index, route_item in enumerate(remaining) if _is_generic_catchall(route_item)),
        len(remaining),
    )
    api_router.routes[:] = [
        *remaining[:catchall_index],
        *mission_routes,
        *remaining[catchall_index:],
    ]


_promote_mission_routes(router)
_promote_mission_routes(legacy_router)
