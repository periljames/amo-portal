from . import models
from .router import router

# Phase 2 makes fleet.aircraft_usage the sole accepted utilisation ledger. Keep
# the legacy technical_aircraft_utilisation model for reconciliation and
# migration evidence, but do not register its duplicate GET/POST API paths.
_CANONICAL_UTILISATION_PATH = "/records/aircraft/{tail_id}/utilisation"
router.routes = [
    route
    for route in router.routes
    if not (
        getattr(route, "path", None) == _CANONICAL_UTILISATION_PATH
        and bool((getattr(route, "methods", set()) or set()) & {"GET", "POST"})
    )
]

__all__ = ["router", "models"]
