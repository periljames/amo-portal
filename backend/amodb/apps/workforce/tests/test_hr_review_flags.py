from __future__ import annotations

import inspect

from amodb.apps.accounts import personnel_import
from amodb.apps.training import workbook_import
from amodb.apps.workforce import hr_router, hr_service, permissions, router, services


def test_current_permission_list_uses_effective_global_grants_only():
    source = inspect.getsource(permissions.permissions_for_user)
    assert "effective_from" in source
    assert "effective_to" in source
    assert "department_id.is_(None)" in source
    assert "base_station_id.is_(None)" in source
    assert "PermissionEffect.DENY in code_effects" in source


def test_current_permission_response_is_never_browser_cached():
    source = inspect.getsource(router.current_permissions)
    assert '"Cache-Control"] = "private, no-store, max-age=0"' in source
    assert '"X-Workforce-Permissions-Source"] = "live"' in source


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
    assert "EmploymentStatus.SUSPENDED" in lookup_source
    assert "effective_from.asc()" in lookup_source
    assert "result.setdefault" in lookup_source
    assert "Employment contract starts on" in readiness_source
    assert "has_effective_contract=contract_is_effective" in readiness_source


def test_imported_hire_date_replaces_placeholders_and_aligns_initial_contract():
    training_source = inspect.getsource(workbook_import._upsert_person)
    personnel_source = inspect.getsource(personnel_import.import_personnel_rows)
    sync_source = inspect.getsource(services.sync_contract_start_from_hire_date)
    readiness_source = inspect.getsource(hr_service._person_readiness_for_user)

    assert "profile.hire_date = imported_hire_date" in training_source
    assert "HIRE_DATE_IMPORT_APPLIED" in training_source
    assert "HIRE_DATE_IMPORT_IGNORED" not in training_source
    assert "PERSONNEL_IMPORT_HIREDATE" in personnel_source
    assert "EmploymentContract.effective_from.asc()" in sync_source
    assert "EmploymentContract.effective_from.desc()" not in sync_source
    assert "Contract start must be aligned" not in readiness_source


def test_default_day_bootstrap_reuses_tenant_day_shift_without_hidden_generation():
    source = inspect.getsource(hr_service.bootstrap_default_day_pattern)
    resolver_source = inspect.getsource(hr_service._resolve_existing_day_shift)
    assert hr_service._DEFAULT_DAY_SHIFT_CODE == "DEFAULT-DAY"
    assert hr_service._DEFAULT_DAY_PATTERN_CODE == "DEFAULT-DAY-5X2"
    assert "_resolve_existing_day_shift" in source
    assert "ShiftTemplate(" not in source
    assert '== "D"' in resolver_source
    assert "Create or activate a day-duty shift" in resolver_source
    assert "code=_DEFAULT_DAY_PATTERN_CODE" in source
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


def test_readiness_recognizes_scoped_automatic_patterns():
    resolver_source = inspect.getsource(hr_service._apply_automatic_pattern_readiness)
    assert "preview_patterns" in resolver_source
    assert 'resolution_source == "RULE"' in resolver_source
    assert 'item.pattern_state = "ASSIGNED"' in resolver_source
    assert "AMBIGUOUS_PATTERN_RULE" in resolver_source
    assert "_apply_automatic_pattern_readiness" in inspect.getsource(hr_service.dashboard_v2)


def test_effective_contract_gap_retains_future_starters():
    source = inspect.getsource(hr_service.dashboard_v2)
    assert "without_effective_contract" in source
    assert "not in current_contracts" in source
    assert "future_contract_users" in source
    assert "Edit future contract" in source
    assert "len(without_effective_contract)" in source


def test_default_day_bootstrap_repairs_non_monday_reserved_anchor():
    source = inspect.getsource(hr_service.bootstrap_default_day_pattern)
    assert "str(current.work_pattern_id) == str(pattern.id)" in source
    assert "current.cycle_anchor_date.weekday() == 0" in source
    assert "not current_is_reserved_default or current_default_anchor_is_monday" in source
    assert "cycle_anchor_date=week_monday" in source


def test_default_day_bootstrap_uses_owned_pattern_id_and_existing_shift():
    source = inspect.getsource(hr_service.bootstrap_default_day_pattern)
    resolver_source = inspect.getsource(hr_service._resolve_existing_day_shift)
    identity_source = inspect.getsource(hr_service._default_day_system_id)
    assert "uuid5" in identity_source
    assert "amo-portal:{amo_id}:{system_key}" in identity_source
    assert "system_id" in resolver_source
    assert "_DEFAULT_DAY_SHIFT_CODE" in resolver_source
    assert "pattern_by_code" in source
    assert "already owned by tenant configuration" in source
    assert "ShiftTemplate(" not in resolver_source
    assert "id=pattern_id" in source
    assert "current.work_pattern_id" in source
    assert "current.work_pattern.code" not in source


def test_default_day_bootstrap_audits_every_controlled_mutation():
    source = inspect.getsource(hr_service.bootstrap_default_day_pattern)
    audit_source = inspect.getsource(hr_service._bootstrap_audit)
    assert "create_audit_event" in audit_source
    assert "correlation_id=operation_id" in audit_source
    assert '"system_owned": True' in audit_source
    for action in (
        'action="bootstrap_create"',
        'action="bootstrap_update"',
        'action="bootstrap_close"',
        'action="bootstrap_delete"',
        'action="bootstrap_assign"',
    ):
        assert action.replace('action="', '').replace('"', '') in source
    assert 'entity_type="ShiftTemplate"' not in source
    assert 'entity_type="WorkPattern"' in source
    assert 'entity_type="EmployeeWorkPatternAssignment"' in source
    assert "before=current_before" in source
    assert "after=_pattern_assignment_snapshot" in source


def test_readiness_labels_only_the_managed_default_pattern():
    source = inspect.getsource(hr_service._person_readiness_for_user)
    assert "managed_default_pattern_id" in source
    assert "str(pattern.work_pattern_id) == managed_default_pattern_id" in source
    assert 'work_pattern.code == "DEFAULT-DAY-5X2"' not in source
    assert "amo_id=amo_id" in inspect.getsource(hr_service.list_people_page_v2)
    assert "amo_id=amo_id" in inspect.getsource(hr_service.dashboard_v2)


def test_bootstrap_definition_snapshots_include_attribution_mutations():
    pattern_source = inspect.getsource(hr_service._work_pattern_snapshot)
    assert '"updated_by_user_id"' in pattern_source
    assert '"updated_at"' in pattern_source
