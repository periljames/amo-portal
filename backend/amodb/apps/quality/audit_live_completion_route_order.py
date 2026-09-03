from __future__ import annotations

from . import audit_live_completion_models as _audit_live_completion_models  # noqa: F401
from . import audit_live_completion_router
from .canonical_router import router
from .route_ordering import assert_unique_routes, promote_route_family
from .router import public_router as quality_public_router


def _is_completion_route(route_item) -> bool:
    path = str(getattr(route_item, "path", ""))
    return (
        "/audit-webauthn/" in path
        or "/closing-acknowledgements" in path
        or "/verification-tokens" in path
        or "/signature/options" in path
        or "/signature/verify" in path
        or ("/report-revisions/" in path and path.endswith("/transitions"))
    ) and ("/quality/" in path or "/qms/" in path)


router.include_router(audit_live_completion_router.router)
promote_route_family(router, predicate=_is_completion_route, label="QMS live-audit completion")

quality_public_router.include_router(audit_live_completion_router.public_router)
assert_unique_routes(quality_public_router, label="QMS public API")
