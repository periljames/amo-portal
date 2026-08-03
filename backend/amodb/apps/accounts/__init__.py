# backend/amodb/apps/accounts/__init__.py
"""
Accounts app.

Responsible for tenant, department, user, role, authorisation, governed
administrator profiles and tenant-scoped department home composition.
"""

from fastapi import Depends

from . import models, schemas, services  # noqa: F401
from .admin_profile_guard import require_active_admin_profile
from .admin_profile_router import router as admin_profile_router
from .department_home_router import router as department_home_router
from . import router_admin as _router_admin
from . import router_public as _router_public

# Every normal /accounts/admin operation requires a short-lived backend-confirmed
# Admin profile. The admin-profile routes themselves are exempt inside the guard
# because they create, revoke and govern the elevated session.
_router_admin.router.dependencies.append(Depends(require_active_admin_profile))
_router_admin.router.include_router(admin_profile_router)

# Mounted below the authenticated /auth surface. The endpoint independently
# resolves the AMO and validates effective department access before returning any
# composed data.
_router_public.router.include_router(department_home_router)

__all__ = [
    "models",
    "schemas",
    "services",
    "admin_profile_router",
    "department_home_router",
    "require_active_admin_profile",
]
