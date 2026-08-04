from __future__ import annotations

from fastapi import APIRouter

from .canonical_router import legacy_router, router


def _is_excellence_route(route_item) -> bool:
    return "/excellence/" in str(getattr(route_item, "path", ""))


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _promote_excellence_routes(api_router: APIRouter) -> None:
    """Keep static continuous-assurance APIs ahead of canonical catch-all routes.

    Starlette resolves matching routes in registration order. The excellence
    extension is attached after the long compatibility router is constructed,
    so it must be promoted or `/excellence/...` can be interpreted as a generic
    QMS module path instead of the governed assurance API.
    """

    excellence_routes = [route_item for route_item in api_router.routes if _is_excellence_route(route_item)]
    if not excellence_routes:
        raise RuntimeError("QMS excellence routes were not registered")

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
_promote_excellence_routes(legacy_router)
