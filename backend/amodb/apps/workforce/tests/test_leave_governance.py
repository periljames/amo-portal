from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from amodb.apps.workforce import models, services


class _NoopDb:
    pass


def _leave_type(availability_type, eligible_gender="ALL"):
    return SimpleNamespace(
        name="Controlled leave",
        availability_type=availability_type,
        eligible_gender=eligible_gender,
        supervisor_approval_required=True,
    )


def _request(*, user_id="employee", department_id="engineering"):
    return SimpleNamespace(
        user_id=user_id,
        amo_id="tenant",
        status=models.LeaveRequestStatus.SUBMITTED,
        starts_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        leave_type=_leave_type(models.AvailabilityType.ANNUAL_LEAVE),
        user=SimpleNamespace(department_id=department_id),
    )


def test_maternity_leave_forces_female_eligibility(monkeypatch) -> None:
    monkeypatch.setattr(
        services,
        "personnel_profile_for_user",
        lambda *args, **kwargs: SimpleNamespace(gender="MALE"),
    )
    leave_type = _leave_type(models.AvailabilityType.MATERNITY_LEAVE, "ALL")

    eligible, reason = services._leave_type_eligibility(
        _NoopDb(),
        amo_id="tenant",
        user_id="employee",
        leave_type=leave_type,
    )

    assert eligible is False
    assert "female" in str(reason).lower()
    assert services._controlled_leave_gender(
        models.AvailabilityType.MATERNITY_LEAVE,
        "ALL",
    ) == "FEMALE"


def test_paternity_leave_forces_male_eligibility(monkeypatch) -> None:
    monkeypatch.setattr(
        services,
        "personnel_profile_for_user",
        lambda *args, **kwargs: SimpleNamespace(gender="FEMALE"),
    )
    leave_type = _leave_type(models.AvailabilityType.PATERNITY_LEAVE, "ALL")

    eligible, reason = services._leave_type_eligibility(
        _NoopDb(),
        amo_id="tenant",
        user_id="employee",
        leave_type=leave_type,
    )

    assert eligible is False
    assert "male" in str(reason).lower()


def test_assigned_immediate_supervisor_can_approve(monkeypatch) -> None:
    row = _request()
    actor = SimpleNamespace(id="supervisor")
    monkeypatch.setattr(
        services,
        "active_contract_for_user",
        lambda *args, **kwargs: SimpleNamespace(supervisor_user_id="supervisor"),
    )
    monkeypatch.setattr(services, "_postholder_department_ids", lambda *args, **kwargs: set())

    assert services.can_actor_supervisor_approve(_NoopDb(), row=row, actor=actor) is True


def test_unrelated_reviewer_cannot_approve_supervisor_stage(monkeypatch) -> None:
    row = _request()
    actor = SimpleNamespace(id="unrelated")
    monkeypatch.setattr(
        services,
        "active_contract_for_user",
        lambda *args, **kwargs: SimpleNamespace(supervisor_user_id="supervisor"),
    )
    monkeypatch.setattr(services, "_postholder_department_ids", lambda *args, **kwargs: set())

    assert services.can_actor_supervisor_approve(_NoopDb(), row=row, actor=actor) is False


def test_active_department_postholder_can_approve(monkeypatch) -> None:
    row = _request(department_id="engineering")
    actor = SimpleNamespace(id="postholder")
    monkeypatch.setattr(
        services,
        "active_contract_for_user",
        lambda *args, **kwargs: SimpleNamespace(supervisor_user_id="someone-else"),
    )
    monkeypatch.setattr(
        services,
        "_postholder_department_ids",
        lambda *args, **kwargs: {"engineering"},
    )

    assert services.can_actor_supervisor_approve(_NoopDb(), row=row, actor=actor) is True
