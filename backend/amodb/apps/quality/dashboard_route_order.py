from __future__ import annotations

from fastapi import APIRouter

from .canonical_router import router
from .dashboard_v2 import qms_operational_dashboard_v2


def _route_endpoint(route_item):
    return getattr(route_item, "endpoint", None)


def _is_generic_get_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return "GET" in methods and path.endswith("/{module_path:path}")


def _promote_dashboard_route(api_router: APIRouter, *, legacy: bool = False) -> None:
    """Keep the static dashboard endpoint ahead of the generic QMS catch-all.

    Starlette resolves routes in registration order. The dashboard extension is
    imported after the canonical router has already registered
    ``/{module_path:path}``, so an appended ``/dashboard-v2`` route is otherwise
    swallowed as the unknown module ``dashboard-v2``.
    """

    matching = [
        route_item
        for route_item in api_router.routes
        if _route_endpoint(route_item) is qms_operational_dashboard_v2
    ]
    if not matching:
        api_router.add_api_route(
            "/dashboard-v2",
            qms_operational_dashboard_v2,
            methods=["GET"],
            include_in_schema=not legacy,
            name="qms_operational_dashboard_v2_legacy" if legacy else "qms_operational_dashboard_v2",
        )
        matching = [
            route_item
            for route_item in api_router.routes
            if _route_endpoint(route_item) is qms_operational_dashboard_v2
        ]

    if not matching:
        raise RuntimeError("QMS dashboard-v2 route could not be registered")

    dashboard_route = matching[0]
    api_router.routes[:] = [
        route_item
        for route_item in api_router.routes
        if _route_endpoint(route_item) is not qms_operational_dashboard_v2
    ]

    catchall_index = next(
        (index for index, route_item in enumerate(api_router.routes) if _is_generic_get_catchall(route_item)),
        len(api_router.routes),
    )
    api_router.routes.insert(catchall_index, dashboard_route)


_promote_dashboard_route(router)
