from __future__ import annotations

import uuid
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, lazyload
from amodb.database import get_db, get_read_db, get_write_db
from amodb.security import get_current_active_user
from amodb.apps.accounts.models import User
from . import models
from .car_rca_router import _car_for_employee, _car_for_guest
from .car_feedback import record_shared_feedback, feedback_changed
from .tenant_security import TenantContext, require_quality_permission, write_tenant_context, assert_quality_permission

router = APIRouter(prefix="/cars/{car_id}/feedback", tags=["Quality / CAR feedback"])
public_router = APIRouter(prefix="/cars/invite/{invite_token}/feedback", tags=["Quality / Public CAR feedback"])


@public_router.get("/events")
def public_feedback_events(invite_token: str):
    import asyncio
    from fastapi.responses import StreamingResponse
    from amodb.database import WriteSessionLocal
    from amodb.apps.events.broker import broker
    def scope():
        with WriteSessionLocal() as db:
            car = _car_for_guest(db, invite_token, lean=True)
            return str(car.id), str(car.amo_id)
    car_id, amo_id = scope()
    async def updates():
        queue = broker.subscribe_async()
        try:
            yield 'data: {"refresh":true}\n\n'
            for _ in range(180):
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=10)
                    if event.entityId == car_id and str(event.metadata.get("amoId")) == amo_id:
                        yield 'data: {"refresh":true}\n\n'
                except asyncio.TimeoutError:
                    # Revalidate revocation, and recover changes missed during reconnect.
                    try:
                        await asyncio.to_thread(scope)
                    except HTTPException:
                        yield 'event: access-ended\ndata: {}\n\n'
                        return
                    yield 'data: {"refresh":true}\n\n'
        finally:
            broker.unsubscribe_async(queue)
    return StreamingResponse(updates(), media_type="text/event-stream",
        headers={"Cache-Control":"no-store", "X-Accel-Buffering":"no"})


class FeedbackCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    client_message_id: uuid.UUID
    actor_name: str = Field(default="Invited respondent", min_length=1, max_length=255)
    visibility: Literal["SHARED", "INTERNAL"] = "SHARED"

    @field_validator("message", "actor_name")
    @classmethod
    def nonblank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Enter a nonblank value.")
        return value


def _item(row, *, public):
    return {"id": str(row.id), "message": row.message, "action_type": row.action_type.value,
        "actor_name": row.actor_name or ("Historical staff activity" if row.actor_user_id else "System"),
        "actor_kind": row.actor_kind, "visibility": row.visibility,
        "created_at": row.created_at, "car_id": str(row.car_id)}


def timeline(db, car, *, public, before=None):
    # Scalar rows avoid the log's default joined CAR and its wider relationship graph.
    query = db.query(*models.CARActionLog.__table__.columns).filter(models.CARActionLog.car_id == car.id)
    if public:
        query = query.filter(models.CARActionLog.visibility == "SHARED")
    if before:
        boundary = query.filter(models.CARActionLog.id == before).first()
        if boundary is None:
            raise HTTPException(status_code=404, detail="History cursor not found")
        from sqlalchemy import or_, and_
        query = query.filter(or_(models.CARActionLog.created_at < boundary.created_at,
            and_(models.CARActionLog.created_at == boundary.created_at, models.CARActionLog.id < boundary.id)))
    rows = query.order_by(models.CARActionLog.created_at.desc(), models.CARActionLog.id.desc()).limit(51).all()
    return {"car_id": str(car.id), "status": car.status.value,
        "root_cause_status": car.root_cause_status, "capa_status": car.capa_status,
        "root_cause_review_note": car.root_cause_review_note, "capa_review_note": car.capa_review_note,
        "items": [_item(row, public=public) for row in rows[:50]],
        "next_cursor": str(rows[49].id) if len(rows) > 50 else None}


def append_message(db, car, payload, *, user=None, public=False):
    key = str(payload.client_message_id)
    def existing():
        return db.query(*models.CARActionLog.__table__.columns).filter(models.CARActionLog.car_id == car.id,
            models.CARActionLog.client_message_id == key).first()
    previous = existing()
    visibility = "SHARED" if public else payload.visibility
    actor_kind = "AUDITEE" if public else "STAFF"
    def check(row):
        if row.message != payload.message or row.visibility != visibility or row.actor_kind != actor_kind or row.actor_user_id != getattr(user, "id", None):
            raise HTTPException(status_code=409, detail="This message identifier was already used for different content.")
        return _item(row, public=public)
    if previous:
        return check(previous)
    if car.status in {models.CARStatus.CLOSED, models.CARStatus.CANCELLED}:
        raise HTTPException(status_code=409, detail="This CAR is closed; its communication history is read only.")
    from types import SimpleNamespace
    event_car = SimpleNamespace(id=car.id, amo_id=car.amo_id)
    row = record_shared_feedback(db, car, payload.message, user=user,
        actor_name=payload.actor_name if public else None, actor_kind=actor_kind, client_message_id=key)
    row.visibility = visibility
    if visibility == "SHARED":
        from .router import _notify_user, _audit_for_finding
        recipients = {car.assigned_to_user_id} if not public else set()
        if public and car.finding_id:
            audit = _audit_for_finding(db, car.finding_id, amo_id=car.amo_id)
            if audit:
                recipients.update({audit.lead_auditor_user_id, audit.assistant_auditor_user_id, audit.observer_auditor_user_id})
        from amodb.apps.accounts.models import AMO
        from urllib.parse import quote
        tenant = db.get(AMO, str(car.amo_id), options=[lazyload("*")])
        tenant_code = quote(str(tenant.login_slug or tenant.amo_code), safe="") if tenant else ""
        for recipient in recipients - {None, getattr(user, "id", None)}:
            _notify_user(db, recipient, f"New shared feedback on {car.car_number}.",
                models.QMSNotificationSeverity.ACTION_REQUIRED, amo_id=str(car.amo_id),
                action_url=f"/maintenance/{tenant_code}/quality/cars?carId={car.id}",
                action_label="Open CAR feedback", entity_type="car", entity_id=car.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = existing()
        if previous:
            return check(previous)
        raise
    db.refresh(row, attribute_names=["id","car_id","action_type","message","actor_name","actor_kind","visibility","created_at"])
    feedback_changed(event_car, getattr(user, "id", None))
    return _item(row, public=public)


@router.get("")
def read_feedback(car_id: uuid.UUID, response: Response, before: uuid.UUID | None = Query(default=None),
    ctx: TenantContext = Depends(require_quality_permission("qms.car.view")), db: Session = Depends(get_read_db)):
    response.headers["Cache-Control"] = "no-store"
    return timeline(db, _car_for_employee(db, ctx, car_id, lean=True), public=False, before=before)


@router.post("", status_code=201)
def post_feedback(car_id: uuid.UUID, payload: FeedbackCreate,
    ctx: TenantContext = Depends(write_tenant_context), db: Session = Depends(get_write_db),
    user: User = Depends(get_current_active_user)):
    assert_quality_permission(db, ctx, "qms.car.view")
    car = _car_for_employee(db, ctx, car_id, lock=True, lean=True)
    from .router import _require_car_write_access
    _require_car_write_access(db, user, car.finding_id, car=car, allow_assignee=True)
    return append_message(db, car, payload, user=user)


@public_router.get("")
def read_public_feedback(invite_token: str, response: Response, before: uuid.UUID | None = Query(default=None), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return timeline(db, _car_for_guest(db, invite_token, lean=True), public=True, before=before)


@public_router.post("", status_code=201)
def post_public_feedback(invite_token: str, payload: FeedbackCreate, db: Session = Depends(get_db)):
    return append_message(db, _car_for_guest(db, invite_token, lock=True, lean=True), payload, public=True)
