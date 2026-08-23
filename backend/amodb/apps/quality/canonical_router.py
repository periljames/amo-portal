"""Canonical Quality API composition.

Core QMS endpoints are composed with dedicated planning and provider-governance
routers in this module.
"""

from fastapi import APIRouter

from .canonical_core_router import *  # noqa: F401,F403
from .canonical_core_router import (
    _pg_set_read_timeout,
    _recover_qms_read_session,
    _table_columns,
    core_router,
    router,
)
from .planner_calendar_enrichment_router import planner_calendar_enrichment_router
from .planner_router import planner_router
from .planner_schedule_router import planner_schedule_router
from .planner_strategic_router import router as planner_strategic_router
from .provider_governance_router import provider_governance_router


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
    """Clone extension routes without copying router lifecycle handlers.

    ``include_router`` also propagates startup and shutdown callbacks. The
    planner worker is owned by the deployed ASGI application, so composition
    restores the destination lifecycle lists immediately after route cloning.
    """

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
    startup_handlers = list(api_router.on_startup)
    shutdown_handlers = list(api_router.on_shutdown)
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
    api_router.on_startup[:] = startup_handlers
    api_router.on_shutdown[:] = shutdown_handlers
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


def _install_specialist_routes(api_router: APIRouter) -> None:
    """Register exact operational routes before generic QMS handlers."""

    for extension_router in (
        planner_router,
        planner_schedule_router,
        planner_strategic_router,
        provider_governance_router,
    ):
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


# Direct core-router consumers and the public Quality router receive the same
# specialist contract ahead of every generic module-path catch-all.
for _api_router in (core_router, router):
    _install_calendar_override(_api_router)
    _install_specialist_routes(_api_router)
