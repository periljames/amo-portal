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


# Public route composition is a separate trust boundary: nested routers must not
# repeat the parent's /quality prefix. Otherwise valid auditee/authenticated
# external-auditor requests silently return 404 after token exchange.
def test_public_audit_routes_are_mounted_at_the_single_quality_prefix() -> None:
    from amodb.apps.quality.router import public_router

    routes = {
        (str(route.path), method, getattr(route.endpoint, "__name__", ""))
        for route in public_router.routes
        for method in set(getattr(route, "methods", None) or ())
    }
    required = {
        ("/quality/audit-access/closing", "GET", "public_closing_context"),
        ("/quality/audit-access/closing/acknowledgements", "POST", "public_closing_acknowledgement"),
        ("/quality/audit-access/presence/heartbeat", "POST", "heartbeat_public_audit_presence"),
        ("/quality/audit-access/collaboration", "GET", "get_public_occurrence_collaboration_scoped"),
    }
    for path, method, endpoint in required:
        assert (path, method, endpoint) in routes, f"Missing public audit endpoint: {method} {path} ({endpoint})"

    paths = {path for path, _, _ in routes}
    assert not any(path.startswith("/quality/quality/") for path in paths)
    assert "/quality/audit-access/governed-document-requests" in paths
    assert "/quality/audit-access/fieldwork/checklist-items/{item_id}/evidence" in paths
