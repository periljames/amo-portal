from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from amodb.apps.fleet import models as fleet_models
from amodb.apps.procurement import models as procurement_models
from amodb.apps.quality import models as quality_models
from amodb.apps.quality.enums import CARProgram
from amodb.apps.work import models as work_models

from . import models as reliability_models


def _value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _explicit_deferral_type(task: work_models.TaskCard) -> str:
    text = " ".join(filter(None, [task.task_code, task.title, task.description])).upper()
    if "MEL" in text:
        return "MEL_DEFERRAL"
    if "CDL" in text:
        return "CDL_DEFERRAL"
    return "DEFECT"


def _task_record(task: work_models.TaskCard) -> Dict[str, Any]:
    deferred = _value(task.status) == "DEFERRED"
    event_type = _explicit_deferral_type(task) if deferred else "DEFECT"
    identity = "TASK_CARD_DEFERRAL" if deferred else "TASK_CARD"
    occurred_at = task.updated_at if deferred else (task.actual_start or task.created_at)
    return {
        "external_id": f"{identity}:{task.id}",
        "event_type": event_type,
        "occurred_at": occurred_at.isoformat(),
        "aircraft_serial_number": task.aircraft_serial_number,
        "ata_chapter": task.ata_chapter,
        "reference_code": task.task_code or str(task.id),
        "description": task.description or task.title,
        "work_order_id": task.work_order_id,
        "task_card_id": task.id,
        "component_id": task.aircraft_component_id,
        "repeat_key": (
            f"{task.aircraft_serial_number}:"
            f"{task.ata_chapter or 'UNK'}:"
            f"{task.task_code or task.title}"
        ),
        "maintenance_status": _value(task.status),
        "maintenance_category": _value(task.category),
        "maintenance_origin": _value(task.origin_type),
        "mel_reference": task.task_code if event_type == "MEL_DEFERRAL" else None,
        "cdl_reference": task.task_code if event_type == "CDL_DEFERRAL" else None,
    }


def collect_tech_log_records(
    db: Session,
    *,
    amo_id: str,
    cursor: datetime,
    limit: int,
) -> List[Dict[str, Any]]:
    reports = (
        db.query(fleet_models.DefectReport)
        .filter(
            fleet_models.DefectReport.amo_id == amo_id,
            fleet_models.DefectReport.created_at > cursor,
        )
        .order_by(fleet_models.DefectReport.created_at.asc())
        .limit(limit)
        .all()
    )
    records: List[Dict[str, Any]] = []
    for report in reports:
        source = _value(report.source)
        records.append(
            {
                "external_id": f"DEFECT_REPORT:{report.id}",
                "operator_event_id": report.operator_event_id,
                "event_type": "PILOT_REPORT" if source == "PILOT" else "DEFECT",
                "occurred_at": report.occurred_at.isoformat(),
                "aircraft_serial_number": report.aircraft_serial_number,
                "ata_chapter": report.ata_chapter,
                "reference_code": report.operator_event_id or str(report.id),
                "description": report.description,
                "work_order_id": report.work_order_id,
                "task_card_id": report.task_card_id,
                "reported_by": report.reported_by,
                "defect_source": source,
            }
        )
    return records


def collect_maintenance_records(
    db: Session,
    *,
    amo_id: str,
    cursor: datetime,
    limit: int,
) -> List[Dict[str, Any]]:
    tasks = (
        db.query(work_models.TaskCard)
        .filter(
            work_models.TaskCard.amo_id == amo_id,
            work_models.TaskCard.updated_at > cursor,
            (
                (work_models.TaskCard.category == work_models.TaskCategoryEnum.DEFECT)
                | (work_models.TaskCard.category == work_models.TaskCategoryEnum.UNSCHEDULED)
                | (work_models.TaskCard.status == work_models.TaskStatusEnum.DEFERRED)
                | (work_models.TaskCard.origin_type == work_models.TaskOriginTypeEnum.NON_ROUTINE)
            ),
        )
        .order_by(work_models.TaskCard.updated_at.asc())
        .limit(limit)
        .all()
    )
    return [_task_record(task) for task in tasks]


def collect_technical_record_events(
    db: Session,
    *,
    amo_id: str,
    cursor: datetime,
    limit: int,
) -> List[Dict[str, Any]]:
    events = (
        db.query(fleet_models.AircraftConfigurationEvent)
        .filter(
            fleet_models.AircraftConfigurationEvent.amo_id == amo_id,
            fleet_models.AircraftConfigurationEvent.created_at > cursor,
        )
        .order_by(fleet_models.AircraftConfigurationEvent.created_at.asc())
        .limit(limit)
        .all()
    )
    records: List[Dict[str, Any]] = []
    for event in events:
        event_value = _value(event.event_type)
        task = None
        if event.task_card_id:
            task = (
                db.query(work_models.TaskCard)
                .filter(
                    work_models.TaskCard.amo_id == amo_id,
                    work_models.TaskCard.id == event.task_card_id,
                )
                .first()
            )
        component = None
        if event.component_instance_id:
            component = (
                db.query(reliability_models.ComponentInstance)
                .filter(
                    reliability_models.ComponentInstance.amo_id == amo_id,
                    reliability_models.ComponentInstance.id == event.component_instance_id,
                )
                .first()
            )
        scheduled = bool(task and task.category == work_models.TaskCategoryEnum.SCHEDULED)
        if event_value == "INSTALL":
            event_type = "INSTALLATION"
        elif event_value in {"REMOVE", "SWAP"}:
            event_type = "SCHEDULED_REMOVAL" if scheduled else "UNSCHEDULED_REMOVAL"
        else:
            continue
        records.append(
            {
                "external_id": f"CONFIG_EVENT:{event.id}",
                "event_type": event_type,
                "occurred_at": event.occurred_at.isoformat(),
                "aircraft_serial_number": event.aircraft_serial_number,
                "ata_chapter": component.ata if component else None,
                "reference_code": event.removal_tracking_id or str(event.id),
                "description": (
                    f"{event_value} {event.part_number or event.from_part_number or 'component'} "
                    f"at {event.position or 'unrecorded position'}"
                ),
                "part_number": (
                    event.part_number
                    or event.from_part_number
                    or (component.part_number if component else None)
                ),
                "component_serial_number": (
                    event.serial_number
                    or event.from_serial_number
                    or (component.serial_number if component else None)
                ),
                "work_order_id": event.work_order_id,
                "task_card_id": event.task_card_id,
                "component_instance_id": event.component_instance_id,
                "position": event.position,
                "removal_tracking_id": event.removal_tracking_id,
                "removal_classification_basis": (
                    "SCHEDULED_TASK" if scheduled else "UNSCHEDULED_OR_UNCLASSIFIED"
                ),
            }
        )
    return records


def collect_reliability_qms_records(
    db: Session,
    *,
    amo_id: str,
    cursor: datetime,
    limit: int,
) -> List[Dict[str, Any]]:
    cars = (
        db.query(quality_models.CorrectiveActionRequest)
        .filter(
            quality_models.CorrectiveActionRequest.amo_id == amo_id,
            quality_models.CorrectiveActionRequest.program == CARProgram.RELIABILITY,
            quality_models.CorrectiveActionRequest.created_at > cursor,
        )
        .order_by(quality_models.CorrectiveActionRequest.created_at.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "external_id": f"RELIABILITY_CAR:{car.id}",
            "event_type": "FRACAS",
            "occurred_at": car.created_at.isoformat(),
            "reference_code": car.car_number,
            "description": f"{car.title}: {car.summary}",
            "severity": _value(car.priority),
            "qms_car_id": str(car.id),
            "qms_finding_id": str(car.finding_id) if car.finding_id else None,
            "qms_status": _value(car.status),
        }
        for car in cars
    ]


def collect_procurement_quality_records(
    db: Session,
    *,
    amo_id: str,
    cursor: datetime,
    limit: int,
) -> List[Dict[str, Any]]:
    risky_dispositions = {
        procurement_models.InspectionDisposition.REJECTED,
        procurement_models.InspectionDisposition.RETURN_TO_SUPPLIER,
        procurement_models.InspectionDisposition.ESCALATED_TO_QUALITY,
    }
    inspections = (
        db.query(procurement_models.ProcurementReceivingInspection)
        .filter(
            procurement_models.ProcurementReceivingInspection.amo_id == amo_id,
            procurement_models.ProcurementReceivingInspection.completed_at > cursor,
            (
                procurement_models.ProcurementReceivingInspection.disposition.in_(risky_dispositions)
                | procurement_models.ProcurementReceivingInspection.suspected_unapproved_part.is_(True)
            ),
        )
        .order_by(procurement_models.ProcurementReceivingInspection.completed_at.asc())
        .limit(limit)
        .all()
    )
    records: List[Dict[str, Any]] = []
    for inspection in inspections:
        receipt = (
            db.query(procurement_models.ProcurementReceipt)
            .filter(
                procurement_models.ProcurementReceipt.amo_id == amo_id,
                procurement_models.ProcurementReceipt.id == inspection.receipt_id,
            )
            .first()
        )
        line = receipt.lines[0] if receipt and receipt.lines else None
        purchase_order = None
        if receipt:
            purchase_order = (
                db.query(procurement_models.ProcurementPurchaseOrder)
                .filter(
                    procurement_models.ProcurementPurchaseOrder.amo_id == amo_id,
                    procurement_models.ProcurementPurchaseOrder.id == receipt.purchase_order_id,
                )
                .first()
            )
        records.append(
            {
                "external_id": f"PROCUREMENT_INSPECTION:{inspection.id}",
                "event_type": "SUPPLIER_ESCAPE",
                "occurred_at": inspection.completed_at.isoformat(),
                "reference_code": receipt.receipt_number if receipt else str(inspection.id),
                "description": (
                    inspection.findings
                    or inspection.conditions
                    or "Receiving inspection quality escape"
                ),
                "severity": "CRITICAL" if inspection.suspected_unapproved_part else "HIGH",
                "part_number": line.part_number if line else None,
                "component_serial_number": line.serial_number if line else None,
                "supplier_id": purchase_order.supplier_id if purchase_order else None,
                "procurement_receipt_id": receipt.id if receipt else None,
                "inspection_disposition": _value(inspection.disposition),
                "suspected_unapproved_part": inspection.suspected_unapproved_part,
            }
        )

    remaining = max(limit - len(records), 0)
    if remaining:
        holds = (
            db.query(procurement_models.ProcurementQualityHold)
            .filter(
                procurement_models.ProcurementQualityHold.amo_id == amo_id,
                procurement_models.ProcurementQualityHold.placed_at > cursor,
                procurement_models.ProcurementQualityHold.status
                == procurement_models.QualityHoldStatus.ACTIVE,
            )
            .order_by(procurement_models.ProcurementQualityHold.placed_at.asc())
            .limit(remaining)
            .all()
        )
        records.extend(
            {
                "external_id": f"PROCUREMENT_HOLD:{hold.id}",
                "event_type": "SUPPLIER_ESCAPE",
                "occurred_at": hold.placed_at.isoformat(),
                "reference_code": hold.hold_number,
                "description": hold.reason,
                "severity": "HIGH",
                "procurement_target_type": hold.target_type,
                "procurement_target_id": hold.target_id,
                "qms_finding_id": hold.qms_finding_id,
                "qms_car_id": hold.qms_car_id,
            }
            for hold in holds
        )
    return records


def collect_internal_records(
    db: Session,
    *,
    source_type: str,
    amo_id: str,
    cursor: datetime,
    limit: int = 2000,
) -> List[Dict[str, Any]]:
    collectors = {
        "TECH_LOG": collect_tech_log_records,
        "MAINTENANCE": collect_maintenance_records,
        "TECH_RECORDS": collect_technical_record_events,
        "QMS": collect_reliability_qms_records,
        "PROCUREMENT": collect_procurement_quality_records,
    }
    collector = collectors.get(source_type)
    if collector is None:
        return []
    return collector(db, amo_id=amo_id, cursor=cursor, limit=limit)
