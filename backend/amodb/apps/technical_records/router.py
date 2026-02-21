from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import AccountRole, User
from amodb.apps.audit.models import AuditEvent
from amodb.apps.crs.models import CRS
from amodb.apps.work.models import WorkOrder

from ...database import get_db
from ...entitlements import require_module
from ...security import get_current_active_user, require_roles
from ..fleet.models import Aircraft, AircraftUsage
from . import models, schemas

router = APIRouter(prefix="/records", tags=["technical_records"], dependencies=[Depends(require_module("work"))])

EDITOR_ROLES = {
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.PLANNING_ENGINEER,
    AccountRole.PRODUCTION_ENGINEER,
    AccountRole.CERTIFYING_ENGINEER,
    AccountRole.CERTIFYING_TECHNICIAN,
}


def _audit(db: Session, amo_id: str, actor_id: str | None, entity_type: str, entity_id: str, action: str, after: dict | None = None):
    db.add(
        AuditEvent(
            amo_id=amo_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_user_id=actor_id,
            after=after,
        )
    )


def _get_settings(db: Session, amo_id: str) -> models.TechnicalRecordSetting:
    settings = db.query(models.TechnicalRecordSetting).filter_by(amo_id=amo_id).first()
    if settings:
        return settings
    settings = models.TechnicalRecordSetting(amo_id=amo_id)
    db.add(settings)
    db.flush()
    return settings


@router.get("/dashboard", response_model=schemas.TechnicalDashboardRead)
def technical_records_dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    amo_id = current_user.effective_amo_id
    now = datetime.now(UTC)
    due_soon = db.query(models.AirworthinessItem).filter(models.AirworthinessItem.amo_id == amo_id, models.AirworthinessItem.next_due_date <= date.today() + timedelta(days=14)).count()
    unmatched_crs = db.query(CRS).filter(CRS.amo_id == amo_id, CRS.work_order_id.is_(None)).count()
    deferrals_expiring = db.query(models.Deferral).filter(models.Deferral.amo_id == amo_id, models.Deferral.status == "Open", models.Deferral.expiry_at <= now + timedelta(days=7)).count()
    open_exceptions = db.query(models.ExceptionQueueItem).filter(models.ExceptionQueueItem.amo_id == amo_id, models.ExceptionQueueItem.status == "Open").count()
    recently_closed = db.query(models.MaintenanceRecord).filter(models.MaintenanceRecord.amo_id == amo_id, models.MaintenanceRecord.performed_at >= now - timedelta(days=30)).count()
    return schemas.TechnicalDashboardRead(tiles=[
        schemas.TechnicalDashboardTile(key="compliance_due", label="Overdue / Due soon compliance items", count=due_soon),
        schemas.TechnicalDashboardTile(key="unmatched_crs", label="Missing or unmatched CRS/sign-offs", count=unmatched_crs),
        schemas.TechnicalDashboardTile(key="deferred_expiry", label="Open deferred defects nearing expiry", count=deferrals_expiring),
        schemas.TechnicalDashboardTile(key="data_quality", label="Data quality exceptions", count=open_exceptions),
        schemas.TechnicalDashboardTile(key="recent_close", label="Recently closed maintenance events", count=recently_closed),
    ])


@router.get("/aircraft")
def aircraft_record_list(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    amo_id = current_user.effective_amo_id
    aircraft = db.query(Aircraft).filter(Aircraft.amo_id == amo_id).all()
    payload = []
    for item in aircraft:
        latest_usage = db.query(AircraftUsage).filter(AircraftUsage.amo_id == amo_id, AircraftUsage.aircraft_serial_number == item.serial_number).order_by(AircraftUsage.date.desc()).first()
        has_open_exception = db.query(models.ExceptionQueueItem).filter(models.ExceptionQueueItem.amo_id == amo_id, models.ExceptionQueueItem.object_type == "Aircraft", models.ExceptionQueueItem.object_id == item.serial_number, models.ExceptionQueueItem.status == "Open").first() is not None
        payload.append({
            "tail": item.registration,
            "tail_id": item.serial_number,
            "type": item.model,
            "operator": item.operator,
            "status": item.status,
            "current_hours": latest_usage.ttaf_after if latest_usage else None,
            "current_cycles": latest_usage.tca_after if latest_usage else None,
            "last_update_date": latest_usage.date.isoformat() if latest_usage else None,
            "record_health": "Attention" if has_open_exception else "OK",
        })
    return payload


@router.get("/aircraft/{tail_id}/utilisation", response_model=list[schemas.AircraftUtilisationRead])
def list_utilisation(tail_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    return db.query(models.AircraftUtilisation).filter_by(amo_id=current_user.effective_amo_id, tail_id=tail_id).order_by(models.AircraftUtilisation.entry_date.desc()).all()


@router.post("/aircraft/{tail_id}/utilisation", response_model=schemas.AircraftUtilisationRead)
def create_utilisation(tail_id: str, payload: schemas.AircraftUtilisationCreate, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*EDITOR_ROLES))):
    if payload.tail_id != tail_id:
        raise HTTPException(status_code=400, detail="tail mismatch")
    if payload.entry_date > date.today():
        raise HTTPException(status_code=400, detail="future dates are not allowed")

    amo_id = current_user.effective_amo_id
    conflict = db.query(models.AircraftUtilisation).filter_by(amo_id=amo_id, tail_id=tail_id, entry_date=payload.entry_date).first()
    has_conflict = conflict is not None
    if has_conflict and not payload.correction_reason:
        raise HTTPException(status_code=400, detail="correction_reason required for conflicting utilisation")

    row = models.AircraftUtilisation(
        amo_id=amo_id,
        tail_id=tail_id,
        entry_date=payload.entry_date,
        hours=payload.hours,
        cycles=payload.cycles,
        source=payload.source,
        conflict_flag=has_conflict,
        correction_reason=payload.correction_reason,
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.flush()

    if has_conflict:
        db.add(models.ExceptionQueueItem(
            amo_id=amo_id,
            ex_type="UtilisationConflict",
            object_type="Aircraft",
            object_id=tail_id,
            summary=f"Duplicate utilisation posting for {payload.entry_date.isoformat()}",
            created_by_user_id=current_user.id,
        ))

    _audit(db, amo_id, current_user.id, "TechnicalUtilisation", str(row.id), "CREATE", {"tail_id": tail_id, "conflict": has_conflict})
    db.commit()
    db.refresh(row)
    return row


@router.get("/deferrals", response_model=list[schemas.DeferralRead])
def list_deferrals(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    return db.query(models.Deferral).filter_by(amo_id=current_user.effective_amo_id).order_by(models.Deferral.expiry_at.asc()).all()


@router.get("/deferrals/{deferral_id}", response_model=schemas.DeferralRead)
def get_deferral(deferral_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    item = db.query(models.Deferral).filter_by(amo_id=current_user.effective_amo_id, id=deferral_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Deferral not found")
    return item


@router.get("/maintenance-records", response_model=list[schemas.MaintenanceRecordRead])
def list_maintenance_records(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    return db.query(models.MaintenanceRecord).filter_by(amo_id=current_user.effective_amo_id).order_by(models.MaintenanceRecord.performed_at.desc()).all()


@router.post("/maintenance-records", response_model=schemas.MaintenanceRecordRead, status_code=status.HTTP_201_CREATED)
def create_maintenance_record(payload: schemas.MaintenanceRecordCreate, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*EDITOR_ROLES))):
    amo_id = current_user.effective_amo_id
    settings = _get_settings(db, amo_id)
    if not settings.allow_manual_maintenance_records and payload.linked_wo_id is None:
        raise HTTPException(status_code=400, detail="manual maintenance record creation disabled")
    item = models.MaintenanceRecord(amo_id=amo_id, **payload.model_dump())
    db.add(item)
    db.flush()
    _audit(db, amo_id, current_user.id, "MaintenanceRecord", str(item.id), "CREATE", payload.model_dump())
    db.commit()
    db.refresh(item)
    return item


@router.get("/maintenance-records/{record_id}", response_model=schemas.MaintenanceRecordRead)
def get_maintenance_record(record_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    item = db.query(models.MaintenanceRecord).filter_by(amo_id=current_user.effective_amo_id, id=record_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Maintenance record not found")
    return item


@router.get("/airworthiness/{item_type}", response_model=list[schemas.AirworthinessItemRead])
def list_airworthiness_items(item_type: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    item_type = item_type.upper()
    if item_type not in {"AD", "SB"}:
        raise HTTPException(status_code=400, detail="item_type must be AD or SB")
    return db.query(models.AirworthinessItem).filter_by(amo_id=current_user.effective_amo_id, item_type=item_type).order_by(models.AirworthinessItem.reference.asc()).all()


@router.post("/airworthiness/{item_type}", response_model=schemas.AirworthinessItemRead)
def create_airworthiness_item(item_type: str, payload: schemas.AirworthinessItemCreate, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*EDITOR_ROLES))):
    item_type = item_type.upper()
    row = models.AirworthinessItem(amo_id=current_user.effective_amo_id, item_type=item_type, **payload.model_dump(exclude={"item_type"}))
    db.add(row)
    db.flush()
    _audit(db, current_user.effective_amo_id, current_user.id, "AirworthinessItem", str(row.id), "CREATE", payload.model_dump())
    db.commit()
    db.refresh(row)
    return row


@router.get("/reconciliation", response_model=list[schemas.ExceptionQueueItemRead])
def list_reconciliation(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    return db.query(models.ExceptionQueueItem).filter_by(amo_id=current_user.effective_amo_id).order_by(models.ExceptionQueueItem.created_at.desc()).all()


@router.post("/reconciliation/{item_id}/resolve", response_model=schemas.ExceptionQueueItemRead)
def resolve_exception(item_id: int, payload: schemas.ExceptionResolveRequest, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*EDITOR_ROLES))):
    item = db.query(models.ExceptionQueueItem).filter_by(amo_id=current_user.effective_amo_id, id=item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Exception item not found")
    item.status = "Resolved"
    item.resolution_notes = payload.resolution_notes
    item.resolved_at = datetime.now(UTC)
    item.resolved_by_user_id = current_user.id
    _audit(db, current_user.effective_amo_id, current_user.id, "ExceptionQueueItem", str(item.id), "RESOLVE", {"resolution_notes": payload.resolution_notes})
    db.commit()
    db.refresh(item)
    return item


@router.get("/settings", response_model=schemas.TechnicalRecordSettingsRead)
def get_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    return _get_settings(db, current_user.effective_amo_id)


@router.put("/settings", response_model=schemas.TechnicalRecordSettingsRead)
def update_settings(payload: schemas.TechnicalRecordSettingsUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_roles(AccountRole.SUPERUSER, AccountRole.AMO_ADMIN))):
    row = _get_settings(db, current_user.effective_amo_id)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    _audit(db, current_user.effective_amo_id, current_user.id, "TechnicalRecordSetting", str(row.id), "UPDATE", payload.model_dump())
    db.commit()
    db.refresh(row)
    return row


@router.get("/traceability")
def traceability(
    tail_id: str | None = None,
    work_order_id: int | None = None,
    record_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    amo_id = current_user.effective_amo_id
    q = db.query(WorkOrder).filter(WorkOrder.amo_id == amo_id)
    if work_order_id:
        q = q.filter(WorkOrder.id == work_order_id)
    if tail_id:
        q = q.filter(WorkOrder.aircraft_serial_number == tail_id)
    if start_date:
        q = q.filter(WorkOrder.open_date >= start_date)
    if end_date:
        q = q.filter(WorkOrder.open_date <= end_date)
    work_orders = q.limit(50).all()

    records = db.query(models.MaintenanceRecord).filter(models.MaintenanceRecord.amo_id == amo_id)
    if record_id:
        records = records.filter(models.MaintenanceRecord.id == record_id)
    if tail_id:
        records = records.filter(models.MaintenanceRecord.tail_id == tail_id)
    records_data = records.limit(50).all()

    crs_rows = db.query(CRS).filter(CRS.amo_id == amo_id)
    if work_order_id:
        crs_rows = crs_rows.filter(CRS.work_order_id == work_order_id)

    return {
        "work_orders": [{"id": wo.id, "wo_number": wo.wo_number, "tail_id": wo.aircraft_serial_number, "status": str(wo.status)} for wo in work_orders],
        "crs": [{"id": c.id, "crs_number": c.crs_number, "work_order_id": c.work_order_id} for c in crs_rows.limit(100).all()],
        "records": [{"id": r.id, "tail_id": r.tail_id, "linked_wo_id": r.linked_wo_id, "performed_at": r.performed_at.isoformat()} for r in records_data],
    }


@router.get("/packs")
def packs_preview(pack_type: str, target_id: str | None = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    settings = _get_settings(db, current_user.effective_amo_id)
    return {
        "pack_type": pack_type,
        "target_id": target_id,
        "retention_years": settings.record_retention_years,
        "mode": "pdf-index-with-links",
        "message": "Bundle generation currently returns PDF index metadata and evidence links list.",
    }
