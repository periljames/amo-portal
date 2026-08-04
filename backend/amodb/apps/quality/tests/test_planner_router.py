from datetime import date
import inspect

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from amodb.apps.quality import canonical_router
from amodb.apps.quality.planner_router import (
    CalendarRescheduleRequest,
    _MUTABLE_CALENDAR_SOURCES,
    _parse_calendar_event_id,
    qms_planner_capabilities,
    qms_planner_reschedule,
)


def test_calendar_event_identifier_contract() -> None:
    assert _parse_calendar_event_id("audits:audit:123:audit_planned") == (
        "audits",
        "audit",
        "123",
        "audit_planned",
    )


@pytest.mark.parametrize(
    "event_id",
    ["", "audits", "audits:audit", "audits::123:audit_planned", "a:b:c:d:e"],
)
def test_invalid_calendar_event_identifier_is_rejected(event_id: str) -> None:
    with pytest.raises(HTTPException) as exc_info:
        _parse_calendar_event_id(event_id)
    assert exc_info.value.status_code == 422


def test_reschedule_requires_reason_and_expected_date_is_optional() -> None:
    payload = CalendarRescheduleRequest(
        event_id="audits:audit:123:audit_planned",
        new_date=date(2026, 7, 27),
        reason="Operational coverage changed.",
    )
    assert payload.expected_old_date is None
    assert payload.new_date == date(2026, 7, 27)

    with pytest.raises(ValidationError):
        CalendarRescheduleRequest(
            event_id="audits:audit:123:audit_planned",
            new_date=date(2026, 7, 27),
            reason="short",
        )


def test_only_authoritative_active_schedule_sources_are_mutable() -> None:
    assert set(_MUTABLE_CALENDAR_SOURCES) == {
        "audit_schedule",
        "audit",
        "car",
        "training_event",
    }
    assert "training_record" not in _MUTABLE_CALENDAR_SOURCES
    assert all(source["permission"] == "qms.calendar.manage" for source in _MUTABLE_CALENDAR_SOURCES.values())

    predicates = {key: str(value["active_predicate"]) for key, value in _MUTABLE_CALENDAR_SOURCES.items()}
    assert "is_active IS TRUE" in predicates["audit_schedule"]
    assert "deleted_at IS NULL" in predicates["audit_schedule"]
    assert "deleted_at IS NULL" in predicates["audit"]
    assert "CLOSED" in predicates["audit"] and "CANCELLED" in predicates["audit"]
    assert "closed_at IS NULL" in predicates["car"]
    assert "CLOSED" in predicates["car"] and "CANCELLED" in predicates["car"]
    assert "CANCELLED" in predicates["training_event"]


def test_reschedule_contract_rechecks_lifecycle_and_logs_before_commit() -> None:
    source = inspect.getsource(qms_planner_reschedule)
    assert source.count("active_predicate") >= 3
    assert "This schedule is no longer active" in source
    assert "left the active calendar" in source
    assert "result.rowcount != 1" in source
    assert "_log_qms_activity(" in source
    assert "calendar_schedule_rescheduled" in source
    assert source.index("_log_qms_activity(") < source.index("db.commit()")
    assert '"reason": payload.reason.strip()' in source
    assert '"trace_id": trace_id' in source


def test_canonical_router_reexports_dashboard_private_helpers() -> None:
    assert callable(canonical_router._pg_set_read_timeout)
    assert callable(canonical_router._recover_qms_read_session)
    assert callable(canonical_router._table_columns)


def _route_index(api_router, endpoint) -> int:
    return next(
        index
        for index, route_item in enumerate(api_router.routes)
        if getattr(route_item, "endpoint", None) is endpoint
    )


def _catchall_index(api_router, method: str) -> int:
    return next(
        index
        for index, route_item in enumerate(api_router.routes)
        if str(getattr(route_item, "path", "")).endswith("/{module_path:path}")
        and method in set(getattr(route_item, "methods", None) or ())
    )


@pytest.mark.parametrize(
    "api_router",
    [canonical_router.core_router, canonical_router.router, canonical_router.legacy_router],
)
def test_planner_routes_precede_generic_catchalls(api_router) -> None:
    assert _route_index(api_router, qms_planner_capabilities) < _catchall_index(api_router, "GET")
    assert _route_index(api_router, qms_planner_reschedule) < _catchall_index(api_router, "PATCH")
