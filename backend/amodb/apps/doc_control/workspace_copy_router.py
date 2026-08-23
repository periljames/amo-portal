from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A6
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import workspace_schemas as schemas
from .workspace_router import _copy_payload
from .workspace_service import (
    active_tenant_users,
    audit,
    get_manual,
    get_profile,
    get_revision,
    is_control_user,
    require_control_user,
    require_manual_access,
    resolve_tenant,
    status_value,
    utcnow,
)


router = APIRouter(prefix="/workspace", tags=["Document Control Controlled Copies"])

_ALLOWED_EVENTS: dict[str, set[str]] = {
    "ISSUED": {"TRANSFER", "LOCATION_CHANGE", "RECALL", "RETURN", "WITHDRAW", "DESTROY"},
    "RECALLED": {"TRANSFER", "LOCATION_CHANGE", "RETURN", "WITHDRAW", "DESTROY"},
    # A returned copy is back in circulation. It may be issued again rather than
    # becoming an artificial terminal state.
    "RETURNED": {"TRANSFER", "LOCATION_CHANGE", "WITHDRAW", "DESTROY"},
    "WITHDRAWN": {"DESTROY"},
    "DESTROYED": set(),
}


class ControlledCopyRegisterCreate(BaseModel):
    manual_id: str
    revision_id: str
    copy_number: str = Field(min_length=1, max_length=64)
    format: Literal["HARDCOPY", "OFFLINE_MEDIA"] = "HARDCOPY"
    holder_user_id: str | None = None
    location_text: str = Field(min_length=2, max_length=255)
    due_back_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class CirculationRequest(BaseModel):
    action: Literal["CHECK_OUT", "CHECK_IN", "VERIFY_LOCATION"]
    due_back_at: datetime | None = None
    holder_user_id: str | None = None
    location_text: str | None = Field(default=None, max_length=255)
    acknowledgement: bool = False
    comments: str | None = Field(default=None, max_length=2000)


def _future(value: datetime) -> bool:
    """Compare API datetimes safely whether clients send an offset or UTC-naive value."""
    now = datetime.now(value.tzinfo) if value.tzinfo is not None else datetime.utcnow()
    return value > now


def _copy(db: Session, tenant_id: str, copy_id: str) -> dm.DocumentControlledCopy:
    row = (
        db.query(dm.DocumentControlledCopy)
        .filter(
            dm.DocumentControlledCopy.tenant_id == tenant_id,
            dm.DocumentControlledCopy.id == copy_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Controlled copy not found")
    return row


def _home_location(row: dm.DocumentControlledCopy) -> str:
    metadata = dict(row.metadata_json or {})
    return str(metadata.get("home_location_text") or row.location_text or "Document Control library").strip()


def _holder_label(db: Session, row: dm.DocumentControlledCopy) -> str | None:
    if row.holder_user_id:
        user = db.query(account_models.User).filter(account_models.User.id == row.holder_user_id).first()
        if user:
            return user.full_name or user.email
    return row.holder_name


def _event_payload(row: dm.DocumentControlledCopyEvent) -> dict:
    return {
        "id": row.id,
        "event_type": row.event_type,
        "actor_user_id": row.actor_user_id,
        "from_holder_user_id": row.from_holder_user_id,
        "to_holder_user_id": row.to_holder_user_id,
        "from_location": row.from_location,
        "to_location": row.to_location,
        "reason": row.reason,
        "evidence": list(row.evidence_json or []),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _reader_event_payload(row: dm.DocumentControlledCopyEvent) -> dict:
    """Expose custody chronology to the present custodian without leaking other staff IDs."""
    return {
        "id": row.id,
        "event_type": row.event_type,
        "actor_user_id": None,
        "from_holder_user_id": None,
        "to_holder_user_id": None,
        "from_location": row.from_location,
        "to_location": row.to_location,
        "reason": row.reason,
        "evidence": [],
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _scan_payload(
    db: Session,
    *,
    tenant_slug: str,
    row: dm.DocumentControlledCopy,
    manual: manual_models.Manual,
    revision: manual_models.ManualRevision,
    current_user: account_models.User,
) -> dict:
    controller = is_control_user(current_user)
    own_copy = str(row.holder_user_id or "") == str(current_user.id)
    events = (
        db.query(dm.DocumentControlledCopyEvent)
        .filter(dm.DocumentControlledCopyEvent.controlled_copy_id == row.id)
        .order_by(dm.DocumentControlledCopyEvent.created_at.desc(), dm.DocumentControlledCopyEvent.id.desc())
        .limit(60)
        .all()
    )
    holder = _holder_label(db, row) if controller or own_copy else None
    if controller:
        event_payloads = [_event_payload(event) for event in events]
    elif own_copy:
        event_payloads = [_reader_event_payload(event) for event in events]
    else:
        event_payloads = []
    return {
        "copy": {
            "id": row.id,
            "manual_id": row.manual_id,
            "revision_id": row.revision_id,
            "copy_number": row.copy_number,
            "format": row.format,
            "holder_user_id": row.holder_user_id if controller or own_copy else None,
            "holder_name": row.holder_name if controller or own_copy else None,
            "location_text": row.location_text,
            "status": row.status,
            "issued_at": row.issued_at.isoformat() if row.issued_at else None,
            "issued_by_user_id": row.issued_by_user_id if controller else None,
            "due_back_at": row.due_back_at.isoformat() if row.due_back_at else None,
            "withdrawn_at": row.withdrawn_at.isoformat() if row.withdrawn_at else None,
            "metadata": dict(row.metadata_json or {}) if controller else {},
            "home_location_text": _home_location(row),
            "holder_display": holder,
            "holder_visible": bool(controller or own_copy),
            "overdue": bool(
                row.due_back_at
                and row.status in {"ISSUED", "RECALLED"}
                and row.due_back_at.date() < datetime.utcnow().date()
            ),
        },
        "document": {
            "id": manual.id,
            "code": manual.code,
            "title": manual.title,
            "manual_type": manual.manual_type,
            "status": manual.status,
        },
        "revision": {
            "id": revision.id,
            "issue_number": revision.issue_number,
            "revision_number": revision.rev_number,
            "status": status_value(revision),
            "effective_date": revision.effective_date.isoformat() if revision.effective_date else None,
        },
        "events": event_payloads,
        "reader_path": f"/maintenance/{tenant_slug}/publications/{manual.id}/rev/{revision.id}/read",
        "capabilities": {
            "control": controller,
            "check_out": row.status == "RETURNED" and not row.holder_user_id,
            "check_in": controller or own_copy,
            "verify_location": controller or own_copy,
            "print_label": controller,
        },
    }


def validate_copy_event(row: dm.DocumentControlledCopy, payload: schemas.ControlledCopyEventCreate) -> None:
    event_type = payload.event_type
    allowed = _ALLOWED_EVENTS.get(row.status, set())
    if event_type not in allowed:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CONTROLLED_COPY_EVENT_INVALID",
                "message": f"{event_type} is not valid while copy {row.copy_number} is {row.status}.",
                "allowed_events": sorted(allowed),
            },
        )
    reason = str(payload.reason or "").strip()
    evidence = list(payload.evidence or [])
    if event_type in {"WITHDRAW", "DESTROY"} and (not reason or not evidence):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "COPY_DISPOSITION_EVIDENCE_REQUIRED",
                "message": "Withdrawal or destruction requires a reason and retained evidence.",
            },
        )
    if event_type == "RECALL" and not reason:
        raise HTTPException(status_code=409, detail="A controlled-copy recall requires a reason")
    if event_type == "TRANSFER":
        requested_location = str(payload.to_location or "").strip()
        if not payload.to_holder_user_id and not requested_location:
            raise HTTPException(status_code=422, detail="A transfer requires a holder or controlled location")
        current_location = str(row.location_text or "").strip()
        target_holder = payload.to_holder_user_id if payload.to_holder_user_id is not None else row.holder_user_id
        target_location = requested_location or current_location
        if str(target_holder or "") == str(row.holder_user_id or "") and target_location == current_location:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CONTROLLED_COPY_NOOP",
                    "message": "A controlled-copy transfer must change the holder or controlled location.",
                },
            )
    if event_type == "LOCATION_CHANGE":
        requested_location = str(payload.to_location or "").strip()
        if not requested_location:
            raise HTTPException(status_code=422, detail="A location change requires the new controlled location")
        if requested_location == str(row.location_text or "").strip():
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CONTROLLED_COPY_NOOP",
                    "message": "A controlled-copy location change must specify a different controlled location.",
                },
            )


@router.post("/t/{tenant_slug}/controlled-copies", include_in_schema=False)
def register_controlled_copy(
    tenant_slug: str,
    payload: ControlledCopyRegisterCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    """Register a physical copy either on its shelf or directly with a custodian."""
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, payload.manual_id)
    revision = get_revision(db, manual, payload.revision_id)
    if status_value(revision) != "PUBLISHED":
        raise HTTPException(status_code=409, detail="Only a published revision can be registered as a controlled copy")
    holder = None
    if payload.holder_user_id:
        holder = active_tenant_users(db, tenant, [payload.holder_user_id])[0]
    location = payload.location_text.strip()
    metadata = {**dict(payload.metadata), "home_location_text": location}
    row = dm.DocumentControlledCopy(
        tenant_id=tenant.amo_id,
        manual_id=manual.id,
        revision_id=revision.id,
        copy_number=payload.copy_number.strip(),
        format=payload.format,
        holder_user_id=holder.id if holder else None,
        holder_name=holder.full_name if holder else None,
        location_text=location,
        status="ISSUED" if holder else "RETURNED",
        issued_by_user_id=current_user.id,
        due_back_at=payload.due_back_at if holder else None,
        metadata_json=metadata,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Controlled copy number already exists for the document") from exc
    db.add(dm.DocumentControlledCopyEvent(
        tenant_id=tenant.amo_id,
        controlled_copy_id=row.id,
        event_type="ISSUE" if holder else "REGISTER",
        actor_user_id=current_user.id,
        to_holder_user_id=row.holder_user_id,
        to_location=row.location_text,
        reason="Registered physical controlled copy",
    ))
    audit(db, tenant, request, "document.copy.registered", "document_controlled_copy", row.id, _copy_payload(row))
    db.commit()
    return _copy_payload(row)


@router.post("/t/{tenant_slug}/controlled-copies/{copy_id}/events", include_in_schema=False)
def create_guarded_copy_event(
    tenant_slug: str,
    copy_id: str,
    payload: schemas.ControlledCopyEventCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = _copy(db, tenant.amo_id, copy_id)
    validate_copy_event(row, payload)
    if payload.to_holder_user_id:
        active_tenant_users(db, tenant, [payload.to_holder_user_id])

    before_holder = row.holder_user_id
    before_location = row.location_text
    event = dm.DocumentControlledCopyEvent(
        tenant_id=tenant.amo_id,
        controlled_copy_id=row.id,
        event_type=payload.event_type,
        actor_user_id=current_user.id,
        from_holder_user_id=before_holder,
        to_holder_user_id=payload.to_holder_user_id,
        from_location=before_location,
        to_location=payload.to_location,
        reason=payload.reason,
        evidence_json=list(payload.evidence),
    )
    db.add(event)
    if payload.event_type == "TRANSFER":
        if payload.to_holder_user_id:
            row.holder_user_id = payload.to_holder_user_id
            row.holder_name = None
            row.status = "ISSUED"
        if payload.to_location:
            row.location_text = payload.to_location.strip()
    elif payload.event_type == "LOCATION_CHANGE":
        row.location_text = str(payload.to_location or "").strip()
    elif payload.event_type == "RECALL":
        row.status = "RECALLED"
    elif payload.event_type == "RETURN":
        row.status = "RETURNED"
        row.holder_user_id = None
        row.holder_name = None
        row.due_back_at = None
        row.location_text = str(payload.to_location or _home_location(row)).strip()
        event.to_holder_user_id = None
        event.to_location = row.location_text
    elif payload.event_type in {"WITHDRAW", "DESTROY"}:
        row.status = "WITHDRAWN" if payload.event_type == "WITHDRAW" else "DESTROYED"
        row.withdrawn_at = utcnow()
    audit(db, tenant, request, f"document.copy.{payload.event_type.lower()}", "document_controlled_copy", row.id, _copy_payload(row))
    db.commit()
    return _copy_payload(row)


@router.get("/t/{tenant_slug}/physical-copies")
def physical_copy_register(
    tenant_slug: str,
    q: str | None = Query(default=None, max_length=255),
    status: str | None = Query(default=None, max_length=32),
    custody: Literal["ON_SHELF", "CHECKED_OUT", "RECALLED"] | None = None,
    overdue: bool = False,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = (
        db.query(dm.DocumentControlledCopy, manual_models.Manual, manual_models.ManualRevision)
        .join(manual_models.Manual, manual_models.Manual.id == dm.DocumentControlledCopy.manual_id)
        .join(manual_models.ManualRevision, manual_models.ManualRevision.id == dm.DocumentControlledCopy.revision_id)
        .filter(
            dm.DocumentControlledCopy.tenant_id == tenant.amo_id,
            manual_models.Manual.tenant_id == tenant.id,
        )
    )
    if q and q.strip():
        needle = f"%{q.strip()}%"
        query = query.filter(or_(
            dm.DocumentControlledCopy.copy_number.ilike(needle),
            dm.DocumentControlledCopy.location_text.ilike(needle),
            manual_models.Manual.code.ilike(needle),
            manual_models.Manual.title.ilike(needle),
        ))
    if status:
        query = query.filter(dm.DocumentControlledCopy.status == status.upper())
    if custody == "ON_SHELF":
        query = query.filter(dm.DocumentControlledCopy.status == "RETURNED", dm.DocumentControlledCopy.holder_user_id.is_(None))
    elif custody == "CHECKED_OUT":
        query = query.filter(dm.DocumentControlledCopy.status.in_(["ISSUED", "RECALLED"]), dm.DocumentControlledCopy.holder_user_id.isnot(None))
    elif custody == "RECALLED":
        query = query.filter(dm.DocumentControlledCopy.status == "RECALLED")
    if overdue:
        query = query.filter(dm.DocumentControlledCopy.due_back_at < utcnow(), dm.DocumentControlledCopy.status.in_(["ISSUED", "RECALLED"]))
    total = query.count()
    rows = (
        query.order_by(manual_models.Manual.code.asc(), dm.DocumentControlledCopy.copy_number.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    holder_ids = {copy.holder_user_id for copy, _manual, _revision in rows if copy.holder_user_id}
    holders = {
        user.id: user
        for user in db.query(account_models.User).filter(account_models.User.id.in_(holder_ids or ["-"])).all()
    }
    items = []
    for copy, manual, revision in rows:
        holder = holders.get(copy.holder_user_id or "")
        items.append({
            **_copy_payload(copy),
            "document": {"id": manual.id, "code": manual.code, "title": manual.title, "manual_type": manual.manual_type},
            "revision": {"id": revision.id, "issue_number": revision.issue_number, "revision_number": revision.rev_number, "status": status_value(revision)},
            "home_location_text": _home_location(copy),
            "holder_display": holder.full_name if holder else copy.holder_name,
            "overdue": bool(copy.due_back_at and copy.status in {"ISSUED", "RECALLED"} and copy.due_back_at.date() < datetime.utcnow().date()),
            "scan_path": f"/maintenance/{tenant_slug}/document-control/library/{manual.id}?tab=distribution&scan={copy.id}",
            "label_path": f"/doc-control/workspace/t/{tenant_slug}/controlled-copies/{copy.id}/label.pdf",
        })
    return {
        "items": items,
        "pagination": {"page": page, "per_page": per_page, "total": total, "returned": len(items)},
        "summary": {
            "on_shelf": sum(1 for item in items if item["status"] == "RETURNED" and not item["holder_user_id"]),
            "checked_out": sum(1 for item in items if item["status"] in {"ISSUED", "RECALLED"} and item["holder_user_id"]),
            "overdue": sum(1 for item in items if item["overdue"]),
        },
    }


@router.get("/t/{tenant_slug}/controlled-copies/{copy_id}/scan")
def scan_controlled_copy(
    tenant_slug: str,
    copy_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = _copy(db, tenant.amo_id, copy_id)
    manual = get_manual(db, tenant, row.manual_id)
    profile = get_profile(db, tenant, manual.id)
    require_manual_access(current_user, profile)
    revision = get_revision(db, manual, row.revision_id)
    return _scan_payload(db, tenant_slug=tenant_slug, row=row, manual=manual, revision=revision, current_user=current_user)


@router.post("/t/{tenant_slug}/controlled-copies/{copy_id}/circulation")
def circulate_controlled_copy(
    tenant_slug: str,
    copy_id: str,
    payload: CirculationRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = _copy(db, tenant.amo_id, copy_id)
    manual = get_manual(db, tenant, row.manual_id)
    require_manual_access(current_user, get_profile(db, tenant, manual.id))
    controller = is_control_user(current_user)
    own_copy = str(row.holder_user_id or "") == str(current_user.id)
    before_holder = row.holder_user_id
    before_location = row.location_text

    if payload.action == "CHECK_OUT":
        if row.status != "RETURNED" or row.holder_user_id:
            raise HTTPException(status_code=409, detail="This physical copy is not currently available on its controlled shelf")
        if not payload.acknowledgement:
            raise HTTPException(status_code=422, detail="Custody acknowledgement is required before check-out")
        if not payload.due_back_at or not _future(payload.due_back_at):
            raise HTTPException(status_code=422, detail="A future return due date is required")
        target_user_id = payload.holder_user_id if controller and payload.holder_user_id else current_user.id
        holder = active_tenant_users(db, tenant, [target_user_id])[0]
        row.holder_user_id = holder.id
        row.holder_name = holder.full_name
        row.status = "ISSUED"
        row.due_back_at = payload.due_back_at
        if payload.location_text:
            row.location_text = payload.location_text.strip()
        event_type = "CHECK_OUT"
        reason = payload.comments or "Physical controlled copy custody accepted"
    elif payload.action == "CHECK_IN":
        if not (controller or own_copy):
            raise HTTPException(status_code=403, detail="Only the current custodian or Document Control may return this copy")
        if row.status not in {"ISSUED", "RECALLED"}:
            raise HTTPException(status_code=409, detail="This physical copy is not checked out")
        row.holder_user_id = None
        row.holder_name = None
        row.status = "RETURNED"
        row.due_back_at = None
        row.location_text = str(payload.location_text or _home_location(row)).strip()
        event_type = "CHECK_IN"
        reason = payload.comments or "Physical controlled copy returned"
    else:
        if not (controller or own_copy):
            raise HTTPException(status_code=403, detail="Only the custodian or Document Control may verify this copy location")
        location = str(payload.location_text or row.location_text).strip()
        if not location:
            raise HTTPException(status_code=422, detail="A verified physical location is required")
        row.location_text = location
        event_type = "LOCATION_VERIFIED"
        reason = payload.comments or "Physical location verified by scan"

    event = dm.DocumentControlledCopyEvent(
        tenant_id=tenant.amo_id,
        controlled_copy_id=row.id,
        event_type=event_type,
        actor_user_id=current_user.id,
        from_holder_user_id=before_holder,
        to_holder_user_id=row.holder_user_id,
        from_location=before_location,
        to_location=row.location_text,
        reason=reason,
        evidence_json=[{
            "method": "PORTAL_QR_SCAN",
            "acknowledgement": payload.acknowledgement,
            "actor_user_id": current_user.id,
        }],
    )
    db.add(event)
    audit(db, tenant, request, f"document.copy.{event_type.lower()}", "document_controlled_copy", row.id, {
        "copy_number": row.copy_number,
        "manual_id": row.manual_id,
        "from_holder_user_id": before_holder,
        "to_holder_user_id": row.holder_user_id,
        "from_location": before_location,
        "to_location": row.location_text,
        "due_back_at": row.due_back_at.isoformat() if row.due_back_at else None,
    })
    db.commit()
    revision = get_revision(db, manual, row.revision_id)
    return _scan_payload(db, tenant_slug=tenant_slug, row=row, manual=manual, revision=revision, current_user=current_user)


def _draw_qr(target: str, size: float = 34 * mm) -> Drawing:
    widget = qr.QrCodeWidget(target)
    x1, y1, x2, y2 = widget.getBounds()
    width = max(1.0, x2 - x1)
    height = max(1.0, y2 - y1)
    scale = min(size / width, size / height)
    drawing = Drawing(size, size, transform=[scale, 0, 0, scale, 0, 0])
    drawing.add(widget)
    return drawing


@router.get("/t/{tenant_slug}/controlled-copies/{copy_id}/label.pdf")
def controlled_copy_label(
    tenant_slug: str,
    copy_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = _copy(db, tenant.amo_id, copy_id)
    manual = get_manual(db, tenant, row.manual_id)
    revision = get_revision(db, manual, row.revision_id)
    origin = str(request.headers.get("origin") or str(request.base_url).rstrip("/")).rstrip("/")
    scan_url = f"{origin}/maintenance/{tenant_slug}/document-control/library/{manual.id}?tab=distribution&scan={row.id}"

    output = BytesIO()
    page_width, page_height = A6
    pdf = canvas.Canvas(output, pagesize=A6)
    pdf.setTitle(f"Controlled copy {manual.code} {row.copy_number}")
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(9 * mm, page_height - 12 * mm, "CONTROLLED DOCUMENT COPY")
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(9 * mm, page_height - 20 * mm, manual.code[:38])
    pdf.setFont("Helvetica", 8)
    title = manual.title if len(manual.title) <= 48 else f"{manual.title[:45]}..."
    pdf.drawString(9 * mm, page_height - 26 * mm, title)
    pdf.drawString(9 * mm, page_height - 33 * mm, f"Issue {revision.issue_number or '—'}  |  Rev {revision.rev_number}")
    pdf.drawString(9 * mm, page_height - 39 * mm, f"Copy no: {row.copy_number}  |  {row.format}")
    pdf.drawString(9 * mm, page_height - 45 * mm, f"Home: {_home_location(row)[:46]}")
    pdf.drawString(9 * mm, page_height - 51 * mm, "Scan before taking, transferring or returning this copy.")
    renderPDF.draw(_draw_qr(scan_url), pdf, page_width - 46 * mm, 13 * mm)
    pdf.setFont("Helvetica-Bold", 7)
    pdf.drawString(9 * mm, 31 * mm, "QR is an identifier, not an access credential.")
    pdf.setFont("Helvetica", 6.5)
    pdf.drawString(9 * mm, 26 * mm, "Login is required. Live custody and revision status are held in AMO Portal.")
    pdf.drawString(9 * mm, 20 * mm, f"Copy ID: {row.id}")
    pdf.rect(5 * mm, 5 * mm, page_width - 10 * mm, page_height - 10 * mm)
    pdf.showPage()
    pdf.save()
    filename = f"{manual.code}-{row.copy_number}-controlled-copy-label.pdf".replace("/", "-").replace("\\", "-")
    return Response(
        content=output.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )
