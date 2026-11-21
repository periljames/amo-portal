from __future__ import annotations

from amodb.apps.quality import audit_checklist_template_route_order as _audit_checklist_template_route_order  # noqa: F401
from amodb.apps.quality.canonical_router import router


def _route_index(api_router, predicate) -> int:
    return next(index for index, route_item in enumerate(api_router.routes) if predicate(route_item))


def test_live_fieldwork_routes_precede_generic_catchall() -> None:
    api_router = router
    mutation_index = _route_index(
        api_router,
        lambda route_item: (
            "/audits/{audit_id}/checklist-items/{item_id}/fieldwork-mutations" in str(getattr(route_item, "path", ""))
            and "POST" in set(getattr(route_item, "methods", None) or ())
        ),
    )
    finding_index = _route_index(
        api_router,
        lambda route_item: (
            "/audits/{audit_id}/checklist-items/{item_id}/fieldwork-findings" in str(getattr(route_item, "path", ""))
            and "POST" in set(getattr(route_item, "methods", None) or ())
        ),
    )
    catchall_index = _route_index(
        api_router,
        lambda route_item: (
            str(getattr(route_item, "path", "")).endswith("/{module_path:path}")
            and "POST" in set(getattr(route_item, "methods", None) or ())
        ),
    )

    assert mutation_index < catchall_index
    assert finding_index < catchall_index
    assert getattr(getattr(api_router.routes[mutation_index], "endpoint", None), "__name__", "") == "mutate_live_fieldwork"
    assert getattr(getattr(api_router.routes[finding_index], "endpoint", None), "__name__", "") == "create_atomic_fieldwork_finding"
