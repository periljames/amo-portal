"""Composition router for aircraft engineering architecture domains."""

from fastapi import APIRouter

from .aircraft_catalogue.router import router as catalogue_router
from .effectivity.router import router as effectivity_router
from .import_staging.router import router as import_staging_router

router = APIRouter(prefix="/architecture", tags=["aircraft architecture"])
router.include_router(catalogue_router)
router.include_router(effectivity_router)
router.include_router(import_staging_router)
