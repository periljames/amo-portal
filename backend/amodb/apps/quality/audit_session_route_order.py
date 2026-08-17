from __future__ import annotations

from fastapi import APIRouter

from . import audit_session_router
from .canonical_router import legacy_router, router


def _is_session_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return (
        ("/quality/audits/" in path and path.endswith("/session"))
        or ("/qms/audits/" in path and path.endswith("/session"))
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


for api_router in (router, legacy_router):
    _register(api_router)
    _promote(api_router)

# External participants and auditee released-data access are additive to the
# session projection. Loading here guarantees their ORM metadata and canonical
# routes exist without changing the historical central Quality bootstrap order.
from . import audit_external_access_route_order as _audit_external_access_route_order  # noqa: F401,E402

# Deterministic report composition and closing assurance are part of the same
# governed audit occurrence. Register their exact routes ahead of the legacy
# generic QMS catch-all so the closing workspace never falls through to a broad
# module-path handler.
from . import audit_report_composition_route_order as _audit_report_composition_route_order  # noqa: F401,E402
from . import audit_closing_assurance_route_order as _audit_closing_assurance_route_order  # noqa: F401,E402

# Archive is a governed continuation of the same occurrence after assurance
# follow-up. Retention, hold and disposition routes therefore share the same
# canonical occurrence chain and remain ahead of the generic catch-all.
from . import audit_archive_governance_route_order as _audit_archive_governance_route_order  # noqa: F401,E402

# Final completion semantics intentionally load after historical report/closing
# routers. This layer adds auditee closing acknowledgement, WebAuthn signing and
# public verification, and shadows the older ISSUE transition with stricter
# exact-hash ceremony gates.
from . import audit_live_completion_route_order as _audit_live_completion_route_order  # noqa: F401,E402
