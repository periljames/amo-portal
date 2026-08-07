from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from amodb.apps.accounts.models import AccountRole
from amodb.apps.reliability import router
from amodb.apps.reliability import workbook_rbac_hardening as rbac


def user(role: AccountRole, *, superuser: bool = False):
    return SimpleNamespace(role=role, is_superuser=superuser)


def test_controlled_approval_is_quality_or_admin_only():
    quality = user(AccountRole.QUALITY_MANAGER)
    admin = user(AccountRole.AMO_ADMIN)
    planner = user(AccountRole.PLANNING_ENGINEER)
    viewer = user(AccountRole.VIEW_ONLY)

    assert rbac.APPROVAL_GUARD(quality) is quality
    assert rbac.APPROVAL_GUARD(admin) is admin
    with pytest.raises(HTTPException) as planner_denied:
        rbac.APPROVAL_GUARD(planner)
    assert planner_denied.value.status_code == 403
    with pytest.raises(HTTPException) as viewer_denied:
        rbac.APPROVAL_GUARD(viewer)
    assert viewer_denied.value.status_code == 403


def test_entry_and_analysis_roles_do_not_gain_configuration_rights():
    planner = user(AccountRole.PLANNING_ENGINEER)
    auditor = user(AccountRole.AUDITOR)

    assert rbac.ENTRY_GUARD(planner) is planner
    assert rbac.ANALYSIS_GUARD(planner) is planner
    assert rbac.ANALYSIS_GUARD(auditor) is auditor

    with pytest.raises(HTTPException) as planner_config_denied:
        rbac.CONFIGURATION_GUARD(planner)
    assert planner_config_denied.value.status_code == 403
    with pytest.raises(HTTPException) as auditor_config_denied:
        rbac.CONFIGURATION_GUARD(auditor)
    assert auditor_config_denied.value.status_code == 403


def test_superuser_override_remains_supported():
    superuser = user(AccountRole.VIEW_ONLY, superuser=True)
    assert rbac.ENTRY_GUARD(superuser) is superuser
    assert rbac.APPROVAL_GUARD(superuser) is superuser
    assert rbac.CONFIGURATION_GUARD(superuser) is superuser
    assert rbac.ANALYSIS_GUARD(superuser) is superuser


def test_every_controlled_policy_route_has_the_expected_dependency():
    for key, guard in rbac.POLICY.items():
        method, path = key
        matched = [
            route
            for route in router.routes
            if isinstance(route, APIRoute)
            and route.path == path
            and method in (route.methods or set())
        ]
        assert matched, f"Missing controlled route: {method} {path}"
        for route in matched:
            dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
            assert guard in dependency_calls, f"Missing RBAC dependency on {method} {path}"


def test_view_only_is_denied_all_controlled_write_policy_classes():
    viewer = user(AccountRole.VIEW_ONLY)
    for guard in {
        rbac.ENTRY_GUARD,
        rbac.APPROVAL_GUARD,
        rbac.CONFIGURATION_GUARD,
        rbac.ANALYSIS_GUARD,
    }:
        with pytest.raises(HTTPException) as denied:
            guard(viewer)
        assert denied.value.status_code == 403
