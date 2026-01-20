from __future__ import annotations

from collections import defaultdict
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.audit import services as audit_services
from amodb.apps.audit import schemas as audit_schemas
from amodb.apps.accounts import services as account_services
from . import models, schemas


def _normalize_part_number(part_number: str) -> str:
    return (part_number or "").strip().upper()


def _get_part_by_number(db: Session, *, amo_id: str, part_number: str) -> Optional[models.InventoryPart]:
    return (
        db.query(models.InventoryPart)
        .filter(
            models.InventoryPart.amo_id == amo_id,
            models.InventoryPart.part_number == _normalize_part_number(part_number),
        )
        .first()
    )


def _ensure_part(
    db: Session,
    *,
    amo_id: str,
    part_number: str,
    description: Optional[str],
    uom: str,
    is_serialized: Optional[bool],
    is_lot_controlled: Optional[bool],
) -> models.InventoryPart:
    part_number = _normalize_part_number(part_number)
    part = _get_part_by_number(db, amo_id=amo_id, part_number=part_number)
    if part:
        return part
    if is_serialized is None or is_lot_controlled is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Part master not found; is_serialized and is_lot_controlled are required to create.",
        )
    part = models.InventoryPart(
        amo_id=amo_id,
        part_number=part_number,
        description=description,
        uom=uom,
        is_serialized=is_serialized,
        is_lot_controlled=is_lot_controlled,
    )
    db.add(part)
    db.flush()
    return part


def _ensure_lot(
    db: Session,
    *,
    amo_id: str,
    part: models.InventoryPart,
    lot_number: Optional[str],
    received_date: Optional[date] = None,
) -> Optional[models.InventoryLot]:
    if not lot_number:
        return None
    lot = (
        db.query(models.InventoryLot)
        .filter(
            models.InventoryLot.amo_id == amo_id,
            models.InventoryLot.part_id == part.id,
            models.InventoryLot.lot_number == lot_number,
        )
        .first()
    )
    if lot:
        return lot
    lot = models.InventoryLot(
        amo_id=amo_id,
        part_id=part.id,
        lot_number=lot_number,
        received_date=received_date,
    )
    db.add(lot)
    db.flush()
    return lot


def _ensure_serial(
    db: Session,
    *,
    amo_id: str,
    part: models.InventoryPart,
    serial_number: Optional[str],
) -> Optional[models.InventorySerial]:
    if not serial_number:
        return None
    serial = (
        db.query(models.InventorySerial)
        .filter(
            models.InventorySerial.amo_id == amo_id,
            models.InventorySerial.part_id == part.id,
            models.InventorySerial.serial_number == serial_number,
        )
        .first()
    )
    if serial:
        return serial
    serial = models.InventorySerial(
        amo_id=amo_id,
        part_id=part.id,
        serial_number=serial_number,
    )
    db.add(serial)
    db.flush()
    return serial


def _current_condition(
    db: Session,
    *,
    amo_id: str,
    part_id: int,
    lot_id: Optional[int],
    serial_id: Optional[int],
    location_id: Optional[int],
) -> Optional[models.InventoryConditionEnum]:
    query = db.query(models.InventoryMovementLedger).filter(
        models.InventoryMovementLedger.amo_id == amo_id,
        models.InventoryMovementLedger.part_id == part_id,
    )
    if lot_id is not None:
        query = query.filter(models.InventoryMovementLedger.lot_id == lot_id)
    if serial_id is not None:
        query = query.filter(models.InventoryMovementLedger.serial_id == serial_id)
    if location_id is not None:
        query = query.filter(
            (models.InventoryMovementLedger.from_location_id == location_id)
            | (models.InventoryMovementLedger.to_location_id == location_id)
        )
    last = query.order_by(models.InventoryMovementLedger.occurred_at.desc()).first()
    if last:
        return last.condition
    return None


def _get_on_hand_quantity(
    db: Session,
    *,
    amo_id: str,
    part_id: int,
    lot_id: Optional[int],
    serial_id: Optional[int],
    location_id: Optional[int],
) -> float:
    query = db.query(models.InventoryMovementLedger).filter(
        models.InventoryMovementLedger.amo_id == amo_id,
        models.InventoryMovementLedger.part_id == part_id,
    )
    if lot_id is not None:
        query = query.filter(models.InventoryMovementLedger.lot_id == lot_id)
    if serial_id is not None:
        query = query.filter(models.InventoryMovementLedger.serial_id == serial_id)
    if location_id is not None:
        query = query.filter(
            (models.InventoryMovementLedger.from_location_id == location_id)
            | (models.InventoryMovementLedger.to_location_id == location_id)
        )
    qty = 0.0
    for entry in query.all():
        qty += _signed_quantity(entry, location_id=location_id)
    return qty


def _signed_quantity(entry: models.InventoryMovementLedger, *, location_id: Optional[int]) -> float:
    if entry.event_type == models.InventoryMovementTypeEnum.RECEIVE:
        return entry.quantity
    if entry.event_type == models.InventoryMovementTypeEnum.RETURN:
        return entry.quantity
    if entry.event_type == models.InventoryMovementTypeEnum.ISSUE:
        return -entry.quantity
    if entry.event_type in {models.InventoryMovementTypeEnum.SCRAP, models.InventoryMovementTypeEnum.VENDOR_RETURN}:
        return -entry.quantity
    if entry.event_type == models.InventoryMovementTypeEnum.TRANSFER:
        if location_id is None:
            return 0.0
        if entry.from_location_id == location_id:
            return -entry.quantity
        if entry.to_location_id == location_id:
            return entry.quantity
        return 0.0
    if entry.event_type == models.InventoryMovementTypeEnum.INSPECT:
        if entry.reference_type == "INSPECT_OUT":
            return -entry.quantity
        if entry.reference_type == "INSPECT_IN":
            return entry.quantity
        return 0.0
    return entry.quantity


def _validate_part_requirements(
    *,
    part: models.InventoryPart,
    lot_number: Optional[str],
    serial_number: Optional[str],
    quantity: float,
) -> None:
    if part.is_serialized:
        if not serial_number:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="serial_number is required for serialized parts.",
            )
        if quantity != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Serialized parts must have quantity=1.",
            )
    else:
        if serial_number:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="serial_number is only allowed for serialized parts.",
            )
    if part.is_lot_controlled and not lot_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="lot_number is required for lot-controlled parts.",
        )


def _register_idempotency(db: Session, *, amo_id: str, scope: str, key: Optional[str], payload: dict) -> None:
    if not key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="idempotency_key is required for this operation.",
        )
    account_services.register_idempotency_key(
        db,
        scope=f"{scope}:{amo_id}",
        key=key,
        payload=payload,
    )


def _audit_event(
    db: Session,
    *,
    amo_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    actor_user_id: Optional[str],
    after_json: dict,
) -> None:
    audit_services.create_audit_event(
        db,
        amo_id=amo_id,
        data=audit_schemas.AuditEventCreate(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_user_id=actor_user_id,
            after_json=after_json,
        ),
    )


def _create_ledger_entry(
    db: Session,
    *,
    amo_id: str,
    part: models.InventoryPart,
    lot: Optional[models.InventoryLot],
    serial: Optional[models.InventorySerial],
    payload: schemas.InventoryMovementBase,
    event_type: models.InventoryMovementTypeEnum,
    condition: Optional[models.InventoryConditionEnum],
    quantity: float,
    from_location_id: Optional[int],
    to_location_id: Optional[int],
    actor_user_id: Optional[str],
    reference_type: Optional[str] = None,
) -> models.InventoryMovementLedger:
    entry = models.InventoryMovementLedger(
        amo_id=amo_id,
        part_id=part.id,
        lot_id=lot.id if lot else None,
        serial_id=serial.id if serial else None,
        quantity=quantity,
        uom=payload.uom,
        event_type=event_type,
        condition=condition,
        from_location_id=from_location_id,
        to_location_id=to_location_id,
        work_order_id=payload.work_order_id,
        task_card_id=payload.task_card_id,
        reference_type=reference_type or payload.reference_type,
        reference_id=payload.reference_id,
        reason_code=getattr(payload, "reason_code", None),
        notes=payload.notes,
        occurred_at=datetime.utcnow(),
        created_by_user_id=actor_user_id,
    )
    db.add(entry)
    db.flush()
    return entry


def receive_inventory(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.InventoryReceiveRequest,
    actor_user_id: Optional[str],
) -> models.InventoryMovementLedger:
    part = _ensure_part(
        db,
        amo_id=amo_id,
        part_number=payload.part_number,
        description=payload.part_description,
        uom=payload.uom,
        is_serialized=payload.is_serialized,
        is_lot_controlled=payload.is_lot_controlled,
    )
    _validate_part_requirements(
        part=part,
        lot_number=payload.lot_number,
        serial_number=payload.serial_number,
        quantity=payload.quantity,
    )
    if not payload.to_location_id:
        raise HTTPException(status_code=400, detail="to_location_id is required for receive.")
    lot = _ensure_lot(db, amo_id=amo_id, part=part, lot_number=payload.lot_number, received_date=payload.received_date)
    serial = _ensure_serial(db, amo_id=amo_id, part=part, serial_number=payload.serial_number)

    _register_idempotency(
        db,
        amo_id=amo_id,
        scope="inventory-receive",
        key=payload.idempotency_key,
        payload=payload.model_dump(),
    )

    condition = payload.condition or models.InventoryConditionEnum.QUARANTINE
    entry = _create_ledger_entry(
        db,
        amo_id=amo_id,
        part=part,
        lot=lot,
        serial=serial,
        payload=payload,
        event_type=models.InventoryMovementTypeEnum.RECEIVE,
        condition=condition,
        quantity=payload.quantity,
        from_location_id=None,
        to_location_id=payload.to_location_id,
        actor_user_id=actor_user_id,
    )
    _audit_event(
        db,
        amo_id=amo_id,
        entity_type="InventoryMovementLedger",
        entity_id=str(entry.id),
        action="receive",
        actor_user_id=actor_user_id,
        after_json={"part_number": part.part_number, "quantity": payload.quantity},
    )

    from amodb.apps.finance import services as finance_services

    finance_services.post_inventory_receipt(
        db,
        amo_id=amo_id,
        amount=Decimal(payload.quantity),
        actor_user_id=actor_user_id,
        reference=f"INV-RECEIVE:{entry.id}",
    )
    return entry


def inspect_inventory(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.InventoryInspectRequest,
    actor_user_id: Optional[str],
) -> List[models.InventoryMovementLedger]:
    part = _get_part_by_number(db, amo_id=amo_id, part_number=payload.part_number)
    if not part:
        raise HTTPException(status_code=404, detail="Part not found.")
    _validate_part_requirements(
        part=part,
        lot_number=payload.lot_number,
        serial_number=payload.serial_number,
        quantity=1 if part.is_serialized else 0.0,
    )
    lot = _ensure_lot(db, amo_id=amo_id, part=part, lot_number=payload.lot_number)
    serial = _ensure_serial(db, amo_id=amo_id, part=part, serial_number=payload.serial_number)

    _register_idempotency(
        db,
        amo_id=amo_id,
        scope="inventory-inspect",
        key=payload.idempotency_key,
        payload=payload.model_dump(),
    )

    current_condition = _current_condition(
        db,
        amo_id=amo_id,
        part_id=part.id,
        lot_id=lot.id if lot else None,
        serial_id=serial.id if serial else None,
        location_id=payload.location_id,
    )
    if current_condition is None:
        current_condition = models.InventoryConditionEnum.QUARANTINE

    qty_available = _get_on_hand_quantity(
        db,
        amo_id=amo_id,
        part_id=part.id,
        lot_id=lot.id if lot else None,
        serial_id=serial.id if serial else None,
        location_id=payload.location_id,
    )
    if qty_available <= 0:
        raise HTTPException(status_code=409, detail="No on-hand quantity available for inspection.")

    out_entry = _create_ledger_entry(
        db,
        amo_id=amo_id,
        part=part,
        lot=lot,
        serial=serial,
        payload=schemas.InventoryMovementBase(
            part_number=payload.part_number,
            quantity=abs(qty_available),
            uom=part.uom,
            from_location_id=payload.location_id,
            to_location_id=payload.location_id,
            notes=payload.notes,
        ),
        event_type=models.InventoryMovementTypeEnum.INSPECT,
        condition=current_condition,
        quantity=abs(qty_available),
        from_location_id=payload.location_id,
        to_location_id=payload.location_id,
        actor_user_id=actor_user_id,
        reference_type="INSPECT_OUT",
    )
    in_entry = _create_ledger_entry(
        db,
        amo_id=amo_id,
        part=part,
        lot=lot,
        serial=serial,
        payload=schemas.InventoryMovementBase(
            part_number=payload.part_number,
            quantity=abs(qty_available),
            uom=part.uom,
            from_location_id=payload.location_id,
            to_location_id=payload.location_id,
            notes=payload.notes,
        ),
        event_type=models.InventoryMovementTypeEnum.INSPECT,
        condition=payload.condition,
        quantity=abs(qty_available),
        from_location_id=payload.location_id,
        to_location_id=payload.location_id,
        actor_user_id=actor_user_id,
        reference_type="INSPECT_IN",
    )
    _audit_event(
        db,
        amo_id=amo_id,
        entity_type="InventoryMovementLedger",
        entity_id=str(in_entry.id),
        action="inspect",
        actor_user_id=actor_user_id,
        after_json={"part_number": part.part_number, "condition": payload.condition.value},
    )
    return [out_entry, in_entry]


def transfer_inventory(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.InventoryTransferRequest,
    actor_user_id: Optional[str],
) -> models.InventoryMovementLedger:
    part = _get_part_by_number(db, amo_id=amo_id, part_number=payload.part_number)
    if not part:
        raise HTTPException(status_code=404, detail="Part not found.")
    _validate_part_requirements(
        part=part,
        lot_number=payload.lot_number,
        serial_number=payload.serial_number,
        quantity=payload.quantity,
    )
    lot = _ensure_lot(db, amo_id=amo_id, part=part, lot_number=payload.lot_number)
    serial = _ensure_serial(db, amo_id=amo_id, part=part, serial_number=payload.serial_number)

    _register_idempotency(
        db,
        amo_id=amo_id,
        scope="inventory-transfer",
        key=payload.idempotency_key,
        payload=payload.model_dump(),
    )

    available = _get_on_hand_quantity(
        db,
        amo_id=amo_id,
        part_id=part.id,
        lot_id=lot.id if lot else None,
        serial_id=serial.id if serial else None,
        location_id=payload.from_location_id,
    )
    if available < payload.quantity:
        raise HTTPException(status_code=409, detail="Insufficient on-hand quantity to transfer.")

    condition = _current_condition(
        db,
        amo_id=amo_id,
        part_id=part.id,
        lot_id=lot.id if lot else None,
        serial_id=serial.id if serial else None,
        location_id=payload.from_location_id,
    )
    entry = _create_ledger_entry(
        db,
        amo_id=amo_id,
        part=part,
        lot=lot,
        serial=serial,
        payload=payload,
        event_type=models.InventoryMovementTypeEnum.TRANSFER,
        condition=condition,
        quantity=payload.quantity,
        from_location_id=payload.from_location_id,
        to_location_id=payload.to_location_id,
        actor_user_id=actor_user_id,
    )
    _audit_event(
        db,
        amo_id=amo_id,
        entity_type="InventoryMovementLedger",
        entity_id=str(entry.id),
        action="transfer",
        actor_user_id=actor_user_id,
        after_json={"part_number": part.part_number, "quantity": payload.quantity},
    )
    return entry


def issue_inventory(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.InventoryIssueRequest,
    actor_user_id: Optional[str],
) -> models.InventoryMovementLedger:
    part = _get_part_by_number(db, amo_id=amo_id, part_number=payload.part_number)
    if not part:
        raise HTTPException(status_code=404, detail="Part not found.")
    _validate_part_requirements(
        part=part,
        lot_number=payload.lot_number,
        serial_number=payload.serial_number,
        quantity=payload.quantity,
    )
    if not payload.from_location_id:
        raise HTTPException(status_code=400, detail="from_location_id is required for issue.")
    lot = _ensure_lot(db, amo_id=amo_id, part=part, lot_number=payload.lot_number)
    serial = _ensure_serial(db, amo_id=amo_id, part=part, serial_number=payload.serial_number)

    _register_idempotency(
        db,
        amo_id=amo_id,
        scope="inventory-issue",
        key=payload.idempotency_key,
        payload=payload.model_dump(),
    )

    available = _get_on_hand_quantity(
        db,
        amo_id=amo_id,
        part_id=part.id,
        lot_id=lot.id if lot else None,
        serial_id=serial.id if serial else None,
        location_id=payload.from_location_id,
    )
    if available < payload.quantity:
        raise HTTPException(status_code=409, detail="Insufficient on-hand quantity to issue.")

    condition = _current_condition(
        db,
        amo_id=amo_id,
        part_id=part.id,
        lot_id=lot.id if lot else None,
        serial_id=serial.id if serial else None,
        location_id=payload.from_location_id,
    )
    if condition and condition != models.InventoryConditionEnum.SERVICEABLE:
        raise HTTPException(
            status_code=409,
            detail="Only SERVICEABLE inventory may be issued.",
        )

    entry = _create_ledger_entry(
        db,
        amo_id=amo_id,
        part=part,
        lot=lot,
        serial=serial,
        payload=payload,
        event_type=models.InventoryMovementTypeEnum.ISSUE,
        condition=condition,
        quantity=payload.quantity,
        from_location_id=payload.from_location_id,
        to_location_id=payload.to_location_id,
        actor_user_id=actor_user_id,
    )
    _audit_event(
        db,
        amo_id=amo_id,
        entity_type="InventoryMovementLedger",
        entity_id=str(entry.id),
        action="issue",
        actor_user_id=actor_user_id,
        after_json={"part_number": part.part_number, "quantity": payload.quantity},
    )

    from amodb.apps.finance import services as finance_services

    finance_services.post_inventory_issue(
        db,
        amo_id=amo_id,
        amount=Decimal(payload.quantity),
        actor_user_id=actor_user_id,
        reference=f"INV-ISSUE:{entry.id}",
    )
    return entry


def return_inventory(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.InventoryReturnRequest,
    actor_user_id: Optional[str],
) -> models.InventoryMovementLedger:
    part = _get_part_by_number(db, amo_id=amo_id, part_number=payload.part_number)
    if not part:
        raise HTTPException(status_code=404, detail="Part not found.")
    _validate_part_requirements(
        part=part,
        lot_number=payload.lot_number,
        serial_number=payload.serial_number,
        quantity=payload.quantity,
    )
    if not payload.to_location_id:
        raise HTTPException(status_code=400, detail="to_location_id is required for return.")
    lot = _ensure_lot(db, amo_id=amo_id, part=part, lot_number=payload.lot_number)
    serial = _ensure_serial(db, amo_id=amo_id, part=part, serial_number=payload.serial_number)

    _register_idempotency(
        db,
        amo_id=amo_id,
        scope="inventory-return",
        key=payload.idempotency_key,
        payload=payload.model_dump(),
    )

    entry = _create_ledger_entry(
        db,
        amo_id=amo_id,
        part=part,
        lot=lot,
        serial=serial,
        payload=payload,
        event_type=models.InventoryMovementTypeEnum.RETURN,
        condition=models.InventoryConditionEnum.SERVICEABLE,
        quantity=payload.quantity,
        from_location_id=payload.from_location_id,
        to_location_id=payload.to_location_id,
        actor_user_id=actor_user_id,
    )
    _audit_event(
        db,
        amo_id=amo_id,
        entity_type="InventoryMovementLedger",
        entity_id=str(entry.id),
        action="return",
        actor_user_id=actor_user_id,
        after_json={"part_number": part.part_number, "quantity": payload.quantity},
    )
    return entry


def scrap_inventory(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.InventoryScrapRequest,
    actor_user_id: Optional[str],
) -> models.InventoryMovementLedger:
    part = _get_part_by_number(db, amo_id=amo_id, part_number=payload.part_number)
    if not part:
        raise HTTPException(status_code=404, detail="Part not found.")
    _validate_part_requirements(
        part=part,
        lot_number=payload.lot_number,
        serial_number=payload.serial_number,
        quantity=payload.quantity,
    )
    if not payload.from_location_id:
        raise HTTPException(status_code=400, detail="from_location_id is required for scrap.")
    if not payload.reason_code:
        raise HTTPException(status_code=400, detail="reason_code is required for scrap.")
    lot = _ensure_lot(db, amo_id=amo_id, part=part, lot_number=payload.lot_number)
    serial = _ensure_serial(db, amo_id=amo_id, part=part, serial_number=payload.serial_number)

    _register_idempotency(
        db,
        amo_id=amo_id,
        scope="inventory-scrap",
        key=payload.idempotency_key,
        payload=payload.model_dump(),
    )

    available = _get_on_hand_quantity(
        db,
        amo_id=amo_id,
        part_id=part.id,
        lot_id=lot.id if lot else None,
        serial_id=serial.id if serial else None,
        location_id=payload.from_location_id,
    )
    if available < payload.quantity:
        raise HTTPException(status_code=409, detail="Insufficient on-hand quantity to scrap.")

    condition = _current_condition(
        db,
        amo_id=amo_id,
        part_id=part.id,
        lot_id=lot.id if lot else None,
        serial_id=serial.id if serial else None,
        location_id=payload.from_location_id,
    )

    entry = _create_ledger_entry(
        db,
        amo_id=amo_id,
        part=part,
        lot=lot,
        serial=serial,
        payload=payload,
        event_type=models.InventoryMovementTypeEnum.SCRAP,
        condition=condition,
        quantity=payload.quantity,
        from_location_id=payload.from_location_id,
        to_location_id=None,
        actor_user_id=actor_user_id,
    )
    _audit_event(
        db,
        amo_id=amo_id,
        entity_type="InventoryMovementLedger",
        entity_id=str(entry.id),
        action="scrap",
        actor_user_id=actor_user_id,
        after_json={"part_number": part.part_number, "quantity": payload.quantity},
    )

    from amodb.apps.finance import services as finance_services

    finance_services.post_inventory_scrap(
        db,
        amo_id=amo_id,
        amount=Decimal(payload.quantity),
        actor_user_id=actor_user_id,
        reference=f"INV-SCRAP:{entry.id}",
    )
    return entry


def list_ledger(
    db: Session,
    *,
    amo_id: str,
    skip: int = 0,
    limit: int = 100,
) -> List[models.InventoryMovementLedger]:
    return (
        db.query(models.InventoryMovementLedger)
        .filter(models.InventoryMovementLedger.amo_id == amo_id)
        .order_by(models.InventoryMovementLedger.occurred_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def list_on_hand(
    db: Session,
    *,
    amo_id: str,
    part_number: Optional[str] = None,
) -> List[schemas.InventoryOnHandItem]:
    query = db.query(models.InventoryMovementLedger).filter(
        models.InventoryMovementLedger.amo_id == amo_id
    )
    if part_number:
        part = _get_part_by_number(db, amo_id=amo_id, part_number=part_number)
        if not part:
            return []
        query = query.filter(models.InventoryMovementLedger.part_id == part.id)

    totals: Dict[tuple, float] = defaultdict(float)
    latest_condition: Dict[tuple, Optional[models.InventoryConditionEnum]] = {}
    for entry in query.all():
        key = (
            entry.part_id,
            entry.lot_id,
            entry.serial_id,
            entry.from_location_id,
            entry.to_location_id,
        )
        location_ids = set()
        if entry.from_location_id:
            location_ids.add(entry.from_location_id)
        if entry.to_location_id:
            location_ids.add(entry.to_location_id)
        for location_id in location_ids:
            signed = _signed_quantity(entry, location_id=location_id)
            qty_key = (entry.part_id, entry.lot_id, entry.serial_id, location_id)
            totals[qty_key] += signed
            if entry.condition:
                latest_condition[qty_key] = entry.condition

    results: List[schemas.InventoryOnHandItem] = []
    for key, qty in totals.items():
        if qty <= 0:
            continue
        part_id, lot_id, serial_id, location_id = key
        part = db.query(models.InventoryPart).filter(models.InventoryPart.id == part_id).first()
        lot = db.query(models.InventoryLot).filter(models.InventoryLot.id == lot_id).first() if lot_id else None
        serial = db.query(models.InventorySerial).filter(models.InventorySerial.id == serial_id).first() if serial_id else None
        condition = latest_condition.get(key)
        results.append(
            schemas.InventoryOnHandItem(
                part_number=part.part_number if part else "",
                lot_number=lot.lot_number if lot else None,
                serial_number=serial.serial_number if serial else None,
                location_id=location_id,
                condition=condition,
                quantity=qty,
            )
        )
    return results


def create_purchase_order(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.PurchaseOrderCreate,
    actor_user_id: Optional[str],
) -> models.PurchaseOrder:
    _register_idempotency(
        db,
        amo_id=amo_id,
        scope="purchase-order",
        key=payload.idempotency_key,
        payload=payload.model_dump(),
    )

    existing = (
        db.query(models.PurchaseOrder)
        .filter(models.PurchaseOrder.amo_id == amo_id, models.PurchaseOrder.po_number == payload.po_number)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Purchase order number already exists.")

    po = models.PurchaseOrder(
        amo_id=amo_id,
        po_number=payload.po_number,
        vendor_id=payload.vendor_id,
        currency=payload.currency,
        requested_by_user_id=actor_user_id,
        notes=payload.notes,
        status=models.PurchaseOrderStatusEnum.DRAFT,
    )
    db.add(po)
    db.flush()

    for line in payload.lines:
        db.add(
            models.PurchaseOrderLine(
                purchase_order_id=po.id,
                part_id=line.part_id,
                description=line.description,
                quantity=line.quantity,
                uom=line.uom,
                unit_price=line.unit_price,
            )
        )
    db.flush()
    _audit_event(
        db,
        amo_id=amo_id,
        entity_type="PurchaseOrder",
        entity_id=str(po.id),
        action="create",
        actor_user_id=actor_user_id,
        after_json={"po_number": po.po_number},
    )
    return po


def approve_purchase_order(
    db: Session,
    *,
    amo_id: str,
    purchase_order_id: int,
    actor_user_id: Optional[str],
) -> models.PurchaseOrder:
    po = (
        db.query(models.PurchaseOrder)
        .filter(models.PurchaseOrder.amo_id == amo_id, models.PurchaseOrder.id == purchase_order_id)
        .first()
    )
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found.")
    if po.status == models.PurchaseOrderStatusEnum.APPROVED:
        return po
    po.status = models.PurchaseOrderStatusEnum.APPROVED
    po.approved_by_user_id = actor_user_id
    po.approved_at = datetime.utcnow()
    db.add(po)
    _audit_event(
        db,
        amo_id=amo_id,
        entity_type="PurchaseOrder",
        entity_id=str(po.id),
        action="approve",
        actor_user_id=actor_user_id,
        after_json={"status": po.status.value},
    )
    return po


def create_goods_receipt(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.GoodsReceiptCreate,
    actor_user_id: Optional[str],
) -> models.GoodsReceipt:
    _register_idempotency(
        db,
        amo_id=amo_id,
        scope="goods-receipt",
        key=payload.idempotency_key,
        payload=payload.model_dump(),
    )

    receipt = models.GoodsReceipt(
        amo_id=amo_id,
        purchase_order_id=payload.purchase_order_id,
        received_at=payload.received_at or datetime.utcnow(),
        received_by_user_id=actor_user_id,
        status=models.GoodsReceiptStatusEnum.POSTED,
        notes=payload.notes,
    )
    db.add(receipt)
    db.flush()

    for line in payload.lines:
        db.add(
            models.GoodsReceiptLine(
                goods_receipt_id=receipt.id,
                part_id=line.part_id,
                lot_number=line.lot_number,
                serial_number=line.serial_number,
                quantity=line.quantity,
                uom=line.uom,
                condition=line.condition,
                location_id=line.location_id,
            )
        )

        if line.part_id is None:
            raise HTTPException(status_code=400, detail="part_id is required for goods receipt lines.")
        part = db.query(models.InventoryPart).filter(models.InventoryPart.id == line.part_id).first()
        if not part:
            raise HTTPException(status_code=404, detail="Part not found for goods receipt line.")

        receive_payload = schemas.InventoryReceiveRequest(
            part_number=part.part_number,
            quantity=line.quantity,
            uom=line.uom,
            lot_number=line.lot_number,
            serial_number=line.serial_number,
            to_location_id=line.location_id,
            condition=line.condition,
            part_description=part.description,
            is_serialized=part.is_serialized,
            is_lot_controlled=part.is_lot_controlled,
            idempotency_key=f"gr:{receipt.id}:{line.part_id}:{line.lot_number or ''}:{line.serial_number or ''}",
        )
        receive_inventory(
            db,
            amo_id=amo_id,
            payload=receive_payload,
            actor_user_id=actor_user_id,
        )

    _audit_event(
        db,
        amo_id=amo_id,
        entity_type="GoodsReceipt",
        entity_id=str(receipt.id),
        action="create",
        actor_user_id=actor_user_id,
        after_json={"goods_receipt_id": receipt.id},
    )
    return receipt
