from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from amodb.apps.accounts.models import User
from amodb.apps.aircraft_induction.router import router as induction_router

from ...entitlements import require_module
from ...security import get_current_active_user

router = APIRouter(
    prefix="/aircraft",
    tags=["aircraft_control"],
    dependencies=[Depends(require_module("fleet"))],
)
router.include_router(induction_router)


def _correction_required() -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "message": "Accepted utilisation entries are immutable.",
            "code": "USAGE_CORRECTION_REQUIRED",
            "action": "Submit a correction request through /records/utilisation/{usage_id}/corrections.",
        },
    )


@router.put("/usage/{usage_id}")
def block_direct_usage_update(
    usage_id: int,
    current_user: User = Depends(get_current_active_user),
):
    del usage_id, current_user
    _correction_required()


@router.delete("/usage/{usage_id}")
def block_direct_usage_delete(
    usage_id: int,
    current_user: User = Depends(get_current_active_user),
):
    del usage_id, current_user
    _correction_required()


# The original importer was embedded in the fleet router. During application
# import this module is loaded before ``fleet.router`` is registered in main,
# allowing the retired route objects to be removed rather than redirected.
from . import router as fleet_router_module  # noqa: E402

LEGACY_IMPORT_PATH_FRAGMENTS = (
    "/import",
    "/ocr",
    "/snapshots",
    "/reconciliation",
)
LEGACY_IMPORT_NAME_TOKENS = (
    "import_",
    "_import",
    "preview_",
    "_preview",
    "ocr_",
    "_ocr",
    "snapshot",
    "reconciliation",
)


def _is_legacy_import_route(route) -> bool:
    path = str(getattr(route, "path", "")).lower()
    name = str(getattr(route, "name", "")).lower()
    if path.startswith("/aircraft/induction"):
        return False
    return any(fragment in path for fragment in LEGACY_IMPORT_PATH_FRAGMENTS) or any(
        token in name for token in LEGACY_IMPORT_NAME_TOKENS
    )


fleet_router_module.router.routes[:] = [
    route for route in fleet_router_module.router.routes if not _is_legacy_import_route(route)
]

# Remove the retired persistence tables from active SQLAlchemy metadata after
# fleet.models has been imported. This prevents future Alembic autogeneration
# from re-creating the deleted importer schema.
from amodb.apps.aircraft_induction import legacy_cleanup as _legacy_cleanup  # noqa: E402,F401
