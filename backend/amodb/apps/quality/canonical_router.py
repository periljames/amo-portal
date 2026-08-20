"""Canonical Quality API composition.

Operational Quality routes are composed here so exact governed APIs take
precedence over broad compatibility handlers. Superseded audit-schedule routes
are removed from every mounted router; the Quality Operations Planner is the
single schedule authority.
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
from .router import router as primary_quality_router
from .planner_calendar_enrichment_router import planner_calendar_enrichment_router
from .planner_router import planner_router
from .planner_schedule_router import planner_schedule_router
from .planner_schedule_authority_router import router as planner_schedule_authority_router
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


def _is_superseded_audit_schedule_route(route_item) -> bool:
    """Identify the removed pre-Planner audit schedule HTTP family."""

    path = str(getattr(route_item, "path", ""))
    return "/audits/schedules" in path


def _retire_superseded_audit_schedule_routes(api_router: APIRouter) -> None:
    api_router.routes[:] = [
        route_item
        for route_item in api_router.routes
        if not _is_superseded_audit_schedule_route(route_item)
    ]


def _capture_extension_routes(api_router: APIRouter, extension_router: APIRouter):
    """Clone extension routes without copying router lifecycle handlers."""

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
    """Register exact operational routes before generic Quality handlers."""

    for extension_router in (
        planner_router,
        planner_schedule_router,
        planner_schedule_authority_router,
        planner_strategic_router,
        provider_governance_router,
    ):
        _insert_before_catchalls(
            api_router,
            _capture_extension_routes(api_router, extension_router),
        )


def _install_calendar_override(api_router: APIRouter) -> None:
    """Replace the older projection route with the timed planner projection."""

    calendar_routes = _capture_extension_routes(api_router, planner_calendar_enrichment_router)
    override_keys = {_route_key(route_item) for route_item in calendar_routes}
    api_router.routes[:] = [
        route_item
        for route_item in api_router.routes
        if _route_key(route_item) not in override_keys
    ]
    _insert_before_catchalls(api_router, calendar_routes)


# Remove the old schedule CRUD/run/restore/purge HTTP family from the primary
# Quality router before FastAPI mounts it. The shared router module still owns
# other active Quality endpoints, so only the superseded route objects are
# retired here.
_retire_superseded_audit_schedule_routes(primary_quality_router)

# Direct core-router consumers and both tenant URL families receive the same
# authoritative planner contract ahead of generic catch-all handling.
for _api_router in (core_router, router, legacy_router):
    _retire_superseded_audit_schedule_routes(_api_router)
    _install_calendar_override(_api_router)
    _install_specialist_routes(_api_router)
