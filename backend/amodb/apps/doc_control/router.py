from __future__ import annotations

from fastapi import APIRouter, Depends

from .router_legacy import router as legacy_router
from .workspace_access import enforce_workspace_access
from .workspace_authority_router import router as workspace_authority_router
from .workspace_copy_router import router as workspace_copy_router
from .workspace_dashboard_router import router as workspace_dashboard_router
from .workspace_integration_router import router as workspace_integration_router
from .workspace_library_router import router as workspace_library_router
from .workspace_record_router import router as workspace_record_router
from .workspace_reports_router import router as workspace_reports_router
from .workspace_router import router as workspace_router
from .workspace_tr_router import router as workspace_tr_router
from .workspace_workflow_authority_router import router as workspace_workflow_authority_router
from .workspace_workflow_router import router as workspace_workflow_router


router = APIRouter()
router.include_router(legacy_router)
# These narrow overrides preserve existing endpoint contracts while correcting
# access filtering, pagination, reader/controller payload separation, source-module
# verification, authority evidence, controlled-copy custody, temporary-revision
# custody, and release safeguards. They must be registered before the compatibility
# workspace router because Starlette resolves matching routes in declaration order.
router.include_router(workspace_dashboard_router, prefix="/doc-control")
router.include_router(workspace_library_router, prefix="/doc-control")
router.include_router(workspace_record_router, prefix="/doc-control")
router.include_router(
    workspace_integration_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_authority_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_copy_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_tr_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_workflow_authority_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
router.include_router(
    workspace_workflow_router,
    prefix="/doc-control",
    dependencies=[Depends(enforce_workspace_access)],
)
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
