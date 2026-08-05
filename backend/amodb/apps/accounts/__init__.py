# backend/amodb/apps/accounts/__init__.py
"""
Accounts app.

Responsible for tenant, department, user, role, authorisation, governed
administrator profiles, corporate structure, personnel governance and
tenant-scoped department home composition.
"""

from fastapi import Depends
from fastapi.dependencies.utils import get_parameterless_sub_dependant
from fastapi.routing import APIRoute

from . import (  # noqa: F401
    assignment_integrity,
    corporate_structure_models,
    models,
    reporting_line_models,
    schemas,
    services,
)
from . import admin_profile_router, department_home_router, portal_preferences_router, router_amo_assets
from .admin_profile_access import active_admin_profile_session
from .admin_profile_concurrency import (
    lock_admin_grant_for_approval,
    serialized_approval_count,
)
from .admin_profile_guard import require_active_admin_profile
from .admin_profile_logout import revoke_admin_profile_on_logout
from .auth_session_context import bind_auth_session_to_token_refresh
from . import router_admin as _router_admin
from . import router_public as _router_public
from . import router_corporate_structure as _router_corporate_structure
from . import router_reporting_lines as _router_reporting_lines
from . import router_reporting_lifecycle as _router_reporting_lifecycle


_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


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


def _strict_reporting_admin_actor(user: models.User) -> bool:
    """Reserve tenant-wide reporting scope for actual tenant administrators.

    Quality and safety managers can still manage units where they are formally
    appointed as unit managers, deputies, accountable managers or supervisory
    position holders. Their functional account role alone no longer exposes the
    entire tenant hierarchy.
    """
    role = str(getattr(getattr(user, "role", None), "value", getattr(user, "role", "")) or "").upper()
    return bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_amo_admin", False)
        or role == "AMO_ADMIN"
    )


# Reporting-line helper functions resolve this policy at request time. Keep
# tenant-wide scope separate from functional quality and safety roles.
_router_reporting_lines._is_admin_actor = _strict_reporting_admin_actor

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

# AMO logo and CRS-template mutations are mounted by main.py through a separate
# router, so they must receive the same elevated-session requirement explicitly.
# Read-only asset retrieval remains available to normal authenticated tenant users.
for _route in router_amo_assets.router.routes:
    if (
        isinstance(_route, APIRoute)
        and bool((_route.methods or set()) & _MUTATING_METHODS)
    ):
        _attach_route_dependency(_route, require_active_admin_profile)

# Revoke elevated profiles during logout and preserve the exact server-side
# authentication-session identity when issuing a refreshed JWT.
for _route in _router_public.router.routes:
    if not isinstance(_route, APIRoute):
        continue
    if _route.path == "/auth/logout" and "POST" in (_route.methods or set()):
        _attach_route_dependency(_route, revoke_admin_profile_on_logout)
    if _route.path == "/auth/extend-session" and "POST" in (_route.methods or set()):
        _attach_route_dependency(_route, bind_auth_session_to_token_refresh)

# Mounted below the authenticated /auth surface. The endpoint independently
# resolves the AMO and validates effective department access before returning any
# composed data. Portal preferences are also mounted here so every deployment
# profile that already exposes the authenticated accounts router receives the
# same per-user accessibility and appearance contract. Corporate workforce and
# reporting routes expose only the signed-in person's record, direct reports or
# explicitly managed organization scope. Display-title changes remain separate
# from access roles, capabilities, credentials and aviation authorisations.
_router_public.router.include_router(department_home_router.router)
_router_public.router.include_router(portal_preferences_router.router)
_router_public.router.include_router(_router_corporate_structure.portal_router)
_router_public.router.include_router(_router_reporting_lines.portal_router)
_router_public.router.include_router(_router_reporting_lifecycle.portal_router)

__all__ = [
    "models",
    "schemas",
    "services",
    "assignment_integrity",
    "corporate_structure_models",
    "reporting_line_models",
    "admin_profile_router",
    "department_home_router",
    "portal_preferences_router",
    "router_amo_assets",
    "active_admin_profile_session",
    "bind_auth_session_to_token_refresh",
    "lock_admin_grant_for_approval",
    "serialized_approval_count",
    "require_active_admin_profile",
    "revoke_admin_profile_on_logout",
]
