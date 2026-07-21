from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from amodb.apps.accounts import models as account_models
from amodb.apps.rostering import models, validation
from amodb.apps.workforce import permissions

UTC = timezone.utc


def assignment(assignment_id: str, starts_at: datetime, ends_at: datetime):
    return SimpleNamespace(
        id=assignment_id,
        amo_id="amo-1",
        user_id="user-1",
        department_id="dept-1",
        base_station_id="base-1",
        shift_template_id="shift-1",
        starts_at=starts_at,
        ends_at=ends_at,
        planned_minutes=int((ends_at - starts_at).total_seconds() // 60),
        status=models.RosterAssignmentStatus.DUTY,
        shift_template=None,
    )


def rule(rule_id: str, rule_type: models.RosterRuleType, *, minutes: int, severity=models.RosterValidationSeverity.BLOCKER):
    parameter_key = "minimum_minutes" if rule_type == models.RosterRuleType.MIN_REST_HOURS else "maximum_minutes"
    return SimpleNamespace(
        id=rule_id,
        code=rule_type.value,
        rule_type=rule_type,
        scope=models.RosterRuleScope.AMO,
        severity=severity,
        parameters_json={parameter_key: minutes},
        allow_override=True,
        department_id=None,
        base_station_id=None,
        shift_template_id=None,
        user_id=None,
        display_order=100,
    )


def test_overlap_is_blocking_and_not_treated_as_rest_shortfall():
    first = assignment("a1", datetime(2026, 7, 21, 5, tzinfo=UTC), datetime(2026, 7, 21, 13, tzinfo=UTC))
    second = assignment("a2", datetime(2026, 7, 21, 12, tzinfo=UTC), datetime(2026, 7, 21, 20, tzinfo=UTC))
    findings = validation._overlap_and_rest_findings(
        [first, second],
        [
            rule("overlap", models.RosterRuleType.OVERLAP, minutes=0),
            rule("rest", models.RosterRuleType.MIN_REST_HOURS, minutes=480),
        ],
    )
    assert len(findings) == 1
    assert findings[0].code == "OVERLAPPING_ASSIGNMENTS"
    assert findings[0].details["overlap_minutes"] == 60


def test_minimum_rest_uses_configured_minutes_not_hardcoded_hours():
    first = assignment("a1", datetime(2026, 7, 21, 5, tzinfo=UTC), datetime(2026, 7, 21, 13, tzinfo=UTC))
    second = assignment("a2", datetime(2026, 7, 21, 20, tzinfo=UTC), datetime(2026, 7, 22, 4, tzinfo=UTC))
    findings = validation._overlap_and_rest_findings(
        [first, second],
        [rule("rest", models.RosterRuleType.MIN_REST_HOURS, minutes=600)],
    )
    assert len(findings) == 1
    assert findings[0].code == models.RosterRuleType.MIN_REST_HOURS.value
    assert findings[0].details == {
        "previous_assignment_id": "a1",
        "rest_minutes": 420,
        "minimum_minutes": 600,
    }


def test_default_permissions_preserve_employee_self_service():
    user = SimpleNamespace(
        role=account_models.AccountRole.TECHNICIAN,
        is_system_account=False,
        is_superuser=False,
        is_amo_admin=False,
        position_title="Aircraft Technician",
        department=None,
    )
    granted = permissions.default_permissions_for(user)
    assert permissions.PermissionCode.ROSTER_VIEW_OWN.value in granted
    assert permissions.PermissionCode.LEAVE_REQUEST.value in granted
    assert permissions.PermissionCode.ROSTER_EDIT.value not in granted


def test_planner_permissions_include_edit_validate_submit_and_allocate():
    user = SimpleNamespace(
        role=account_models.AccountRole.PLANNING_ENGINEER,
        is_system_account=False,
        is_superuser=False,
        is_amo_admin=False,
        position_title="Planning Engineer",
        department=None,
    )
    granted = permissions.default_permissions_for(user)
    expected = {
        permissions.PermissionCode.ROSTER_EDIT.value,
        permissions.PermissionCode.ROSTER_VALIDATE.value,
        permissions.PermissionCode.ROSTER_SUBMIT.value,
        permissions.PermissionCode.ROSTER_ALLOCATE_WORK.value,
    }
    assert expected.issubset(granted)
    assert permissions.PermissionCode.ROSTER_OVERRIDE_BLOCKER.value not in granted
