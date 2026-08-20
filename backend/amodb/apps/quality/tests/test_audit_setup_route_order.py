from __future__ import annotations

import pytest

from amodb.apps.quality import audit_session_route_order as _audit_session_route_order  # noqa: F401
from amodb.apps.quality.canonical_router import legacy_router, router


def _route_index(api_router, predicate) -> int:
    return next(index for index, route_item in enumerate(api_router.routes) if predicate(route_item))


@pytest.mark.parametrize("api_router", [router, legacy_router])
def test_setup_patch_precedes_generic_catchall(api_router) -> None:
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
