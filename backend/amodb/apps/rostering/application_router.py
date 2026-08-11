# backend/amodb/apps/rostering/application_router.py
"""Application-level router aggregate for workforce-integrated rostering.

`amodb.main` historically imports `amodb.apps.rostering.router.router`. The
package initializer replaces that submodule export with this aggregate, which
preserves the existing bootstrap import while mounting the canonical sibling
prefixes `/rostering` and `/workforce`.
"""
from fastapi import APIRouter

from . import router as rostering_route_module
from .aircraft_allocation_router import router as aircraft_allocation_router
from .automation_router import router as automation_router
from .code_registry_router import router as code_registry_router
from .commitments_router import router as commitments_router
from ..workforce.bulk_router import router as workforce_bulk_router
from ..workforce.governance_router import router as workforce_governance_router
from ..workforce.hr_router import router as workforce_hr_router
from ..workforce.router_entry import router as workforce_router
from ..workforce.selection_router import router as workforce_selection_router

router = APIRouter()
router.include_router(rostering_route_module.router)
router.include_router(code_registry_router)
router.include_router(aircraft_allocation_router)
router.include_router(automation_router)
router.include_router(commitments_router)
router.include_router(workforce_router)
router.include_router(workforce_hr_router)
router.include_router(workforce_governance_router)
router.include_router(workforce_selection_router)
router.include_router(workforce_bulk_router)

__all__ = ["router"]
