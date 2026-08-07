from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import backend_currentness, models


router = APIRouter(
    prefix="/content-packs/governance",
    tags=["aircraft OEM backend governance"],
)


@router.get(
    "/packs/{pack_id}/currentness",
    response_model=backend_currentness.ContentPackCurrentnessRead,
)
def get_content_pack_currentness(
    pack_id: str,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    pack = db.get(models.AircraftContentPack, pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Content pack not found")
    return backend_currentness.content_pack_currentness(db, pack=pack)


@router.get(
    "/publications/{publication_id}/content-impact",
    response_model=list[backend_currentness.PublicationContentImpactItem],
)
def get_publication_content_impact(
    publication_id: str,
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    publication = db.get(models.AircraftOemPublication, publication_id)
    if not publication:
        raise HTTPException(status_code=404, detail="OEM publication not found")
    return backend_currentness.publication_content_impact(
        db,
        publication=publication,
    )
