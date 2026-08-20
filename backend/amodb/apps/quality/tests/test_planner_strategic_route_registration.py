from __future__ import annotations

from fastapi import APIRouter

from amodb.apps.quality.canonical_router import core_router, legacy_router, router


def _route_index(api_router: APIRouter, suffix: str) -> int:
    for index, route_item in enumerate(api_router.routes):
        if str(getattr(route_item, "path", "")).endswith(suffix):
            return index
    raise AssertionError(f"Route ending with {suffix!r} is not registered")


def test_strategic_planner_route_is_registered_before_generic_catchall() -> None:
    for api_router in (core_router, router, legacy_router):
        strategic_index = _route_index(api_router, "/planner/strategic")
        catchall_index = _route_index(api_router, "/{module_path:path}")
        assert strategic_index < catchall_index
