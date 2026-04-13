from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
import shutil

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.accounts.models import AccountRole, User
from amodb.apps.audit.models import AuditEvent
from amodb.apps.crs.models import CRS, CRSSignoff
from amodb.apps.work.models import WorkOrder

from ...database import get_db
from ...entitlements import require_module
from ...security import get_current_active_user, require_roles
from ..fleet.models import Aircraft, AircraftUsage
from . import models, schemas
from .publication_sources import get_publication_adapters

router = APIRouter(prefix="/records", tags=["technical_records"], dependencies=[Depends(require_module("work"))])

EDITOR_ROLES = {
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.PLANNING_ENGINEER,
    AccountRole.PRODUCTION_ENGINEER,
    AccountRole.CERTIFYING_ENGINEER,
    AccountRole.CERTIFYING_TECHNICIAN,
}
PLANNING_EDITOR_ROLES = {
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.PLANNING_ENGINEER,
}
PRODUCTION_EXECUTION_ROLES = {
    AccountRole.SUPERUSER,
    AccountRole.AMO_ADMIN,
    AccountRole.PRODUCTION_ENGINEER,
    AccountRole.CERTIFYING_ENGINEER,
    AccountRole.CERTIFYING_TECHNICIAN,
}
WATCHLIST_REVIEW_OPEN_STATUSES = ("Matched", "Under Review")
COMPLIANCE_OPEN_STATUSES = ("Under Review", "Planned", "Scheduled", "In Work", "Awaiting Certification")
COMPLIANCE_PRIORITIZED_STATUSES = ("Under Review", "Planned")



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




def _create_history(db: Session, amo_id: str, action_id: int, to_status: str, actor_id: str | None, event_type: str, from_status: str | None = None, notes: str | None = None):
    db.add(models.ComplianceActionHistory(
        amo_id=amo_id,
        compliance_action_id=action_id,
        from_status=from_status,
        to_status=to_status,
        event_type=event_type,
        event_notes=notes,
        actor_user_id=actor_id,
    ))


def _matches_watchlist(publication: dict, criteria: dict) -> bool:
    if not criteria:
        return True
    for key in ("authority", "document_type", "ata_chapter"):
        allowed = criteria.get(key)
        if allowed and str(publication.get(key, "")).lower() not in {str(v).lower() for v in allowed}:
            return False
    kws = [str(v).lower() for v in criteria.get("keywords", []) if str(v).strip()]
    if kws:
        source_text = f"{publication.get('title','')} {publication.get('doc_number','')}".lower()
        if not any(k in source_text for k in kws):
            return False
    return True



def _exec_evidence_dir(amo_id: str) -> Path:
    root = Path(__file__).resolve().parents[2] / "generated" / "technical_records" / "execution_evidence" / amo_id
    root.mkdir(parents=True, exist_ok=True)
    return root

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
    due_soon = db.query(models.AirworthinessItem).filter(
        models.AirworthinessItem.amo_id == amo_id,
        models.AirworthinessItem.next_due_date <= date.today() + timedelta(days=14),
    ).count()
    work_orders_missing_crs = (
        db.query(WorkOrder)
        .outerjoin(CRS, CRS.work_order_id == WorkOrder.id)
        .filter(
            WorkOrder.amo_id == amo_id,
            WorkOrder.status.in_(["INSPECTED", "CLOSED"]),
            CRS.id.is_(None),
        )
        .count()
    )
    crs_missing_signoff = (
        db.query(CRS)
        .join(WorkOrder, CRS.work_order_id == WorkOrder.id)
        .outerjoin(CRSSignoff, CRSSignoff.crs_id == CRS.id)
        .filter(WorkOrder.amo_id == amo_id, CRSSignoff.id.is_(None))
        .count()
    )
    unmatched_crs = work_orders_missing_crs + crs_missing_signoff
    deferrals_expiring = db.query(models.Deferral).filter(models.Deferral.amo_id == amo_id, models.Deferral.status == "Open", models.Deferral.expiry_at <= now + timedelta(days=7)).count()
    open_exceptions = db.query(models.ExceptionQueueItem).filter(models.ExceptionQueueItem.amo_id == amo_id, models.ExceptionQueueItem.status == "Open").count()
    recently_closed = db.query(models.MaintenanceRecord).filter(models.MaintenanceRecord.amo_id == amo_id, models.MaintenanceRecord.performed_at >= now - timedelta(days=30)).count()
    return schemas.TechnicalDashboardRead(tiles=[
        schemas.TechnicalDashboardTile(key="compliance_due", label="Overdue / Due soon compliance items", count=due_soon),
        schemas.TechnicalDashboardTile(key="unmatched_crs", label="Work orders pending CRS / sign-off reconciliation", count=unmatched_crs),
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

    crs_rows = db.query(CRS).join(WorkOrder, CRS.work_order_id == WorkOrder.id).filter(WorkOrder.amo_id == amo_id)
    if work_order_id:
        crs_rows = crs_rows.filter(CRS.work_order_id == work_order_id)
    if tail_id:
        crs_rows = crs_rows.filter(CRS.aircraft_serial_number == tail_id)
    if start_date:
        crs_rows = crs_rows.filter(CRS.crs_issue_date >= start_date)
    if end_date:
        crs_rows = crs_rows.filter(CRS.crs_issue_date <= end_date)

    return {
        "work_orders": [{"id": wo.id, "wo_number": wo.wo_number, "tail_id": wo.aircraft_serial_number, "status": str(wo.status)} for wo in work_orders],
        "crs": [{"id": c.id, "crs_number": c.crs_serial, "work_order_id": c.work_order_id, "tail_id": c.aircraft_serial_number, "issue_date": c.crs_issue_date.isoformat() if c.crs_issue_date else None} for c in crs_rows.limit(100).all()],
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


@router.get("/planning/dashboard", response_model=schemas.PlanningDashboardRead)
def planning_dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    amo_id = current_user.effective_amo_id
    today = date.today()
    horizon = today + timedelta(days=14)
    summary = {
        "due_soon": db.query(models.AirworthinessItem).filter(models.AirworthinessItem.amo_id == amo_id, models.AirworthinessItem.next_due_date.isnot(None), models.AirworthinessItem.next_due_date <= horizon).count(),
        "overdue": db.query(models.AirworthinessItem).filter(models.AirworthinessItem.amo_id == amo_id, models.AirworthinessItem.next_due_date.isnot(None), models.AirworthinessItem.next_due_date < today).count(),
        "open_deferrals": db.query(models.Deferral).filter_by(amo_id=amo_id, status="Open").count(),
        "open_watchlist_reviews": db.query(models.AirworthinessPublicationMatch).filter(models.AirworthinessPublicationMatch.amo_id == amo_id, models.AirworthinessPublicationMatch.review_status.in_(WATCHLIST_REVIEW_OPEN_STATUSES)).count(),
        "open_compliance_actions": db.query(models.ComplianceAction).filter(models.ComplianceAction.amo_id == amo_id, models.ComplianceAction.status.in_(COMPLIANCE_OPEN_STATUSES)).count(),
    }
    priority_items = []
    for d in db.query(models.Deferral).filter_by(amo_id=amo_id, status="Open").order_by(models.Deferral.expiry_at.asc()).limit(5).all():
        priority_items.append({"type": "Deferral", "ref": d.defect_ref, "tail": d.tail_id, "due": d.expiry_at.isoformat(), "status": d.status})
    for a in db.query(models.ComplianceAction).filter(models.ComplianceAction.amo_id == amo_id, models.ComplianceAction.status.in_(COMPLIANCE_PRIORITIZED_STATUSES)).order_by(models.ComplianceAction.created_at.desc()).limit(5).all():
        priority_items.append({"type": "Compliance", "ref": f"CA-{a.id}", "due": a.due_date.isoformat() if a.due_date else None, "status": a.status})
    return schemas.PlanningDashboardRead(summary=summary, priority_items=priority_items)


@router.get("/production/dashboard", response_model=schemas.ProductionDashboardRead)
def production_dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    amo_id = current_user.effective_amo_id
    active = db.query(WorkOrder).filter(WorkOrder.amo_id == amo_id, WorkOrder.status.in_(["RELEASED", "IN_PROGRESS", "INSPECTED"])).count()
    overdue = db.query(WorkOrder).filter(WorkOrder.amo_id == amo_id, WorkOrder.due_date.isnot(None), WorkOrder.due_date < date.today(), WorkOrder.status.notin_(["CLOSED", "ARCHIVED", "CANCELLED"])).count()
    awaiting_cert = db.query(models.ComplianceAction).filter(models.ComplianceAction.amo_id == amo_id, models.ComplianceAction.status == "Awaiting Certification").count()
    summary = {"active_work_orders": active, "overdue_tasks": overdue, "awaiting_certification": awaiting_cert}
    bottlenecks = [
        {"name": "Awaiting certification", "count": awaiting_cert, "route": "/production/compliance-items"},
        {"name": "Overdue work orders", "count": overdue, "route": "/production/work-order-execution"},
    ]
    return schemas.ProductionDashboardRead(summary=summary, bottlenecks=bottlenecks)


@router.get("/watchlists", response_model=list[schemas.WatchlistRead])
def list_watchlists(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    return db.query(models.AirworthinessWatchlist).filter_by(amo_id=current_user.effective_amo_id).order_by(models.AirworthinessWatchlist.updated_at.desc()).all()


@router.post("/watchlists", response_model=schemas.WatchlistRead)
def create_watchlist(payload: schemas.WatchlistCreate, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*PLANNING_EDITOR_ROLES))):
    row = models.AirworthinessWatchlist(amo_id=current_user.effective_amo_id, created_by_user_id=current_user.id, **payload.model_dump())
    db.add(row)
    db.flush()
    _audit(db, current_user.effective_amo_id, current_user.id, "AirworthinessWatchlist", str(row.id), "CREATE", payload.model_dump())
    db.commit()
    db.refresh(row)
    return row


@router.post("/watchlists/{watchlist_id}/run", response_model=schemas.WatchlistRunResult)
def run_watchlist(watchlist_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*PLANNING_EDITOR_ROLES))):
    amo_id = current_user.effective_amo_id
    watchlist = db.query(models.AirworthinessWatchlist).filter_by(amo_id=amo_id, id=watchlist_id).first()
    if not watchlist:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    publications_ingested = 0
    source_publications = []
    for adapter in get_publication_adapters():
        source_publications.extend(adapter.fetch(watchlist.criteria_json or {}))
    for pub in source_publications:
        if not _matches_watchlist(pub, watchlist.criteria_json or {}):
            continue
        existing = db.query(models.AirworthinessPublication).filter_by(amo_id=amo_id, source=pub["source"], doc_number=pub["doc_number"]).first()
        if not existing:
            existing = models.AirworthinessPublication(amo_id=amo_id, raw_metadata_json={}, source_link=None, published_date=pub.get("published_date") or date.today(), **{k: v for k, v in pub.items() if k != "published_date"})
            db.add(existing)
            db.flush()
            publications_ingested += 1
        if db.query(models.AirworthinessPublicationMatch).filter_by(amo_id=amo_id, watchlist_id=watchlist.id, publication_id=existing.id).first():
            continue
        match = models.AirworthinessPublicationMatch(
            amo_id=amo_id,
            watchlist_id=watchlist.id,
            publication_id=existing.id,
            classification="Potentially Applicable",
            review_status="Matched",
            matched_fleet_json=[a.serial_number for a in db.query(Aircraft).filter(Aircraft.amo_id == amo_id).limit(5).all()],
        )
        db.add(match)

    watchlist.run_count += 1
    watchlist.last_run_at = datetime.now(UTC)
    watchlist.next_run_at = datetime.now(UTC) + timedelta(days=1)
    db.flush()
    matches_created = db.query(models.AirworthinessPublicationMatch).filter_by(amo_id=amo_id, watchlist_id=watchlist.id).count()
    _audit(db, amo_id, current_user.id, "AirworthinessWatchlist", str(watchlist.id), "RUN", {"matches": matches_created})
    db.commit()
    return schemas.WatchlistRunResult(watchlist_id=watchlist.id, publications_ingested=publications_ingested, matches_created=matches_created)


@router.get("/publications/review", response_model=list[schemas.PublicationReviewRead])
def publication_review_queue(status_filter: str | None = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    amo_id = current_user.effective_amo_id
    q = db.query(models.AirworthinessPublicationMatch, models.AirworthinessPublication).join(
        models.AirworthinessPublication, models.AirworthinessPublication.id == models.AirworthinessPublicationMatch.publication_id
    ).filter(models.AirworthinessPublicationMatch.amo_id == amo_id)
    if status_filter:
        q = q.filter(models.AirworthinessPublicationMatch.review_status == status_filter)
    rows = q.order_by(models.AirworthinessPublicationMatch.created_at.desc()).all()
    out = []
    for match, publication in rows:
        out.append(schemas.PublicationReviewRead(
            match_id=match.id, watchlist_id=match.watchlist_id, publication_id=publication.id, authority=publication.authority, source=publication.source,
            document_type=publication.document_type, doc_number=publication.doc_number, title=publication.title, effectivity_summary=publication.effectivity_summary,
            classification=match.classification, review_status=match.review_status, matched_fleet=match.matched_fleet_json or [], ageing_days=max(0, (date.today() - match.created_at.date()).days),
            assigned_reviewer_user_id=match.assigned_reviewer_user_id, published_date=publication.published_date
        ))
    return out


@router.post("/publications/review/{match_id}/decision", response_model=schemas.PublicationReviewRead)
def decide_publication_review(match_id: int, payload: schemas.PublicationReviewDecisionRequest, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*PLANNING_EDITOR_ROLES))):
    amo_id = current_user.effective_amo_id
    row = db.query(models.AirworthinessPublicationMatch).filter_by(amo_id=amo_id, id=match_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Match not found")
    pub = db.query(models.AirworthinessPublication).filter_by(amo_id=amo_id, id=row.publication_id).first()
    row.review_status = payload.review_status
    row.classification = payload.classification
    row.assigned_reviewer_user_id = payload.assigned_reviewer_user_id or current_user.id
    row.reviewed_at = datetime.now(UTC)
    _audit(db, amo_id, current_user.id, "PublicationMatch", str(row.id), "REVIEW", payload.model_dump())
    db.commit()
    return schemas.PublicationReviewRead(
        match_id=row.id, watchlist_id=row.watchlist_id, publication_id=pub.id, authority=pub.authority, source=pub.source, document_type=pub.document_type,
        doc_number=pub.doc_number, title=pub.title, effectivity_summary=pub.effectivity_summary, classification=row.classification, review_status=row.review_status,
        matched_fleet=row.matched_fleet_json or [], ageing_days=max(0, (date.today() - row.created_at.date()).days), assigned_reviewer_user_id=row.assigned_reviewer_user_id, published_date=pub.published_date
    )


@router.get("/compliance-actions", response_model=list[schemas.ComplianceActionRead])
def list_compliance_actions(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    return db.query(models.ComplianceAction).filter_by(amo_id=current_user.effective_amo_id).order_by(models.ComplianceAction.updated_at.desc()).all()


@router.post("/compliance-actions", response_model=schemas.ComplianceActionRead)
def create_compliance_action(payload: schemas.ComplianceActionCreate, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*PLANNING_EDITOR_ROLES))):
    amo_id = current_user.effective_amo_id
    match = db.query(models.AirworthinessPublicationMatch).filter_by(amo_id=amo_id, id=payload.publication_match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Publication match not found")
    row = models.ComplianceAction(amo_id=amo_id, created_by_user_id=current_user.id, **payload.model_dump())
    db.add(row)
    db.flush()
    _create_history(db, amo_id, row.id, row.status, current_user.id, "CREATE")
    if match.review_status == "Matched":
        match.review_status = "Under Review"
    _audit(db, amo_id, current_user.id, "ComplianceAction", str(row.id), "CREATE", payload.model_dump())
    db.commit()
    db.refresh(row)
    return row


@router.post("/compliance-actions/{action_id}/status", response_model=schemas.ComplianceActionRead)
def update_compliance_action_status(action_id: int, payload: schemas.ComplianceActionStatusUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*PLANNING_EDITOR_ROLES, *PRODUCTION_EXECUTION_ROLES))):
    amo_id = current_user.effective_amo_id
    row = db.query(models.ComplianceAction).filter_by(amo_id=amo_id, id=action_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Compliance action not found")
    previous = row.status
    row.status = payload.status
    _create_history(db, amo_id, row.id, payload.status, current_user.id, "STATUS_CHANGE", previous, payload.event_notes)
    _audit(db, amo_id, current_user.id, "ComplianceAction", str(row.id), "STATUS_CHANGE", payload.model_dump())
    db.commit()
    db.refresh(row)
    return row


@router.get("/production/evidence", response_model=list[schemas.ProductionExecutionEvidenceRead])
def list_execution_evidence(work_order_id: int | None = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    q = db.query(models.ProductionExecutionEvidence).filter(models.ProductionExecutionEvidence.amo_id == current_user.effective_amo_id)
    if work_order_id:
        q = q.filter(models.ProductionExecutionEvidence.work_order_id == work_order_id)
    return q.order_by(models.ProductionExecutionEvidence.created_at.desc()).all()


@router.post("/production/evidence/upload", response_model=schemas.ProductionExecutionEvidenceRead)
async def upload_execution_evidence(
    work_order_id: int = Form(...),
    task_card_id: int | None = Form(None),
    notes: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*PRODUCTION_EXECUTION_ROLES)),
):
    wo = db.query(WorkOrder).filter(WorkOrder.amo_id == current_user.effective_amo_id, WorkOrder.id == work_order_id).first()
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")

    target_dir = _exec_evidence_dir(current_user.effective_amo_id)
    safe_name = f"{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{Path(file.filename or 'evidence.bin').name}"
    path = target_dir / safe_name
    with path.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    row = models.ProductionExecutionEvidence(
        amo_id=current_user.effective_amo_id,
        work_order_id=work_order_id,
        task_card_id=task_card_id,
        file_name=file.filename or safe_name,
        storage_path=str(path),
        content_type=file.content_type,
        notes=notes,
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.flush()
    _audit(db, current_user.effective_amo_id, current_user.id, "ProductionExecutionEvidence", str(row.id), "UPLOAD", {"work_order_id": work_order_id, "task_card_id": task_card_id})
    db.commit()
    db.refresh(row)
    return row


@router.get("/production/release-gates", response_model=list[schemas.ProductionReleaseGateRead])
def list_release_gates(status_filter: str | None = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    q = db.query(models.ProductionReleaseGate).filter(models.ProductionReleaseGate.amo_id == current_user.effective_amo_id)
    if status_filter:
        q = q.filter(models.ProductionReleaseGate.status == status_filter)
    return q.order_by(models.ProductionReleaseGate.updated_at.desc()).all()


@router.post("/production/release-gates", response_model=schemas.ProductionReleaseGateRead)
def upsert_release_gate(payload: schemas.ProductionReleaseGateUpsert, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*PRODUCTION_EXECUTION_ROLES))):
    amo_id = current_user.effective_amo_id
    wo = db.query(WorkOrder).filter(WorkOrder.amo_id == amo_id, WorkOrder.id == payload.work_order_id).first()
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")

    row = db.query(models.ProductionReleaseGate).filter_by(amo_id=amo_id, work_order_id=payload.work_order_id).first()
    if not row:
        row = models.ProductionReleaseGate(amo_id=amo_id, work_order_id=payload.work_order_id)
        db.add(row)
        db.flush()

    row.status = payload.status
    row.readiness_notes = payload.readiness_notes
    row.blockers_json = payload.blockers_json
    row.handed_to_records = payload.handed_to_records
    if payload.handed_to_records:
        row.handed_to_records_at = datetime.now(UTC)
    row.evidence_count = db.query(models.ProductionExecutionEvidence).filter(models.ProductionExecutionEvidence.amo_id == amo_id, models.ProductionExecutionEvidence.work_order_id == payload.work_order_id).count()
    if payload.sign_off:
        row.signed_off_by_user_id = current_user.id
        row.signed_off_at = datetime.now(UTC)

    if row.handed_to_records:
        record = db.query(models.MaintenanceRecord).filter(models.MaintenanceRecord.amo_id == amo_id, models.MaintenanceRecord.linked_wo_id == payload.work_order_id).first()
        if not record:
            db.add(models.MaintenanceRecord(
                amo_id=amo_id,
                tail_id=wo.aircraft_serial_number,
                performed_at=datetime.now(UTC),
                description=f"Release preparation handoff for WO {wo.wo_number}",
                reference_data_text="Release prep gate",
                certifying_user_id=current_user.id,
                outcome="Ready for records reconciliation",
                linked_wo_id=wo.id,
                linked_wp_id=wo.work_package_ref,
                evidence_asset_ids=[str(e.id) for e in db.query(models.ProductionExecutionEvidence).filter(models.ProductionExecutionEvidence.amo_id == amo_id, models.ProductionExecutionEvidence.work_order_id == wo.id).all()],
            ))

    _audit(db, amo_id, current_user.id, "ProductionReleaseGate", str(row.id), "UPSERT", payload.model_dump())
    db.commit()
    db.refresh(row)
    return row
