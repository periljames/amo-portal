from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import models, schemas, services

router = APIRouter(prefix="/content-packs", tags=["aircraft content packs"])


@router.post("/bootstrap", response_model=list[schemas.ContentPackRead])
def bootstrap_packs(
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    return services.bootstrap_source_intake_packs(db, user=user)


@router.get("", response_model=list[schemas.ContentPackRead])
def list_packs(
    db: Session = Depends(get_db),
    _: account_models.User = Depends(get_current_active_user),
):
    return db.query(models.AircraftContentPack).order_by(models.AircraftContentPack.code).all()


@router.post("/{pack_id}/revisions", response_model=schemas.ContentRevisionRead, status_code=201)
def create_revision(
    pack_id: str,
    payload: schemas.ContentRevisionCreate,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    pack = db.get(models.AircraftContentPack, pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Content pack not found")
    return services.create_revision(db, pack=pack, payload=payload, user=user)


@router.post("/revisions/{revision_id}/publish", response_model=schemas.ContentRevisionRead)
def publish_revision(
    revision_id: str,
    payload: schemas.PublishContentRevision,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    revision = db.get(models.AircraftContentPackRevision, revision_id)
    if not revision:
        raise HTTPException(status_code=404, detail="Content-pack revision not found")
    return services.publish_revision(
        db,
        revision=revision,
        expected_content_hash=payload.expected_content_hash,
        user=user,
    )
