# backend/amodb/apps/workforce/router_entry/__init__.py
"""Canonical aggregate router for all workforce endpoints."""
from fastapi import APIRouter
from sqlalchemy.orm import selectinload

from .. import router as core_router_module
from ..people_router import router as people_router

core_router_module.selectinload = selectinload

router = APIRouter()
router.include_router(core_router_module.router)
router.include_router(people_router)

__all__ = ["router"]
