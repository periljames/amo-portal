from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.routing import APIRoute

from .canonical_router import router as canonical_router
from .router import router as legacy_quality_router
from .tenant_security import resolve_tenant_context


_TARGET_PATH = "/quality/audits/personnel/options"


def _is_personnel_route(route_item) -> bool:
    return str(getattr(route_item, "path", "")) == _TARGET_PATH


def _is_generic_workflow_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module}/{record_id}/{action}") and "POST" in methods


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _identity(route_item) -> tuple[str, frozenset[str]]:
    return (
        str(getattr(route_item, "path", "")),
        frozenset(getattr(route_item, "methods", None) or ()),
    )


def _register_and_promote(api_router: APIRouter) -> None:
    source = next(
        (
            item
            for item in legacy_quality_router.routes
            if isinstance(item, APIRoute) and _is_personnel_route(item)
        ),
        None,
    )
    if source is None:
        raise RuntimeError("QMS audit personnel options route was not registered")

    relative_path = str(source.path).removeprefix("/quality")
    target_identity = (
        f"/api/maintenance/{{amo_code}}/quality{relative_path}",
        frozenset(source.methods or ()),
    )
    existing = {_identity(item) for item in api_router.routes}
    if target_identity not in existing:
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

    personnel_routes = [
        item
        for item in api_router.routes
        if str(getattr(item, "path", "")).endswith("/audits/personnel/options")
    ]
    if not personnel_routes:
        raise RuntimeError("Canonical QMS audit personnel options route was not registered")

    remaining = [item for item in api_router.routes if item not in personnel_routes]
    insertion_index = next(
        (
            index
            for index, item in enumerate(remaining)
            if _is_generic_workflow_route(item) or _is_generic_catchall(item)
        ),
        len(remaining),
    )
    api_router.routes[:] = [
        *remaining[:insertion_index],
        *personnel_routes,
        *remaining[insertion_index:],
    ]


_register_and_promote(canonical_router)
