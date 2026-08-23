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
    compliance_audit_policy,
    compliance_policy,
    configured_rule_policy,
    consent_notification_policy,
    consent_policy,
    consent_revalidation_policy,
    exemption_policy,
    extended_duty_day_policy,
    extended_duty_policy,
    extended_duty_validation_policy,
    lifecycle_error_policy,
    lineage,
    protected_rest_exact_policy,
    roster_control,
    shift_scheduling_policy,
    starter_shift_semantics_policy,
    statutory_rule_policy,
    structured_error_policy,
    template_usage_policy,
    version_copy_policy,
)
from . import router as rostering_route_module
from .aircraft_allocation_router import router as aircraft_allocation_router
from .automation_router import router as automation_router
from .calendar_subscription_status_router import router as calendar_subscription_status_router
from .code_registry_router import router as code_registry_router
from .commitments_router import router as commitments_router
from .consent_router import router as consent_router
from .exemption_router import router as exemption_router
from .extended_duty_router import router as extended_duty_router
from .rest_code_canonicalization import router as rest_code_canonicalization_router
from .roster_control_router import router as roster_control_router
from .shift_semantics_router import router as shift_semantics_router
from .workflow_state_router import router as workflow_state_router
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
starter_shift_semantics_policy.install(code_registry)
# Historical catalogue/validation code still contains an implicit default-rule
# bootstrap. Disable it before any validation wrapper is installed so tenants
# use only their explicitly governed rule sets and a missing legacy helper can
# never turn an ordinary planner mutation into HTTP 500.
configured_rule_policy.install_service_policy(rostering_route_module.services)
compliance_policy.install_validation_policy()
# Replace candidate sampling with exact continuous interval coverage before any
# validation request can run. The compatibility seam inside compliance_policy
# resolves this function at runtime, so the exact evaluator governs every caller.
protected_rest_exact_policy.install()
# Maintenance assignment-duration and prior-rest rules are server-side hard
# aviation limits. They cannot be converted to warnings by consent or approval.
statutory_rule_policy.install()
# The controlled extension policy sits inside the statutory validator: it may
# recognize an ordinary shift-duration excess only when a governed extension
# exists, but it adds a non-overridable recovery-rest check and leaves all other
# hard rules intact.
extended_duty_validation_policy.install()
# Authority exemptions wrap the final statutory finding set; they remain the
# only path that can report a hard rule as compliant under a verified exemption.
exemption_policy.install_validation_policy()
# Every canonical validation pass is audited. New hard blockers and resolved
# hard blockers are traced, and the existing notification channel informs the
# planner without creating a parallel notification subsystem.
compliance_audit_policy.install()

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
# Tenant-controlled scheduling eligibility is enforced server-side before the
# consent mutation wrapper is installed. Generated work patterns resolve the
# same guarded bulk function at runtime, so hidden/retired shifts cannot be
# introduced through a direct API or pattern-generation bypass.
shift_scheduling_policy.install_service_policy(rostering_route_module.services)
# Route consent events through the existing portal notification service before
# installing mutation/lifecycle hooks; the hooks call the wrapped service at
# runtime, so create/edit/accept/decline/supervisor actions share one channel.
consent_notification_policy.install()
# A controlled extension must also be expressly permitted by the active daily
# duty rule. This wraps only the extension service and then revalidates it.
extended_duty_day_policy.install()
# Controlled unserviceability extensions then bind themselves to the same
# consent functions. A material assignment edit cancels the extension consent;
# supervisor approval still re-runs the ordinary statutory validation engine.
extended_duty_policy.install()
# Every personnel/supervisor decision gets a fresh authoritative compliance pass
# before the roster may be considered ready for organizational approval.
consent_revalidation_policy.install()
# Consent generation and lifecycle gating are installed on the same canonical
# public service facade so single, bulk and generated assignments cannot bypass
# acknowledgement policy, and submit/approve/publish always re-check it.
consent_policy.install_service_policy(rostering_route_module.services)
# Convert statutory lifecycle failures into actionable domain errors after all
# workflow policies are installed, preserving consent errors unchanged.
lifecycle_error_policy.install_service_policy(rostering_route_module.services)
# Keep domain error codes/metadata intact at the legacy FastAPI translation
# boundary instead of collapsing them to generic submit/publish failures.
structured_error_policy.install(rostering_route_module)

router = APIRouter()
router.include_router(calendar_subscription_status_router)
router.include_router(roster_control_router)
router.include_router(rostering_route_module.router)
router.include_router(code_registry_router)
router.include_router(shift_semantics_router)
router.include_router(consent_router)
router.include_router(exemption_router)
router.include_router(extended_duty_router)
router.include_router(workflow_state_router)
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
