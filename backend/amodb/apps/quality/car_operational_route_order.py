from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.routing import APIRoute

from .canonical_router import router as canonical_router
from .router import router as legacy_quality_router
from .tenant_security import resolve_tenant_context


def _is_car_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return path.startswith("/quality/cars")


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _identity(route_item) -> tuple[str, frozenset[str]]:
    return (
        str(getattr(route_item, "path", "")),
        frozenset(getattr(route_item, "methods", None) or ()),
    )


def _clone_car_routes(api_router: APIRouter) -> None:
    """Expose the authoritative CAR engine under the canonical tenant route.

    The legacy CAR handlers remain the single business-logic owner.  Canonical
    aliases add the tenant-path resolver so a URL for one AMO cannot be used
    with another AMO's authenticated session, then promote the exact handlers
    ahead of the generic Quality catch-all.
    """

    existing = {_identity(item) for item in api_router.routes}
    for source in legacy_quality_router.routes:
        if not isinstance(source, APIRoute) or not _is_car_route(source):
            continue
        relative_path = str(source.path).removeprefix("/quality")
        target_identity = (f"/api/maintenance/{{amo_code}}/quality{relative_path}", frozenset(source.methods or ()))
        if target_identity in existing:
            continue
        api_router.add_api_route(
            relative_path,
            source.endpoint,
            methods=list(source.methods or ()),
            response_model=source.response_model,
            status_code=source.status_code,
            tags=source.tags,
            dependencies=[Depends(resolve_tenant_context), *list(source.dependencies or [])],
            summary=source.summary,
            description=source.description,
            response_description=source.response_description,
            responses=source.responses,
            deprecated=source.deprecated,
            operation_id=None,
            response_model_include=source.response_model_include,
            response_model_exclude=source.response_model_exclude,
            response_model_by_alias=source.response_model_by_alias,
            response_model_exclude_unset=source.response_model_exclude_unset,
            response_model_exclude_defaults=source.response_model_exclude_defaults,
            response_model_exclude_none=source.response_model_exclude_none,
            include_in_schema=source.include_in_schema,
            response_class=source.response_class,
            name=f"canonical_{source.name}",
            openapi_extra=source.openapi_extra,
        )
        existing.add(target_identity)

    car_routes = [item for item in api_router.routes if "/cars" in str(getattr(item, "path", "")) and not _is_generic_catchall(item)]
    remaining = [item for item in api_router.routes if item not in car_routes]
    catchall_index = next(
        (index for index, item in enumerate(remaining) if _is_generic_catchall(item)),
        len(remaining),
    )
    api_router.routes[:] = [*remaining[:catchall_index], *car_routes, *remaining[catchall_index:]]


_clone_car_routes(canonical_router)
