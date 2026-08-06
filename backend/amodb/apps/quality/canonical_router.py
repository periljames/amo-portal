"""Canonical Quality API composition.

The established QMS endpoints remain in ``canonical_router_legacy`` while the
modern planning surfaces are isolated in dedicated routers. Keeping composition
in this module preserves every existing import path used by the application.
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
from .planner_calendar_enrichment_router import planner_calendar_enrichment_router
from .planner_router import planner_router
from .planner_schedule_router import planner_schedule_router


def _route_endpoint(route_item):
    return getattr(route_item, "endpoint", None)


def _route_key(route_item) -> tuple[str, frozenset[str]]:
    return (
        str(getattr(route_item, "path", "")),
        frozenset(getattr(route_item, "methods", None) or ()),
    )


def _is_generic_catchall(route_item) -> bool:
    return str(getattr(route_item, "path", "")).endswith("/{module_path:path}")


def _capture_extension_routes(api_router: APIRouter, extension_router: APIRouter):
    """Clone extension routes with the destination router's public prefix."""

    extension_endpoints = {
        _route_endpoint(route_item)
        for route_item in extension_router.routes
        if _route_endpoint(route_item) is not None
    }
    api_router.routes[:] = [
        route_item
        for route_item in api_router.routes
        if _route_endpoint(route_item) not in extension_endpoints
    ]

    existing_route_ids = {id(route_item) for route_item in api_router.routes}
    api_router.include_router(extension_router)
    extension_routes = [
        route_item
        for route_item in api_router.routes
        if id(route_item) not in existing_route_ids
    ]
    api_router.routes[:] = [
        route_item
        for route_item in api_router.routes
        if id(route_item) in existing_route_ids
    ]
    return extension_routes


def _insert_before_catchalls(api_router: APIRouter, routes: list) -> None:
    catchall_index = next(
        (
            index
            for index, route_item in enumerate(api_router.routes)
            if _is_generic_catchall(route_item)
        ),
        len(api_router.routes),
    )
    api_router.routes[catchall_index:catchall_index] = routes


def _install_planner_routes(api_router: APIRouter) -> None:
    """Register exact planner routes before generic QMS handlers."""

    for extension_router in (planner_router, planner_schedule_router):
        _insert_before_catchalls(
            api_router,
            _capture_extension_routes(api_router, extension_router),
        )


def _install_calendar_override(api_router: APIRouter) -> None:
    """Replace the legacy projection route with the timed planner projection."""

    calendar_routes = _capture_extension_routes(api_router, planner_calendar_enrichment_router)
    override_keys = {_route_key(route_item) for route_item in calendar_routes}
    api_router.routes[:] = [
        route_item
        for route_item in api_router.routes
        if _route_key(route_item) not in override_keys
    ]
    _insert_before_catchalls(api_router, calendar_routes)


# Direct core-router consumers and both public URL families must receive the same
# planner contract, ahead of every generic module-path catch-all. The calendar
# override removes the older exact projection route, avoiding duplicate OpenAPI
# operations while retaining all non-planner legacy endpoints.
for _api_router in (core_router, router, legacy_router):
    _install_calendar_override(_api_router)
    _install_planner_routes(_api_router)
