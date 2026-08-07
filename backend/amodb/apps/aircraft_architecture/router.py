"""Composition router for aircraft engineering architecture domains."""

from fastapi import APIRouter

from .aircraft_catalogue.router import router as catalogue_router
from .aircraft_induction.router import router as induction_router
from .content_packs.backend_admin_router import router as content_pack_backend_admin_router
from .content_packs.backend_assembly_router import router as content_pack_assembly_router
from .content_packs.backend_currentness_router import router as content_pack_currentness_router
from .content_packs.backend_router import router as content_pack_backend_router
from .content_packs.ingestion_router import router as content_pack_ingestion_router
from .content_packs.router import router as content_packs_router
from .daily_utilisation.router import router as daily_utilisation_router
from .effectivity.router import router as effectivity_router
from .import_staging.router import router as import_staging_router
from .tenant_programmes.router import router as tenant_programmes_router
from .tenant_programmes.overlay_router import router as tenant_programme_overlay_router

router = APIRouter(prefix="/architecture", tags=["aircraft architecture"])
router.include_router(catalogue_router)
router.include_router(effectivity_router)
router.include_router(import_staging_router)
router.include_router(tenant_programmes_router)
router.include_router(tenant_programme_overlay_router)
router.include_router(induction_router)
router.include_router(content_packs_router)
router.include_router(content_pack_ingestion_router)
router.include_router(content_pack_backend_router)
router.include_router(content_pack_backend_admin_router)
router.include_router(content_pack_currentness_router)
router.include_router(content_pack_assembly_router)
router.include_router(daily_utilisation_router)
