# backend/amodb/apps/accounts/__init__.py
"""
Accounts app.

Responsible for tenant, department, user, role, authorisation, governed
administrator profiles and tenant-scoped department home composition.
"""

from fastapi import Depends
from fastapi.dependencies.utils import get_parameterless_sub_dependant
from fastapi.routing import APIRoute

from . import models, schemas, services  # noqa: F401
from . import admin_profile_router, department_home_router
from .admin_profile_access import active_admin_profile_session
from .admin_profile_concurrency import (
    lock_admin_grant_for_approval,
    serialized_approval_count,
)
from .admin_profile_guard import require_active_admin_profile
from .admin_profile_logout import revoke_admin_profile_on_logout
from . import router_admin as _router_admin
from . import router_public as _router_public


def _attach_route_dependency(route: APIRoute, dependency) -> None:
    """Attach a parameterless dependency to an already-created FastAPI route."""
    if any(item.call is dependency for item in route.dependant.dependencies):
        return
    depends = Depends(dependency)
    route.dependencies.append(depends)
    route.dependant.dependencies.insert(
        0,
        get_parameterless_sub_dependant(depends=depends, path=route.path_format),
    )


def _attach_router_dependency(router, dependency) -> None:
    """Apply a dependency to existing routes and all routes registered later."""
    depends = Depends(dependency)
    if not any(getattr(item, "dependency", None) is dependency for item in router.dependencies):
        router.dependencies.append(depends)
    for route in router.routes:
        if isinstance(route, APIRoute):
            _attach_route_dependency(route, dependency)


# These endpoints resolve module-level helpers at request time. Keep the router
# modules importable while replacing only the governed policy functions.
admin_profile_router._approval_count = serialized_approval_count
department_home_router._admin_profile_active = active_admin_profile_session

# Preserve the original /accounts/admin router object and prefix. Register the
# profile endpoints, serialize approval requests before their foreign-key insert,
# then protect every existing and future tenant administration route.
_admin_routes = _router_admin.router
_admin_routes.include_router(admin_profile_router.router)
for _route in _admin_routes.routes:
    if (
        isinstance(_route, APIRoute)
        and "/admin-profile/" in _route.path
        and _route.path.endswith("/approve")
        and "POST" in (_route.methods or set())
    ):
        _attach_route_dependency(_route, lock_admin_grant_for_approval)
_attach_router_dependency(_admin_routes, require_active_admin_profile)

# Revoke elevated Admin Profile sessions within the same server-side logout
# transaction. The normal logout endpoint still owns access-token revocation and
# audit logging.
for _route in _router_public.router.routes:
    if (
        isinstance(_route, APIRoute)
        and _route.path == "/auth/logout"
        and "POST" in (_route.methods or set())
    ):
        _attach_route_dependency(_route, revoke_admin_profile_on_logout)

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
    "active_admin_profile_session",
    "lock_admin_grant_for_approval",
    "serialized_approval_count",
    "require_active_admin_profile",
    "revoke_admin_profile_on_logout",
]
