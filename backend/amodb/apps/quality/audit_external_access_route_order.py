from __future__ import annotations

from fastapi import APIRouter

from . import audit_external_access_models as _audit_external_access_models  # noqa: F401
from . import audit_guest_document_models as _audit_guest_document_models  # noqa: F401
from . import audit_external_access_router
from . import audit_external_fieldwork_router as _audit_external_fieldwork_router  # noqa: F401
from . import audit_external_session_guard_router as _audit_external_session_guard_router  # noqa: F401
from . import audit_external_participant_guard_router
from . import audit_external_finding_draft_router
from . import audit_external_finding_promotion_router
from . import audit_external_fieldwork_draft_enable_router as _audit_external_fieldwork_draft_enable_router  # noqa: F401
from . import audit_finding_release_status_router
from . import audit_guest_documents_router
from .canonical_router import legacy_router, router


def _is_external_access_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return (
        "/external-participants" in path
        or "/external-finding-drafts" in path
        or path.endswith("/finding-releases")
        or "/document-requests/" in path and "/submissions" in path
        or ("/findings/" in path and path.endswith("/release"))
    ) and ("/quality/" in path or "/qms/" in path)


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _has_route(api_router: APIRouter, *, path_fragment: str, method: str | None = None, name: str | None = None) -> bool:
    for item in api_router.routes:
        if path_fragment not in str(getattr(item, "path", "")):
            continue
        if method and method not in set(getattr(item, "methods", None) or ()):
            continue
        if name and str(getattr(item, "name", "")) != name:
            continue
        return True
    return False


def _register(api_router: APIRouter) -> None:
    # The assurance guard intentionally precedes the legacy create route. It
    # delegates valid EMAIL_LINK invitations and rejects unenforced MFA/PASSKEY
    # labels before the older handler can persist them.
    if not _has_route(api_router, path_fragment="/external-participants", name="create_external_participant_guarded"):
        api_router.include_router(audit_external_participant_guard_router.router)
    if not _has_route(api_router, path_fragment="/external-participants", method="GET"):
        api_router.include_router(audit_external_access_router.router)
    if not _has_route(api_router, path_fragment="/external-finding-drafts", method="GET"):
        api_router.include_router(audit_external_finding_draft_router.router)
    if not _has_route(api_router, path_fragment="/external-finding-drafts", name="promote_external_finding_draft"):
        api_router.include_router(audit_external_finding_promotion_router.router)
    if not any(str(getattr(item, "path", "")).endswith("/finding-releases") for item in api_router.routes):
        api_router.include_router(audit_finding_release_status_router.router)
    if not any("/document-requests/" in str(getattr(item, "path", "")) and "/submissions" in str(getattr(item, "path", "")) for item in api_router.routes):
        api_router.include_router(audit_guest_documents_router.router)


def _promote(api_router: APIRouter) -> None:
    routes = [item for item in api_router.routes if _is_external_access_route(item)]
    if not routes:
        raise RuntimeError("QMS external audit access routes were not registered")
    remaining = [item for item in api_router.routes if not _is_external_access_route(item)]
    catchall_index = next((index for index, item in enumerate(remaining) if _is_generic_catchall(item)), len(remaining))
    api_router.routes[:] = [*remaining[:catchall_index], *routes, *remaining[catchall_index:]]


for api_router in (router, legacy_router):
    _register(api_router)
    _promote(api_router)
