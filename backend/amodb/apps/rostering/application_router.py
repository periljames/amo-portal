# backend/amodb/apps/rostering/application_router.py
"""Application-level router aggregate for workforce-integrated rostering.

`amodb.main` historically imports `amodb.apps.rostering.router.router`.  The
package initializer replaces that submodule export with this aggregate, which
preserves the existing bootstrap import while mounting both canonical sibling
prefixes: `/rostering` and `/workforce`.
"""
from fastapi import APIRouter

from . import router as rostering_route_module
from ..workforce.router_entry import router as workforce_router

router = APIRouter()
router.include_router(rostering_route_module.router)
router.include_router(workforce_router)

__all__ = ["router"]
