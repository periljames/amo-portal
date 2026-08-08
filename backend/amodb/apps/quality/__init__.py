# backend/amodb/apps/quality/__init__.py
from __future__ import annotations

from fastapi import APIRouter

# Primary Quality API exports.
from .router import router, public_router  # noqa: F401

# Register extension metadata and assurance permission alignment before route
# dependencies are evaluated during application startup.
from . import excellence_models as _excellence_models  # noqa: F401,E402
from . import mission_models as _mission_models  # noqa: F401,E402
from . import audit_programme_models as _audit_programme_models  # noqa: F401,E402
from . import people_models as _people_models  # noqa: F401,E402
from . import assurance_case_models as _assurance_case_models  # noqa: F401,E402
from . import intelligence_models as _intelligence_models  # noqa: F401,E402
from . import audit_preparation_models as _audit_preparation_models  # noqa: F401,E402
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
from . import audit_programme_router as _audit_programme_router  # noqa: F401,E402
from . import audit_programme_queue_router as _audit_programme_queue_router  # noqa: F401,E402
from . import audit_programme_schedule_router as _audit_programme_schedule_router  # noqa: F401,E402
from . import people_router as _people_router  # noqa: F401,E402
from . import assurance_case_router as _assurance_case_router  # noqa: F401,E402
from . import intelligence_router as _intelligence_router  # noqa: F401,E402
from . import intelligence_governance_router as _intelligence_governance_router  # noqa: F401,E402
from . import audit_preparation_router as _audit_preparation_router  # noqa: F401,E402
from . import planner_assignment_guard_router as _planner_assignment_guard_router  # noqa: F401,E402
from . import planner_assignment_lifecycle_guard as _planner_assignment_lifecycle_guard  # noqa: F401,E402


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

# Audit Programmes and the Audit Universe add governed planning primitives around
# the existing audit schedule/execution engine. They do not create shadow audit,
# workforce, training, supplier or tooling records.
_include_once(
    _canonical_router.router,
    _audit_programme_router.router,
    "/api/maintenance/{amo_code}/quality/audit-programmes",
)
_include_once(
    _canonical_router.legacy_router,
    _audit_programme_router.router,
    "/api/maintenance/{amo_code}/qms/audit-programmes",
)

# The scheduling queue is a bounded join of approved/active programme
# requirements. It prevents the frontend from issuing one detail request per
# programme revision simply to discover work awaiting the Planner.
_canonical_router.router.include_router(_audit_programme_queue_router.router)
_canonical_router.legacy_router.include_router(_audit_programme_queue_router.router)

# Programme-to-Planner linkage is a focused transactional adapter around the
# authoritative audit schedule engine. It is deliberately registered after the
# programme CRUD routes so only the schedule-link operations overlap the same
# route family.
_canonical_router.router.include_router(_audit_programme_schedule_router.router)
_canonical_router.legacy_router.include_router(_audit_programme_schedule_router.router)

# People & Privileges owns only Quality authorization decisions, hard eligibility
# and independence declarations. Training, Workforce and Rostering stay the
# authoritative source of their own records.
_include_once(
    _canonical_router.router,
    _people_router.router,
    "/api/maintenance/{amo_code}/quality/people",
)
_include_once(
    _canonical_router.legacy_router,
    _people_router.router,
    "/api/maintenance/{amo_code}/qms/people",
)

# Assurance Cases coordinate source-backed investigations and corrective-action
# effectiveness without creating duplicate audit, CAR, supplier or maintenance
# records. Investigation statements and lifecycle events remain attributable.
_include_once(
    _canonical_router.router,
    _assurance_case_router.router,
    "/api/maintenance/{amo_code}/quality/assurance-cases",
)
_include_once(
    _canonical_router.legacy_router,
    _assurance_case_router.router,
    "/api/maintenance/{amo_code}/qms/assurance-cases",
)

# Quality Intelligence is a bounded read model over governed source records. It
# exposes transparent calculations and deterministic surveillance factors; it
# does not manufacture predictive compliance or risk scores.
_include_once(
    _canonical_router.router,
    _intelligence_router.router,
    "/api/maintenance/{amo_code}/quality/intelligence",
)
_include_once(
    _canonical_router.legacy_router,
    _intelligence_router.router,
    "/api/maintenance/{amo_code}/qms/intelligence",
)

# Signal rules/observations and the approval impact graph are governed adjuncts
# under the same Intelligence workspace. These routes are additive to /overview
# and are included directly because the workspace prefix is already registered.
_canonical_router.router.include_router(_intelligence_governance_router.router)
_canonical_router.legacy_router.include_router(_intelligence_governance_router.router)

# Preparation revisions preserve the controlled checklist/criteria/document
# request state used to prepare an audit. They snapshot authoritative records;
# they do not replace the live execution workflow.
_include_once(
    _canonical_router.router,
    _audit_preparation_router.router,
    "/api/maintenance/{amo_code}/quality/audits/{audit_id}/preparation-revisions",
)
_include_once(
    _canonical_router.legacy_router,
    _audit_preparation_router.router,
    "/api/maintenance/{amo_code}/qms/audits/{audit_id}/preparation-revisions",
)

# Governed assignment routes intentionally override selected Planner writes.
# The original scheduling functions remain authoritative and are called only
# after People & Privileges hard gates have been evaluated.
_canonical_router.router.include_router(_planner_assignment_guard_router.router)
_canonical_router.legacy_router.include_router(_planner_assignment_guard_router.router)

# Promote static assurance APIs ahead of the canonical catch-all and collapse
# path/method overlaps in favour of the latest, most specific handler.
from . import excellence_route_order as _excellence_route_order  # noqa: F401,E402
from . import mission_route_order as _mission_route_order  # noqa: F401,E402
from . import audit_programme_route_order as _audit_programme_route_order  # noqa: F401,E402
from . import people_route_order as _people_route_order  # noqa: F401,E402
from . import assurance_case_route_order as _assurance_case_route_order  # noqa: F401,E402
from . import intelligence_route_order as _intelligence_route_order  # noqa: F401,E402
from . import audit_preparation_route_order as _audit_preparation_route_order  # noqa: F401,E402
from . import planner_assignment_guard_route_order as _planner_assignment_guard_route_order  # noqa: F401,E402
