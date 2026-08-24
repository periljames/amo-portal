from datetime import date
import inspect

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from amodb.apps.quality import canonical_router
from amodb.apps.quality import planner_calendar_router as calendar_module
from amodb.apps.quality.planner_calendar_enrichment_router import qms_planner_calendar_enriched
from amodb.apps.quality.planner_calendar_router import (
    _active_training_lifecycle_sql,
    _calendar_page,
    qms_planner_calendar,
)
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


def test_training_projection_selects_only_latest_active_record(monkeypatch) -> None:
    monkeypatch.setattr(
        calendar_module,
        "_table_columns",
        lambda _db, _table: {"record_status", "source_status"},
    )
    lifecycle = _active_training_lifecycle_sql(object())
    assert "r.record_status" in lifecycle
    assert "r.source_status" in lifecycle
    assert "RENEWED" in lifecycle
    assert "SUPERSEDED" in lifecycle

    source = inspect.getsource(qms_planner_calendar)
    assert "ROW_NUMBER() OVER" in source
    assert "PARTITION BY r.user_id, r.course_id" in source
    assert "record_rank = 1" in source
    assert source.index("record_rank = 1") < source.index("event_date >= :start_date")
    assert "/quality/audits/{row.get('id')}/setup" in source
    assert "/quality/audits/{row.get('id')}/overview" not in source
    assert "/quality/cars/{row.get('id')}/overview" in source


def test_calendar_page_is_stable_and_reports_next_offset() -> None:
    events = [
        {"id": "3", "date": "2026-08-20", "title": "Zulu"},
        {"id": "1", "date": "2026-08-18", "title": "Alpha"},
        {"id": "2", "date": "2026-08-19", "title": "Bravo"},
    ]
    page, has_more, next_offset = _calendar_page(events=events, offset=1, limit=1)
    assert [item["id"] for item in page] == ["2"]
    assert has_more is True
    assert next_offset == 2


def test_calendar_rejects_invalid_range_before_query(monkeypatch) -> None:
    class Context:
        amo_id = "amo-a"
        amo_code = "tenant-a"
        user_id = "quality-user-a"

    monkeypatch.setattr(calendar_module, "set_postgres_tenant_context", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(calendar_module, "_pg_set_read_timeout", lambda *_args, **_kwargs: None)

    with pytest.raises(HTTPException) as exc_info:
        qms_planner_calendar(
            start=date(2026, 8, 20),
            end=date(2026, 8, 18),
            limit=120,
            offset=0,
            view="week",
            source="all",
            ctx=Context(),
            db=object(),
        )
    assert exc_info.value.status_code == 422


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


def _route_count(api_router, endpoint) -> int:
    return sum(
        1
        for route_item in api_router.routes
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
    [canonical_router.core_router, canonical_router.router],
)
def test_planner_routes_precede_generic_catchalls(api_router) -> None:
    assert _route_index(api_router, qms_planner_calendar_enriched) < _catchall_index(api_router, "GET")
    assert _route_index(api_router, qms_planner_capabilities) < _catchall_index(api_router, "GET")
    assert _route_index(api_router, qms_planner_reschedule) < _catchall_index(api_router, "PATCH")
    assert _route_count(api_router, qms_planner_calendar_enriched) == 1

    calendar_gets = [
        route_item
        for route_item in api_router.routes
        if str(getattr(route_item, "path", "")).endswith("/integrations/calendar")
        and "GET" in set(getattr(route_item, "methods", None) or ())
    ]
    assert len(calendar_gets) == 1
    assert getattr(calendar_gets[0], "endpoint", None) is qms_planner_calendar_enriched


def test_router_cloning_does_not_copy_planner_lifecycle_handlers() -> None:
    for api_router in (canonical_router.core_router, canonical_router.router):
        lifecycle_names = {
            getattr(handler, "__name__", "")
            for handler in [*api_router.on_startup, *api_router.on_shutdown]
        }
        assert "_start_scheduler" not in lifecycle_names
        assert "_stop_scheduler" not in lifecycle_names


def _deployed_calendar_routes(app):
    return [
        route_item
        for route_item in app.routes
        if str(getattr(route_item, "path", "")).endswith("/integrations/calendar")
        and "GET" in set(getattr(route_item, "methods", None) or ())
    ]


@pytest.mark.parametrize("app_module", ["amodb.main", "amodb.quality_main"])
def test_deployed_apps_have_one_enriched_calendar_per_public_family(app_module: str) -> None:
    module = __import__(app_module, fromlist=["app"])
    app = module.app
    routes = _deployed_calendar_routes(app)
    by_path: dict[str, list] = {}
    for route_item in routes:
        by_path.setdefault(str(route_item.path), []).append(route_item)

    canonical_path = "/api/maintenance/{amo_code}/quality/integrations/calendar"
    assert len(by_path.get(canonical_path, [])) == 1
    assert all(
        getattr(route_item, "endpoint", None) is qms_planner_calendar_enriched
        for route_item in by_path[canonical_path]
    )

    operation_ids = [
        str(getattr(route_item, "operation_id", ""))
        for route_item in app.routes
        if getattr(route_item, "operation_id", None)
    ]
    assert len(operation_ids) == len(set(operation_ids))
