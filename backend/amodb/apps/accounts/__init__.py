# backend/amodb/apps/accounts/__init__.py
"""
Accounts app.

Responsible for tenant, department, user, role, authorisation and governed
administrator-profile records. Importing the package registers the dedicated
administrator-profile router on the existing accounts administration router so
there is one mounted accounts surface in the FastAPI application.
"""

from . import models, schemas, services  # noqa: F401
from .admin_profile_router import router as admin_profile_router
from . import router_admin as _router_admin

_router_admin.router.include_router(admin_profile_router)

__all__ = ["models", "schemas", "services", "admin_profile_router"]
