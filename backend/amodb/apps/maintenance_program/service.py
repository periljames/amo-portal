# backend/amodb/apps/maintenance_program/service.py
#
# Maintenance-program business logic and fleet planning projections.

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from .models import (
    AircraftProgramStatusEnum,
    AmpAircraftProgramItem as AircraftProgramItem,
    AmpProgramItem as MaintenanceProgramItem,
    ProgramItemStatusEnum,
)
from .schemas import (
    AircraftProgramItemDueList,
    AircraftProgramItemRead,
    FleetDueItemRead,
    FleetPlanningOverview,
    FleetPlanningSummary,
    FleetUtilisationRead,
)
from ..fleet.models import Aircraft, AircraftComponent, AircraftUsage
from ..work.models import (
    TaskCard,
    TaskCategoryEnum,
    TaskOriginTypeEnum,
    TaskPriorityEnum,
    TaskStatusEnum,
    WorkOrder,
    WorkOrderStatusEnum,
    WorkOrderTypeEnum,
)

DUE_SOON_HOURS = 50.0
DUE_SOON_CYCLES = 50.0
DUE_SOON_DAYS = 30
UTILISATION_CURRENT_DAYS = 2


def _supported_model_kwargs(model: type, values: Dict[str, Any]) -> Dict[str, Any]:
    columns = {column.name for column in model.__table__.columns}
    return {key: value for key, value in values.items() if key in columns}


def _get_aircraft_or_raise(db: Session, aircraft_sn: str, amo_id: str) -> Aircraft:
    aircraft = (
        db.query(Aircraft)
        .filter(Aircraft.serial_number == aircraft_sn, Aircraft.amo_id == amo_id)
        .first()
    )
    if aircraft is None:
        raise ValueError("Aircraft not found in the active tenant.")
    return aircraft


def _get_aircraft_utilisation(
    db: Session,
    aircraft_sn: str,
    amo_id: str,
) -> Tuple[float, float, date, Optional[AircraftUsage]]:
    """Return authoritative planning counters from the latest usage ledger row.

    Aircraft snapshot totals are retained only as a compatibility fallback for
    aircraft that have not yet received a ledger entry.
    """

    aircraft = _get_aircraft_or_raise(db, aircraft_sn, amo_id)
    latest_usage = (
        db.query(AircraftUsage)
        .filter(
            AircraftUsage.amo_id == amo_id,
            AircraftUsage.aircraft_serial_number == aircraft_sn,
        )
        .order_by(AircraftUsage.date.desc(), AircraftUsage.techlog_no.desc())
        .first()
    )

    if latest_usage is not None:
        hours = latest_usage.ttaf_after
        cycles = latest_usage.tca_after
        return (
            float(hours if hours is not None else aircraft.total_hours or 0.0),
            float(cycles if cycles is not None else aircraft.total_cycles or 0.0),
            latest_usage.date,
            latest_usage,
        )

    return (
        float(aircraft.total_hours or 0.0),
        float(aircraft.total_cycles or 0.0),
        aircraft.last_log_date or date.today(),
        None,
    )


def create_program_item(
    db: Session,
    *,
    template_code: str,
    title: str,
    created_by_user_id: Optional[str] = None,
    **kwargs: Any,
) -> MaintenanceProgramItem:
    values = _supported_model_kwargs(MaintenanceProgramItem, kwargs)
    item = MaintenanceProgramItem(template_code=template_code, title=title, **values)
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
    stmt = stmt.order_by(
        MaintenanceProgramItem.template_code,
        MaintenanceProgramItem.ata_chapter,
        MaintenanceProgramItem.task_number,
    )
    return list(db.execute(stmt).scalars().all())


def update_program_item(
    db: Session,
    item: MaintenanceProgramItem,
    *,
    updated_by_user_id: Optional[str] = None,
    **kwargs: Any,
) -> MaintenanceProgramItem:
    for field, value in _supported_model_kwargs(MaintenanceProgramItem, kwargs).items():
        if value is not None:
            setattr(item, field, value)
    item.updated_by_user_id = updated_by_user_id
    db.flush()
    return item


def create_aircraft_program_item(
    db: Session,
    *,
    amo_id: str,
    aircraft_serial_number: str,
    program_item: MaintenanceProgramItem,
    created_by_user_id: Optional[str] = None,
    aircraft_component: Optional[AircraftComponent] = None,
    **overrides: Any,
) -> AircraftProgramItem:
    _get_aircraft_or_raise(db, aircraft_serial_number, amo_id)
    values = _supported_model_kwargs(AircraftProgramItem, overrides)
    api = AircraftProgramItem(
        aircraft_serial_number=aircraft_serial_number,
        program_item_id=program_item.id,
        aircraft_component_id=aircraft_component.id if aircraft_component else None,
        **values,
    )
    api.created_by_user_id = created_by_user_id
    api.updated_by_user_id = created_by_user_id
    db.add(api)
    db.flush()
    return api


def get_aircraft_program_item(
    db: Session,
    *,
    api_id: int,
    amo_id: Optional[str] = None,
) -> Optional[AircraftProgramItem]:
    query = db.query(AircraftProgramItem).filter(AircraftProgramItem.id == api_id)
    if amo_id:
        query = query.join(
            Aircraft,
            Aircraft.serial_number == AircraftProgramItem.aircraft_serial_number,
        ).filter(Aircraft.amo_id == amo_id)
    return query.first()


def list_aircraft_program_items_for_aircraft(
    db: Session,
    *,
    amo_id: str,
    aircraft_serial_number: str,
    status: Optional[AircraftProgramStatusEnum] = None,
) -> List[AircraftProgramItem]:
    _get_aircraft_or_raise(db, aircraft_serial_number, amo_id)
    stmt = (
        select(AircraftProgramItem)
        .join(Aircraft, Aircraft.serial_number == AircraftProgramItem.aircraft_serial_number)
        .where(
            AircraftProgramItem.aircraft_serial_number == aircraft_serial_number,
            Aircraft.amo_id == amo_id,
        )
        .order_by(AircraftProgramItem.id)
    )
    if status:
        stmt = stmt.where(AircraftProgramItem.status == status)
    return list(db.execute(stmt).scalars().all())


def update_aircraft_program_item(
    db: Session,
    api: AircraftProgramItem,
    *,
    updated_by_user_id: Optional[str] = None,
    **kwargs: Any,
) -> AircraftProgramItem:
    for field, value in _supported_model_kwargs(AircraftProgramItem, kwargs).items():
        if value is not None:
            setattr(api, field, value)
    api.updated_by_user_id = updated_by_user_id
    db.flush()
    return api


def _calendar_anchor(program_item: MaintenanceProgramItem, api: AircraftProgramItem) -> Tuple[Optional[date], str]:
    if api.last_done_date is not None:
        return api.last_done_date, "ACCOMPLISHMENT"
    if program_item.threshold_days is not None:
        created_at = api.created_at
        if created_at is not None:
            return created_at.date(), "DERIVED_INITIAL_BASELINE"
    return None, "MISSING_BASELINE"


def _calculate_due_state(
    *,
    program_item: MaintenanceProgramItem,
    api: AircraftProgramItem,
    current_hours: float,
    current_cycles: float,
    today: date,
) -> Dict[str, Any]:
    next_hours: Optional[float] = None
    if program_item.interval_hours is not None and api.last_done_hours is not None:
        next_hours = float(api.last_done_hours + program_item.interval_hours)
    elif program_item.threshold_hours is not None:
        next_hours = float(program_item.threshold_hours)

    next_cycles: Optional[float] = None
    if program_item.interval_cycles is not None and api.last_done_cycles is not None:
        next_cycles = float(api.last_done_cycles + program_item.interval_cycles)
    elif program_item.threshold_cycles is not None:
        next_cycles = float(program_item.threshold_cycles)

    next_date: Optional[date] = None
    baseline_status = "BASELINED"
    if program_item.interval_days is not None and api.last_done_date is not None:
        next_date = api.last_done_date + timedelta(days=int(program_item.interval_days))
    elif program_item.threshold_days is not None:
        anchor, baseline_status = _calendar_anchor(program_item, api)
        if anchor is not None:
            next_date = anchor + timedelta(days=int(program_item.threshold_days))
    elif program_item.interval_days is not None:
        baseline_status = "MISSING_BASELINE"

    remaining_hours = None if next_hours is None else next_hours - current_hours
    remaining_cycles = None if next_cycles is None else next_cycles - current_cycles
    remaining_days = None if next_date is None else float((next_date - today).days)

    signed_remaining = (remaining_hours, remaining_cycles, remaining_days)
    overdue = any(value is not None and value < 0 for value in signed_remaining)
    due_soon = any(
        value is not None and 0 <= value <= threshold
        for value, threshold in (
            (remaining_hours, DUE_SOON_HOURS),
            (remaining_cycles, DUE_SOON_CYCLES),
            (remaining_days, float(DUE_SOON_DAYS)),
        )
    )

    if overdue:
        status = AircraftProgramStatusEnum.OVERDUE
    elif due_soon:
        status = AircraftProgramStatusEnum.DUE_SOON
    else:
        status = AircraftProgramStatusEnum.PLANNED

    if (
        next_hours is None
        and next_cycles is None
        and next_date is None
        and baseline_status == "MISSING_BASELINE"
    ):
        status = AircraftProgramStatusEnum.PLANNED

    return {
        "next_due_hours": next_hours,
        "next_due_cycles": next_cycles,
        "next_due_date": next_date,
        "remaining_hours": remaining_hours,
        "remaining_cycles": remaining_cycles,
        "remaining_days": remaining_days,
        "overdue_by_hours": abs(remaining_hours) if remaining_hours is not None and remaining_hours < 0 else None,
        "overdue_by_cycles": abs(remaining_cycles) if remaining_cycles is not None and remaining_cycles < 0 else None,
        "overdue_by_days": abs(remaining_days) if remaining_days is not None and remaining_days < 0 else None,
        "status": status,
        "baseline_status": baseline_status,
    }


def _persist_due_state(api: AircraftProgramItem, state: Dict[str, Any]) -> None:
    api.next_due_hours = state["next_due_hours"]
    api.next_due_cycles = state["next_due_cycles"]
    api.next_due_date = state["next_due_date"]
    # Existing database constraints require non-negative stored remaining values.
    # The signed values are calculated and returned by the read projections.
    api.remaining_hours = None if state["remaining_hours"] is None else max(0.0, state["remaining_hours"])
    api.remaining_cycles = None if state["remaining_cycles"] is None else max(0.0, state["remaining_cycles"])
    api.remaining_days = None if state["remaining_days"] is None else max(0, int(state["remaining_days"]))
    api.status = state["status"]


def recompute_due_for_aircraft(
    db: Session,
    *,
    amo_id: str,
    aircraft_serial_number: str,
    include_completed: bool = False,
    persist: bool = True,
) -> List[AircraftProgramItem]:
    hours, cycles, today, _latest_usage = _get_aircraft_utilisation(
        db,
        aircraft_serial_number,
        amo_id,
    )
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
    api_items = list(db.execute(stmt).scalars().all())
    if not api_items:
        return []

    program_ids = {api.program_item_id for api in api_items}
    program_map = {
        item.id: item
        for item in db.execute(
            select(MaintenanceProgramItem).where(MaintenanceProgramItem.id.in_(program_ids))
        ).scalars().all()
    }

    for api in api_items:
        program_item = program_map.get(api.program_item_id)
        if not program_item or program_item.status != ProgramItemStatusEnum.ACTIVE:
            api.status = AircraftProgramStatusEnum.SUSPENDED
            continue
        state = _calculate_due_state(
            program_item=program_item,
            api=api,
            current_hours=hours,
            current_cycles=cycles,
            today=today,
        )
        if persist:
            _persist_due_state(api, state)
    if persist:
        db.flush()
    return api_items


def get_due_list_for_aircraft(
    db: Session,
    *,
    amo_id: str,
    aircraft_serial_number: str,
) -> AircraftProgramItemDueList:
    current_hours, current_cycles, today, _latest_usage = _get_aircraft_utilisation(
        db,
        aircraft_serial_number,
        amo_id,
    )
    items = list_aircraft_program_items_for_aircraft(
        db,
        amo_id=amo_id,
        aircraft_serial_number=aircraft_serial_number,
    )
    read_items: List[AircraftProgramItemRead] = []
    for api in items:
        program_item = api.program_item
        if program_item is None or program_item.status != ProgramItemStatusEnum.ACTIVE:
            continue
        state = _calculate_due_state(
            program_item=program_item,
            api=api,
            current_hours=current_hours,
            current_cycles=current_cycles,
            today=today,
        )
        read_items.append(
            AircraftProgramItemRead.model_validate(api).model_copy(
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

    return AircraftProgramItemDueList(
        aircraft_serial_number=aircraft_serial_number,
        generated_at=datetime.now(timezone.utc),
        due_now_count=sum(1 for item in read_items if item.status == AircraftProgramStatusEnum.OVERDUE),
        due_soon_count=sum(1 for item in read_items if item.status == AircraftProgramStatusEnum.DUE_SOON),
        overdue_count=sum(1 for item in read_items if item.status == AircraftProgramStatusEnum.OVERDUE),
        items=read_items,
    )


def _severity_key(item: FleetDueItemRead) -> Tuple[int, float, str, str]:
    status_rank = {
        AircraftProgramStatusEnum.OVERDUE: 0,
        AircraftProgramStatusEnum.DUE_SOON: 1,
        AircraftProgramStatusEnum.PLANNED: 2,
        AircraftProgramStatusEnum.COMPLETED: 3,
        AircraftProgramStatusEnum.SUSPENDED: 4,
    }.get(item.status, 5)
    remaining_values = [
        value
        for value in (item.remaining_days, item.remaining_hours, item.remaining_cycles)
        if value is not None
    ]
    nearest = min(remaining_values) if remaining_values else float("inf")
    return (status_rank, nearest, item.registration, item.task_code or item.task_title)


def get_fleet_planning_overview(
    db: Session,
    *,
    amo_id: str,
    horizon_days: int = 90,
    status_filter: Optional[AircraftProgramStatusEnum] = None,
    search: Optional[str] = None,
    limit: int = 1000,
) -> FleetPlanningOverview:
    today = date.today()
    horizon_date = today + timedelta(days=horizon_days)
    aircraft_rows = (
        db.query(Aircraft)
        .filter(Aircraft.amo_id == amo_id, Aircraft.is_active.is_(True))
        .order_by(Aircraft.registration.asc())
        .all()
    )
    aircraft_by_sn = {aircraft.serial_number: aircraft for aircraft in aircraft_rows}
    serials = list(aircraft_by_sn)

    usage_rows: List[AircraftUsage] = []
    if serials:
        usage_rows = (
            db.query(AircraftUsage)
            .filter(
                AircraftUsage.amo_id == amo_id,
                AircraftUsage.aircraft_serial_number.in_(serials),
            )
            .order_by(
                AircraftUsage.aircraft_serial_number.asc(),
                AircraftUsage.date.desc(),
                AircraftUsage.techlog_no.desc(),
            )
            .all()
        )

    latest_usage: Dict[str, AircraftUsage] = {}
    seven_day_hours: Dict[str, float] = defaultdict(float)
    seven_day_cutoff = today - timedelta(days=6)
    for usage in usage_rows:
        latest_usage.setdefault(usage.aircraft_serial_number, usage)
        if usage.date >= seven_day_cutoff:
            seven_day_hours[usage.aircraft_serial_number] += float(usage.block_hours or 0.0)

    current_by_aircraft: Dict[str, Tuple[float, float, date]] = {}
    for serial_number, aircraft in aircraft_by_sn.items():
        latest = latest_usage.get(serial_number)
        if latest:
            current_by_aircraft[serial_number] = (
                float(latest.ttaf_after if latest.ttaf_after is not None else aircraft.total_hours or 0.0),
                float(latest.tca_after if latest.tca_after is not None else aircraft.total_cycles or 0.0),
                latest.date,
            )
        else:
            current_by_aircraft[serial_number] = (
                float(aircraft.total_hours or 0.0),
                float(aircraft.total_cycles or 0.0),
                aircraft.last_log_date or today,
            )

    due_items: List[FleetDueItemRead] = []
    due_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: {"overdue": 0, "due_soon": 0})
    next_due_candidates: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    unbaselined = 0

    if serials:
        api_items = (
            db.query(AircraftProgramItem)
            .join(Aircraft, Aircraft.serial_number == AircraftProgramItem.aircraft_serial_number)
            .join(MaintenanceProgramItem, MaintenanceProgramItem.id == AircraftProgramItem.program_item_id)
            .filter(
                Aircraft.amo_id == amo_id,
                AircraftProgramItem.aircraft_serial_number.in_(serials),
                MaintenanceProgramItem.status == ProgramItemStatusEnum.ACTIVE,
            )
            .order_by(AircraftProgramItem.aircraft_serial_number, AircraftProgramItem.id)
            .all()
        )
    else:
        api_items = []

    for api in api_items:
        aircraft = aircraft_by_sn.get(api.aircraft_serial_number)
        program_item = api.program_item
        if aircraft is None or program_item is None:
            continue
        current_hours, current_cycles, last_log_date = current_by_aircraft[api.aircraft_serial_number]
        state = _calculate_due_state(
            program_item=program_item,
            api=api,
            current_hours=current_hours,
            current_cycles=current_cycles,
            today=today,
        )
        if state["status"] == AircraftProgramStatusEnum.OVERDUE:
            due_counts[api.aircraft_serial_number]["overdue"] += 1
        elif state["status"] == AircraftProgramStatusEnum.DUE_SOON:
            due_counts[api.aircraft_serial_number]["due_soon"] += 1
        if state["baseline_status"] == "MISSING_BASELINE" and all(
            state[key] is None
            for key in ("next_due_date", "next_due_hours", "next_due_cycles")
        ):
            unbaselined += 1

        next_due_candidates[api.aircraft_serial_number].append(state)
        due_item = FleetDueItemRead(
            api_id=api.id,
            aircraft_serial_number=api.aircraft_serial_number,
            registration=aircraft.registration,
            model=aircraft.model or aircraft.aircraft_model_code or aircraft.template,
            program_item_id=api.program_item_id,
            task_code=api.override_task_code or program_item.task_code or program_item.task_number,
            task_title=api.override_title or program_item.title,
            ata_chapter=program_item.ata_chapter,
            status=state["status"],
            current_hours=current_hours,
            current_cycles=current_cycles,
            last_log_date=last_log_date,
            next_due_date=state["next_due_date"],
            next_due_hours=state["next_due_hours"],
            next_due_cycles=state["next_due_cycles"],
            remaining_days=state["remaining_days"],
            remaining_hours=state["remaining_hours"],
            remaining_cycles=state["remaining_cycles"],
            overdue_by_days=state["overdue_by_days"],
            overdue_by_hours=state["overdue_by_hours"],
            overdue_by_cycles=state["overdue_by_cycles"],
            baseline_status=state["baseline_status"],
        )
        due_items.append(due_item)

    utilisation: List[FleetUtilisationRead] = []
    for serial_number, aircraft in aircraft_by_sn.items():
        latest = latest_usage.get(serial_number)
        current_hours, current_cycles, last_log_date = current_by_aircraft[serial_number]
        if latest is None and aircraft.last_log_date is None:
            freshness_status = "MISSING"
            days_since_log = None
        else:
            days_since_log = max(0, (today - last_log_date).days)
            freshness_status = "CURRENT" if days_since_log <= UTILISATION_CURRENT_DAYS else "STALE"

        states = next_due_candidates.get(serial_number, [])
        date_values = [state["next_due_date"] for state in states if state["next_due_date"] is not None]
        hour_values = [state["next_due_hours"] for state in states if state["next_due_hours"] is not None]
        cycle_values = [state["next_due_cycles"] for state in states if state["next_due_cycles"] is not None]
        utilisation.append(
            FleetUtilisationRead(
                aircraft_serial_number=serial_number,
                registration=aircraft.registration,
                model=aircraft.model or aircraft.aircraft_model_code or aircraft.template,
                current_hours=current_hours,
                current_cycles=current_cycles,
                last_log_date=None if freshness_status == "MISSING" else last_log_date,
                days_since_log=days_since_log,
                freshness_status=freshness_status,
                seven_day_daily_average_hours=round(seven_day_hours.get(serial_number, 0.0) / 7.0, 2),
                overdue_count=due_counts[serial_number]["overdue"],
                due_soon_count=due_counts[serial_number]["due_soon"],
                next_due_date=min(date_values) if date_values else None,
                next_due_hours=min(hour_values) if hour_values else None,
                next_due_cycles=min(cycle_values) if cycle_values else None,
            )
        )

    summary = FleetPlanningSummary(
        fleet_aircraft=len(aircraft_rows),
        utilisation_current=sum(1 for row in utilisation if row.freshness_status == "CURRENT"),
        utilisation_stale=sum(1 for row in utilisation if row.freshness_status == "STALE"),
        utilisation_missing=sum(1 for row in utilisation if row.freshness_status == "MISSING"),
        overdue=sum(1 for item in due_items if item.status == AircraftProgramStatusEnum.OVERDUE),
        due_soon=sum(1 for item in due_items if item.status == AircraftProgramStatusEnum.DUE_SOON),
        planned=sum(1 for item in due_items if item.status == AircraftProgramStatusEnum.PLANNED),
        unbaselined=unbaselined,
        due_within_horizon=sum(
            1
            for item in due_items
            if item.status in {AircraftProgramStatusEnum.OVERDUE, AircraftProgramStatusEnum.DUE_SOON}
            or (item.next_due_date is not None and item.next_due_date <= horizon_date)
        ),
    )

    needle = (search or "").strip().lower()
    filtered_due_items = due_items
    if status_filter is not None:
        filtered_due_items = [item for item in filtered_due_items if item.status == status_filter]
    if needle:
        filtered_due_items = [
            item
            for item in filtered_due_items
            if needle
            in " ".join(
                filter(
                    None,
                    (
                        item.registration,
                        item.aircraft_serial_number,
                        item.model,
                        item.task_code,
                        item.task_title,
                        item.ata_chapter,
                    ),
                )
            ).lower()
        ]

    filtered_due_items.sort(key=_severity_key)
    utilisation.sort(key=lambda row: (row.freshness_status != "MISSING", row.freshness_status != "STALE", row.registration))
    return FleetPlanningOverview(
        generated_at=datetime.now(timezone.utc),
        horizon_days=horizon_days,
        summary=summary,
        utilisation=utilisation,
        due_items=filtered_due_items[:limit],
    )


def create_work_order_from_program_items(
    db: Session,
    *,
    amo_id: str,
    aircraft_serial_number: str,
    program_item_ids: Sequence[int],
    check_type: Optional[str] = None,
    wo_number: Optional[str] = None,
    created_by_user_id: Optional[str] = None,
    description: Optional[str] = None,
) -> WorkOrder:
    _get_aircraft_or_raise(db, aircraft_serial_number, amo_id)
    if not wo_number:
        wo_number = f"{aircraft_serial_number}-{int(datetime.now(timezone.utc).timestamp())}"

    wo = WorkOrder(
        amo_id=amo_id,
        wo_number=wo_number,
        aircraft_serial_number=aircraft_serial_number,
        check_type=check_type,
        description=description or f"Scheduled tasks for {aircraft_serial_number}",
        wo_type=WorkOrderTypeEnum.PERIODIC,
        status=WorkOrderStatusEnum.DRAFT,
        is_scheduled=True,
        open_date=date.today(),
        created_by_user_id=created_by_user_id,
        updated_by_user_id=created_by_user_id,
    )
    db.add(wo)
    db.flush()

    api_items = (
        db.query(AircraftProgramItem)
        .join(Aircraft, Aircraft.serial_number == AircraftProgramItem.aircraft_serial_number)
        .filter(
            Aircraft.amo_id == amo_id,
            AircraftProgramItem.aircraft_serial_number == aircraft_serial_number,
            AircraftProgramItem.program_item_id.in_(program_item_ids),
        )
        .all()
    )
    if not api_items:
        return wo

    program_ids = {api.program_item_id for api in api_items}
    program_map = {
        item.id: item
        for item in db.execute(
            select(MaintenanceProgramItem).where(MaintenanceProgramItem.id.in_(program_ids))
        ).scalars().all()
    }

    for api in api_items:
        program_item = program_map.get(api.program_item_id)
        if not program_item:
            continue
        card = TaskCard(
            amo_id=amo_id,
            work_order_id=wo.id,
            aircraft_serial_number=aircraft_serial_number,
            aircraft_component_id=api.aircraft_component_id,
            program_item_id=api.program_item_id,
            ata_chapter=program_item.ata_chapter,
            task_code=api.override_task_code or program_item.task_number or program_item.task_code,
            title=api.override_title or program_item.title,
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
        api.status = AircraftProgramStatusEnum.PLANNED
        api.updated_by_user_id = created_by_user_id

    db.flush()
    return wo
