from . import models
from .router import router

# The canonical utilisation control router owns the accepted ledger contract.
# Remove the two legacy Technical Records handlers before OpenAPI and runtime
# routing are assembled so duplicate paths cannot bypass correction control.
_LEGACY_UTILISATION_PATH = "/records/aircraft/{tail_id}/utilisation"
router.routes[:] = [
    route
    for route in router.routes
    if not (
        getattr(route, "path", None) == _LEGACY_UTILISATION_PATH
        and bool({"GET", "POST"}.intersection(getattr(route, "methods", set()) or set()))
    )
]

# Fleet rollout and spreadsheet retirement are final Technical Records cutover
# controls. Mount them under /records/rollout while the Planning frontend keeps
# the operational cockpit inside Utilisation Control.
from amodb.apps.integrations.rollout_router import router as rollout_router

router.include_router(rollout_router)

__all__ = ["router", "models"]
