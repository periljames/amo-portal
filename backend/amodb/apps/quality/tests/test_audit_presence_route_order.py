from __future__ import annotations

from amodb.apps.quality import audit_session_route_order as _audit_session_route_order  # noqa: F401
from amodb.apps.quality.canonical_router import router


def _route_index(api_router, predicate) -> int:
    return next(index for index, route_item in enumerate(api_router.routes) if predicate(route_item))


def test_presence_routes_precede_generic_catchall() -> None:
    api_router = router
    heartbeat_index = _route_index(
        api_router,
        lambda route_item: (
            "/audits/{audit_id}/presence/heartbeat" in str(getattr(route_item, "path", ""))
            and "POST" in set(getattr(route_item, "methods", None) or ())
        ),
    )
    list_index = _route_index(
        api_router,
        lambda route_item: (
            str(getattr(route_item, "path", "")).endswith("/audits/{audit_id}/presence")
            and "GET" in set(getattr(route_item, "methods", None) or ())
        ),
    )
    catchall_index = _route_index(
        api_router,
        lambda route_item: (
            str(getattr(route_item, "path", "")).endswith("/{module_path:path}")
            and bool(set(getattr(route_item, "methods", None) or ()) & {"GET", "POST"})
        ),
    )

    assert heartbeat_index < catchall_index
    assert list_index < catchall_index
    assert getattr(getattr(api_router.routes[heartbeat_index], "endpoint", None), "__name__", "") == (
        "heartbeat_internal_audit_presence"
    )
    assert getattr(getattr(api_router.routes[list_index], "endpoint", None), "__name__", "") == (
        "list_internal_audit_presence"
    )
