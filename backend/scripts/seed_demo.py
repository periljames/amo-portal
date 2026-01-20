from __future__ import annotations

from datetime import date, datetime, timezone

from amodb.database import WriteSessionLocal
from amodb.apps.accounts import models as account_models
from amodb.apps.accounts import schemas as account_schemas
from amodb.apps.accounts import services as account_services
from amodb.apps.fleet import models as fleet_models
from amodb.apps.work import models as work_models
from amodb.apps.work import schemas as work_schemas
from amodb.apps.work import services as work_services
from amodb.apps.reliability import models as reliability_models
from amodb.apps.reliability import schemas as reliability_schemas
from amodb.apps.reliability import services as reliability_services
from amodb.utils.identifiers import generate_uuid7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_or_create_amo(db) -> account_models.AMO:
    amo = db.query(account_models.AMO).filter(account_models.AMO.amo_code == "DEMO").first()
    if amo:
        return amo
    amo = account_models.AMO(
        amo_code="DEMO",
        name="Demo AMO",
        login_slug="demo-amo",
        contact_email="ops@demo-amo.example",
        time_zone="UTC",
        is_active=True,
    )
    db.add(amo)
    db.commit()
    db.refresh(amo)
    return amo


def _get_or_create_admin(db, amo: account_models.AMO) -> account_models.User:
    user = (
        db.query(account_models.User)
        .filter(account_models.User.amo_id == amo.id, account_models.User.email == "admin@demo-amo.example")
        .first()
    )
    if user:
        return user
    user = account_services.create_user(
        db,
        account_schemas.UserCreate(
            amo_id=amo.id,
            department_id=None,
            staff_code="DEMO-ADMIN",
            email="admin@demo-amo.example",
            first_name="Demo",
            last_name="Admin",
            full_name="Demo Admin",
            role=account_models.AccountRole.AMO_ADMIN,
            position_title="Maintenance Manager",
            phone="+0000000000",
            regulatory_authority=None,
            licence_number=None,
            licence_state_or_country=None,
            licence_expires_on=None,
            password="ChangeMe123!",
        ),
    )
    return user


def _get_or_create_aircraft(db, amo: account_models.AMO) -> fleet_models.Aircraft:
    aircraft = (
        db.query(fleet_models.Aircraft)
        .filter(fleet_models.Aircraft.amo_id == amo.id, fleet_models.Aircraft.serial_number == "DEMO-AC01")
        .first()
    )
    if aircraft:
        return aircraft
    aircraft = fleet_models.Aircraft(
        serial_number="DEMO-AC01",
        registration="N123DM",
        amo_id=amo.id,
        aircraft_model_code="C208B",
        template="C208B",
        make="Cessna",
        model="208B",
        total_hours=1250.5,
        total_cycles=820,
        last_log_date=date.today(),
        status="OPEN",
        is_active=True,
    )
    db.add(aircraft)
    db.commit()
    db.refresh(aircraft)
    return aircraft


def _seed_baseline_components(db, aircraft: fleet_models.Aircraft) -> None:
    baseline = [
        {"position": "LH ENGINE", "part_number": "PT6A-114", "serial_number": "ENG-LH-001", "ata": "72"},
        {"position": "RH ENGINE", "part_number": "PT6A-114", "serial_number": "ENG-RH-002", "ata": "72"},
        {"position": "APU", "part_number": "GTCP36-150", "serial_number": "APU-001", "ata": "49"},
    ]
    for item in baseline:
        existing = (
            db.query(fleet_models.AircraftComponent)
            .filter(
                fleet_models.AircraftComponent.amo_id == aircraft.amo_id,
                fleet_models.AircraftComponent.aircraft_serial_number == aircraft.serial_number,
                fleet_models.AircraftComponent.position == item["position"],
            )
            .first()
        )
        if existing:
            continue

        component = fleet_models.AircraftComponent(
            amo_id=aircraft.amo_id,
            aircraft_serial_number=aircraft.serial_number,
            position=item["position"],
            part_number=item["part_number"],
            serial_number=item["serial_number"],
            ata=item["ata"],
            installed_date=date.today(),
            installed_hours=aircraft.total_hours,
            installed_cycles=aircraft.total_cycles,
            current_hours=aircraft.total_hours,
            current_cycles=aircraft.total_cycles,
            is_installed=True,
        )
        db.add(component)
        db.flush()

        instance = (
            db.query(reliability_models.ComponentInstance)
            .filter(
                reliability_models.ComponentInstance.amo_id == aircraft.amo_id,
                reliability_models.ComponentInstance.part_number == component.part_number,
                reliability_models.ComponentInstance.serial_number == component.serial_number,
            )
            .first()
        )
        if not instance:
            instance = reliability_models.ComponentInstance(
                amo_id=aircraft.amo_id,
                part_number=component.part_number,
                serial_number=component.serial_number,
                ata=component.ata,
            )
            db.add(instance)
            db.flush()

        config_event = (
            db.query(fleet_models.AircraftConfigurationEvent)
            .filter(
                fleet_models.AircraftConfigurationEvent.amo_id == aircraft.amo_id,
                fleet_models.AircraftConfigurationEvent.aircraft_serial_number == aircraft.serial_number,
                fleet_models.AircraftConfigurationEvent.position == component.position,
                fleet_models.AircraftConfigurationEvent.event_type == fleet_models.ConfigurationEventTypeEnum.INSTALL,
            )
            .first()
        )
        if not config_event:
            db.add(
                fleet_models.AircraftConfigurationEvent(
                    amo_id=aircraft.amo_id,
                    aircraft_serial_number=aircraft.serial_number,
                    component_instance_id=instance.id,
                    occurred_at=_utcnow(),
                    event_type=fleet_models.ConfigurationEventTypeEnum.INSTALL,
                    position=component.position,
                    part_number=component.part_number,
                    serial_number=component.serial_number,
                )
            )

    db.commit()


def _seed_defect_workflow(
    db,
    amo: account_models.AMO,
    aircraft: fleet_models.Aircraft,
    actor: account_models.User,
) -> tuple[work_models.WorkOrder, work_models.TaskCard]:
    defect = (
        db.query(fleet_models.DefectReport)
        .filter(
            fleet_models.DefectReport.amo_id == amo.id,
            fleet_models.DefectReport.idempotency_key == "seed-demo-defect-1",
        )
        .first()
    )
    if defect:
        work_order = db.query(work_models.WorkOrder).filter(work_models.WorkOrder.id == defect.work_order_id).first()
        task = db.query(work_models.TaskCard).filter(work_models.TaskCard.id == defect.task_card_id).first()
        return work_order, task

    operator_event_id = generate_uuid7()
    wo_payload = work_schemas.WorkOrderCreate(
        wo_number=f"DEMO-DEF-{date.today():%Y%m%d}",
        aircraft_serial_number=aircraft.serial_number,
        description="Demo defect: oil pressure fluctuation",
        wo_type=work_models.WorkOrderTypeEnum.DEFECT,
        status=work_models.WorkOrderStatusEnum.RELEASED,
        is_scheduled=False,
        open_date=date.today(),
        operator_event_id=operator_event_id,
        tasks=[
            work_schemas.TaskCardCreate(
                title="Investigate oil pressure fluctuation",
                description="Perform troubleshooting and document findings.",
                category=work_models.TaskCategoryEnum.DEFECT,
                origin_type=work_models.TaskOriginTypeEnum.NON_ROUTINE,
                priority=work_models.TaskPriorityEnum.HIGH,
                ata_chapter="79",
                operator_event_id=operator_event_id,
                steps=[
                    work_schemas.TaskStepCreate(
                        step_no=1,
                        instruction_text="Inspect oil pressure sensor wiring.",
                        required_flag=True,
                        measurement_type="OHMS",
                        expected_range={"min": 0.0, "max": 5.0},
                    ),
                    work_schemas.TaskStepCreate(
                        step_no=2,
                        instruction_text="Operational test run at idle and 75% torque.",
                        required_flag=True,
                        measurement_type="PSI",
                        expected_range={"min": 90.0, "max": 110.0},
                    ),
                ],
            )
        ],
    )
    work_order = work_services.create_work_order(db, amo_id=amo.id, payload=wo_payload, actor=actor)
    db.commit()
    db.refresh(work_order)

    task = (
        db.query(work_models.TaskCard)
        .filter(work_models.TaskCard.work_order_id == work_order.id)
        .order_by(work_models.TaskCard.id.asc())
        .first()
    )
    defect = fleet_models.DefectReport(
        amo_id=amo.id,
        aircraft_serial_number=aircraft.serial_number,
        reported_by="Demo Pilot",
        source=fleet_models.DefectSourceEnum.PILOT,
        description="Oil pressure fluctuated during climb.",
        ata_chapter="79",
        occurred_at=_utcnow(),
        operator_event_id=operator_event_id,
        idempotency_key="seed-demo-defect-1",
        work_order_id=work_order.id,
        task_card_id=task.id if task else None,
        created_by_user_id=actor.id,
    )
    db.add(defect)
    db.commit()
    return work_order, task


def _execute_and_close_task(
    db,
    task: work_models.TaskCard,
    actor: account_models.User,
) -> None:
    steps = (
        db.query(work_models.TaskStep)
        .filter(work_models.TaskStep.task_id == task.id)
        .order_by(work_models.TaskStep.step_no.asc())
        .all()
    )
    for idx, step in enumerate(steps, start=1):
        existing_exec = (
            db.query(work_models.TaskStepExecution)
            .filter(
                work_models.TaskStepExecution.task_id == task.id,
                work_models.TaskStepExecution.task_step_id == step.id,
            )
            .first()
        )
        if existing_exec:
            continue
        execution_payload = work_schemas.TaskStepExecutionCreate(
            result_text="Completed",
            measurement_value=1.0 * idx,
            attachment_id=f"demo-attachment-{idx}",
            signed_flag=True,
            signature_hash="demo-signature",
        )
        work_services.execute_task_step(
            db,
            amo_id=task.amo_id,
            task=task,
            step=step,
            payload=execution_payload,
            actor=actor,
        )

    if task.status != work_models.TaskStatusEnum.COMPLETED:
        work_services.update_task(
            db,
            task=task,
            data={"status": work_models.TaskStatusEnum.COMPLETED, "actual_end": _utcnow()},
            actor=actor,
        )
    if not task.inspector_signoffs:
        work_services.record_task_inspection(
            db,
            amo_id=task.amo_id,
            task=task,
            payload=work_schemas.InspectorSignOffCreate(
                notes="Demo inspection complete.",
                signed_flag=True,
                signature_hash="demo-inspector-signature",
            ),
            actor=actor,
        )
    db.commit()


def _inspect_and_close_work_order(
    db,
    work_order: work_models.WorkOrder,
    actor: account_models.User,
) -> None:
    if work_order.status != work_models.WorkOrderStatusEnum.INSPECTED:
        work_services.update_work_order(
            db,
            work_order=work_order,
            payload=work_schemas.WorkOrderUpdate(status=work_models.WorkOrderStatusEnum.INSPECTED),
            actor=actor,
        )
    if not work_order.inspector_signoffs:
        work_services.record_work_order_inspection(
            db,
            amo_id=work_order.amo_id,
            work_order=work_order,
            payload=work_schemas.InspectorSignOffCreate(
                notes="Demo work order inspection.",
                signed_flag=True,
                signature_hash="demo-wo-signature",
            ),
            actor=actor,
        )
    if work_order.status != work_models.WorkOrderStatusEnum.CLOSED:
        work_services.update_work_order(
            db,
            work_order=work_order,
            payload=work_schemas.WorkOrderUpdate(
                status=work_models.WorkOrderStatusEnum.CLOSED,
                closed_date=date.today(),
                closure_reason="NO_CRS_REQUIRED",
                closure_notes="Demo closure with inspection.",
            ),
            actor=actor,
        )
    db.commit()


def _seed_swap_event(db, work_order: work_models.WorkOrder, actor: account_models.User) -> None:
    component = (
        db.query(fleet_models.AircraftComponent)
        .filter(
            fleet_models.AircraftComponent.amo_id == work_order.amo_id,
            fleet_models.AircraftComponent.aircraft_serial_number == work_order.aircraft_serial_number,
            fleet_models.AircraftComponent.position == "LH ENGINE",
        )
        .first()
    )
    if not component:
        return

    idempotency_key = "seed-demo-swap-1"
    existing_movement = (
        db.query(reliability_models.PartMovementLedger)
        .filter(
            reliability_models.PartMovementLedger.amo_id == work_order.amo_id,
            reliability_models.PartMovementLedger.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing_movement:
        return

    component.part_number = "PT6A-114A"
    component.serial_number = "ENG-LH-SWAP"
    db.add(component)
    db.flush()

    instance = (
        db.query(reliability_models.ComponentInstance)
        .filter(
            reliability_models.ComponentInstance.amo_id == work_order.amo_id,
            reliability_models.ComponentInstance.part_number == component.part_number,
            reliability_models.ComponentInstance.serial_number == component.serial_number,
        )
        .first()
    )
    if not instance:
        instance = reliability_models.ComponentInstance(
            amo_id=work_order.amo_id,
            part_number=component.part_number,
            serial_number=component.serial_number,
            ata=component.ata,
        )
        db.add(instance)
        db.flush()

    movement_payload = reliability_schemas.PartMovementLedgerCreate(
        aircraft_serial_number=work_order.aircraft_serial_number,
        component_id=component.id,
        component_instance_id=instance.id,
        work_order_id=work_order.id,
        task_card_id=None,
        event_type=reliability_models.PartMovementTypeEnum.SWAP,
        event_date=date.today(),
        notes="Demo swap event",
        idempotency_key=idempotency_key,
    )
    reliability_services.create_part_movement(
        db,
        amo_id=work_order.amo_id,
        data=movement_payload,
        removal_tracking_id=None,
        actor_user_id=actor.id,
    )
    db.commit()


def main() -> None:
    db = WriteSessionLocal()
    try:
        amo = _get_or_create_amo(db)
        admin = _get_or_create_admin(db, amo)
        aircraft = _get_or_create_aircraft(db, amo)
        _seed_baseline_components(db, aircraft)
        work_order, task = _seed_defect_workflow(db, amo, aircraft, admin)
        if task:
            _execute_and_close_task(db, task, admin)
        if work_order:
            _inspect_and_close_work_order(db, work_order, admin)
            _seed_swap_event(db, work_order, admin)
    finally:
        db.close()


if __name__ == "__main__":
    main()
