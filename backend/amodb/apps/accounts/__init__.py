# backend/amodb/apps/accounts/__init__.py
"""
Accounts app.

Responsible for tenant, department, user, role, authorisation and governed
administrator-profile records. Importing the package registers the dedicated
administrator-profile router and applies the backend elevation guard to the
canonical tenant administration surface.
"""

from fastapi import Depends

from . import models, schemas, services  # noqa: F401
from .admin_profile_guard import require_active_admin_profile
from .admin_profile_router import router as admin_profile_router
from . import router_admin as _router_admin

# Every normal /accounts/admin operation requires a short-lived backend-confirmed
# Admin profile. The admin-profile routes themselves are exempt inside the guard
# because they create, revoke and govern the elevated session.
_router_admin.router.dependencies.append(Depends(require_active_admin_profile))
_router_admin.router.include_router(admin_profile_router)

__all__ = [
    "models",
    "schemas",
    "services",
    "admin_profile_router",
    "require_active_admin_profile",
]
