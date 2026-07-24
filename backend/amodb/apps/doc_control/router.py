from __future__ import annotations

from fastapi import APIRouter, Depends

from .router_legacy import router as legacy_router
from .workspace_access import enforce_workspace_access
from .workspace_library_router import router as workspace_library_router
from .workspace_record_router import router as workspace_record_router
from .workspace_reports_router import router as workspace_reports_router
from .workspace_router import router as workspace_router


router = APIRouter()
router.include_router(legacy_router)
# These narrow overrides preserve the existing endpoint contracts while correcting
# access filtering, pagination, and reader/controller payload separation. They must
# be registered before the compatibility workspace router because Starlette resolves
# matching routes in declaration order.
router.include_router(workspace_library_router, prefix="/doc-control")
router.include_router(workspace_record_router, prefix="/doc-control")
router.include_router(
    workspace_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_reports_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
