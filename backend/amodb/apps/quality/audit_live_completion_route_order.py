from __future__ import annotations

from fastapi import APIRouter

from . import audit_live_completion_models as _audit_live_completion_models  # noqa: F401
from . import audit_live_completion_router
from .canonical_router import router
from .router import public_router as quality_public_router


def _is_completion_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return (
        "/audit-webauthn/" in path
        or "/closing-acknowledgements" in path
        or "/verification-tokens" in path
        or "/signature/options" in path
        or "/signature/verify" in path
        or ("/report-revisions/" in path and path.endswith("/transitions"))
    ) and "/quality/" in path


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _signature(route_item) -> tuple[str, frozenset[str]]:
    return str(getattr(route_item, "path", "")), frozenset(getattr(route_item, "methods", None) or ())


def _register_and_promote(api_router: APIRouter) -> None:
    """Mount the complete completion router and retain one exact route per method."""

    api_router.include_router(audit_live_completion_router.router)

    completion = [item for item in api_router.routes if _is_completion_route(item)]
    if not completion:
        raise RuntimeError("QMS live-audit completion routes were not registered")

    selected_reversed = []
    seen: set[tuple[str, frozenset[str]]] = set()
    for item in reversed(completion):
        marker = _signature(item)
        if marker in seen:
            continue
        seen.add(marker)
        selected_reversed.append(item)
    selected = list(reversed(selected_reversed))

    completion_signatures = {_signature(item) for item in completion}
    remaining = [
        item for item in api_router.routes
        if not (_signature(item) in completion_signatures and _is_completion_route(item))
    ]
    catchall_index = next((i for i, item in enumerate(remaining) if _is_generic_catchall(item)), len(remaining))
    api_router.routes[:] = [*remaining[:catchall_index], *selected, *remaining[catchall_index:]]


def _synchronise_public_completion_routes() -> None:
    """Register every public completion route without relying on one sentinel."""

    existing = {_signature(item) for item in quality_public_router.routes}
    for item in audit_live_completion_router.public_router.routes:
        marker = _signature(item)
        if marker in existing:
            continue
        quality_public_router.routes.append(item)
        existing.add(marker)


_register_and_promote(router)
_synchronise_public_completion_routes()
