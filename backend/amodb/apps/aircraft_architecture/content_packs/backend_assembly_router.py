from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import backend_assembly, governance, models, schemas


router = APIRouter(
    prefix="/content-packs/governance",
    tags=["aircraft OEM backend governance"],
)


def _pack(db: Session, pack_id: str) -> models.AircraftContentPack:
    row = db.get(models.AircraftContentPack, pack_id)
    if not row:
        raise HTTPException(status_code=404, detail="Content pack not found")
    return row


@router.post(
    "/packs/{pack_id}/assembly/preview",
    response_model=backend_assembly.OemBaselineAssemblyPreview,
)
def preview_oem_baseline_assembly(
    pack_id: str,
    payload: backend_assembly.OemBaselineAssemblyCreate,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    governance.require_source_contributor(user)
    preview, _, _, _, _ = backend_assembly.preview_assembly(
        db,
        pack=_pack(db, pack_id),
        payload=payload,
    )
    return preview


@router.post(
    "/packs/{pack_id}/assembly",
    response_model=schemas.ContentRevisionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_oem_baseline_assembly(
    pack_id: str,
    payload: backend_assembly.OemBaselineAssemblyCreate,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    return backend_assembly.create_assembled_revision(
        db,
        pack=_pack(db, pack_id),
        payload=payload,
        user=user,
    )
