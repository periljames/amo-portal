# backend/amodb/apps/maintenance_program/service.py
#
# Service / business-logic functions for the maintenance_program module.
#
# Responsibilities:
# - CRUD helpers for MaintenanceProgramItem and AircraftProgramItem.
# - Scheduling logic: compute next-due / remaining using thresholds/intervals.
# - Build "what is due" lists per aircraft.
# - Create WorkOrders + TaskCards from selected due items.

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from .models import (
    AmpProgramItem as MaintenanceProgramItem,
    AmpAircraftProgramItem as AircraftProgramItem,
    ProgramItemStatusEnum,
    AircraftProgramStatusEnum,
)
from .schemas import (
    AircraftProgramItemDueList,
)

from ..fleet.models import Aircraft, AircraftComponent
from ..work.models import (
    WorkOrder,
    TaskCard,
    TaskCategoryEnum,
    TaskOriginTypeEnum,
    TaskPriorityEnum,
    TaskStatusEnum,
    WorkOrderTypeEnum,
    WorkOrderStatusEnum,
)


# ---------------------------------------------------------------------------
# Helper – get current utilisation for an aircraft
# ---------------------------------------------------------------------------


def _get_aircraft_utilisation(db: Session, aircraft_sn: str) -> Tuple[float, float, date]:
    """
    Returns (total_hours, total_cycles, last_log_date) for the aircraft.
    Falls back to 0 / today if no data (should not really happen for active a/c).
    """
    stmt = select(Aircraft).where(Aircraft.serial_number == aircraft_sn)
    aircraft = db.execute(stmt).scalar_one()

    hours = aircraft.total_hours or 0.0
    cycles = aircraft.total_cycles or 0.0
    last_date: date = aircraft.last_log_date or date.today()
    return float(hours), float(cycles), last_date


# ---------------------------------------------------------------------------
# CRUD – MaintenanceProgramItem
# ---------------------------------------------------------------------------


def create_program_item(
    db: Session,
    *,
    template_code: str,
    title: str,
    created_by_user_id: Optional[int] = None,
    **kwargs,
) -> MaintenanceProgramItem:
    """
    Simple creator for an AMP task definition.
    Extra fields (intervals, thresholds, ATA etc.) are passed via **kwargs.
    """
    item = MaintenanceProgramItem(
        template_code=template_code,
        title=title,
        **kwargs,
    )
    item.created_by_user_id = created_by_user_id
    item.updated_by_user_id = created_by_user_id
    db.add(item)
    db.flush()
    return item


def get_program_item(db: Session, item_id: int) -> Optional[MaintenanceProgramItem]:
    return db.get(MaintenanceProgramItem, item_id)


def list_program_items(
    db: Session,
    *,
    template_code: Optional[str] = None,
    status: Optional[ProgramItemStatusEnum] = ProgramItemStatusEnum.ACTIVE,
) -> List[MaintenanceProgramItem]:
    stmt = select(MaintenanceProgramItem)

    conditions = []
    if template_code:
        conditions.append(MaintenanceProgramItem.template_code == template_code)
    if status:
        conditions.append(MaintenanceProgramItem.status == status)

    if conditions:
        stmt = stmt.where(and_(*conditions))

    stmt = stmt.order_by(MaintenanceProgramItem.ata_chapter, MaintenanceProgramItem.task_number)
    return list(db.execute(stmt).scalars().all())


def update_program_item(
    db: Session,
    item: MaintenanceProgramItem,
    *,
    updated_by_user_id: Optional[int] = None,
    **kwargs,
) -> MaintenanceProgramItem:
    for field, value in kwargs.items():
        if hasattr(item, field) and value is not None:
            setattr(item, field, value)
    item.updated_by_user_id = updated_by_user_id
    db.flush()
    return item


# ---------------------------------------------------------------------------
# CRUD – AircraftProgramItem
# ---------------------------------------------------------------------------


def create_aircraft_program_item(
    db: Session,
    *,
    aircraft_serial_number: str,
    program_item: MaintenanceProgramItem,
    created_by_user_id: Optional[int] = None,
    aircraft_component: Optional[AircraftComponent] = None,
    **overrides,
) -> AircraftProgramItem:
    """
    Create a per-aircraft instance of a MaintenanceProgramItem.

    Typical when:
    - applying a template AMP to a new aircraft, or
    - rolling out a new program item to applicable aircraft.
    """
    api = AircraftProgramItem(
        aircraft_serial_number=aircraft_serial_number,
        program_item_id=program_item.id,
        aircraft_component_id=aircraft_component.id if aircraft_component else None,
        **overrides,
    )
    api.created_by_user_id = created_by_user_id
    api.updated_by_user_id = created_by_user_id
    db.add(api)
    db.flush()
    return api


def get_aircraft_program_item(
    db: Session,
    api_id: int,
) -> Optional[AircraftProgramItem]:
    return db.get(AircraftProgramItem, api_id)


def list_aircraft_program_items_for_aircraft(
    db: Session,
    *,
    aircraft_serial_number: str,
    status: Optional[AircraftProgramStatusEnum] = None,
) -> List[AircraftProgramItem]:
    stmt = (
        select(AircraftProgramItem)
        .where(AircraftProgramItem.aircraft_serial_number == aircraft_serial_number)
        .order_by(AircraftProgramItem.id)
    )
    if status:
        stmt = stmt.where(AircraftProgramItem.status == status)
    return list(db.execute(stmt).scalars().all())


def update_aircraft_program_item(
    db: Session,
    api: AircraftProgramItem,
    *,
    updated_by_user_id: Optional[int] = None,
    **kwargs,
) -> AircraftProgramItem:
    for field, value in kwargs.items():
        if hasattr(api, field) and value is not None:
            setattr(api, field, value)
    api.updated_by_user_id = updated_by_user_id
    db.flush()
    return api


# ---------------------------------------------------------------------------
# Scheduling logic
# ---------------------------------------------------------------------------


def _compute_next_due_for_item(
    *,
    program_item: MaintenanceProgramItem,
    api: AircraftProgramItem,
    current_hours: float,
    current_cycles: float,
    today: date,
) -> None:
    """
    In-place computation of next_due_* and remaining_* on an AircraftProgramItem.

    Rules (simple to start, you can refine later):
      - If last_done_* is known and interval_* set -> next_due = last_done + interval.
      - Else if threshold_* set -> next_due = threshold.
      - remaining = next_due - current utilization (or date diff).
    """

    # HOURS
    next_hours: Optional[float] = None
    if program_item.interval_hours and api.last_done_hours is not None:
        next_hours = api.last_done_hours + program_item.interval_hours
    elif program_item.threshold_hours is not None:
        next_hours = program_item.threshold_hours

    # CYCLES
    next_cycles: Optional[float] = None
    if program_item.interval_cycles and api.last_done_cycles is not None:
        next_cycles = api.last_done_cycles + program_item.interval_cycles
    elif program_item.threshold_cycles is not None:
        next_cycles = program_item.threshold_cycles

    # CALENDAR (days)
    next_date: Optional[date] = None
    if program_item.interval_days and api.last_done_date is not None:
        next_date = api.last_done_date + timedelta(days=int(program_item.interval_days))
    elif program_item.threshold_days is not None:
        # assume threshold relative to "today" if no better anchor
        next_date = today + timedelta(days=int(program_item.threshold_days))

    api.next_due_hours = next_hours
    api.next_due_cycles = next_cycles
    api.next_due_date = next_date

    # Remaining
    api.remaining_hours = None if next_hours is None else next_hours - current_hours
    api.remaining_cycles = None if next_cycles is None else next_cycles - current_cycles
    api.remaining_days = None if next_date is None else (next_date - today).days

    # Status logic (basic; you can tune thresholds later)
    status = AircraftProgramStatusEnum.PLANNED

    overdue = any(
        val is not None and val < 0
        for val in (api.remaining_hours, api.remaining_cycles, api.remaining_days)
    )
    if overdue:
        status = AircraftProgramStatusEnum.OVERDUE
    else:
        due_soon = any(
            val is not None and val <= 50  # starter threshold for hours/cycles
            for val in (api.remaining_hours, api.remaining_cycles)
        ) or (api.remaining_days is not None and api.remaining_days <= 30)

        if due_soon:
            status = AircraftProgramStatusEnum.DUE_SOON

    api.status = status


def recompute_due_for_aircraft(
    db: Session,
    *,
    aircraft_serial_number: str,
    include_completed: bool = False,
) -> List[AircraftProgramItem]:
    """
    Recalculate next-due / remaining for all program items on an aircraft.
    Returns the updated AircraftProgramItem objects.
    """
    hours, cycles, today = _get_aircraft_utilisation(db, aircraft_serial_number)

    stmt = select(AircraftProgramItem).where(
        AircraftProgramItem.aircraft_serial_number == aircraft_serial_number
    )
    if not include_completed:
        stmt = stmt.where(
            AircraftProgramItem.status != AircraftProgramStatusEnum.COMPLETED
        )

    api_items = list(db.execute(stmt).scalars().all())
    if not api_items:
        return []

    # Preload program items into a dict to avoid N+1 queries
    program_ids = {api.program_item_id for api in api_items}
    p_stmt = select(MaintenanceProgramItem).where(
        MaintenanceProgramItem.id.in_(program_ids)
    )
    program_map = {
        p.id: p
        for p in db.execute(p_stmt).scalars().all()
    }

    for api in api_items:
        program_item = program_map.get(api.program_item_id)
        if not program_item or program_item.status != ProgramItemStatusEnum.ACTIVE:
            # If the master is inactive, mark as suspended for now
            api.status = AircraftProgramStatusEnum.SUSPENDED
            continue

        _compute_next_due_for_item(
            program_item=program_item,
            api=api,
            current_hours=hours,
            current_cycles=cycles,
            today=today,
        )

    db.flush()
    return api_items


def get_due_list_for_aircraft(
    db: Session,
    *,
    aircraft_serial_number: str,
) -> AircraftProgramItemDueList:
    """
    Convenience wrapper that recomputes due data and returns a typed
    AircraftProgramItemDueList schema.
    """
    recompute_due_for_aircraft(db, aircraft_serial_number=aircraft_serial_number)

    stmt = (
        select(AircraftProgramItem)
        .where(AircraftProgramItem.aircraft_serial_number == aircraft_serial_number)
        .order_by(AircraftProgramItem.status.desc(), AircraftProgramItem.id)
    )
    items = list(db.execute(stmt).scalars().all())

    from .schemas import AircraftProgramItemRead  # local import to avoid circular

    read_items = [AircraftProgramItemRead.model_validate(i) for i in items]

    return AircraftProgramItemDueList(
        aircraft_serial_number=aircraft_serial_number,
        generated_at=datetime.utcnow(),
        items=read_items,
    )


# ---------------------------------------------------------------------------
# Creating work orders / task cards from due items
# ---------------------------------------------------------------------------


def create_work_order_from_program_items(
    db: Session,
    *,
    aircraft_serial_number: str,
    program_item_ids: Sequence[int],
    check_type: Optional[str] = None,
    wo_number: Optional[str] = None,
    created_by_user_id: Optional[int] = None,
    description: Optional[str] = None,
) -> WorkOrder:
    """
    Create a WorkOrder and TaskCards for the given program items on an aircraft.

    - Uses the per-aircraft AircraftProgramItem to populate title / component.
    - Links TaskCard.program_item_id for traceability.
    """
    # Basic auto WO number if not supplied – you can replace with your own generator
    if not wo_number:
        wo_number = f"{aircraft_serial_number}-{int(datetime.utcnow().timestamp())}"

    wo = WorkOrder(
        wo_number=wo_number,
        aircraft_serial_number=aircraft_serial_number,
        check_type=check_type,
        description=description or f"Scheduled tasks for {aircraft_serial_number}",
        wo_type=WorkOrderTypeEnum.PERIODIC,
        status=WorkOrderStatusEnum.OPEN,
        is_scheduled=True,
        open_date=date.today(),
        created_by_user_id=created_by_user_id,
        updated_by_user_id=created_by_user_id,
    )
    db.add(wo)
    db.flush()

    # Load AircraftProgramItems + their master definitions
    stmt = select(AircraftProgramItem).where(
        and_(
            AircraftProgramItem.aircraft_serial_number == aircraft_serial_number,
            AircraftProgramItem.program_item_id.in_(program_item_ids),
        )
    )
    api_items = list(db.execute(stmt).scalars().all())

    if not api_items:
        return wo

    program_ids = {api.program_item_id for api in api_items}
    p_stmt = select(MaintenanceProgramItem).where(
        MaintenanceProgramItem.id.in_(program_ids)
    )
    program_map = {
        p.id: p
        for p in db.execute(p_stmt).scalars().all()
    }

    for api in api_items:
        program_item = program_map.get(api.program_item_id)
        if not program_item:
            continue

        title = api.override_title or program_item.title
        task_code = (
            api.override_task_code
            or program_item.task_number
            or program_item.task_code
        )

        card = TaskCard(
            work_order_id=wo.id,
            aircraft_serial_number=aircraft_serial_number,
            aircraft_component_id=api.aircraft_component_id,
            program_item_id=api.program_item_id,
            ata_chapter=program_item.ata_chapter,
            task_code=task_code,
            title=title,
            description=program_item.description,
            category=TaskCategoryEnum.SCHEDULED,
            origin_type=TaskOriginTypeEnum.SCHEDULED,
            priority=TaskPriorityEnum.MEDIUM,
            zone=program_item.default_zone,
            status=TaskStatusEnum.PLANNED,
            created_by_user_id=created_by_user_id,
            updated_by_user_id=created_by_user_id,
        )
        db.add(card)

        # Optional: mark the aircraft program status as PLANNED for this WO
        api.status = AircraftProgramStatusEnum.PLANNED
        api.updated_by_user_id = created_by_user_id

    db.flush()
    return wo
