from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import models, schemas, services

router = APIRouter(prefix="/inductions", tags=["aircraft induction"])


@router.post("", response_model=schemas.AircraftInductionRead, status_code=201)
def create_induction(
    payload: schemas.AircraftInductionCreate,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    return services.induct_aircraft(db, payload=payload, user=user)


@router.get("/{induction_id}", response_model=schemas.AircraftInductionRead)
def read_induction(
    induction_id: str,
    db: Session = Depends(get_db),
    user: account_models.User = Depends(get_current_active_user),
):
    amo_id = services.require_human_induction_authority(user)
    row = db.get(models.AircraftInduction, induction_id)
    if not row or row.amo_id != amo_id:
        raise HTTPException(status_code=404, detail="Aircraft induction not found")
    return row
