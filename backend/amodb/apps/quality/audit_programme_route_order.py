from __future__ import annotations

from fastapi import APIRouter

from .canonical_router import router
from .route_ordering import assert_unique_routes


def _is_audit_programme_route(route_item: object) -> bool:
    path = str(getattr(route_item, "path", ""))
    return "/quality/audit-programmes" in path or "/qms/audit-programmes" in path


def _is_generic_quality_write(route_item: object) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return (
        (path.endswith("/{module}/{record_id}/{action}") and "POST" in methods)
        or (path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"}))
    )


def _specificity(route_item: object, registration_index: int) -> tuple[int, int, int, int]:
    path = str(getattr(route_item, "path", ""))
    segments = [segment for segment in path.split("/") if segment]
    parameter_count = sum(1 for segment in segments if "{" in segment)
    literal_count = len(segments) - parameter_count
    return parameter_count, -literal_count, -len(segments), registration_index


def _promote_audit_programme_routes(api_router: APIRouter) -> None:
    """Place programme writes ahead of the legacy generic workflow handler.

    ``POST /audit-programmes/universe/ensure-defaults`` has the same three
    trailing segments as ``POST /{module}/{record_id}/{action}``. Starlette
    dispatches the first match, so placing programme routes only ahead of the
    module-path catch-all still lets the generic handler incorrectly return an
    "Unsupported QMS workflow action" 404.
    """

    programme_routes = [item for item in api_router.routes if _is_audit_programme_route(item)]
    if not programme_routes:
        raise RuntimeError("QMS audit programme routes were not registered")
    assert_unique_routes(APIRouter(routes=programme_routes), label="QMS audit programme")

    registration_order = {id(item): index for index, item in enumerate(programme_routes)}
    programme_routes.sort(key=lambda item: _specificity(item, registration_order[id(item)]))
    remaining = [item for item in api_router.routes if not _is_audit_programme_route(item)]
    insertion_index = next(
        (index for index, item in enumerate(remaining) if _is_generic_quality_write(item)),
        len(remaining),
    )
    api_router.routes[:] = [
        *remaining[:insertion_index],
        *programme_routes,
        *remaining[insertion_index:],
    ]


_promote_audit_programme_routes(router)
