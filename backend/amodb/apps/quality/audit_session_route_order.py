from __future__ import annotations

from fastapi import APIRouter

from . import audit_session_router
from .canonical_router import router


def _is_session_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    is_setup_update = path.endswith("/audits/{audit_id}/setup") and "PATCH" in methods
    return (
        ("/quality/audits/" in path or "/qms/audits/" in path)
        and (path.endswith("/session") or "/audits/resolve/" in path or is_setup_update)
    )


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _register(api_router: APIRouter) -> None:
    if not any(_is_session_route(item) for item in api_router.routes):
        api_router.include_router(audit_session_router.router)


def _promote(api_router: APIRouter) -> None:
    routes = [item for item in api_router.routes if _is_session_route(item)]
    if not routes:
        raise RuntimeError("QMS audit session routes were not registered")
    remaining = [item for item in api_router.routes if not _is_session_route(item)]
    catchall_index = next((index for index, item in enumerate(remaining) if _is_generic_catchall(item)), len(remaining))
    api_router.routes[:] = [*remaining[:catchall_index], *routes, *remaining[catchall_index:]]


for api_router in (router,):
    _register(api_router)
    _promote(api_router)

from . import audit_external_access_route_order as _audit_external_access_route_order  # noqa: F401,E402
from . import audit_evidence_route_order as _audit_evidence_route_order  # noqa: F401,E402
from . import audit_presence_route_order as _audit_presence_route_order  # noqa: F401,E402
from . import audit_occurrence_completion_route_order as _audit_occurrence_completion_route_order  # noqa: F401,E402
from . import audit_report_composition_route_order as _audit_report_composition_route_order  # noqa: F401,E402
from . import audit_closing_assurance_route_order as _audit_closing_assurance_route_order  # noqa: F401,E402
from . import audit_archive_governance_route_order as _audit_archive_governance_route_order  # noqa: F401,E402
from . import audit_live_completion_route_order as _audit_live_completion_route_order  # noqa: F401,E402
