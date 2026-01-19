from __future__ import annotations

from datetime import datetime, timezone, date
import uuid

import pytest
from fastapi import HTTPException

from amodb.apps.accounts import models as account_models
from amodb.apps.fleet import models as fleet_models
from amodb.apps.fleet import router as fleet_router
from amodb.apps.fleet import schemas as fleet_schemas
from amodb.apps.work import models as work_models
from amodb.apps.work import schemas as work_schemas
from amodb.apps.work import services as work_services
from amodb.apps.reliability import schemas as reliability_schemas
from amodb.apps.reliability import services as reliability_services


def _create_amo(db, amo_code: str) -> account_models.AMO:
    amo = account_models.AMO(
        amo_code=amo_code,
        name=f"{amo_code} AMO",
        login_slug=amo_code.lower(),
    )
    db.add(amo)
    db.commit()
    db.refresh(amo)
    return amo


def _create_user(db, amo_id: str, role: account_models.AccountRole) -> account_models.User:
    user = account_models.User(
        amo_id=amo_id,
        email=f"{role.value.lower()}@example.com",
        staff_code=f"{role.value[:6]}-1",
        first_name=role.value.title(),
        last_name="User",
        full_name=f"{role.value} User",
        hashed_password="test-hash",
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_aircraft(db, amo_id: str) -> fleet_models.Aircraft:
    ac = fleet_models.Aircraft(
        serial_number=f"SN-{amo_id[-4:]}",
        registration=f"REG-{amo_id[-4:]}",
        amo_id=amo_id,
    )
    db.add(ac)
    db.commit()
    db.refresh(ac)
    return ac


def test_component_collision_scoped_to_amo(db_session):
    amo_a = _create_amo(db_session, "AMO-A")
    amo_b = _create_amo(db_session, "AMO-B")

    ac_a = _create_aircraft(db_session, amo_a.id)
    ac_b = _create_aircraft(db_session, amo_b.id)

    comp_a = fleet_models.AircraftComponent(
        amo_id=amo_a.id,
        aircraft_serial_number=ac_a.serial_number,
        position="L ENG",
        part_number="PN-1",
        serial_number="SN-1",
    )
    comp_b = fleet_models.AircraftComponent(
        amo_id=amo_b.id,
        aircraft_serial_number=ac_b.serial_number,
        position="L ENG",
        part_number="PN-1",
        serial_number="SN-1",
    )
    db_session.add_all([comp_a, comp_b])
    db_session.commit()

    collision_a = fleet_router._find_component_collision(
        db_session,
        amo_a.id,
        "PN-1",
        "SN-1",
    )
    collision_b = fleet_router._find_component_collision(
        db_session,
        amo_b.id,
        "PN-1",
        "SN-1",
    )
    assert collision_a is not None
    assert collision_b is not None
    assert collision_a.amo_id == amo_a.id
    assert collision_b.amo_id == amo_b.id


def test_work_order_transition_blocks_inspection(db_session):
    amo = _create_amo(db_session, "AMO-C")
    user = _create_user(db_session, amo.id, account_models.AccountRole.AMO_ADMIN)
    aircraft = _create_aircraft(db_session, amo.id)

    wo_payload = work_schemas.WorkOrderCreate(
        wo_number="WO-1",
        aircraft_serial_number=aircraft.serial_number,
        status=work_models.WorkOrderStatusEnum.RELEASED,
        is_scheduled=False,
    )
    work_order = work_services.create_work_order(
        db_session,
        amo_id=amo.id,
        payload=wo_payload,
        actor=user,
    )
    task = work_models.TaskCard(
        amo_id=amo.id,
        work_order_id=work_order.id,
        aircraft_serial_number=aircraft.serial_number,
        title="Task",
        category=work_models.TaskCategoryEnum.DEFECT,
        origin_type=work_models.TaskOriginTypeEnum.NON_ROUTINE,
    )
    db_session.add(task)
    db_session.commit()

    with pytest.raises(HTTPException):
        work_services.update_work_order(
            db_session,
            work_order=work_order,
            payload=work_schemas.WorkOrderUpdate(status=work_models.WorkOrderStatusEnum.INSPECTED),
            actor=user,
        )


def test_task_inspection_requires_steps(db_session):
    amo = _create_amo(db_session, "AMO-D")
    user = _create_user(db_session, amo.id, account_models.AccountRole.CERTIFYING_ENGINEER)
    aircraft = _create_aircraft(db_session, amo.id)

    work_order = work_models.WorkOrder(
        amo_id=amo.id,
        wo_number="WO-INSPECT",
        aircraft_serial_number=aircraft.serial_number,
        status=work_models.WorkOrderStatusEnum.RELEASED,
        is_scheduled=False,
    )
    db_session.add(work_order)
    db_session.flush()

    task = work_models.TaskCard(
        amo_id=amo.id,
        work_order_id=work_order.id,
        aircraft_serial_number=aircraft.serial_number,
        title="Inspect task",
        category=work_models.TaskCategoryEnum.DEFECT,
        origin_type=work_models.TaskOriginTypeEnum.NON_ROUTINE,
        status=work_models.TaskStatusEnum.COMPLETED,
    )
    db_session.add(task)
    db_session.flush()

    step = work_models.TaskStep(
        amo_id=amo.id,
        task_id=task.id,
        step_no=1,
        instruction_text="Check item",
        required_flag=True,
    )
    db_session.add(step)
    db_session.commit()

    with pytest.raises(HTTPException):
        work_services.record_task_inspection(
            db_session,
            amo_id=amo.id,
            task=task,
            payload=work_schemas.InspectorSignOffCreate(notes="fail"),
            actor=user,
        )


def test_configuration_event_on_removal(db_session):
    amo = _create_amo(db_session, "AMO-E")
    user = _create_user(db_session, amo.id, account_models.AccountRole.AMO_ADMIN)
    aircraft = _create_aircraft(db_session, amo.id)

    comp = fleet_models.AircraftComponent(
        amo_id=amo.id,
        aircraft_serial_number=aircraft.serial_number,
        position="L ENG",
        part_number="PN-2",
        serial_number="SN-2",
        is_installed=True,
    )
    db_session.add(comp)
    db_session.commit()

    movement_payload = reliability_schemas.PartMovementLedgerCreate(
        aircraft_serial_number=aircraft.serial_number,
        component_id=comp.id,
        event_type=reliability_schemas.PartMovementTypeEnum.REMOVE,
        event_date=date.today(),
        notes="Removal",
    )
    movement = reliability_services.create_part_movement(
        db_session,
        amo_id=amo.id,
        data=movement_payload,
        removal_tracking_id=str(uuid.uuid4()),
        actor_user_id=user.id,
    )
    db_session.refresh(comp)
    assert movement.id is not None
    assert comp.is_installed is False

    events = (
        db_session.query(fleet_models.AircraftConfigurationEvent)
        .filter(fleet_models.AircraftConfigurationEvent.amo_id == amo.id)
        .all()
    )
    assert len(events) == 1


def test_defect_idempotency(db_session):
    amo = _create_amo(db_session, "AMO-F")
    user = _create_user(db_session, amo.id, account_models.AccountRole.AMO_ADMIN)
    aircraft = _create_aircraft(db_session, amo.id)

    payload = fleet_schemas.DefectReportCreate(
        reported_by="Pilot",
        source=fleet_models.DefectSourceEnum.PILOT,
        description="Issue",
        ata_chapter="27",
        occurred_at=datetime.now(timezone.utc),
        create_work_order=False,
        idempotency_key="idem-1",
    )

    defect = fleet_router.create_defect_report(
        serial_number=aircraft.serial_number,
        payload=payload,
        db=db_session,
        current_user=user,
        idempotency_key="idem-1",
    )
    defect_repeat = fleet_router.create_defect_report(
        serial_number=aircraft.serial_number,
        payload=payload,
        db=db_session,
        current_user=user,
        idempotency_key="idem-1",
    )
    assert defect.id == defect_repeat.id
