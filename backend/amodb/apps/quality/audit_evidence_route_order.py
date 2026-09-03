from __future__ import annotations

from . import audit_evidence_models as _audit_evidence_models  # noqa: F401
from . import audit_evidence_router
from .canonical_router import router
from .route_ordering import assert_unique_routes, promote_route_family
from .router import public_router as quality_public_router


def _is_evidence_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return (
        "/evidence" in path
        or ("/findings/" in path and path.endswith("/release"))
    ) and ("/quality/" in path or "/qms/" in path)


router.include_router(audit_evidence_router.router)
promote_route_family(router, predicate=_is_evidence_route, label="QMS audit evidence")

quality_public_router.include_router(audit_evidence_router.public_router)
assert_unique_routes(quality_public_router, label="QMS public API")
