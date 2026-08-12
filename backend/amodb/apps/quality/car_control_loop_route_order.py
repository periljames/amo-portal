from __future__ import annotations

from fastapi import APIRouter

from .canonical_router import legacy_router, router
from . import car_control_loop_session_context as _car_control_loop_session_context  # noqa: F401,E402
from . import car_control_loop_authority_guard as _car_control_loop_authority_guard  # noqa: E402


# Reviewer/closure authority routes are registered after the base and sequence
# guards so the route-order pass below retains these stricter handlers for the
# overlapping milestone-decision and close operations.
router.include_router(_car_control_loop_authority_guard.router)
legacy_router.include_router(_car_control_loop_authority_guard.router)


def _is_control_loop_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return "/cars/" in path and "/control-loop" in path and ("/quality/" in path or "/qms/" in path)


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _route_signature(route_item) -> tuple[str, frozenset[str]]:
    return (
        str(getattr(route_item, "path", "")),
        frozenset(getattr(route_item, "methods", None) or ()),
    )


def _promote_control_loop_routes(api_router: APIRouter) -> None:
    registered = [route_item for route_item in api_router.routes if _is_control_loop_route(route_item)]
    if not registered:
        raise RuntimeError("QMS CAR control-loop routes were not registered")

    selected_reversed = []
    seen: set[tuple[str, frozenset[str]]] = set()
    for route_item in reversed(registered):
        signature = _route_signature(route_item)
        if signature in seen:
            continue
        seen.add(signature)
        selected_reversed.append(route_item)
    selected = list(reversed(selected_reversed))

    remaining = [route_item for route_item in api_router.routes if not _is_control_loop_route(route_item)]
    catchall_index = next(
        (index for index, route_item in enumerate(remaining) if _is_generic_catchall(route_item)),
        len(remaining),
    )
    api_router.routes[:] = [*remaining[:catchall_index], *selected, *remaining[catchall_index:]]


_promote_control_loop_routes(router)
_promote_control_loop_routes(legacy_router)
