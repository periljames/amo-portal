from __future__ import annotations

from fastapi import APIRouter

from .canonical_router import router


def _is_excellence_route(route_item) -> bool:
    return "/excellence/" in str(getattr(route_item, "path", ""))


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _route_signature(route_item) -> tuple[str, frozenset[str]]:
    return (
        str(getattr(route_item, "path", "")),
        frozenset(getattr(route_item, "methods", None) or ()),
    )


def _promote_excellence_routes(api_router: APIRouter) -> None:
    """Promote assurance APIs and prefer the latest exact route override.

    The base excellence router supplies the initial contract. The wiring router
    registers stricter handlers for controls, evidence and graph endpoints.
    Starlette resolves the first matching route, so exact path/method duplicates
    are collapsed in reverse registration order before all assurance routes are
    placed ahead of the canonical catch-all.
    """

    registered = [route_item for route_item in api_router.routes if _is_excellence_route(route_item)]
    if not registered:
        raise RuntimeError("QMS excellence routes were not registered")

    selected_reversed = []
    seen: set[tuple[str, frozenset[str]]] = set()
    for route_item in reversed(registered):
        signature = _route_signature(route_item)
        if signature in seen:
            continue
        seen.add(signature)
        selected_reversed.append(route_item)
    excellence_routes = list(reversed(selected_reversed))

    remaining = [route_item for route_item in api_router.routes if not _is_excellence_route(route_item)]
    catchall_index = next(
        (index for index, route_item in enumerate(remaining) if _is_generic_catchall(route_item)),
        len(remaining),
    )
    api_router.routes[:] = [
        *remaining[:catchall_index],
        *excellence_routes,
        *remaining[catchall_index:],
    ]


_promote_excellence_routes(router)
