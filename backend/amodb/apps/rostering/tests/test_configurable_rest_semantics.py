from __future__ import annotations

from types import SimpleNamespace

from amodb.apps.rostering import compliance_policy, models
from amodb.apps.rostering.code_registry_models import RosterDutySemantic


def test_protected_rest_uses_configured_semantic_not_literal_code_or_kind():
    shift = SimpleNamespace(
        id="shift-rest-custom",
        code="ZZ",
        kind=models.ShiftTemplateKind.OTHER,
        counts_as_duty=False,
    )
    policy = SimpleNamespace(duty_semantic=RosterDutySemantic.REST)
    row = SimpleNamespace(
        shift_template=shift,
        status=models.RosterAssignmentStatus.OTHER,
    )

    assert compliance_policy.assignment_is_protected_rest(
        row,
        policies={shift.id: policy},
    ) is True


def test_non_rest_non_duty_semantic_does_not_satisfy_weekly_rest():
    shift = SimpleNamespace(
        id="shift-leave-custom",
        code="LV",
        kind=models.ShiftTemplateKind.OTHER,
        counts_as_duty=False,
    )
    policy = SimpleNamespace(duty_semantic=RosterDutySemantic.LEAVE)
    row = SimpleNamespace(
        shift_template=shift,
        status=models.RosterAssignmentStatus.LEAVE,
    )

    assert compliance_policy.assignment_is_protected_rest(
        row,
        policies={shift.id: policy},
    ) is False


def test_consecutive_duty_rule_is_a_non_overridable_planning_warning():
    row = SimpleNamespace(
        code=compliance_policy.CONSECUTIVE_DUTY_RULE,
        parameters_json={"maximum_days": 12},
        severity=models.RosterValidationSeverity.WARNING,
        allow_override=True,
    )

    compliance_policy._govern_rule(row)

    assert row.parameters_json["maximum_days"] == 12
    assert row.severity == models.RosterValidationSeverity.WARNING
    assert row.allow_override is False
    assert compliance_policy.statutory_rule_is_non_overridable(row.code) is False


def test_normal_hours_warning_carries_overtime_classification_metadata():
    row = SimpleNamespace(
        code=compliance_policy.NORMAL_HOURS_CLASSIFICATION_RULE,
        parameters_json={"window_days": 7, "maximum_minutes": 52 * 60},
        severity=models.RosterValidationSeverity.BLOCKER,
        allow_override=True,
    )

    compliance_policy._govern_rule(row)

    assert row.severity == models.RosterValidationSeverity.WARNING
    assert row.allow_override is False
    assert row.parameters_json["classification"] == "ORDINARY_OT"
    assert row.parameters_json["minimum_multiplier"] == 1.5
