"""Workforce and HR integration domain for duty rostering."""

from . import calculations, models, permissions, schemas, services
from . import hr_service
from .leave_balance_locking import load_leave_balance_for_update
from .work_pattern_assignment_locking import install_default_day_pattern_lock_scope

# Keep every leave transition on the same PostgreSQL-safe balance lock path.
# The service helper remains the internal call site used by submit, approval,
# rejection and cancellation workflows.
services._leave_balance = load_leave_balance_for_update

# The default-day bootstrap queries assignment rows with eager relationships.
# Scope PostgreSQL row locks to the assignment table so the endpoint does not
# fail by attempting to lock nullable outer-join rows.
install_default_day_pattern_lock_scope(hr_service)

__all__ = [
    "calculations",
    "hr_service",
    "models",
    "permissions",
    "schemas",
    "services",
]
