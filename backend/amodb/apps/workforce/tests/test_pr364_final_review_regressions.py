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


def test_supervisor_stage_requires_assigned_supervisor():
    db = MagicMock()
    request_query = _query_returning(_overtime_row())
    contract = SimpleNamespace(supervisor_user_id="assigned-supervisor")
    contract_query = _query_returning(contract)
    db.query.side_effect = [request_query, contract_query]

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
