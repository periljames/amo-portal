# backend/amodb/apps/quality/__init__.py
from __future__ import annotations

from fastapi import APIRouter

# Primary Quality API exports.
from .router import router, public_router  # noqa: F401

# Focused extensions are loaded only after the compatibility router is complete.
# The module prepends its enriched token route to the same public_router object,
# so both the full portal and bounded Quality entrypoint receive it automatically.
from . import public_invite_extensions as _public_invite_extensions  # noqa: F401,E402


def _deduplicate_exact_routes(api_router: APIRouter) -> None:
    """Remove duplicate decorators that register the same endpoint twice.

    Quality's large compatibility router previously contained an accidental
    duplicate evidence-pack decorator. FastAPI accepts that shape but publishes
    duplicate OpenAPI operations and makes route-order behaviour harder to
    reason about. Preserve legitimately different handlers while collapsing an
    exact path/method/endpoint duplicate.
    """

    unique_routes = []
    seen: set[tuple[str, frozenset[str], int]] = set()
    for route_item in api_router.routes:
        path = str(getattr(route_item, "path", ""))
        methods = frozenset(getattr(route_item, "methods", None) or ())
        endpoint_marker = id(getattr(route_item, "endpoint", route_item))
        signature = (path, methods, endpoint_marker)
        if signature in seen:
            continue
        seen.add(signature)
        unique_routes.append(route_item)
    api_router.routes[:] = unique_routes


_deduplicate_exact_routes(router)
_deduplicate_exact_routes(public_router)
