from __future__ import annotations

from .canonical_router import router
from .route_ordering import promote_route_family


def _is_preparation_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return ("/quality/audits/" in path or "/qms/audits/" in path) and (
        "/preparation-revisions" in path
        or path.endswith(("/preparation-readiness", "/activity", "/work-package", "/offline-pack"))
    )


promote_route_family(router, predicate=_is_preparation_route, label="QMS audit preparation")

from . import audit_preparation_context_route_order as _audit_preparation_context_route_order  # noqa: F401,E402

# Audit Notice governance is registered through this already-imported audit
# extension point so notice routes and models are available without widening
# the central Quality bootstrap surface.
from . import audit_notice_route_order as _audit_notice_route_order  # noqa: F401,E402
