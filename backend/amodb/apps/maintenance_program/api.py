# backend/amodb/apps/maintenance_program/api.py

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...database import get_db
from ...entitlements import require_module
from ...security import get_current_active_user, require_roles
from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import services as account_services
from amodb.apps.work.schemas import WorkOrderRead

from . import projection
from . import service as services
from .models import AircraftProgramStatusEnum, ProgramItemStatusEnum
from .schemas import (
    AircraftProgramItemCreate,
    AircraftProgramItemDueList,
    AircraftProgramItemRead,
    AircraftProgramItemUpdate,
    FleetPlanningOverview,
    MaintenanceProgramItemCreate,
    MaintenanceProgramItemRead,
    MaintenanceProgramItemUpdate,
)

PROGRAM_WRITE_ROLES = [
    "SUPERUSER",
    "AMO_ADMIN",
    "BASE_MAINTENANCE_MANAGER",
    "PLANNING_ENGINEER",
]

router = APIRouter(
    prefix="/maintenance-program",
    tags=["maintenance_program"],
    dependencies=[Depends(require_module("maintenance_program"))],
)


@router.post(
    "/program-items/",
    response_model=MaintenanceProgramItemRead,
    status_code=status.HTTP_201_CREATED,
)
def create_program_item(
    payload: MaintenanceProgramItemCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*PROGRAM_WRITE_ROLES)),
) -> MaintenanceProgramItemRead:
    item = services.create_program_item(
        db,
        template_code=payload.template_code,
        title=payload.title,
        created_by_user_id=current_user.id,
        ata_chapter=payload.ata_chapter,
        task_number=payload.task_number,
        task_code=payload.task_code,
        description=payload.description,
        interval_hours=payload.interval_hours,
        interval_cycles=payload.interval_cycles,
        interval_days=payload.interval_days,
        threshold_hours=payload.threshold_hours,
        threshold_cycles=payload.threshold_cycles,
        threshold_days=payload.threshold_days,
        default_zone=payload.default_zone,
        notes=payload.notes,
    )
    db.commit()
    db.refresh(item)
    return MaintenanceProgramItemRead.model_validate(item)


@router.get("/program-items/", response_model=List[MaintenanceProgramItemRead])
def list_program_items(
    template_code: Optional[str] = None,
    status_filter: Optional[ProgramItemStatusEnum] = ProgramItemStatusEnum.ACTIVE,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> List[MaintenanceProgramItemRead]:
    del current_user
    items = services.list_program_items(
        db,
        template_code=template_code,
        status=status_filter,
    )
    return [MaintenanceProgramItemRead.model_validate(item) for item in items]


@router.get("/program-items/{item_id}", response_model=MaintenanceProgramItemRead)
def get_program_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> MaintenanceProgramItemRead:
    del current_user
    item = services.get_program_item(db, item_id=item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Program item not found")
    return MaintenanceProgramItemRead.model_validate(item)


@router.patch("/program-items/{item_id}", response_model=MaintenanceProgramItemRead)
def update_program_item(
    item_id: int,
    payload: MaintenanceProgramItemUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*PROGRAM_WRITE_ROLES)),
) -> MaintenanceProgramItemRead:
    item = services.get_program_item(db, item_id=item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Program item not found")
    services.update_program_item(
        db,
        item,
        updated_by_user_id=current_user.id,
        **payload.model_dump(exclude_unset=True),
    )
    db.commit()
    db.refresh(item)
    return MaintenanceProgramItemRead.model_validate(item)


@router.post(
    "/aircraft/{aircraft_sn}/items/",
    response_model=AircraftProgramItemRead,
    status_code=status.HTTP_201_CREATED,
)
def create_aircraft_program_item(
    aircraft_sn: str,
    payload: AircraftProgramItemCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*PROGRAM_WRITE_ROLES)),
) -> AircraftProgramItemRead:
    program_item = services.get_program_item(db, item_id=payload.program_item_id)
    if not program_item:
        raise HTTPException(status_code=404, detail="Program item not found")
    try:
        api = services.create_aircraft_program_item(
            db,
            amo_id=current_user.effective_amo_id,
            aircraft_serial_number=aircraft_sn,
            program_item=program_item,
            created_by_user_id=current_user.id,
            aircraft_component=None,
            override_title=payload.override_title,
            override_task_code=payload.override_task_code,
            notes=payload.notes,
            last_done_hours=payload.last_done_hours,
            last_done_cycles=payload.last_done_cycles,
            last_done_date=payload.last_done_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    db.refresh(api)
    return AircraftProgramItemRead.model_validate(api)


@router.get(
    "/aircraft/{aircraft_sn}/items/",
    response_model=List[AircraftProgramItemRead],
)
def list_aircraft_program_items(
    aircraft_sn: str,
    status_filter: Optional[AircraftProgramStatusEnum] = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> List[AircraftProgramItemRead]:
    try:
        items = services.list_aircraft_program_items_for_aircraft(
            db,
            amo_id=current_user.effective_amo_id,
            aircraft_serial_number=aircraft_sn,
            status=status_filter,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [AircraftProgramItemRead.model_validate(item) for item in items]


@router.patch(
    "/aircraft/{aircraft_sn}/items/{api_id}",
    response_model=AircraftProgramItemRead,
)
def update_aircraft_program_item(
    aircraft_sn: str,
    api_id: int,
    payload: AircraftProgramItemUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*PROGRAM_WRITE_ROLES)),
) -> AircraftProgramItemRead:
    api = services.get_aircraft_program_item(
        db,
        api_id=api_id,
        amo_id=current_user.effective_amo_id,
    )
    if not api or api.aircraft_serial_number != aircraft_sn:
        raise HTTPException(status_code=404, detail="Aircraft program item not found")
    services.update_aircraft_program_item(
        db,
        api,
        updated_by_user_id=current_user.id,
        **payload.model_dump(exclude_unset=True),
    )
    db.commit()
    db.refresh(api)
    return AircraftProgramItemRead.model_validate(api)


@router.get("/fleet/due-list", response_model=FleetPlanningOverview)
def get_fleet_due_list(
    horizon_days: int = Query(90, ge=1, le=730),
    status_filter: Optional[AircraftProgramStatusEnum] = None,
    search: Optional[str] = Query(None, max_length=120),
    limit: int = Query(1000, ge=1, le=5000),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> FleetPlanningOverview:
    return projection.get_fleet_planning_overview(
        db,
        amo_id=current_user.effective_amo_id,
        horizon_days=horizon_days,
        status_filter=status_filter,
        search=search,
        limit=limit,
    )


@router.post(
    "/aircraft/{aircraft_sn}/recompute-due",
    response_model=AircraftProgramItemDueList,
)
def recompute_due_for_aircraft(
    aircraft_sn: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*PROGRAM_WRITE_ROLES)),
) -> AircraftProgramItemDueList:
    try:
        projection.recompute_due_for_aircraft(
            db,
            amo_id=current_user.effective_amo_id,
            aircraft_serial_number=aircraft_sn,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return projection.get_due_list_for_aircraft(
        db,
        amo_id=current_user.effective_amo_id,
        aircraft_serial_number=aircraft_sn,
    )


@router.get(
    "/aircraft/{aircraft_sn}/due-list",
    response_model=AircraftProgramItemDueList,
)
def get_due_list_for_aircraft(
    aircraft_sn: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
) -> AircraftProgramItemDueList:
    try:
        return projection.get_due_list_for_aircraft(
            db,
            amo_id=current_user.effective_amo_id,
            aircraft_serial_number=aircraft_sn,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class CreateWOFromProgramRequest(BaseModel):
    program_item_ids: List[int]
    check_type: Optional[str] = None
    wo_number: Optional[str] = None
    description: Optional[str] = None


@router.post(
    "/aircraft/{aircraft_sn}/work-orders/from-program",
    response_model=WorkOrderRead,
    status_code=status.HTTP_201_CREATED,
)
def create_work_order_from_program_items(
    aircraft_sn: str,
    payload: CreateWOFromProgramRequest,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(require_roles(*PROGRAM_WRITE_ROLES)),
) -> WorkOrderRead:
    selected_program_ids = set(payload.program_item_ids)
    if not selected_program_ids:
        raise HTTPException(status_code=400, detail="No program_item_ids supplied")

    try:
        aircraft_items = services.list_aircraft_program_items_for_aircraft(
            db,
            amo_id=current_user.effective_amo_id,
            aircraft_serial_number=aircraft_sn,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    available_program_ids = {item.program_item_id for item in aircraft_items}
    missing_program_ids = sorted(selected_program_ids - available_program_ids)
    if missing_program_ids:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Selected maintenance requirements are not assigned to this aircraft.",
                "program_item_ids": missing_program_ids,
            },
        )

    try:
        wo = services.create_work_order_from_program_items(
            db,
            amo_id=current_user.effective_amo_id,
            aircraft_serial_number=aircraft_sn,
            program_item_ids=sorted(selected_program_ids),
            check_type=payload.check_type,
            wo_number=payload.wo_number,
            description=payload.description,
            created_by_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    run_count = len(selected_program_ids)
    account_services.record_usage(
        db,
        amo_id=current_user.effective_amo_id,
        meter_key=account_services.METER_KEY_AUTOMATION_RUNS,
        quantity=run_count,
        commit=False,
    )
    account_services.record_usage(
        db,
        amo_id=current_user.effective_amo_id,
        meter_key=account_services.METER_KEY_SCHEDULED_JOBS,
        quantity=run_count,
        commit=False,
    )
    db.commit()
    db.refresh(wo)
    return WorkOrderRead.model_validate(wo)
