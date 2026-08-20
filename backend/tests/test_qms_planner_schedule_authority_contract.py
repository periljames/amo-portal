from __future__ import annotations

from amodb.apps.quality import router as primary_quality_router
from amodb.apps.quality.canonical_router import legacy_router, router
from amodb.apps.quality.planner_router import _MUTABLE_CALENDAR_SOURCES


def _paths(api_router) -> list[str]:
    return [str(getattr(item, "path", "")) for item in api_router.routes]


def test_superseded_audit_schedule_http_family_is_not_mounted():
    for api_router in (primary_quality_router, router, legacy_router):
        retired = [path for path in _paths(api_router) if "/audits/schedules" in path]
        assert retired == []


def test_authoritative_planner_schedule_routes_are_mounted_before_catchall():
    for api_router in (router, legacy_router):
        paths = _paths(api_router)
        list_index = next(index for index, path in enumerate(paths) if path.endswith("/integrations/calendar/audit-schedules"))
        date_index = next(index for index, path in enumerate(paths) if path.endswith("/integrations/calendar/audit-schedules/{schedule_id}/date"))
        catchall_index = next(index for index, path in enumerate(paths) if path.endswith("/{module_path:path}"))
        assert list_index < catchall_index
        assert date_index < catchall_index


def test_audit_schedule_templates_cannot_use_generic_calendar_rescheduler():
    assert "audit_schedule" not in _MUTABLE_CALENDAR_SOURCES
    assert {"audit", "car", "training_event"}.issubset(_MUTABLE_CALENDAR_SOURCES)
