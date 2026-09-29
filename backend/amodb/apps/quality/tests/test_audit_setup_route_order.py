from __future__ import annotations

import inspect

from amodb.apps.quality import audit_session_route_order as _audit_session_route_order  # noqa: F401
from amodb.apps.quality.canonical_router import router
from amodb.apps.quality.audit_session_router import AuditSetupUpdate, update_audit_setup


def _route_index(api_router, predicate) -> int:
    return next(index for index, route_item in enumerate(api_router.routes) if predicate(route_item))


def test_setup_patch_precedes_generic_catchall() -> None:
    api_router = router
    setup_index = _route_index(
        api_router,
        lambda route_item: (
            str(getattr(route_item, "path", "")).endswith("/audits/{audit_id}/setup")
            and "PATCH" in set(getattr(route_item, "methods", None) or ())
        ),
    )
    catchall_index = _route_index(
        api_router,
        lambda route_item: (
            str(getattr(route_item, "path", "")).endswith("/{module_path:path}")
            and "PATCH" in set(getattr(route_item, "methods", None) or ())
        ),
    )

    assert setup_index < catchall_index
    assert getattr(getattr(api_router.routes[setup_index], "endpoint", None), "__name__", "") == "update_audit_setup"


def test_setup_reschedule_requires_and_audits_a_reason() -> None:
    fields = AuditSetupUpdate.model_fields
    assert "reschedule_reason" in fields
    source = inspect.getsource(update_audit_setup)
    assert "AUDIT_RESCHEDULE_REASON_REQUIRED" in source
    assert 'action="audit_setup_rescheduled"' in source
    assert '"reason": reschedule_reason' in source
    assert "_log_qms_activity(" in source



def test_setup_can_replace_legacy_invalid_schedule_without_validating_old_window() -> None:
    source = inspect.getsource(update_audit_setup)

    assert "current_start_time, current_end_time = validate_planned_window" not in source
    assert "if schedule_fields_present:" in source
    assert "historical_time_text" in source
    assert "validate_planned_window(" in source
