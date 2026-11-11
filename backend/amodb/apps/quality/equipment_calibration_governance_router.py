"""Calibration control using canonical QMS asset, certificate and OOT registers.

The inventory serial (when supplied) is validated through the authoritative
Inventory model and stored only as a typed foreign identifier. Quality does not
duplicate Inventory parts or movement ledgers. A due/unsafe asset is denied at
the eligibility API; operational consumers must call that gate before assignment.
"""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.inventory import models as inventory_models
from amodb.database import get_read_db, get_write_db
from .canonical_core_router import _insert_record, _log_qms_activity
from .qms_evidence_reference_validation import require_evidence_records
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context

router = APIRouter(prefix="/equipment-calibration/governance", tags=["QMS calibration governance"])
_EQUIPMENT = "qms_equipment"
_CAL = "qms_calibration_records"
_CERT = "qms_calibration_certificates"
_OOT = "qms_out_of_tolerance_events"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EquipmentCreate(Strict):
    title: str = Field(min_length=4, max_length=255)
    description: str = Field(min_length=8, max_length=5000)
    asset_reference: str = Field(min_length=2, max_length=100)
    inventory_serial_id: int | None = Field(default=None, ge=1)
    owner_user_id: str = Field(min_length=1, max_length=36)
    calibration_due: date
    traceability_policy: str = Field(min_length=8, max_length=4000)


class Versioned(Strict):
    expected_version: int = Field(ge=1)


class CalibrationSubmitted(Versioned):
    title: str = Field(min_length=4, max_length=255)
    certificate_number: str = Field(min_length=3, max_length=128)
    certificate_evidence_ids: list[str] = Field(min_length=1, max_length=20)
    calibration_date: date
    next_due: date
    issuing_lab: str = Field(min_length=3, max_length=255)
    standard_reference: str = Field(min_length=3, max_length=255)
    result: Literal["IN_TOLERANCE", "OUT_OF_TOLERANCE"]
    notes: str = Field(min_length=8, max_length=8000)


class CalibrationDecision(Versioned):
    calibration_id: str = Field(min_length=1, max_length=36)
    accepted: bool
    rationale: str = Field(min_length=12, max_length=4000)


class OutOfTolerance(Versioned):
    description: str = Field(min_length=12, max_length=8000)
    detected_on: date
    last_known_good: date | None = None
    affected_work_references: list[str] = Field(default_factory=list, max_length=100)
    evidence_record_ids: list[str] = Field(min_length=1, max_length=30)


class OotDisposition(Versioned):
    event_id: str = Field(min_length=1, max_length=36)
    impact_assessment: str = Field(min_length=20, max_length=8000)
    disposition: Literal["RECALIBRATE", "REPAIR", "SCRAP", "NO_ADVERSE_IMPACT"]
    affected_work_references: list[str] = Field(default_factory=list, max_length=100)
    evidence_record_ids: list[str] = Field(min_length=1, max_length=30)


class ReturnToService(Versioned):
    rationale: str = Field(min_length=12, max_length=4000)
    closure_evidence_ids: list[str] = Field(min_length=1, max_length=30)


def _init(db: Session, ctx: TenantContext) -> None:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _user(db: Session, ctx: TenantContext, user_id: str) -> None:
    found = db.query(account_models.User.id).filter(
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.id == user_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).first()
    if not found:
        raise HTTPException(422, "Equipment custodian must be an active account in the tenant.")


def _asset(db: Session, ctx: TenantContext, asset_id: str, *, lock=False) -> dict[str, Any]:
    statement = f"SELECT * FROM {_EQUIPMENT} WHERE id=:id AND amo_id=:amo_id AND deleted_at IS NULL"
    if lock:
        statement += " FOR UPDATE"
    row = db.execute(text(statement), {"amo_id": ctx.amo_id, "id": asset_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Equipment is not registered in this tenant.")
    return dict(row)


def _version(row: dict[str, Any], expected: int) -> None:
    value = int((row.get("payload") or {}).get("version", 1))
    if value != expected:
        raise HTTPException(409, {"code": "EQUIPMENT_VERSION_CONFLICT", "expected": expected, "actual": value})


def _children(db: Session, ctx: TenantContext, table: str, asset_id: str) -> list[dict[str, Any]]:
    if table not in {_CAL, _CERT, _OOT}:
        raise ValueError("Unsupported calibration table.")
    rows = db.execute(text(
        f"SELECT * FROM {table} WHERE amo_id=:amo_id AND deleted_at IS NULL "
        "AND payload->>'equipment_id'=:id ORDER BY created_at DESC LIMIT 251"
    ), {"amo_id": ctx.amo_id, "id": asset_id}).mappings().all()
    if len(rows) > 250:
        raise HTTPException(409, "Calibration history exceeds the bounded read limit. Paginate before releasing equipment.")
    return [dict(row) for row in rows]


def _change(db: Session, ctx: TenantContext, row: dict[str, Any], request: Request,
            action: str, data: dict[str, Any], *, status: str | None = None,
            due: date | None = None) -> dict[str, Any]:
    properties = dict(row.get("payload") or {})
    properties.update(data)
    properties["version"] = int(properties.get("version", 1)) + 1
    current = db.execute(text(
        f"UPDATE {_EQUIPMENT} SET status=:status, payload=CAST(:payload AS jsonb), "
        "due_date=COALESCE(:due, due_date), updated_at=now(), updated_by=:actor "
        "WHERE id=:id AND amo_id=:amo_id AND deleted_at IS NULL RETURNING *"
    ), {"amo_id": ctx.amo_id, "id": row["id"], "actor": ctx.user_id,
        "status": status or row["status"], "payload": json.dumps(properties), "due": due}).mappings().one()
    _log_qms_activity(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id,
                      action=action, module="equipment-calibration", entity_type=_EQUIPMENT,
                      entity_id=str(row["id"]), new_value={"version": properties["version"], "change": data}, request=request)
    db.commit()
    return dict(current)


def _eligibility(asset: dict[str, Any], *, today: date) -> dict[str, Any]:
    due = asset.get("due_date")
    reason = "SERVICEABLE" if asset["status"] == "SERVICEABLE" else f"STATUS_{asset['status']}"
    if due is None:
        reason = "NO_VERIFIED_CALIBRATION_DUE_DATE"
    elif not (asset.get("payload") or {}).get("verified_calibration_id"):
        reason = "NO_INDEPENDENTLY_VERIFIED_CALIBRATION"
    elif due < today:
        reason = "CALIBRATION_OVERDUE"
    elif asset["status"] != "SERVICEABLE":
        reason = f"STATUS_{asset['status']}"
    return {"eligible": reason == "SERVICEABLE",
            "reason": reason, "equipment_id": str(asset["id"]), "next_due": due,
            "status": asset["status"], "verified_calibration_id": (asset.get("payload") or {}).get("verified_calibration_id")}


@router.get("/participants")
def equipment_people(
    ctx: TenantContext = Depends(require_quality_permission("qms.equipment.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    users = db.query(account_models.User).filter(
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).order_by(account_models.User.full_name).limit(100).all()
    return {"items": [{"id": row.id, "name": row.full_name} for row in users]}


@router.get("/inventory-serials")
def eligible_inventory_serials(
    q: str = Query(default="", max_length=64),
    ctx: TenantContext = Depends(require_quality_permission("qms.equipment.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    query = db.query(inventory_models.InventorySerial, inventory_models.InventoryPart).join(
        inventory_models.InventoryPart,
        inventory_models.InventoryPart.id == inventory_models.InventorySerial.part_id,
    ).filter(
        inventory_models.InventorySerial.amo_id == ctx.amo_id,
        inventory_models.InventoryPart.amo_id == ctx.amo_id,
    )
    if q:
        query = query.filter(inventory_models.InventorySerial.serial_number.ilike(f"%{q.strip()}%"))
    rows = query.limit(50).all()
    return {"items": [{"id": serial.id, "serial": serial.serial_number,
                       "part_number": part.part_number} for serial, part in rows]}


@router.get("/assets")
def assets(
    limit: int = Query(default=25, ge=1, le=50), offset: int = Query(default=0, ge=0, le=100000),
    ctx: TenantContext = Depends(require_quality_permission("qms.equipment.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    params = {"amo_id": ctx.amo_id, "limit": limit, "offset": offset}
    total = db.execute(text(
        f"SELECT COUNT(*) FROM {_EQUIPMENT} WHERE amo_id=:amo_id AND deleted_at IS NULL"
    ), params).scalar_one()
    rows = db.execute(text(
        f"SELECT * FROM {_EQUIPMENT} WHERE amo_id=:amo_id AND deleted_at IS NULL "
        "ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
    ), params).mappings().all()
    return {"items": [{**dict(row), "eligibility": _eligibility(dict(row), today=date.today())} for row in rows],
            "total": total, "limit": limit, "offset": offset}


@router.get("/eligibility")
def equipment_eligibility(
    asset_id: str | None = Query(default=None, max_length=36),
    inventory_serial_id: int | None = Query(default=None, ge=1),
    ctx: TenantContext = Depends(require_quality_permission("qms.equipment.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    if (asset_id is None) == (inventory_serial_id is None):
        raise HTTPException(422, "Supply exactly one known equipment ID or inventory serial ID.")
    if asset_id:
        asset = _asset(db, ctx, asset_id)
    else:
        row = db.execute(text(
            f"SELECT * FROM {_EQUIPMENT} WHERE amo_id=:amo_id AND deleted_at IS NULL "
            "AND payload->>'inventory_serial_id'=:serial ORDER BY created_at DESC LIMIT 1"
        ), {"amo_id": ctx.amo_id, "serial": str(inventory_serial_id)}).mappings().first()
        if not row:
            return {"eligible": False, "reason": "UNREGISTERED_FOR_CALIBRATION"}
        asset = dict(row)
    return _eligibility(asset, today=date.today())


@router.post("/assets", status_code=201)
def create_equipment(
    body: EquipmentCreate, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.equipment.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    _user(db, ctx, body.owner_user_id)
    if body.inventory_serial_id:
        found = db.query(inventory_models.InventorySerial.id).filter(
            inventory_models.InventorySerial.amo_id == ctx.amo_id,
            inventory_models.InventorySerial.id == body.inventory_serial_id,
        ).first()
        if not found:
            raise HTTPException(422, "Inventory serial does not belong to this tenant.")
        existing = db.execute(text(
            f"SELECT id FROM {_EQUIPMENT} WHERE amo_id=:amo_id AND deleted_at IS NULL "
            "AND payload->>'inventory_serial_id'=:serial LIMIT 1"
        ), {"amo_id": ctx.amo_id, "serial": str(body.inventory_serial_id)}).first()
        if existing:
            raise HTTPException(409, "Inventory serial is already governed by another calibration asset.")
    asset = _insert_record(db, table=_EQUIPMENT, amo_id=ctx.amo_id,
                           actor_user_id=ctx.user_id, payload={
                               "title": body.title, "description": body.description, "status": "QUARANTINED",
                               "owner_user_id": body.owner_user_id, "due_date": body.calibration_due,
                               "payload": {"version": 1, "asset_reference": body.asset_reference,
                                           "inventory_serial_id": body.inventory_serial_id,
                                           "traceability_policy": body.traceability_policy,
                                           "verified_calibration_id": None},
                           })
    _log_qms_activity(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id,
                      action="equipment_registered_quarantined", module="equipment-calibration",
                      entity_type=_EQUIPMENT, entity_id=str(asset["id"]), new_value=asset, request=request)
    db.commit()
    return {"asset": asset}


@router.get("/assets/{asset_id}")
def asset_detail(
    asset_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.equipment.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    asset = _asset(db, ctx, asset_id)
    return {"asset": asset, "eligibility": _eligibility(asset, today=date.today()),
            "calibrations": _children(db, ctx, _CAL, asset_id),
            "certificates": _children(db, ctx, _CERT, asset_id),
            "out_of_tolerance": _children(db, ctx, _OOT, asset_id)}


@router.post("/assets/{asset_id}/calibrations", status_code=201)
def submit_calibration(
    asset_id: str, body: CalibrationSubmitted, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.equipment.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    asset = _asset(db, ctx, asset_id, lock=True)
    _version(asset, body.expected_version)
    if body.next_due <= body.calibration_date:
        raise HTTPException(422, "The next calibration date must follow the certified calibration date.")
    if body.calibration_date > date.today():
        raise HTTPException(422, "Calibration evidence cannot be dated in the future.")
    if asset["status"] == "PENDING_VERIFICATION":
        raise HTTPException(409, "An earlier calibration submission awaits independent verification.")
    require_evidence_records(db, ctx.amo_id, body.certificate_evidence_ids, required=True)
    calibration = _insert_record(db, table=_CAL, amo_id=ctx.amo_id,
                                 actor_user_id=ctx.user_id, payload={
                                     "title": body.title, "status": "PENDING_VERIFICATION",
                                     "due_date": body.next_due, "description": body.notes,
                                     "payload": {"equipment_id": asset_id, "certificate_number": body.certificate_number,
                                                 "certificate_evidence_ids": body.certificate_evidence_ids,
                                                 "calibration_date": body.calibration_date.isoformat(),
                                                 "next_due": body.next_due.isoformat(),
                                                 "issuing_lab": body.issuing_lab,
                                                 "standard_reference": body.standard_reference,
                                                 "result": body.result},
                                 })
    if body.result == "OUT_OF_TOLERANCE":
        _insert_record(db, table=_OOT, amo_id=ctx.amo_id,
                       actor_user_id=ctx.user_id, payload={
                           "title": "Out-of-tolerance calibration result",
                           "status": "OPEN", "description": body.notes,
                           "payload": {"equipment_id": asset_id,
                                       "detected_on": body.calibration_date.isoformat(),
                                       "source_calibration_id": str(calibration["id"]),
                                       "evidence_record_ids": body.certificate_evidence_ids,
                                       "affected_work_references": []},
                       })
    new_status = "QUARANTINED" if body.result == "OUT_OF_TOLERANCE" else "PENDING_VERIFICATION"
    asset = _change(db, ctx, asset, request, "calibration_submitted",
                    {"pending_calibration_id": str(calibration["id"])}, status=new_status)
    return {"asset": asset, "calibration": calibration}


@router.post("/assets/{asset_id}/calibrations/verify")
def verify_calibration(
    asset_id: str, body: CalibrationDecision, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.equipment.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    asset = _asset(db, ctx, asset_id, lock=True)
    _version(asset, body.expected_version)
    record = next((item for item in _children(db, ctx, _CAL, asset_id)
                   if str(item["id"]) == body.calibration_id), None)
    if not record or record["status"] != "PENDING_VERIFICATION":
        raise HTTPException(409, "Calibration is not awaiting independent certificate verification.")
    if str(record["created_by"]) == str(ctx.user_id):
        raise HTTPException(403, "The person submitting the certificate cannot independently verify it.")
    cert = dict(record.get("payload") or {})
    if str((asset["payload"] or {}).get("pending_calibration_id")) != str(record["id"]):
        raise HTTPException(409, "A newer certificate is pending; verify current evidence.")
    require_evidence_records(db, ctx.amo_id, cert["certificate_evidence_ids"], required=True)
    valid_result = cert["result"] == "IN_TOLERANCE"
    next_due = date.fromisoformat(cert["next_due"])
    open_events = [item for item in _children(db, ctx, _OOT, asset_id) if item["status"] != "CLOSED"]
    unresolved = [event for event in open_events if event["status"] == "OPEN"]
    if body.accepted and (not valid_result or next_due < date.today() or unresolved):
        raise HTTPException(409, "The certificate is not in tolerance, is overdue or has an unresolved impact assessment.")
    # A disposed OOT event still requires a separate controlled release. A
    # newly verified certificate never silently restores a quarantined asset.
    status = "VERIFIED" if body.accepted else "REJECTED"
    data = {**cert, "verification_reason": body.rationale, "verified_by": ctx.user_id, "verified_at": _now()}
    db.execute(text(
        f"UPDATE {_CAL} SET status=:status, payload=CAST(:payload AS jsonb), "
        "updated_at=now(), updated_by=:actor WHERE id=:id AND amo_id=:amo_id"
    ), {"id": record["id"], "amo_id": ctx.amo_id, "status": status,
        "payload": json.dumps(data), "actor": ctx.user_id})
    if body.accepted:
        _insert_record(db, table=_CERT, amo_id=ctx.amo_id, actor_user_id=ctx.user_id, payload={
            "title": cert["certificate_number"], "status": "VERIFIED", "due_date": next_due,
            "description": "Controller-verified certificate for calibrated equipment.",
            "payload": {"equipment_id": asset_id, "calibration_id": str(record["id"]),
                        "certificate_evidence_ids": cert["certificate_evidence_ids"],
                        "issuing_lab": cert["issuing_lab"], "standard_reference": cert["standard_reference"]},
        })
    asset = _change(db, ctx, asset, request, "calibration_verified" if body.accepted else "calibration_rejected",
                    {"pending_calibration_id": None,
                     "verified_calibration_id": str(record["id"]) if body.accepted else (asset["payload"] or {}).get("verified_calibration_id")},
                    status=("QUARANTINED" if open_events else "SERVICEABLE") if body.accepted else "QUARANTINED",
                    due=next_due if body.accepted else None)
    return {"asset": asset, "calibration_status": status}


@router.post("/assets/{asset_id}/out-of-tolerance", status_code=201)
def report_out_of_tolerance(
    asset_id: str, body: OutOfTolerance, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.equipment.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    asset = _asset(db, ctx, asset_id, lock=True)
    _version(asset, body.expected_version)
    require_evidence_records(db, ctx.amo_id, body.evidence_record_ids, required=True)
    event = _insert_record(db, table=_OOT, amo_id=ctx.amo_id,
                           actor_user_id=ctx.user_id, payload={
                               "title": "Out-of-tolerance event", "status": "OPEN",
                               "description": body.description,
                               "payload": {"equipment_id": asset_id,
                                           "detected_on": body.detected_on.isoformat(),
                                           "last_known_good": body.last_known_good.isoformat() if body.last_known_good else None,
                                           "affected_work_references": body.affected_work_references,
                                           "evidence_record_ids": body.evidence_record_ids},
                           })
    updated = _change(db, ctx, asset, request, "equipment_out_of_tolerance",
                      {"latest_out_of_tolerance_id": str(event["id"])}, status="QUARANTINED")
    return {"asset": updated, "event": event}


@router.post("/assets/{asset_id}/out-of-tolerance/disposition")
def disposition_oot(
    asset_id: str, body: OotDisposition, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.equipment.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    asset = _asset(db, ctx, asset_id, lock=True)
    _version(asset, body.expected_version)
    event = next((event for event in _children(db, ctx, _OOT, asset_id)
                  if str(event["id"]) == body.event_id), None)
    if not event or event["status"] != "OPEN":
        raise HTTPException(409, "Out-of-tolerance event does not await disposition.")
    if str(event["created_by"]) == str(ctx.user_id):
        raise HTTPException(403, "Independent assessment is required to dispose of out-of-tolerance impact.")
    require_evidence_records(db, ctx.amo_id, body.evidence_record_ids, required=True)
    data = dict(event.get("payload") or {})
    data.update({"disposition": body.disposition, "impact_assessment": body.impact_assessment,
                 "affected_work_references": body.affected_work_references,
                 "disposition_evidence_ids": body.evidence_record_ids,
                 "disposed_by": ctx.user_id, "disposed_at": _now()})
    db.execute(text(
        f"UPDATE {_OOT} SET status='DISPOSITION_RECORDED', payload=CAST(:payload AS jsonb), "
        "updated_at=now(), updated_by=:actor WHERE id=:id AND amo_id=:amo_id"
    ), {"id": event["id"], "amo_id": ctx.amo_id, "actor": ctx.user_id, "payload": json.dumps(data)})
    updated = _change(db, ctx, asset, request, "out_of_tolerance_disposition_recorded",
                      {"latest_disposition_id": str(event["id"])}, status="QUARANTINED")
    return {"asset": updated}


@router.post("/assets/{asset_id}/return-to-service")
def release_equipment(
    asset_id: str, body: ReturnToService, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.equipment.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    asset = _asset(db, ctx, asset_id, lock=True)
    _version(asset, body.expected_version)
    if asset["status"] != "QUARANTINED":
        raise HTTPException(409, "Only quarantined equipment can be independently released.")
    events = _children(db, ctx, _OOT, asset_id)
    if any(item["status"] == "OPEN" for item in events):
        raise HTTPException(409, "Undisposed out-of-tolerance events prevent release.")
    last_cal = (asset.get("payload") or {}).get("verified_calibration_id")
    if not last_cal or not asset.get("due_date") or asset["due_date"] < date.today():
        raise HTTPException(409, "A current independently verified in-tolerance calibration is required.")
    recent = next((cal for cal in _children(db, ctx, _CAL, asset_id)
                   if str(cal["id"]) == str(last_cal) and cal["status"] == "VERIFIED"), None)
    if not recent:
        raise HTTPException(409, "The referenced verified calibration was not found in this tenant.")
    calibration_date = date.fromisoformat(recent["payload"]["calibration_date"])
    for event in events:
        if event["status"] != "DISPOSITION_RECORDED" and event["status"] != "CLOSED":
            raise HTTPException(409, "Every out-of-tolerance event must have an independent disposition.")
        detected_on = date.fromisoformat(event["payload"]["detected_on"])
        if calibration_date < detected_on:
            raise HTTPException(409, "Fresh calibration after the out-of-tolerance event is required for release.")
    if str(asset["owner_user_id"]) == str(ctx.user_id):
        raise HTTPException(403, "Custodian cannot independently authorise release.")
    require_evidence_records(db, ctx.amo_id, body.closure_evidence_ids, required=True)
    for event in events:
        if event["status"] == "DISPOSITION_RECORDED":
            db.execute(text(
                f"UPDATE {_OOT} SET status='CLOSED', updated_at=now(), updated_by=:actor "
                "WHERE id=:id AND amo_id=:amo_id"
            ), {"id": event["id"], "amo_id": ctx.amo_id, "actor": ctx.user_id})
    updated = _change(db, ctx, asset, request, "equipment_independently_released",
                      {"release_reason": body.rationale, "release_evidence_ids": body.closure_evidence_ids,
                       "released_by": ctx.user_id, "released_at": _now()}, status="SERVICEABLE")
    return {"asset": updated}
