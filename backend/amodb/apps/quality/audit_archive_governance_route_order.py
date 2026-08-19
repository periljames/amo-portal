from __future__ import annotations

from fastapi import APIRouter

from . import audit_archive_governance_models as _audit_archive_governance_models  # noqa: F401
from . import audit_archive_governance_router
from . import audit_archive_package_router
from . import audit_archive_evidence_hardening as _audit_archive_evidence_hardening  # noqa: F401
from .canonical_router import legacy_router, router


def _is_archive_governance_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return (
        "/audit-retention-policy" in path
        or ("/audits/" in path and "/archive-governance" in path)
        or ("/audits/" in path and "/archive-manifests" in path)
        or ("/audits/" in path and "/legal-holds/" in path)
    ) and ("/quality/" in path or "/qms/" in path)


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _signature(route_item) -> tuple[str, frozenset[str]]:
    return (
        str(getattr(route_item, "path", "")),
        frozenset(getattr(route_item, "methods", None) or ()),
    )


def _register(api_router: APIRouter) -> None:
    if not any(_is_archive_governance_route(item) for item in api_router.routes):
        api_router.include_router(audit_archive_governance_router.router)
    package_endpoints = {getattr(item, "endpoint", None) for item in audit_archive_package_router.router.routes}
    if not any(getattr(item, "endpoint", None) in package_endpoints for item in api_router.routes):
        api_router.include_router(audit_archive_package_router.router)


def _promote(api_router: APIRouter) -> None:
    registered = [item for item in api_router.routes if _is_archive_governance_route(item)]
    if not registered:
        raise RuntimeError("QMS audit archive governance routes were not registered")

    # Package-control routes are registered last. Collapse exact path/method
    # overlaps in favour of the latest route so generation, state projection and
    # disposition use the physical package/checksum controls while the remaining
    # retention and legal-hold routes stay authoritative in the base router.
    selected_reversed = []
    seen: set[tuple[str, frozenset[str]]] = set()
    for route_item in reversed(registered):
        signature = _signature(route_item)
        if signature in seen:
            continue
        seen.add(signature)
        selected_reversed.append(route_item)
    selected = list(reversed(selected_reversed))

    remaining = [item for item in api_router.routes if not _is_archive_governance_route(item)]
    catchall_index = next((index for index, item in enumerate(remaining) if _is_generic_catchall(item)), len(remaining))
    api_router.routes[:] = [*remaining[:catchall_index], *selected, *remaining[catchall_index:]]


for api_router in (router, legacy_router):
    _register(api_router)
    _promote(api_router)
