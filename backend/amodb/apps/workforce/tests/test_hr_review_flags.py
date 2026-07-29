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

def test_hr_people_register_starts_from_active_tenant_users():
    source = inspect.getsource(hr_service._active_tenant_users)
    assert "User.is_active.is_(True)" in source
    assert "User.is_system_account.is_(False)" in source
    people_source = inspect.getsource(hr_service.list_people_page_v2)
    assert "_active_tenant_users" in people_source
    assert "_readiness_contracts_by_user" in people_source
    assert "contract=contracts.get" in people_source


def test_hr_readiness_surfaces_the_next_future_contract():
    lookup_source = inspect.getsource(hr_service._readiness_contracts_by_user)
    readiness_source = inspect.getsource(hr_service._person_readiness_for_user)
    assert "effective_from > on_date" in lookup_source
    assert "effective_from.asc()" in lookup_source
    assert "result.setdefault" in lookup_source
    assert "Employment contract starts on" in readiness_source
    assert "has_effective_contract=contract_is_effective" in readiness_source


def test_default_day_bootstrap_is_explicit_and_canonical():
    source = inspect.getsource(hr_service.bootstrap_default_day_pattern)
    assert 'code="DEFAULT-DAY"' in source
    assert 'code="DEFAULT-DAY-5X2"' in source
    assert "EmployeeWorkPatternAssignment" in source
    assert "with_for_update" in source
    assert "datetime.now(_amo_zone" in source
    assert "days_by_index" in source
    assert "range(7)" in source
    assert "week_monday = today - timedelta(days=today.weekday())" in source
    assert "cycle_anchor_date=week_monday" in source
    assert "current.effective_to = today - timedelta(days=1)" in source
    assert "db.delete(current)" in source
    assert "current.work_pattern_id = pattern.id" not in source


def test_active_user_readiness_uses_tenant_local_date():
    assert "datetime.now(_amo_zone" in inspect.getsource(hr_service.list_people_page_v2)
    assert "datetime.now(_amo_zone" in inspect.getsource(hr_service.dashboard_v2)


def test_effective_contract_gap_retains_future_starters():
    source = inspect.getsource(hr_service.dashboard_v2)
    assert "without_effective_contract" in source
    assert "not in current_contracts" in source
    assert "future_contract_users" in source
    assert "Edit future contract" in source
    assert "len(without_effective_contract)" in source


def test_default_day_bootstrap_repairs_non_monday_reserved_anchor():
    source = inspect.getsource(hr_service.bootstrap_default_day_pattern)
    assert 'current.work_pattern.code == "DEFAULT-DAY-5X2"' in source
    assert "current.cycle_anchor_date.weekday() == 0" in source
    assert "not current_is_reserved_default or current_default_anchor_is_monday" in source
    assert "cycle_anchor_date=week_monday" in source
