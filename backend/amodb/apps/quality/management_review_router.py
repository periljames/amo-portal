"""Tenant-scoped management reviews on the existing canonical QMS records.

Meetings, decisions and follow-up are governed together; generic register writes
must not bypass this workflow. No parallel source tables are introduced.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.database import get_read_db, get_write_db
from .canonical_core_router import _log_qms_activity
from .tenant_security import TenantContext, assert_quality_permission, resolve_tenant_context, set_postgres_tenant_context

router = APIRouter(prefix="/management-review/workspace", tags=["Management Review"])
MEETINGS = "qms_management_reviews"
ACTIONS = "qms_management_review_actions"
MEETING_TRANSITIONS = {
    "DRAFT": {"SCHEDULED", "CANCELLED"},
    "SCHEDULED": {"IN_PROGRESS", "DRAFT", "CANCELLED"},
    "IN_PROGRESS": {"PENDING_APPROVAL", "CANCELLED"},
    "PENDING_APPROVAL": {"APPROVED", "IN_PROGRESS"},
    "APPROVED": {"CLOSED"}, "CLOSED": set(), "CANCELLED": set(),
}
ACTION_TRANSITIONS = {
    "OPEN": {"IN_PROGRESS", "CANCELLED"},
    "IN_PROGRESS": {"PENDING_VERIFICATION", "CANCELLED"},
    "PENDING_VERIFICATION": {"CLOSED", "IN_PROGRESS"},
    "CLOSED": {"IN_PROGRESS"}, "CANCELLED": set(),
}
TERMINAL_ACTIONS = {"CLOSED", "CANCELLED"}


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class ReviewInput(StrictBody):
    topic: str = Field(min_length=2, max_length=150)
    summary: str = Field(min_length=2, max_length=12000)
    source_reference: str = Field(default="", max_length=1000)


class ReviewDecision(StrictBody):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), max_length=36)
    title: str = Field(min_length=3, max_length=255)
    rationale: str = Field(min_length=3, max_length=12000)


class MeetingBody(StrictBody):
    title: str = Field(min_length=3, max_length=255)
    review_date: date
    chair_user_id: str = Field(min_length=1, max_length=36)
    attendee_user_ids: list[str] = Field(default_factory=list, max_length=100)
    agenda: str = Field(default="", max_length=24000)
    inputs: list[ReviewInput] = Field(default_factory=list, max_length=100)
    minutes: str = Field(default="", max_length=48000)
    decisions: list[ReviewDecision] = Field(default_factory=list, max_length=100)


class MeetingUpdate(MeetingBody):
    expected_version: int = Field(ge=1)


class Transition(StrictBody):
    status: str = Field(min_length=2, max_length=40)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=4000)


class ActionBody(StrictBody):
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(default="", max_length=12000)
    owner_user_id: str = Field(min_length=1, max_length=36)
    due_date: date
    decision_id: str = Field(min_length=1, max_length=36)


class ActionUpdate(ActionBody):
    expected_version: int = Field(ge=1)
    completion_evidence: str = Field(default="", max_length=12000)


def _context(db, ctx, *, write=False):
    assert_quality_permission(db, ctx, "qms.management_review.manage" if write else "qms.management_review.view")
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)


def _payload(row):
    value = row.get("payload") or {}
    return json.loads(value) if isinstance(value, str) else dict(value)


def _public(row):
    result = dict(row)
    result["payload"] = _payload(result)
    result["version"] = int(result["payload"].get("version", 1))
    return result


def _record(db, table, ctx, record_id, *, lock=False):
    suffix = " FOR UPDATE" if lock and db.bind.dialect.name == "postgresql" else ""
    row = db.execute(text(f"SELECT * FROM {table} WHERE id=:id AND amo_id=:amo AND deleted_at IS NULL{suffix}"),
                     {"id": record_id, "amo": ctx.amo_id}).mappings().first()
    if not row:
        raise HTTPException(404, "This Quality record was not found in this tenant.")
    return _public(row)


def _version(row, expected):
    if row["version"] != expected:
        raise HTTPException(409, "This record changed. Refresh it before saving your changes.")


def _members(db, ctx, ids):
    for user_id in set(ids):
        found = db.execute(text("SELECT id FROM users WHERE id=:id AND amo_id=:amo AND is_active=true"),
                           {"id": user_id, "amo": ctx.amo_id}).first()
        if not found:
            raise HTTPException(422, "Choose an active chair, attendee or action owner from this tenant.")


def validate_meeting_transition(row, target, actions):
    current = row["status"]
    if target not in MEETING_TRANSITIONS.get(current, set()):
        raise HTTPException(409, f"A {current.lower().replace('_', ' ')} review cannot move to {target.lower().replace('_', ' ')}.")
    p = _payload(row)
    if target == "SCHEDULED" and (not row.get("due_date") or not row.get("owner_user_id") or not p.get("agenda", "").strip()):
        raise HTTPException(422, "Set the meeting date, chair and agenda before scheduling.")
    if target == "PENDING_APPROVAL" and (not p.get("minutes", "").strip() or not p.get("decisions") or not p.get("inputs")):
        raise HTTPException(422, "Record review inputs, minutes and at least one decision before submitting for approval.")
    if target in {"CLOSED", "CANCELLED"} and any(a["status"] not in TERMINAL_ACTIONS for a in actions):
        raise HTTPException(422, "Close or cancel all follow-up actions before closing or cancelling this review.")


def validate_action_transition(row, target):
    if target not in ACTION_TRANSITIONS.get(row["status"], set()):
        raise HTTPException(409, "This action transition is unavailable. Refresh the action.")
    if target in {"PENDING_VERIFICATION", "CLOSED"} and not _payload(row).get("completion_evidence", "").strip():
        raise HTTPException(422, "Record completion evidence before submitting or verifying this action.")


def _actions(db, ctx, review_id):
    # The JSON parent relation is always combined with tenant ownership.
    clause = "payload->>'review_id'" if db.bind.dialect.name == "postgresql" else "json_extract(payload, '$.review_id')"
    rows = db.execute(text(f"SELECT * FROM {ACTIONS} WHERE amo_id=:amo AND deleted_at IS NULL AND {clause}=:parent ORDER BY due_date, created_at"),
                      {"amo": ctx.amo_id, "parent": review_id}).mappings().all()
    return [_public(r) for r in rows]


def _save(db, table, ctx, values, *, existing=None, event, request=None, module="management-review", reason=None):
    now = datetime.now(timezone.utc)
    p = dict(values.pop("payload", {}))
    p["version"] = existing["version"] + 1 if existing else 1
    history = list(_payload(existing).get("history", [])) if existing else []
    entry = {"event": event, "at": now.isoformat(), "by": ctx.user_id,
             "status": values.get("status", existing.get("status") if existing else "DRAFT")}
    if reason:
        entry["reason"] = reason
    if module in {"risk", "system"} and "likelihood" in p:
        entry["assessment"] = {key: p.get(key) for key in ("likelihood", "consequence", "rating", "risk_score")}
    history.append(entry)
    p["history"] = history
    values = {**values, "payload": json.dumps(p, default=str), "amo_id": ctx.amo_id, "updated_by": ctx.user_id, "updated_at": now}
    cast = "CAST(:payload AS jsonb)" if db.bind.dialect.name == "postgresql" else ":payload"
    if existing:
        values["id"] = existing["id"]
        assignments = ", ".join(f"{k}={cast if k == 'payload' else ':'+k}" for k in values if k not in {"id", "amo_id"})
        row = db.execute(text(f"UPDATE {table} SET {assignments} WHERE id=:id AND amo_id=:amo_id RETURNING *"), values).mappings().one()
    else:
        values.update(id=str(uuid.uuid4()), created_by=ctx.user_id, created_at=now)
        columns = ", ".join(values)
        binds = ", ".join(cast if k == "payload" else ":"+k for k in values)
        row = db.execute(text(f"INSERT INTO {table} ({columns}) VALUES ({binds}) RETURNING *"), values).mappings().one()
    result = _public(row)
    _log_qms_activity(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id, action=event,
                      module=module, entity_type=table, entity_id=result["id"],
                      previous_value=existing, new_value=result, request=request)
    return result


def _meeting_values(body):
    p = body.model_dump(mode="json", exclude={"expected_version"})
    return {"title": body.title, "due_date": body.review_date, "owner_user_id": body.chair_user_id,
            "description": body.agenda, "payload": p}


@router.get("/members")
def members(ctx: TenantContext = Depends(resolve_tenant_context), db: Session = Depends(get_read_db)):
    _context(db, ctx)
    rows = db.execute(text("SELECT id, first_name, last_name, email FROM users WHERE amo_id=:amo AND is_active=true ORDER BY first_name, last_name"), {"amo": ctx.amo_id}).mappings().all()
    return {"items": [dict(r) for r in rows]}


@router.get("")
def overview(view: Literal["dashboard", "meetings", "actions", "open-actions", "closed-actions"] = "dashboard",
             q: str = Query("", max_length=80), offset: int = Query(0, ge=0, le=100000),
             ctx: TenantContext = Depends(resolve_tenant_context), db: Session = Depends(get_read_db)):
    _context(db, ctx)
    table = ACTIONS if "actions" in view else MEETINGS
    where = "amo_id=:amo AND deleted_at IS NULL"
    params = {"amo": ctx.amo_id, "offset": offset, "q": "%" + q.lower() + "%"}
    if q:
        where += " AND lower(title) LIKE :q"
    if view == "open-actions": where += " AND status NOT IN ('CLOSED', 'CANCELLED')"
    if view == "closed-actions": where += " AND status IN ('CLOSED', 'CANCELLED')"
    total = db.execute(text(f"SELECT count(*) FROM {table} WHERE {where}"), params).scalar_one()
    rows = db.execute(text(f"SELECT * FROM {table} WHERE {where} ORDER BY due_date DESC, created_at DESC LIMIT 30 OFFSET :offset"), params).mappings().all()
    stats = {}
    for key, source, condition in [
        ("meetings", MEETINGS, "1=1"), ("awaiting_approval", MEETINGS, "status='PENDING_APPROVAL'"),
        ("open_actions", ACTIONS, "status NOT IN ('CLOSED','CANCELLED')"),
        ("overdue_actions", ACTIONS, "status NOT IN ('CLOSED','CANCELLED') AND due_date < CURRENT_DATE"),
    ]:
        stats[key] = db.execute(text(f"SELECT count(*) FROM {source} WHERE amo_id=:amo AND deleted_at IS NULL AND {condition}"), params).scalar_one()
    return {"items": [_public(r) for r in rows], "total": total, "offset": offset, "limit": 30, "summary": stats}


@router.post("/meetings", status_code=201)
def create_meeting(body: MeetingBody, request: Request, ctx: TenantContext = Depends(resolve_tenant_context), db: Session = Depends(get_write_db)):
    _context(db, ctx, write=True)
    _members(db, ctx, [body.chair_user_id, *body.attendee_user_ids])
    row = _save(db, MEETINGS, ctx, {**_meeting_values(body), "status": "DRAFT"}, event="REVIEW_CREATED", request=request)
    db.commit()
    return row


@router.get("/meetings/{review_id}")
def meeting(review_id: str, ctx: TenantContext = Depends(resolve_tenant_context), db: Session = Depends(get_read_db)):
    _context(db, ctx)
    row = _record(db, MEETINGS, ctx, review_id)
    return {**row, "actions": _actions(db, ctx, review_id)}


@router.put("/meetings/{review_id}")
def update_meeting(review_id: str, body: MeetingUpdate, request: Request, ctx: TenantContext = Depends(resolve_tenant_context), db: Session = Depends(get_write_db)):
    _context(db, ctx, write=True)
    row = _record(db, MEETINGS, ctx, review_id, lock=True)
    _version(row, body.expected_version)
    if row["status"] not in {"DRAFT", "SCHEDULED", "IN_PROGRESS"}:
        raise HTTPException(409, "Return the meeting to preparation before editing approved or submitted minutes.")
    _members(db, ctx, [body.chair_user_id, *body.attendee_user_ids])
    decision_ids = [d.id for d in body.decisions]
    if len(decision_ids) != len(set(decision_ids)):
        raise HTTPException(422, "Each decision must have a unique identifier.")
    if any(_payload(a).get("decision_id") not in decision_ids for a in _actions(db, ctx, review_id)):
        raise HTTPException(422, "A decision linked to an action cannot be removed.")
    saved = _save(db, MEETINGS, ctx, _meeting_values(body), existing=row, event="REVIEW_UPDATED", request=request)
    db.commit()
    return saved


@router.post("/meetings/{review_id}/transition")
def transition_meeting(review_id: str, body: Transition, request: Request, ctx: TenantContext = Depends(resolve_tenant_context), db: Session = Depends(get_write_db)):
    _context(db, ctx, write=True)
    row = _record(db, MEETINGS, ctx, review_id, lock=True)
    _version(row, body.expected_version)
    validate_meeting_transition(row, body.status, _actions(db, ctx, review_id))
    p = {**_payload(row), "last_reason": body.reason}
    if body.status == "APPROVED":
        p["approval"] = {"by": ctx.user_id, "at": datetime.now(timezone.utc).isoformat(), "reason": body.reason}
    saved = _save(db, MEETINGS, ctx, {"status": body.status, "payload": p}, existing=row, event="REVIEW_" + body.status, request=request, reason=body.reason)
    db.commit()
    return saved


@router.post("/meetings/{review_id}/actions", status_code=201)
def create_action(review_id: str, body: ActionBody, request: Request, ctx: TenantContext = Depends(resolve_tenant_context), db: Session = Depends(get_write_db)):
    _context(db, ctx, write=True)
    parent = _record(db, MEETINGS, ctx, review_id, lock=True)
    if parent["status"] in {"CLOSED", "CANCELLED"}:
        raise HTTPException(409, "This meeting no longer accepts new actions.")
    if body.decision_id not in {d["id"] for d in _payload(parent).get("decisions", [])}:
        raise HTTPException(422, "Choose a decision retained in this meeting.")
    _members(db, ctx, [body.owner_user_id])
    values = body.model_dump(mode="json", exclude={"decision_id"})
    values["payload"] = {"review_id": review_id, "decision_id": body.decision_id, "completion_evidence": ""}
    values["status"] = "OPEN"
    saved = _save(db, ACTIONS, ctx, values, event="REVIEW_ACTION_CREATED", request=request)
    db.commit()
    return saved


@router.put("/actions/{action_id}")
def update_action(action_id: str, body: ActionUpdate, request: Request, ctx: TenantContext = Depends(resolve_tenant_context), db: Session = Depends(get_write_db)):
    _context(db, ctx, write=True)
    # Lock parent first everywhere to serialize action creation/closeout.
    initial = _record(db, ACTIONS, ctx, action_id)
    parent = _record(db, MEETINGS, ctx, _payload(initial)["review_id"], lock=True)
    row = _record(db, ACTIONS, ctx, action_id, lock=True)
    _version(row, body.expected_version)
    if parent["status"] in {"CLOSED", "CANCELLED"} or row["status"] in TERMINAL_ACTIONS:
        raise HTTPException(409, "Closed or cancelled records cannot be edited.")
    if body.decision_id not in {d["id"] for d in _payload(parent).get("decisions", [])}:
        raise HTTPException(422, "Choose a decision retained in this meeting.")
    _members(db, ctx, [body.owner_user_id])
    values = body.model_dump(mode="json", exclude={"expected_version", "decision_id", "completion_evidence"})
    values["payload"] = {**_payload(row), "decision_id": body.decision_id, "completion_evidence": body.completion_evidence}
    saved = _save(db, ACTIONS, ctx, values, existing=row, event="REVIEW_ACTION_UPDATED", request=request)
    db.commit()
    return saved


@router.get("/actions/{action_id}")
def action_detail(action_id: str, ctx: TenantContext = Depends(resolve_tenant_context), db: Session = Depends(get_read_db)):
    _context(db, ctx)
    return _record(db, ACTIONS, ctx, action_id)


@router.post("/actions/{action_id}/transition")
def transition_action(action_id: str, body: Transition, request: Request, ctx: TenantContext = Depends(resolve_tenant_context), db: Session = Depends(get_write_db)):
    _context(db, ctx, write=True)
    initial = _record(db, ACTIONS, ctx, action_id)
    parent = _record(db, MEETINGS, ctx, _payload(initial)["review_id"], lock=True)
    row = _record(db, ACTIONS, ctx, action_id, lock=True)
    _version(row, body.expected_version)
    if parent["status"] in {"CLOSED", "CANCELLED"}:
        raise HTTPException(409, "This meeting is closed or cancelled.")
    validate_action_transition(row, body.status)
    p = {**_payload(row), "last_reason": body.reason}
    if body.status == "CLOSED": p["verification"] = {"by": ctx.user_id, "at": datetime.now(timezone.utc).isoformat(), "reason": body.reason}
    saved = _save(db, ACTIONS, ctx, {"status": body.status, "payload": p}, existing=row, event="REVIEW_ACTION_" + body.status, request=request, reason=body.reason)
    db.commit()
    return saved
