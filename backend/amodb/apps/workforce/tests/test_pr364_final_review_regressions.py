from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from amodb.apps.accounts import models as account_models
from amodb.apps.workforce import hr_service, models, services


def _query_returning(value):
    query = MagicMock()
    query.options.return_value = query
    query.filter.return_value = query
    query.with_for_update.return_value = query
    query.order_by.return_value = query
    query.first.return_value = value
    return query


def _overtime_row(user_id: str = "employee-1"):
    return SimpleNamespace(
        id="ot-1",
        amo_id="amo-1",
        user_id=user_id,
        starts_at=datetime(2026, 7, 29, 17, tzinfo=timezone.utc),
        status=models.OvertimeRequestStatus.SUBMITTED,
    )


def _decision(stage: str = "SUPERVISOR"):
    return SimpleNamespace(stage=stage, decision="APPROVED", comment="Reviewed")


def test_overtime_requester_cannot_self_approve():
    db = MagicMock()
    db.query.return_value = _query_returning(_overtime_row())

    with pytest.raises(ValueError, match="cannot approve their own"):
        hr_service.decide_overtime(
            db,
            amo_id="amo-1",
            actor_user_id="employee-1",
            request_id="ot-1",
            payload=_decision(),
        )

    db.add.assert_not_called()


def test_supervisor_stage_requires_assigned_supervisor(monkeypatch):
    db = MagicMock()
    request_query = _query_returning(_overtime_row())
    contract = SimpleNamespace(supervisor_user_id="assigned-supervisor")
    contract_query = _query_returning(contract)
    db.query.side_effect = [request_query, contract_query]
    monkeypatch.setattr(
        hr_service,
        "_amo_work_date",
        lambda *args, **kwargs: date(2026, 7, 29),
    )

    with pytest.raises(ValueError, match="assigned supervisor"):
        hr_service.decide_overtime(
            db,
            amo_id="amo-1",
            actor_user_id="different-manager",
            request_id="ot-1",
            payload=_decision(),
        )

    db.add.assert_not_called()


class _PatternQuery:
    def __init__(self, *, first_value=None):
        self.first_value = first_value
        self.criteria = []
        self.joined = False

    def join(self, *args, **kwargs):
        self.joined = True
        return self

    def options(self, *args, **kwargs):
        return self

    def filter(self, *criteria):
        self.criteria.extend(criteria)
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self.first_value

    def all(self):
        return []


def test_pattern_generation_query_excludes_inactive_patterns():
    amo_query = _PatternQuery(first_value=SimpleNamespace(time_zone="UTC"))
    assignment_query = _PatternQuery()
    db = MagicMock()

    def query(entity):
        return amo_query if entity is account_models.AMO else assignment_query

    db.query.side_effect = query
    payload = SimpleNamespace(
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 31),
        user_ids=[],
        roster_version_id=None,
    )

    response = services.preview_patterns(db, amo_id="amo-1", payload=payload)

    assert response.item_count == 0
    assert assignment_query.joined is True
    assert any("work_patterns.is_active" in str(item) for item in assignment_query.criteria)


class _CountQuery:
    def __init__(self, value: int):
        self.value = value

    def filter(self, *args, **kwargs):
        return self

    def scalar(self):
        return self.value


def test_dashboard_pending_counts_are_uncapped():
    expected = {
        "leave": 73,
        "timesheet": 81,
        "overtime": 64,
        "attendance_exception": 92,
    }
    db = MagicMock()

    def query(expression):
        rendered = str(expression)
        if "leave_requests" in rendered:
            return _CountQuery(expected["leave"])
        if "timesheets" in rendered:
            return _CountQuery(expected["timesheet"])
        if "overtime_requests" in rendered:
            return _CountQuery(expected["overtime"])
        if "roster_actual_variances" in rendered:
            return _CountQuery(expected["attendance_exception"])
        raise AssertionError(rendered)

    db.query.side_effect = query

    assert hr_service._pending_queue_counts(db, amo_id="amo-1") == expected


def test_leave_minutes_follow_work_pattern_instead_of_charging_24_hour_days(monkeypatch):
    db = MagicMock()
    db.query.return_value = _query_returning(SimpleNamespace(time_zone="Africa/Nairobi"))
    monkeypatch.setattr(
        services,
        "preview_patterns",
        lambda *_args, **_kwargs: SimpleNamespace(items=[
            SimpleNamespace(planned_minutes=480),
            SimpleNamespace(planned_minutes=0),
            SimpleNamespace(planned_minutes=480),
        ]),
    )

    requested = services._requested_minutes(
        db,
        amo_id="amo-1",
        user_id="employee-1",
        starts_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
        ends_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
        explicit=None,
    )

    assert requested == 960


def test_attendance_exception_serializes_canonical_evidence():
    row = SimpleNamespace(
        id="variance-1",
        amo_id="amo-1",
        roster_assignment_id="assignment-1",
        user_id="employee-1",
        planned_minutes=480,
        attendance_minutes=430,
        productive_minutes=410,
        variance_minutes=-50,
        classification="UNDER_RECORDED",
        metadata_json={"source": "attendance"},
        calculated_at=datetime(2026, 7, 29, 18, tzinfo=timezone.utc),
    )
    user = SimpleNamespace(full_name="Amina Engineer")

    result = hr_service.serialize_attendance_exception(row, user=user)

    assert result.user_full_name == "Amina Engineer"
    assert result.roster_assignment_id == "assignment-1"
    assert result.variance_minutes == -50
    assert result.metadata_json == {"source": "attendance"}


@pytest.mark.parametrize(
    ("state", "event_type"),
    [
        ("CLOCKED_OUT", models.AttendanceEventType.CLOCK_IN),
        ("WORKING", models.AttendanceEventType.BREAK_START),
        ("WORKING", models.AttendanceEventType.CLOCK_OUT),
        ("ON_BREAK", models.AttendanceEventType.BREAK_END),
        ("ON_BREAK", models.AttendanceEventType.CLOCK_OUT),
    ],
)
def test_attendance_live_state_accepts_only_valid_transitions(state, event_type):
    services._validate_attendance_transition(state=state, event_type=event_type)


@pytest.mark.parametrize(
    ("state", "event_type"),
    [
        ("CLOCKED_OUT", models.AttendanceEventType.CLOCK_OUT),
        ("WORKING", models.AttendanceEventType.CLOCK_IN),
        ("ON_BREAK", models.AttendanceEventType.BREAK_START),
    ],
)
def test_attendance_live_state_rejects_duplicate_or_impossible_transitions(state, event_type):
    with pytest.raises(ValueError, match="not valid"):
        services._validate_attendance_transition(state=state, event_type=event_type)


class _ScalarQuery:
    def __init__(self, value):
        self.value = value

    def filter(self, *args, **kwargs):
        return self

    def scalar(self):
        return self.value


def test_amo_work_date_uses_tenant_timezone():
    db = MagicMock()
    db.query.return_value = _ScalarQuery("Africa/Nairobi")
    instant = datetime(2026, 7, 29, 22, 30, tzinfo=timezone.utc)
    assert hr_service._amo_work_date(db, amo_id="amo-1", instant=instant) == date(2026, 7, 30)


def test_roster_assignment_validation_rejects_cross_user_link():
    assignment = SimpleNamespace(
        amo_id="amo-1",
        user_id="employee-2",
        deleted_at=None,
        starts_at=datetime(2026, 7, 29, 17, tzinfo=timezone.utc),
        ends_at=datetime(2026, 7, 29, 20, tzinfo=timezone.utc),
    )
    db = MagicMock()
    db.query.return_value = _query_returning(assignment)
    with pytest.raises(ValueError, match="does not belong"):
        hr_service._validated_roster_assignment(
            db,
            amo_id="amo-1",
            user_id="employee-1",
            assignment_id="assignment-1",
            starts_at=datetime(2026, 7, 29, 18, tzinfo=timezone.utc),
            ends_at=datetime(2026, 7, 29, 19, tzinfo=timezone.utc),
        )


def test_people_register_is_paginated_without_truncating_total(monkeypatch):
    contracts = []
    for index in range(0, 501):
        user = SimpleNamespace(
            id=f"user-{index}",
            staff_code=f"S{index:04d}",
            full_name=f"Employee {index:04d}",
            position_title="Engineer",
            department=None,
        )
        contracts.append(SimpleNamespace(
            id=f"contract-{index}",
            user_id=user.id,
            user=user,
            employment_status=models.EmploymentStatus.ACTIVE,
            contract_type=models.ContractType.PERMANENT,
            effective_from=date(2026, 1, 1),
            effective_to=None,
            primary_base_station_id=None,
            primary_base=None,
            supervisor=None,
            standard_weekly_minutes=2400,
            standard_daily_minutes=480,
            fte_percentage=100,
            cost_centre=None,
            payroll_number=None,
            overtime_eligible=True,
            night_shift_eligible=False,
            standby_eligible=False,
        ))
    monkeypatch.setattr(hr_service, "_active_contracts", lambda *args, **kwargs: contracts)
    monkeypatch.setattr(hr_service, "_effective_patterns", lambda *args, **kwargs: {})
    monkeypatch.setattr(hr_service, "_active_leave", lambda *args, **kwargs: {})
    result = hr_service.list_people_page(MagicMock(), amo_id="amo-1", page=6, page_size=100)
    assert result.total == 501
    assert result.pages == 6
    assert len(result.items) == 1
