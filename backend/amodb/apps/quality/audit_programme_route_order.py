from __future__ import annotations

from fastapi import APIRouter

from .canonical_router import legacy_router, router


def _is_audit_programme_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return "/quality/audit-programmes" in path or "/qms/audit-programmes" in path


def _is_generic_catchall(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    methods = set(getattr(route_item, "methods", None) or ())
    return path.endswith("/{module_path:path}") and bool(methods & {"GET", "POST", "PATCH", "DELETE"})


def _signature(route_item) -> tuple[str, frozenset[str]]:
    return str(getattr(route_item, "path", "")), frozenset(getattr(route_item, "methods", None) or ())


def _promote(api_router: APIRouter) -> None:
    registered = [item for item in api_router.routes if _is_audit_programme_route(item)]
    if not registered:
        raise RuntimeError("QMS Audit Programme routes were not registered")
    selected_reversed = []
    seen: set[tuple[str, frozenset[str]]] = set()
    for item in reversed(registered):
        sig = _signature(item)
        if sig in seen:
            continue
        seen.add(sig); selected_reversed.append(item)
    specific = list(reversed(selected_reversed))
    remaining = [item for item in api_router.routes if not _is_audit_programme_route(item)]
    catchall = next((index for index, item in enumerate(remaining) if _is_generic_catchall(item)), len(remaining))
    api_router.routes[:] = [*remaining[:catchall], *specific, *remaining[catchall:]]


_promote(router)
_promote(legacy_router)
