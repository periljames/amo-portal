"""Read and persistence projections for maintenance due status.

The legacy service originally reused the latest log date as the calendar
calculation date. This module keeps the accepted counter source from the usage
ledger while always evaluating calendar exposure against the actual current
calendar date.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import service
from .models import (
    AircraftProgramStatusEnum,
    AmpAircraftProgramItem as AircraftProgramItem,
    AmpProgramItem as MaintenanceProgramItem,
    ProgramItemStatusEnum,
)
from .schemas import AircraftProgramItemDueList, AircraftProgramItemRead, FleetPlanningOverview
from ..fleet.models import Aircraft


def recompute_due_for_aircraft(
    db: Session,
    *,
    amo_id: str,
    aircraft_serial_number: str,
    include_completed: bool = False,
) -> List[AircraftProgramItem]:
    current_hours, current_cycles, _last_log_date, _latest_usage = service._get_aircraft_utilisation(
        db,
        aircraft_serial_number,
        amo_id,
    )
    calculation_date = date.today()
    stmt = (
        select(AircraftProgramItem)
        .join(Aircraft, Aircraft.serial_number == AircraftProgramItem.aircraft_serial_number)
        .where(
            AircraftProgramItem.aircraft_serial_number == aircraft_serial_number,
            Aircraft.amo_id == amo_id,
        )
    )
    if not include_completed:
        stmt = stmt.where(AircraftProgramItem.status != AircraftProgramStatusEnum.COMPLETED)
    items = list(db.execute(stmt).scalars().all())
    if not items:
        return []

    program_ids = {item.program_item_id for item in items}
    program_map = {
        item.id: item
        for item in db.execute(
            select(MaintenanceProgramItem).where(MaintenanceProgramItem.id.in_(program_ids))
        ).scalars().all()
    }

    for item in items:
        program_item = program_map.get(item.program_item_id)
        if not program_item or program_item.status != ProgramItemStatusEnum.ACTIVE:
            item.status = AircraftProgramStatusEnum.SUSPENDED
            continue
        state = service._calculate_due_state(
            program_item=program_item,
            api=item,
            current_hours=current_hours,
            current_cycles=current_cycles,
            today=calculation_date,
        )
        service._persist_due_state(item, state)
    db.flush()
    return items


def get_due_list_for_aircraft(
    db: Session,
    *,
    amo_id: str,
    aircraft_serial_number: str,
) -> AircraftProgramItemDueList:
    current_hours, current_cycles, _last_log_date, _latest_usage = service._get_aircraft_utilisation(
        db,
        aircraft_serial_number,
        amo_id,
    )
    calculation_date = date.today()
    items = service.list_aircraft_program_items_for_aircraft(
        db,
        amo_id=amo_id,
        aircraft_serial_number=aircraft_serial_number,
    )
    read_items: List[AircraftProgramItemRead] = []
    for item in items:
        program_item = item.program_item
        if program_item is None or program_item.status != ProgramItemStatusEnum.ACTIVE:
            continue
        state = service._calculate_due_state(
            program_item=program_item,
            api=item,
            current_hours=current_hours,
            current_cycles=current_cycles,
            today=calculation_date,
        )
        read_items.append(
            AircraftProgramItemRead.model_validate(item).model_copy(
                update={
                    "next_due_hours": state["next_due_hours"],
                    "next_due_cycles": state["next_due_cycles"],
                    "next_due_date": state["next_due_date"],
                    "remaining_hours": state["remaining_hours"],
                    "remaining_cycles": state["remaining_cycles"],
                    "remaining_days": state["remaining_days"],
                    "status": state["status"],
                }
            )
        )

    overdue_count = sum(
        1 for item in read_items if item.status == AircraftProgramStatusEnum.OVERDUE
    )
    return AircraftProgramItemDueList(
        aircraft_serial_number=aircraft_serial_number,
        generated_at=datetime.now(timezone.utc),
        due_now_count=overdue_count,
        due_soon_count=sum(
            1 for item in read_items if item.status == AircraftProgramStatusEnum.DUE_SOON
        ),
        overdue_count=overdue_count,
        items=read_items,
    )


def get_fleet_planning_overview(
    db: Session,
    *,
    amo_id: str,
    horizon_days: int,
    status_filter: AircraftProgramStatusEnum | None,
    search: str | None,
    limit: int,
) -> FleetPlanningOverview:
    return service.get_fleet_planning_overview(
        db,
        amo_id=amo_id,
        horizon_days=horizon_days,
        status_filter=status_filter,
        search=search,
        limit=limit,
    )
