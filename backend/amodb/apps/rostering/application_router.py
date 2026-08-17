# backend/amodb/apps/rostering/application_router.py
"""Application-level router aggregate for workforce-integrated rostering.

`amodb.main` historically imports `amodb.apps.rostering.router.router`. The
package initializer replaces that submodule export with this aggregate, which
preserves the existing bootstrap import while mounting the canonical sibling
prefixes `/rostering` and `/workforce`.
"""
from fastapi import APIRouter

from . import (
    calendar_subscriptions,
    code_registry,
    compliance_policy,
    lineage,
    roster_control,
    template_usage_policy,
    version_copy_policy,
)
from . import router as rostering_route_module
from .aircraft_allocation_router import router as aircraft_allocation_router
from .automation_router import router as automation_router
from .calendar_subscription_status_router import router as calendar_subscription_status_router
from .code_registry_router import router as code_registry_router
from .commitments_router import router as commitments_router
from .rest_code_canonicalization import router as rest_code_canonicalization_router
from .roster_control_router import router as roster_control_router
from ..workforce import pattern_rest_policy
from ..workforce import pay_policy_store
from ..workforce import services as workforce_services
from ..workforce import timesheet_pay_policy
from ..workforce.bulk_router import router as workforce_bulk_router
from ..workforce.governance_router import router as workforce_governance_router
from ..workforce.hr_router import router as workforce_hr_router
from ..workforce.pay_policy_router import router as workforce_pay_policy_router
from ..workforce.router_entry import router as workforce_router
from ..workforce.selection_router import router as workforce_selection_router

_LEGACY_CALENDAR_PATHS = {
    "/rostering/calendar/subscription",
    "/rostering/calendar/feed/{token}.ics",
}
rostering_route_module.router.routes = [
    route
    for route in rostering_route_module.router.routes
    if getattr(route, "path", None) not in _LEGACY_CALENDAR_PATHS
]

roster_control.ensure_assignment_lineages = lineage.ensure_assignment_lineages
roster_control.subscription_status = calendar_subscriptions.subscription_status
roster_control.issue_calendar_subscription = calendar_subscriptions.issue_calendar_subscription
roster_control.revoke_calendar_subscription = calendar_subscriptions.revoke_calendar_subscription
roster_control.resolve_calendar_subscription = calendar_subscriptions.resolve_calendar_subscription

template_usage_policy.install_code_registry_policy(code_registry)
compliance_policy.install_validation_policy()

# All planners share the same rest semantics: an OFF pattern day without an
# explicit template is persisted as canonical RD rather than anonymous empty
# calendar space. This also upgrades the older 5D/2O recipe behavior.
pattern_rest_policy.install_service_policy(workforce_services)

# Attach contract-owned floors before the timesheet classifier runs. A stored
# contractual rate may raise the entitlement floor; user/supervisor input may
# never lower it.
pay_policy_store.install_timesheet_policy(timesheet_pay_policy)
timesheet_pay_policy.install_service_policy(workforce_services)

roster_control.install_service_policy(rostering_route_module.services)
version_copy_policy.install_service_policy(rostering_route_module.services)

router = APIRouter()
router.include_router(calendar_subscription_status_router)
router.include_router(roster_control_router)
router.include_router(rostering_route_module.router)
router.include_router(code_registry_router)
router.include_router(rest_code_canonicalization_router)
router.include_router(aircraft_allocation_router)
router.include_router(automation_router)
router.include_router(commitments_router)
router.include_router(workforce_router)
router.include_router(workforce_hr_router)
router.include_router(workforce_governance_router)
router.include_router(workforce_selection_router)
router.include_router(workforce_bulk_router)
router.include_router(workforce_pay_policy_router)

__all__ = ["router"]
