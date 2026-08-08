# backend/amodb/apps/quality/__init__.py
from __future__ import annotations

from fastapi import APIRouter

# Primary Quality API exports.
from .router import router, public_router  # noqa: F401

# Register extension metadata and assurance permission alignment before route
# dependencies are evaluated during application startup.
from . import excellence_models as _excellence_models  # noqa: F401,E402
from . import mission_models as _mission_models  # noqa: F401,E402
from . import assurance_permissions as _assurance_permissions  # noqa: F401,E402

# Focused extensions are loaded only after the compatibility router is complete.
from . import audit_file_controls as _audit_file_controls  # noqa: F401,E402
from . import audit_workflow_contract as _audit_workflow_contract  # noqa: F401,E402
from . import public_invite_extensions as _public_invite_extensions  # noqa: F401,E402
from . import register_pagination as _register_pagination  # noqa: F401,E402


def _deduplicate_exact_routes(api_router: APIRouter) -> None:
    """Remove accidental duplicate decorators while preserving distinct handlers."""

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
# tenant prefixes. Later extension routers intentionally override selected base
# paths with stricter tenant validation, schema-aware aggregation and lifecycle
# transition enforcement.
from . import canonical_router as _canonical_router  # noqa: F401,E402
from . import excellence_router as _excellence_router  # noqa: F401,E402
from . import assurance_wiring_router as _assurance_wiring_router  # noqa: F401,E402
from . import assurance_metrics_router as _assurance_metrics_router  # noqa: F401,E402
from . import assurance_lifecycle_guard_router as _assurance_lifecycle_guard_router  # noqa: F401,E402
from . import mission_router as _mission_router  # noqa: F401,E402
from . import mission_management_guard_router as _mission_management_guard_router  # noqa: F401,E402
from . import mission_lifecycle_guard_router as _mission_lifecycle_guard_router  # noqa: F401,E402


def _include_once(parent: APIRouter, child: APIRouter, unique_path_fragment: str) -> None:
    if any(unique_path_fragment in str(getattr(route_item, "path", "")) for route_item in parent.routes):
        return
    parent.include_router(child)


_include_once(
    _canonical_router.router,
    _excellence_router.router,
    "/api/maintenance/{amo_code}/quality/excellence/overview",
)
_include_once(
    _canonical_router.legacy_router,
    _excellence_router.router,
    "/api/maintenance/{amo_code}/qms/excellence/overview",
)
_include_once(
    _canonical_router.router,
    _assurance_wiring_router.router,
    "/api/maintenance/{amo_code}/quality/excellence/source-catalog",
)
_include_once(
    _canonical_router.legacy_router,
    _assurance_wiring_router.router,
    "/api/maintenance/{amo_code}/qms/excellence/source-catalog",
)

# Metrics intentionally override the wiring router's broad aggregation paths.
# Register them directly so the later route-order pass can retain the latest
# exact path/method handler rather than treating the overlap as duplication.
_canonical_router.router.include_router(_assurance_metrics_router.router)
_canonical_router.legacy_router.include_router(_assurance_metrics_router.router)

# Lifecycle endpoints intentionally overlap the base wiring contract. They are
# registered last so create, approval and test operations retain strict state
# transition and evidence gates.
_canonical_router.router.include_router(_assurance_lifecycle_guard_router.router)
_canonical_router.legacy_router.include_router(_assurance_lifecycle_guard_router.router)

# Missions are additive governed workflows rather than a duplicate operational
# register. They coordinate evidence and decisions sourced from other AMO
# domains, and keep canonical and legacy tenant aliases contract-compatible.
_include_once(
    _canonical_router.router,
    _mission_router.router,
    "/api/maintenance/{amo_code}/quality/missions",
)
_include_once(
    _canonical_router.legacy_router,
    _mission_router.router,
    "/api/maintenance/{amo_code}/qms/missions",
)

# Write guards override only the Mission operations that require stronger tenant
# participant validation, gate evidence checks and attributable human approval.
_canonical_router.router.include_router(_mission_management_guard_router.router)
_canonical_router.legacy_router.include_router(_mission_management_guard_router.router)
_canonical_router.router.include_router(_mission_lifecycle_guard_router.router)
_canonical_router.legacy_router.include_router(_mission_lifecycle_guard_router.router)

# Promote static assurance APIs ahead of the canonical catch-all and collapse
# path/method overlaps in favour of the latest, most specific handler.
from . import excellence_route_order as _excellence_route_order  # noqa: F401,E402
from . import mission_route_order as _mission_route_order  # noqa: F401,E402
