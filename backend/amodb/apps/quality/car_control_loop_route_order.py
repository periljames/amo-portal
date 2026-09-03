from __future__ import annotations

from . import car_control_loop_authority_guard
from . import car_control_loop_evidence_guard
from .canonical_router import router
from .route_ordering import promote_route_family


router.include_router(car_control_loop_authority_guard.router)
router.include_router(car_control_loop_evidence_guard.router)


def _is_control_loop_route(route_item: object) -> bool:
    path = str(getattr(route_item, "path", ""))
    return (
        "/cars/" in path
        and "/control-loop" in path
        and ("/quality/" in path or "/qms/" in path)
    )


promote_route_family(router, predicate=_is_control_loop_route, label="QMS CAR control loop")

# The session projection is registered from this established extension point.
from . import audit_session_route_order as _audit_session_route_order  # noqa: E402,F401
