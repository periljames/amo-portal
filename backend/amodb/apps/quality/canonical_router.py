"""Canonical Quality API composition.

The established QMS endpoints remain in ``canonical_router_legacy`` while the
modern planning surface is isolated in ``planner_router``. Keeping composition in
this module preserves every existing import path used by the application.
"""

from fastapi import APIRouter

from .canonical_router_legacy import *  # noqa: F401,F403
from .canonical_router_legacy import (
    _pg_set_read_timeout,
    _recover_qms_read_session,
    _table_columns,
    core_router,
    legacy_router,
    router,
)
from .planner_router import planner_router


def _route_endpoint(route_item):
    return getattr(route_item, "endpoint", None)


def _is_generic_catchall(route_item) -> bool:
    return str(getattr(route_item, "path", "")).endswith("/{module_path:path}")


def _install_planner_before_catchalls(api_router: APIRouter) -> None:
    """Register exact planner routes before the generic QMS path handlers.

    ``canonical_router_legacy`` mounts its catch-all GET/POST/PATCH/DELETE routes
    before this composition module is imported. Starlette resolves routes in
    registration order, so simply appending the planner router would make the
    generic handlers swallow planner capability and reschedule requests.
    """

    planner_endpoints = {
        _route_endpoint(route_item)
        for route_item in planner_router.routes
        if _route_endpoint(route_item) is not None
    }
    api_router.routes[:] = [
        route_item
        for route_item in api_router.routes
        if _route_endpoint(route_item) not in planner_endpoints
    ]

    existing_route_ids = {id(route_item) for route_item in api_router.routes}
    api_router.include_router(planner_router)
    planner_routes = [
        route_item
        for route_item in api_router.routes
        if id(route_item) not in existing_route_ids
    ]
    api_router.routes[:] = [
        route_item
        for route_item in api_router.routes
        if id(route_item) in existing_route_ids
    ]

    catchall_index = next(
        (
            index
            for index, route_item in enumerate(api_router.routes)
            if _is_generic_catchall(route_item)
        ),
        len(api_router.routes),
    )
    api_router.routes[catchall_index:catchall_index] = planner_routes


# Direct core-router consumers and both public URL families must receive the same
# planner contract, ahead of every generic module-path catch-all.
_install_planner_before_catchalls(core_router)
_install_planner_before_catchalls(router)
_install_planner_before_catchalls(legacy_router)
