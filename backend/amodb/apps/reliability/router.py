# backend/amodb/apps/reliability/router.py

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from amodb.entitlements import require_module
from amodb.security import get_current_active_user
from ...database import get_write_db
from ..accounts import models as account_models
from . import schemas, services

router = APIRouter(
    prefix="/reliability",
    tags=["reliability"],
    dependencies=[Depends(require_module("reliability"))],
)


@router.post(
    "/templates/seed",
    response_model=List[schemas.ReliabilityProgramTemplateRead],
    status_code=status.HTTP_201_CREATED,
)
def seed_templates(
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    created = services.seed_default_templates(
        db,
        amo_id=current_user.amo_id,
        created_by_user_id=current_user.id,
    )
    return created


@router.post(
    "/trends",
    response_model=schemas.DefectTrendRead,
    status_code=status.HTTP_201_CREATED,
)
def create_trend(
    payload: schemas.DefectTrendCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    trend = services.compute_defect_trend(
        db,
        amo_id=current_user.amo_id,
        window_start=payload.window_start,
        window_end=payload.window_end,
        aircraft_serial_number=payload.aircraft_serial_number,
        ata_chapter=payload.ata_chapter,
    )
    return trend


@router.post(
    "/recurring",
    response_model=schemas.RecurringFindingRead,
    status_code=status.HTTP_201_CREATED,
)
def upsert_recurring(
    payload: schemas.RecurringFindingCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    instance = services.upsert_recurring_finding(
        db,
        amo_id=current_user.amo_id,
        data=payload,
    )
    return instance


@router.post(
    "/recommendations",
    response_model=schemas.ReliabilityRecommendationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_recommendation(
    payload: schemas.ReliabilityRecommendationCreate,
    current_user: account_models.User = Depends(get_current_active_user),
    db: Session = Depends(get_write_db),
):
    return services.create_recommendation(
        db,
        amo_id=current_user.amo_id,
        data=payload,
        created_by_user_id=current_user.id,
    )
