"""Composition router for aircraft engineering architecture domains."""

from fastapi import APIRouter

from .aircraft_catalogue.router import router as catalogue_router

router = APIRouter(prefix="/architecture", tags=["aircraft architecture"])
router.include_router(catalogue_router)
