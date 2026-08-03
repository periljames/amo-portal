# backend/amodb/apps/accounts/__init__.py
"""
Accounts app.

Responsible for tenant, department, user, role, authorisation, governed
administrator profiles and tenant-scoped department home composition.
"""

from fastapi import APIRouter, Depends

from . import models, schemas, services  # noqa: F401
from . import admin_profile_router, department_home_router
from .admin_profile_guard import require_active_admin_profile
from . import router_admin as _router_admin
from . import router_public as _router_public

# Register the profile endpoints first, then include the already-built admin
# router inside a parent router whose dependency is applied while routes are
# copied. Mutating APIRouter.dependencies after decorators have registered routes
# does not update their dependant graphs.
_admin_routes = _router_admin.router
_admin_routes.include_router(admin_profile_router.router)
_protected_admin_routes = APIRouter(dependencies=[Depends(require_active_admin_profile)])
_protected_admin_routes.include_router(_admin_routes)
_router_admin.router = _protected_admin_routes

# Mounted below the authenticated /auth surface. The endpoint independently
# resolves the AMO and validates effective department access before returning any
# composed data.
_router_public.router.include_router(department_home_router.router)

__all__ = [
    "models",
    "schemas",
    "services",
    "admin_profile_router",
    "department_home_router",
    "require_active_admin_profile",
]
