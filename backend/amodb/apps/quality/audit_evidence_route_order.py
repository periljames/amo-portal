from __future__ import annotations

from fastapi import APIRouter

from . import audit_evidence_models as _audit_evidence_models  # noqa: F401
from . import audit_evidence_router
from .canonical_router import legacy_router, router
from .router import public_router as quality_public_router


def _is_evidence_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return (
        "/evidence" in path
        or ("/findings/" in path and path.endswith("/release"))
    ) and ("/quality/" in path or "/qms/" in path)


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _signature(route_item) -> tuple[str, frozenset[str]]:
    return str(getattr(route_item, "path", "")), frozenset(getattr(route_item, "methods", None) or ())


def _register_and_promote(api_router: APIRouter) -> None:
    if not any("/evidence" in str(getattr(item, "path", "")) for item in api_router.routes):
        api_router.include_router(audit_evidence_router.router)
    else:
        # The controlled finding-release endpoint is intentionally an exact-path
        # replacement for the earlier permissive release route. Ensure it is
        # registered even when other evidence routes already exist.
        if not any(str(getattr(item, "name", "")) == "release_audit_finding_with_controlled_evidence" for item in api_router.routes):
            api_router.include_router(audit_evidence_router.router)

    candidates = [item for item in api_router.routes if _is_evidence_route(item)]
    selected_reversed = []
    seen: set[tuple[str, frozenset[str]]] = set()
    for item in reversed(candidates):
        marker = _signature(item)
        if marker in seen:
            continue
        seen.add(marker)
        selected_reversed.append(item)
    selected = list(reversed(selected_reversed))
    signatures = {_signature(item) for item in candidates}
    remaining = [item for item in api_router.routes if not (_signature(item) in signatures and _is_evidence_route(item))]
    catchall = next((index for index, item in enumerate(remaining) if _is_generic_catchall(item)), len(remaining))
    api_router.routes[:] = [*remaining[:catchall], *selected, *remaining[catchall:]]


for _api_router in (router, legacy_router):
    _register_and_promote(_api_router)

if not any("/quality/audit-access/findings/" in str(getattr(item, "path", "")) and "/evidence/" in str(getattr(item, "path", "")) for item in quality_public_router.routes):
    quality_public_router.include_router(audit_evidence_router.public_router)
