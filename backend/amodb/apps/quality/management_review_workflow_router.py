"""Governed management-review lifecycle on the existing canonical QMS tables.

No shadow review register: uses qms_management_reviews and its canonical inputs,
minutes, decisions, actions and approvals. All mutations are tenant-scoped,
serialized on the review and recorded in the existing activity history.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_read_db, get_write_db
from .canonical_core_router import _insert_record, _log_qms_activity, _table_columns
from .qms_evidence_reference_validation import require_evidence_records
from .tenant_security import (
    TenantContext, require_quality_permission, set_postgres_tenant_context,
)

router = APIRouter(prefix="/management-review", tags=["QMS governed management review"])

_TABLES: dict[str, str] = {
    "inputs": "qms_management_review_inputs",
    "minutes": "qms_management_review_minutes",
    "decisions": "qms_management_review_decisions",
    "actions": "qms_management_review_actions",
    "approvals": "qms_management_review_approvals",
}
_SOURCE_TABLES: dict[str, str] = {
    "AUDIT": "qms_audits",
    "CAR": "quality_cars",
    "RISK": "qms_risks",
    "SUPPLIER": "qms_suppliers",
    "EQUIPMENT": "qms_equipment",
    "TRAINING": "training_records",
}
_REVIEW_EDITABLE = {"DRAFT"}
_REVIEW_APPROVABLE = {"PENDING_APPROVAL"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateMeeting(StrictModel):
    title: str = Field(min_length=4, max_length=255)
    meeting_date: date
    agenda: list[str] = Field(min_length=1, max_length=40)
    attendees: list[str] = Field(min_length=1, max_length=50)
    purpose: str = Field(min_length=8, max_length=4000)


class Versioned(StrictModel):
    expected_version: int = Field(ge=1)


class InputCreate(Versioned):
    title: str = Field(min_length=4, max_length=255)
    summary: str = Field(min_length=8, max_length=5000)
    source_type: Literal["AUDIT", "CAR", "RISK", "SUPPLIER", "EQUIPMENT", "TRAINING"]
    source_id: str = Field(min_length=1, max_length=64)


class MinutesCreate(Versioned):
    description: str = Field(min_length=12, max_length=12000)


class DecisionCreate(Versioned):
    title: str = Field(min_length=4, max_length=255)
    rationale: str = Field(min_length=8, max_length=8000)
    action_required: bool


class ActionCreate(Versioned):
    title: str = Field(min_length=4, max_length=255)
    description: str = Field(min_length=8, max_length=8000)
    owner_user_id: str = Field(min_length=1, max_length=36)
    due_date: date
    decision_id: str = Field(min_length=1, max_length=36)


class Transition(Versioned):
    rationale: str = Field(min_length=8, max_length=4000)


class CompleteAction(StrictModel):
    evidence_references: list[str] = Field(min_length=1, max_length=30)
    statement: str = Field(min_length=8, max_length=4000)


class VerifyAction(StrictModel):
    accepted: bool
    reason: str = Field(min_length=8, max_length=4000)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _init(db: Session, ctx: TenantContext) -> None:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)


def _user(db: Session, ctx: TenantContext, identifier: str) -> None:
    record = db.query(account_models.User.id).filter(
        account_models.User.id == identifier,
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).first()
    if not record:
        raise HTTPException(422, "Selected person is not an active user in this tenant.")


def _meeting(db: Session, ctx: TenantContext, meeting_id: str, *, lock: bool = False) -> dict[str, Any]:
    sql = """SELECT * FROM qms_management_reviews
             WHERE id = :id AND amo_id = :amo_id AND deleted_at IS NULL"""
    if lock:
        sql += " FOR UPDATE"
    row = db.execute(text(sql), {"id": meeting_id, "amo_id": ctx.amo_id}).mappings().first()
    if row is None:
        raise HTTPException(404, "Management-review meeting not found in this tenant.")
    return dict(row)


def _version(row: dict[str, Any], expected: int) -> None:
    actual = int((row.get("payload") or {}).get("version", 1))
    if actual != expected:
        raise HTTPException(409, {"code": "REVIEW_VERSION_CONFLICT", "expected": expected, "current": actual})


def _related(db: Session, ctx: TenantContext, meeting_id: str, kind: str) -> list[dict[str, Any]]:
    table = _TABLES[kind]
    rows = db.execute(text(
        f"SELECT * FROM {table} WHERE amo_id = :amo_id AND deleted_at IS NULL "
        "AND payload ->> 'meeting_id' = :meeting_id ORDER BY created_at, id LIMIT 251"
    ), {"amo_id": ctx.amo_id, "meeting_id": meeting_id}).mappings().all()
    if len(rows) > 250:
        raise HTTPException(409, "Review item count exceeds the verified 250-item read limit. Resolve pagination before approval.")
    return [dict(row) for row in rows]


def _bump(db: Session, ctx: TenantContext, row: dict[str, Any], status: str | None = None) -> dict[str, Any]:
    data = dict(row.get("payload") or {})
    data["version"] = int(data.get("version", 1)) + 1
    # PostgreSQL row lock acquired by _meeting() makes the increment atomic.
    updated = db.execute(text("""
        UPDATE qms_management_reviews
        SET payload = CAST(:payload AS jsonb), status = :status,
            updated_at = now(), updated_by = :user
        WHERE id = :id AND amo_id = :amo_id AND deleted_at IS NULL RETURNING *
    """), {
        "payload": json.dumps(data),
        "status": status or row["status"], "user": ctx.user_id,
        "id": row["id"], "amo_id": ctx.amo_id,
    }).mappings().one()
    return dict(updated)


def _activity(db: Session, ctx: TenantContext, row: dict[str, Any], action: str, request: Request, extra: Any = None) -> None:
    _log_qms_activity(
        db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id,
        action=action, module="management-review", entity_type="qms_management_reviews",
        entity_id=str(row["id"]), new_value={"version": (row.get("payload") or {}).get("version"), "detail": extra},
        request=request,
    )


def _append(db: Session, ctx: TenantContext, row: dict[str, Any], kind: str,
            *, title: str, description: str, data: dict[str, Any],
            request: Request, owner: str | None = None, due_date: date | None = None) -> dict[str, Any]:
    if str(row["status"]) not in _REVIEW_EDITABLE:
        raise HTTPException(409, "The meeting is submitted; changes require a formally reopened draft.")
    saved = _insert_record(db, table=_TABLES[kind], amo_id=ctx.amo_id,
                           actor_user_id=ctx.user_id, payload={
                               "title": title, "description": description,
                               "status": "ASSIGNED" if kind == "actions" else "RECORDED",
                               "owner_user_id": owner, "due_date": due_date,
                               "payload": {"meeting_id": str(row["id"]), **data,
                                           "recorded_by": ctx.user_id, "recorded_at": _now()},
                           })
    updated = _bump(db, ctx, row)
    _activity(db, ctx, updated, f"management_review_{kind}_recorded", request, {"item_id": saved["id"]})
    db.commit()
    return {"item": saved, "meeting_version": updated["payload"]["version"]}


@router.get("/participants")
def list_review_participants(
    q: str = Query(default="", max_length=80),
    ctx: TenantContext = Depends(require_quality_permission("qms.management_review.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    query = db.query(account_models.User).filter(
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    )
    if q.strip():
        query = query.filter(account_models.User.full_name.ilike(f"%{q.strip()}%"))
    rows = query.order_by(account_models.User.full_name).limit(50).all()
    return {"items": [{"id": row.id, "name": row.full_name,
                       "position": row.position_title or ""} for row in rows]}


@router.get("/sources")
def list_review_sources(
    source_type: Literal["AUDIT", "CAR", "RISK", "SUPPLIER", "EQUIPMENT", "TRAINING"],
    q: str = Query(default="", max_length=80),
    ctx: TenantContext = Depends(require_quality_permission("qms.management_review.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    table = _SOURCE_TABLES[source_type]
    # Limit source discovery to minimal tenant-scoped labels, not entire
    # personal/training/quality rows or potentially large JSON evidence blobs.
    columns = _table_columns(db, table)
    label_field = next((field for field in ("title", "name", "car_number", "audit_ref", "course_id")
                        if field in columns), None)
    label_sql = f"CAST({label_field} AS text)" if label_field else "CAST(id AS text)"
    rows = db.execute(text(
        f"SELECT CAST(id AS text) AS id, {label_sql} AS label FROM {table} "
        "WHERE amo_id=:amo_id "
        f"AND (CAST(id AS text) ILIKE :query OR {label_sql} ILIKE :query) "
        "ORDER BY created_at DESC LIMIT 30"
    ), {"amo_id": ctx.amo_id, "query": f"%{q.strip()}%"}).mappings().all()
    return {"items": [{"id": row["id"], "label": row["label"] or row["id"]} for row in rows]}


@router.get("/meetings")
def list_meetings(
    limit: int = Query(default=25, ge=1, le=50), offset: int = Query(default=0, ge=0, le=100000),
    ctx: TenantContext = Depends(require_quality_permission("qms.management_review.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    params = {"amo_id": ctx.amo_id, "limit": limit, "offset": offset}
    total = db.execute(text(
        "SELECT COUNT(*) FROM qms_management_reviews WHERE amo_id=:amo_id AND deleted_at IS NULL"
    ), params).scalar_one()
    rows = db.execute(text(
        "SELECT * FROM qms_management_reviews WHERE amo_id=:amo_id AND deleted_at IS NULL "
        "ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
    ), params).mappings().all()
    return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.post("/meetings", status_code=201)
def create_meeting(
    payload: CreateMeeting, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.management_review.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    for person in set(payload.attendees):
        _user(db, ctx, person)
    row = _insert_record(db, table="qms_management_reviews", amo_id=ctx.amo_id,
                         actor_user_id=ctx.user_id, payload={
                             "title": payload.title, "status": "DRAFT",
                             "description": payload.purpose, "due_date": payload.meeting_date,
                             "payload": {"version": 1, "meeting_date": payload.meeting_date.isoformat(),
                                         "agenda": payload.agenda, "attendees": payload.attendees,
                                         "purpose": payload.purpose},
                         })
    _activity(db, ctx, row, "management_review_meeting_created", request)
    db.commit()
    return {"meeting": row}


@router.get("/meetings/{meeting_id}")
def meeting_detail(
    meeting_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.management_review.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _meeting(db, ctx, meeting_id)
    return {"meeting": row, **{kind: _related(db, ctx, meeting_id, kind) for kind in _TABLES}}


@router.post("/meetings/{meeting_id}/inputs", status_code=201)
def add_input(
    meeting_id: str, payload: InputCreate, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.management_review.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _meeting(db, ctx, meeting_id, lock=True)
    _version(row, payload.expected_version)
    source_table = _SOURCE_TABLES[payload.source_type]
    found = db.execute(text(f"SELECT id FROM {source_table} WHERE CAST(id AS text)=:id AND amo_id=:amo_id"),
                       {"id": payload.source_id, "amo_id": ctx.amo_id}).first()
    if not found:
        raise HTTPException(422, "The selected source record could not be verified in this tenant.")
    return _append(db, ctx, row, "inputs", title=payload.title, description=payload.summary,
                   data={"source_type": payload.source_type, "source_id": payload.source_id}, request=request)


@router.post("/meetings/{meeting_id}/minutes", status_code=201)
def add_minutes(
    meeting_id: str, payload: MinutesCreate, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.management_review.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _meeting(db, ctx, meeting_id, lock=True)
    _version(row, payload.expected_version)
    return _append(db, ctx, row, "minutes", title="Meeting minutes", description=payload.description,
                   data={}, request=request)


@router.post("/meetings/{meeting_id}/decisions", status_code=201)
def add_decision(
    meeting_id: str, payload: DecisionCreate, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.management_review.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _meeting(db, ctx, meeting_id, lock=True)
    _version(row, payload.expected_version)
    return _append(db, ctx, row, "decisions", title=payload.title,
                   description=payload.rationale, data={"action_required": payload.action_required}, request=request)


@router.post("/meetings/{meeting_id}/actions", status_code=201)
def add_action(
    meeting_id: str, payload: ActionCreate, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.management_review.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _meeting(db, ctx, meeting_id, lock=True)
    _version(row, payload.expected_version)
    _user(db, ctx, payload.owner_user_id)
    decisions = _related(db, ctx, meeting_id, "decisions")
    if not any(str(item["id"]) == payload.decision_id and item["payload"].get("action_required") for item in decisions):
        raise HTTPException(422, "Actions must link to a decision that requires follow-up.")
    return _append(db, ctx, row, "actions", title=payload.title, description=payload.description,
                   data={"decision_id": payload.decision_id}, request=request,
                   owner=payload.owner_user_id, due_date=payload.due_date)


@router.post("/meetings/{meeting_id}/submit")
def submit_meeting(
    meeting_id: str, payload: Transition, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.management_review.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _meeting(db, ctx, meeting_id, lock=True)
    _version(row, payload.expected_version)
    if row["status"] != "DRAFT":
        raise HTTPException(409, "Only a draft management review can be submitted.")
    items = {kind: _related(db, ctx, meeting_id, kind) for kind in ("inputs", "minutes", "decisions", "actions")}
    if not all(items[kind] for kind in ("inputs", "minutes", "decisions")):
        raise HTTPException(409, "Source-backed inputs, minutes and decisions are required before submission.")
    required = {str(item["id"]) for item in items["decisions"] if item["payload"].get("action_required")}
    assigned = {item["payload"].get("decision_id") for item in items["actions"]}
    if required - assigned:
        raise HTTPException(409, "Every decision requiring corrective follow-up needs an accountable action.")
    updated = _bump(db, ctx, row, status="PENDING_APPROVAL")
    _activity(db, ctx, updated, "management_review_submitted", request, {"rationale": payload.rationale})
    db.commit()
    return {"meeting": updated}


@router.post("/meetings/{meeting_id}/approve")
def approve_meeting(
    meeting_id: str, payload: Transition, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.management_review.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _meeting(db, ctx, meeting_id, lock=True)
    _version(row, payload.expected_version)
    if row["status"] not in _REVIEW_APPROVABLE:
        raise HTTPException(409, "The review is not awaiting formal approval.")
    if str(row["created_by"]) == str(ctx.user_id):
        raise HTTPException(403, "Independent review approval is required.")
    saved = _insert_record(db, table=_TABLES["approvals"], amo_id=ctx.amo_id,
                           actor_user_id=ctx.user_id, payload={
                               "title": "Management review approved", "status": "APPROVED",
                               "description": payload.rationale,
                               "payload": {"meeting_id": meeting_id, "approved_by": ctx.user_id, "approved_at": _now()},
                           })
    updated = _bump(db, ctx, row, status="APPROVED")
    _activity(db, ctx, updated, "management_review_approved", request, {"approval_id": saved["id"]})
    db.commit()
    return {"meeting": updated, "approval": saved}


@router.post("/meetings/{meeting_id}/actions/{action_id}/complete")
def complete_review_action(
    meeting_id: str, action_id: str, payload: CompleteAction, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.management_review.view")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _meeting(db, ctx, meeting_id, lock=True)
    if row["status"] != "APPROVED":
        raise HTTPException(409, "Management review actions cannot be completed before approval.")
    actions = _related(db, ctx, meeting_id, "actions")
    item = next((a for a in actions if str(a["id"]) == action_id), None)
    if not item:
        raise HTTPException(404, "Action not found for this management review.")
    if str(item["owner_user_id"]) != str(ctx.user_id):
        raise HTTPException(403, "Only the assigned action owner may submit implementation evidence.")
    if item["status"] not in {"ASSIGNED", "REWORK"}:
        raise HTTPException(409, "Action has already been submitted or verified.")
    evidence = [value.strip() for value in payload.evidence_references if value.strip()]
    if len(evidence) != len(payload.evidence_references):
        raise HTTPException(422, "Every evidence reference must identify a retained record.")
    require_evidence_records(db, ctx.amo_id, evidence, required=True)
    details = dict(item["payload"] or {})
    details.update({"implementation_evidence": evidence, "implementation_statement": payload.statement,
                    "implemented_by": ctx.user_id, "implemented_at": _now()})
    db.execute(text(
        "UPDATE qms_management_review_actions SET status='AWAITING_VERIFICATION', "
        "payload=CAST(:payload AS jsonb), updated_at=now(), updated_by=:actor "
        "WHERE id=:id AND amo_id=:amo_id"
    ), {"payload": json.dumps(details), "actor": ctx.user_id,
        "id": action_id, "amo_id": ctx.amo_id})
    updated = _bump(db, ctx, row)
    _activity(db, ctx, updated, "management_review_action_implemented", request, {"action_id": action_id})
    db.commit()
    return {"action_id": action_id, "status": "AWAITING_VERIFICATION", "meeting_version": updated["payload"]["version"]}


@router.post("/meetings/{meeting_id}/actions/{action_id}/verify")
def verify_review_action(
    meeting_id: str, action_id: str, payload: VerifyAction, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.management_review.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _meeting(db, ctx, meeting_id, lock=True)
    if row["status"] != "APPROVED":
        raise HTTPException(409, "Management review is not approved.")
    items = _related(db, ctx, meeting_id, "actions")
    item = next((a for a in items if str(a["id"]) == action_id), None)
    if not item or item["status"] != "AWAITING_VERIFICATION":
        raise HTTPException(409, "Only a submitted action can be independently verified.")
    if str(item["owner_user_id"]) == str(ctx.user_id):
        raise HTTPException(403, "The action owner cannot verify their own implementation.")
    details = dict(item["payload"] or {})
    details.update({"verification_reason": payload.reason, "verified_by": ctx.user_id,
                    "verified_at": _now(), "verification_accepted": payload.accepted})
    status = "VERIFIED" if payload.accepted else "REWORK"
    db.execute(text(
        "UPDATE qms_management_review_actions SET status=:status, "
        "payload=CAST(:payload AS jsonb), updated_at=now(), updated_by=:actor "
        "WHERE id=:id AND amo_id=:amo_id"
    ), {"status": status, "payload": json.dumps(details), "actor": ctx.user_id,
        "id": action_id, "amo_id": ctx.amo_id})
    updated = _bump(db, ctx, row)
    _activity(db, ctx, updated, "management_review_action_verified" if payload.accepted else "management_review_action_rejected",
              request, {"action_id": action_id, "reason": payload.reason})
    db.commit()
    return {"action_id": action_id, "status": status, "meeting_version": updated["payload"]["version"]}


@router.post("/meetings/{meeting_id}/close")
def close_meeting(
    meeting_id: str, payload: Transition, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.management_review.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _meeting(db, ctx, meeting_id, lock=True)
    _version(row, payload.expected_version)
    if row["status"] != "APPROVED":
        raise HTTPException(409, "Only an approved meeting can close.")
    actions = _related(db, ctx, meeting_id, "actions")
    if any(item["status"] != "VERIFIED" for item in actions):
        raise HTTPException(409, "Every assigned action must have independent verified effectiveness before closure.")
    updated = _bump(db, ctx, row, status="CLOSED")
    _activity(db, ctx, updated, "management_review_closed", request, {"rationale": payload.rationale})
    db.commit()
    return {"meeting": updated}
