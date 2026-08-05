"""Workforce and HR integration domain for duty rostering."""

# WorkPatternDay owns a foreign-key relationship to the canonical rostering
# ShiftTemplate model. Import that model whenever the workforce domain is loaded
# so isolated account/workforce tests and scripts cannot configure an incomplete
# SQLAlchemy registry merely because the application router was not imported.
from amodb.apps.rostering import models as rostering_models  # noqa: F401

from . import calculations, models, permissions, schemas, services
from .leave_balance_locking import load_leave_balance_for_update

# Keep every leave transition on the same PostgreSQL-safe balance lock path.
# The service helper remains the internal call site used by submit, approval,
# rejection and cancellation workflows.
services._leave_balance = load_leave_balance_for_update

__all__ = [
    "calculations",
    "models",
    "permissions",
    "schemas",
    "services",
    "rostering_models",
]
