from __future__ import annotations

import inspect

from amodb.apps.workforce import hr_router, hr_service, permissions


def test_current_permission_list_uses_effective_global_grants_only():
    source = inspect.getsource(permissions.permissions_for_user)
    assert "effective_from" in source
    assert "effective_to" in source
    assert "department_id.is_(None)" in source
    assert "base_station_id.is_(None)" in source
    assert "PermissionEffect.DENY in code_effects" in source


def test_hr_pattern_assignment_returns_created_record_id():
    source = inspect.getsource(hr_router.hr_create_work_pattern_assignment)
    assert "created_id = row.id" in source
    assert "item.id == created_id" in source
    assert ")[0]" not in source


def test_overtime_workflow_is_listable_creatable_and_actionable():
    router_source = inspect.getsource(hr_router)
    service_source = inspect.getsource(hr_service)
    assert "/overtime-requests" in router_source
    assert "hr_decide_overtime_request" in router_source
    assert "OVERTIME_APPROVE" in router_source
    assert "ATTENDANCE_APPROVE" in router_source
    assert "with_for_update" in inspect.getsource(hr_service.decide_overtime)
    assert "OvertimeApproval" in service_source
    assert "SUPERVISOR_APPROVED" in service_source
    assert "HR_APPROVED" in service_source
