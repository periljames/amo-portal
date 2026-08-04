"""Workforce and HR integration domain for duty rostering."""

from . import calculations, models, permissions, schemas, services
from .leave_balance_locking import load_leave_balance_for_update

# Keep every leave transition on the same PostgreSQL-safe balance lock path.
# The service helper remains the internal call site used by submit, approval,
# rejection and cancellation workflows.
services._leave_balance = load_leave_balance_for_update

__all__ = ["calculations", "models", "permissions", "schemas", "services"]
