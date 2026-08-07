"""Fail-closed role gates for controlled Reliability workbook operations.

The workbook-parity routes were recovered in several modules and are registered
onto the shared Reliability router.  This module applies one explicit policy
matrix after registration so write/approval/configuration actions cannot fall
back to the weaker "any active tenant user" contract.
"""
from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends
from fastapi.dependencies.utils import get_parameterless_sub_dependant
from fastapi.routing import APIRoute

from amodb.apps.accounts.models import AccountRole
from amodb.security import require_roles


ENTRY_GUARD = require_roles(
    AccountRole.AMO_ADMIN,
    AccountRole.QUALITY_MANAGER,
    AccountRole.SAFETY_MANAGER,
    AccountRole.PLANNING_ENGINEER,
    AccountRole.PRODUCTION_ENGINEER,
    AccountRole.QUALITY_INSPECTOR,
)
APPROVAL_GUARD = require_roles(
    AccountRole.AMO_ADMIN,
    AccountRole.QUALITY_MANAGER,
)
CONFIGURATION_GUARD = require_roles(
    AccountRole.AMO_ADMIN,
    AccountRole.QUALITY_MANAGER,
)
ANALYSIS_GUARD = require_roles(
    AccountRole.AMO_ADMIN,
    AccountRole.QUALITY_MANAGER,
    AccountRole.SAFETY_MANAGER,
    AccountRole.PLANNING_ENGINEER,
    AccountRole.PRODUCTION_ENGINEER,
    AccountRole.QUALITY_INSPECTOR,
    AccountRole.AUDITOR,
)

# Import endpoints retain their existing stricter data-governance guard inside
# workbook_parity_imports/workbook_reference_import.  The matrix below covers
# workbook operations that otherwise depended only on get_current_active_user.
POLICY: dict[tuple[str, str], Callable] = {
    ("POST", "/reliability/workbook-parity/records"): ENTRY_GUARD,
    ("POST", "/reliability/workbook-parity/records/{record_id}/approve"): APPROVAL_GUARD,
    ("POST", "/reliability/workbook-parity/records/{record_id}/close"): APPROVAL_GUARD,
    ("POST", "/reliability/workbook-parity/mappings"): CONFIGURATION_GUARD,
    ("POST", "/reliability/workbook-parity/mappings/seed-defaults"): CONFIGURATION_GUARD,
    ("POST", "/reliability/workbook-parity/report-layouts/seed"): CONFIGURATION_GUARD,
    ("POST", "/reliability/workbook-parity/report-layouts"): CONFIGURATION_GUARD,
    ("POST", "/reliability/workbook-parity/statistical-alerts/calculate"): ANALYSIS_GUARD,
    ("POST", "/reliability/workbook-parity/reports/render"): ANALYSIS_GUARD,
}


def apply(router) -> None:
    """Attach role dependencies to every matching APIRoute, including duplicates."""
    matched: set[tuple[str, str]] = set()
    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods or set():
            key = (method.upper(), route.path)
            guard = POLICY.get(key)
            if guard is None:
                continue
            marker = f"reliability-rbac:{method.upper()}:{route.path}"
            if marker in getattr(route, "tags", []):
                matched.add(key)
                continue
            dependency = Depends(guard)
            route.dependencies.append(dependency)
            route.dependant.dependencies.insert(
                0,
                get_parameterless_sub_dependant(
                    depends=dependency,
                    path=route.path_format,
                ),
            )
            route.tags.append(marker)
            matched.add(key)

    missing = set(POLICY) - matched
    if missing:
        rendered = ", ".join(f"{method} {path}" for method, path in sorted(missing))
        raise RuntimeError(f"Reliability workbook RBAC routes were not registered: {rendered}")
