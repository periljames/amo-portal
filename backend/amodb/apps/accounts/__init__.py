# backend/amodb/apps/accounts/__init__.py
"""
Accounts app

Responsible for:
- Multi-tenant AMO / Department definitions
- User accounts, roles, and regulatory licence details
- Staff authorisations (who can sign what, for which aircraft/checks)
- Account security events (login, lockout, reset)
- Public auth endpoints (login, password reset, first superuser)
- Admin endpoints (manage AMOs, departments, users, authorisations)

Other apps (fleet, work, crs, etc.) should depend on these models
for anything related to "who is allowed to do what".
"""

from . import models, schemas, services  # noqa: F401

__all__ = ["models", "schemas", "services"]
