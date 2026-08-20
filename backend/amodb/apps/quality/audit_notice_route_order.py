from __future__ import annotations

from fastapi import APIRouter

from . import audit_notice_router
from .canonical_router import legacy_router, router


def _is_notice_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return (
        "/quality/audit-notice-policies" in path
        or "/qms/audit-notice-policies" in path
        or ("/quality/audits/" in path and "/notices" in path)
        or ("/qms/audits/" in path and "/notices" in path)
    )


def _is_generic_workflow_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module}/{record_id}/{action}") and "POST" in methods


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _register(api_router: APIRouter) -> None:
    if not any(_is_notice_route(item) for item in api_router.routes):
        api_router.include_router(audit_notice_router.router)


def _promote(api_router: APIRouter) -> None:
    routes = [item for item in api_router.routes if _is_notice_route(item)]
    if not routes:
        raise RuntimeError("QMS audit notice routes were not registered")
    remaining = [item for item in api_router.routes if not _is_notice_route(item)]
    insertion_index = next(
        (
            index
            for index, item in enumerate(remaining)
            if _is_generic_workflow_route(item) or _is_generic_catchall(item)
        ),
        len(remaining),
    )
    api_router.routes[:] = [*remaining[:insertion_index], *routes, *remaining[insertion_index:]]


for api_router in (router, legacy_router):
    _register(api_router)
    _promote(api_router)

# Checklist template governance extends the same audit route family and is
# registered after notice routes so both remain ahead of the generic reader.
from . import audit_checklist_template_route_order as _audit_checklist_template_route_order  # noqa: F401,E402
