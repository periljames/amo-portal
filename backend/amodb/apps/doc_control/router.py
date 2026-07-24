from __future__ import annotations

from fastapi import APIRouter

from .router_legacy import router as legacy_router
from .workspace_reports_router import router as workspace_reports_router
from .workspace_router import router as workspace_router


router = APIRouter()
router.include_router(legacy_router)
router.include_router(workspace_router, prefix="/doc-control")
router.include_router(workspace_reports_router, prefix="/doc-control")
