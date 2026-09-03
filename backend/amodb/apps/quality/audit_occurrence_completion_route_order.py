from __future__ import annotations

from fastapi import APIRouter

from . import audit_occurrence_completion_models as _audit_occurrence_completion_models  # noqa: F401
from . import audit_occurrence_assignment_router
from . import audit_occurrence_completion_router
from . import audit_controlled_document_collaboration_router
from . import audit_public_collaboration_scope_router
from .canonical_router import router
from .router import public_router as quality_public_router


def _is_occurrence_completion_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return (
        "/audits/" in path
        and any(
            fragment in path
            for fragment in (
                "/assignment-eligibility",
                "/independence",
                "/assignments",
                "/governed-document-requests",
                "/controlled-document-submissions",
                "/document-control/documents",
                "/meetings",
                "/closing-narrative",
            )
        )
    )


def _is_generic_workflow_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module}/{record_id}/{action}") and "POST" in methods


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _promote_occurrence_routes(api_router: APIRouter) -> None:
    """Place exact occurrence routes ahead of broad legacy workflow handlers.

    The legacy POST ``/{module}/{record_id}/{action}`` route also matches exact
    paths such as ``/audits/{audit_id}/meetings``,
    ``/audits/{audit_id}/independence``, ``/audits/{audit_id}/assignments``,
    and ``/audits/{audit_id}/governed-document-requests``. Starlette dispatches
    the first matching route, so appending the occurrence router causes valid
    writes to be misclassified as unsupported workflow actions and returned as 404.
    """

    occurrence_routes = [item for item in api_router.routes if _is_occurrence_completion_route(item)]
    if not occurrence_routes:
        raise RuntimeError("QMS audit occurrence completion routes were not registered")

    remaining = [item for item in api_router.routes if not _is_occurrence_completion_route(item)]
    insertion_index = next(
        (
            index
            for index, item in enumerate(remaining)
            if _is_generic_workflow_route(item) or _is_generic_catchall(item)
        ),
        len(remaining),
    )
    api_router.routes[:] = [*remaining[:insertion_index], *occurrence_routes, *remaining[insertion_index:]]


for api_router in (router,):
    if not any("/assignment-eligibility" in str(getattr(item, "path", "")) for item in api_router.routes):
        api_router.include_router(audit_occurrence_assignment_router.router)
    if not any("/governed-document-requests" in str(getattr(item, "path", "")) for item in api_router.routes):
        api_router.include_router(audit_occurrence_completion_router.router)
    if not any("/controlled-document-submissions" in str(getattr(item, "path", "")) for item in api_router.routes):
        api_router.include_router(audit_controlled_document_collaboration_router.router)
    _promote_occurrence_routes(api_router)

# Use the scope-aware collaboration projection rather than mounting the legacy
# public occurrence router. The hardened endpoint performs scope checks before
# querying meetings, closing narrative, or released-finding CAR data.
if not any("/quality/audit-access/collaboration" in str(getattr(item, "path", "")) for item in quality_public_router.routes):
    quality_public_router.include_router(audit_public_collaboration_scope_router.router)
if not any("/quality/audit-access/governed-document-requests" in str(getattr(item, "path", "")) for item in quality_public_router.routes):
    quality_public_router.include_router(audit_controlled_document_collaboration_router.public_router)
