from __future__ import annotations

from fastapi import APIRouter

from .router_legacy import router as legacy_router
from .workspace_library_router import router as workspace_library_router
from .workspace_reports_router import router as workspace_reports_router
from .workspace_router import router as workspace_router


router = APIRouter()
router.include_router(legacy_router)
# The library override preserves the existing endpoint contract while correcting
# access filtering and pagination. It must be registered before the compatibility
# workspace router because Starlette resolves matching routes in declaration order.
router.include_router(workspace_library_router, prefix="/doc-control")
router.include_router(workspace_router, prefix="/doc-control")
router.include_router(workspace_reports_router, prefix="/doc-control")
