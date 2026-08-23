from __future__ import annotations

from fastapi import APIRouter

from . import audit_checklist_template_router
from .canonical_router import router


def _is_checklist_governance_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return (
        "/quality/audit-checklist-templates" in path
        or "/qms/audit-checklist-templates" in path
        or ("/quality/audits/" in path and "/checklist-bindings" in path)
        or ("/qms/audits/" in path and "/checklist-bindings" in path)
    )


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _register(api_router: APIRouter) -> None:
    if not any(_is_checklist_governance_route(item) for item in api_router.routes):
        api_router.include_router(audit_checklist_template_router.router)


def _promote(api_router: APIRouter) -> None:
    routes = [item for item in api_router.routes if _is_checklist_governance_route(item)]
    if not routes:
        raise RuntimeError("QMS checklist template governance routes were not registered")
    remaining = [item for item in api_router.routes if not _is_checklist_governance_route(item)]
    catchall_index = next((index for index, item in enumerate(remaining) if _is_generic_catchall(item)), len(remaining))
    api_router.routes[:] = [*remaining[:catchall_index], *routes, *remaining[catchall_index:]]


for api_router in (router,):
    _register(api_router)
    _promote(api_router)

# Canonical checklist execution metadata extends the authoritative legacy
# checklist rows without replacing or duplicating the execution engine.
from . import audit_checklist_execution_route_order as _audit_checklist_execution_route_order  # noqa: F401,E402

# Report revisions extend the same governed audit family while preserving the
# existing upload/download projection for backwards-compatible audit screens.
from . import audit_report_governance_route_order as _audit_report_governance_route_order  # noqa: F401,E402
