# backend/amodb/apps/quality/__init__.py
from __future__ import annotations

from fastapi import APIRouter

# Primary Quality API exports.
from .router import router, public_router  # noqa: F401

# Register extension metadata before application startup or test metadata creation.
from . import excellence_models as _excellence_models  # noqa: F401,E402

# Focused extensions are loaded only after the compatibility router is complete.
# They replace narrowly scoped routes on the same exported router objects, so
# both the full portal and bounded Quality entrypoint receive the corrections.
from . import audit_file_controls as _audit_file_controls  # noqa: F401,E402
from . import audit_workflow_contract as _audit_workflow_contract  # noqa: F401,E402
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

# Register the operational dashboard, then explicitly place its static route
# ahead of the generic /{module_path:path} fallback on both canonical aliases.
from . import dashboard_v2 as _dashboard_v2  # noqa: F401,E402
from . import dashboard_route_order as _dashboard_route_order  # noqa: F401,E402

# Continuous-assurance APIs live under the canonical Quality and legacy QMS
# tenant prefixes. Register them before main.py imports the exported router
# objects so the full portal and bounded Quality service expose identical paths.
from . import canonical_router as _canonical_router  # noqa: F401,E402
from . import excellence_router as _excellence_router  # noqa: F401,E402


def _include_once(parent: APIRouter, child: APIRouter, prefix_marker: str) -> None:
    if any(str(getattr(route_item, "path", "")).startswith(prefix_marker) for route_item in parent.routes):
        return
    parent.include_router(child)


_include_once(_canonical_router.router, _excellence_router.router, "/api/maintenance/{amo_code}/quality/excellence")
_include_once(_canonical_router.legacy_router, _excellence_router.router, "/api/maintenance/{amo_code}/qms/excellence")

# The compatibility router ends with a generic module catch-all. Promote the
# newly included static assurance endpoints ahead of it so Starlette resolves
# them as APIs rather than unknown module paths.
from . import excellence_route_order as _excellence_route_order  # noqa: F401,E402
