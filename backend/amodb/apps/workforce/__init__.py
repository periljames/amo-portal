"""Workforce and HR integration domain for duty rostering."""

from . import calculations, models, permissions, schemas, services
from . import bulk_models, governance_models, hr_people_directory, hr_people_facets, hr_service
from .leave_balance_locking import load_leave_balance_for_update
from .retired_pattern_guard import install_retired_default_pattern_guard
from .work_pattern_assignment_locking import install_default_day_pattern_lock_scope

services._leave_balance = load_leave_balance_for_update
hr_people_directory.list_people_facets = hr_people_facets.list_people_facets
install_default_day_pattern_lock_scope(hr_service)
install_retired_default_pattern_guard(hr_service)

# Route contract batches through the eligible-only snapshot wrapper. The
# durable operation service remains shared for status, idempotency and retry.
from . import bulk_service, bulk_submission  # noqa: E402
bulk_service.submit_contract_batch = bulk_submission.submit_contract_batch

# Keep governed choices and lifecycle dates authoritative even where legacy
# service entry points remain for backwards-compatible imports.
from . import governance_directory, governance_mutations, offboarding_governance, supervisor_governance  # noqa: E402
governance_directory.list_supervisors = supervisor_governance.list_supervisors
governance_mutations._supervisor = supervisor_governance.require_supervisor
governance_mutations._schedule_offboarding = offboarding_governance.schedule_offboarding
governance_mutations.apply_due_offboarding = offboarding_governance.apply_due_offboarding

__all__ = [
    "bulk_models",
    "calculations",
    "governance_models",
    "hr_people_directory",
    "hr_people_facets",
    "hr_service",
    "models",
    "permissions",
    "schemas",
    "services",
]
