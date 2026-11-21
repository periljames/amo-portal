"""Controlled regulator/customer interface on the existing canonical QMS tables.

External communications are never sent automatically. An approved response is
recorded as submitted only with independently retained submission evidence.
Commitment closure is attributable, tenant-scoped and separately verified.
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
from .canonical_core_router import _insert_record, _log_qms_activity
from .qms_evidence_reference_validation import require_evidence_records
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context

router = APIRouter(prefix="/external-interface/governance", tags=["QMS external commitments"])
_KIND = {
    "REGULATOR": "qms_regulator_findings",
    "CUSTOMER": "qms_customer_complaints",
    "AUTHORITY": "qms_authority_correspondence",
}
_CHILD = {
    "responses": "qms_external_responses",
    "commitments": "qms_external_commitments",
}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExternalCreate(Strict):
    kind: Literal["REGULATOR", "CUSTOMER", "AUTHORITY"]
    title: str = Field(min_length=4, max_length=255)
    description: str = Field(min_length=12, max_length=8000)
    source_reference: str = Field(min_length=2, max_length=255)
    received_on: date
    response_due: date
    owner_user_id: str = Field(min_length=1, max_length=36)


class Versioned(Strict):
    expected_version: int = Field(ge=1)


class ResponseCreate(Versioned):
    title: str = Field(min_length=4, max_length=255)
    response_text: str = Field(min_length=30, max_length=12000)
    supporting_evidence_ids: list[str] = Field(default_factory=list, max_length=30)


class ReviewResponse(Versioned):
    response_id: str = Field(min_length=1, max_length=36)
    rationale: str = Field(min_length=12, max_length=4000)


class SendResponse(Versioned):
    response_id: str = Field(min_length=1, max_length=36)
    submitted_on: date
    method: str = Field(min_length=3, max_length=80)
    external_reference: str = Field(min_length=2, max_length=255)
    submission_evidence_ids: list[str] = Field(min_length=1, max_length=30)


class CommitmentCreate(Versioned):
    title: str = Field(min_length=4, max_length=255)
    description: str = Field(min_length=12, max_length=4000)
    owner_user_id: str = Field(min_length=1, max_length=36)
    due_date: date


class CommitmentComplete(Strict):
    implementation_statement: str = Field(min_length=12, max_length=8000)
    evidence_record_ids: list[str] = Field(min_length=1, max_length=30)


class CommitmentVerify(Strict):
    accepted: bool
    reason: str = Field(min_length=12, max_length=4000)


class CloseExternal(Versioned):
    reason: str = Field(min_length=12, max_length=4000)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _init(db: Session, ctx: TenantContext) -> None:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)


def _user(db: Session, ctx: TenantContext, user_id: str) -> None:
    found = db.query(account_models.User.id).filter(
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.id == user_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).first()
    if not found:
        raise HTTPException(422, "The named accountable person is not active in this tenant.")


def _external(db: Session, ctx: TenantContext, kind: str, record_id: str, lock=False) -> dict[str, Any]:
    sql = f"SELECT * FROM {_KIND[kind]} WHERE id=:id AND amo_id=:amo_id AND deleted_at IS NULL"
    if lock:
        sql += " FOR UPDATE"
    result = db.execute(text(sql), {"id": record_id, "amo_id": ctx.amo_id}).mappings().first()
    if not result:
        raise HTTPException(404, "External issue not found in this organisation.")
    return dict(result)


def _version(row: dict[str, Any], expected: int) -> None:
    actual = int((row.get("payload") or {}).get("version", 1))
    if actual != expected:
        raise HTTPException(409, {"code": "EXTERNAL_VERSION_CONFLICT", "expected": expected, "actual": actual})


def _children(db: Session, ctx: TenantContext, kind: str, parent_id: str) -> list[dict[str, Any]]:
    table = _CHILD[kind]
    rows = db.execute(text(
        f"SELECT * FROM {table} WHERE amo_id=:amo_id AND deleted_at IS NULL "
        "AND payload->>'external_id'=:parent_id ORDER BY created_at LIMIT 201"
    ), {"amo_id": ctx.amo_id, "parent_id": parent_id}).mappings().all()
    if len(rows) > 200:
        raise HTTPException(409, "External response or commitment count exceeds the bounded read limit.")
    return [dict(row) for row in rows]


def _bump(db: Session, ctx: TenantContext, row: dict[str, Any], kind: str,
          request: Request, action: str, details: dict[str, Any],
          status: str | None = None) -> dict[str, Any]:
    changes = dict(row.get("payload") or {})
    changes.update(details)
    changes["version"] = int(changes.get("version", 1)) + 1
    updated = db.execute(text(
        f"UPDATE {_KIND[kind]} SET payload=CAST(:payload AS jsonb), status=:status, "
        "updated_at=now(), updated_by=:actor "
        "WHERE id=:id AND amo_id=:amo_id AND deleted_at IS NULL RETURNING *"
    ), {"id": row["id"], "amo_id": ctx.amo_id, "status": status or row["status"],
        "actor": ctx.user_id, "payload": json.dumps(changes)}).mappings().one()
    _log_qms_activity(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id,
                      action=action, module="external-interface", entity_type=_KIND[kind],
                      entity_id=str(row["id"]), new_value={"version": changes["version"], "details": details},
                      request=request)
    db.commit()
    return dict(updated)


@router.get("/participants")
def external_people(
    ctx: TenantContext = Depends(require_quality_permission("qms.finding.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    users = db.query(account_models.User).filter(
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).order_by(account_models.User.full_name).limit(100).all()
    return {"items": [{"id": row.id, "name": row.full_name} for row in users]}


@router.get("/records")
def external_list(
    kind: Literal["REGULATOR", "CUSTOMER", "AUTHORITY"] = "REGULATOR",
    limit: int = Query(default=25, ge=1, le=50), offset: int = Query(default=0, ge=0, le=100000),
    ctx: TenantContext = Depends(require_quality_permission("qms.finding.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    table = _KIND[kind]
    params = {"amo_id": ctx.amo_id, "limit": limit, "offset": offset}
    total = db.execute(text(
        f"SELECT COUNT(*) FROM {table} WHERE amo_id=:amo_id AND deleted_at IS NULL"
    ), params).scalar_one()
    rows = db.execute(text(
        f"SELECT * FROM {table} WHERE amo_id=:amo_id AND deleted_at IS NULL "
        "ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
    ), params).mappings().all()
    return {"kind": kind, "items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.post("/records", status_code=201)
def external_create(
    body: ExternalCreate, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.finding.create")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    _user(db, ctx, body.owner_user_id)
    record = _insert_record(db, table=_KIND[body.kind], amo_id=ctx.amo_id,
                            actor_user_id=ctx.user_id, payload={
                                "title": body.title, "description": body.description,
                                "status": "RECEIVED", "owner_user_id": body.owner_user_id,
                                "due_date": body.response_due,
                                "payload": {"kind": body.kind, "version": 1,
                                            "source_reference": body.source_reference,
                                            "received_on": body.received_on.isoformat()},
                            })
    _log_qms_activity(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id,
                      action="external_issue_received", module="external-interface",
                      entity_type=_KIND[body.kind], entity_id=str(record["id"]),
                      new_value=record, request=request)
    db.commit()
    return {"record": record}


@router.get("/records/{kind}/{record_id}")
def external_detail(
    kind: Literal["REGULATOR", "CUSTOMER", "AUTHORITY"], record_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.finding.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    item = _external(db, ctx, kind, record_id)
    return {"record": item, "responses": _children(db, ctx, "responses", record_id),
            "commitments": _children(db, ctx, "commitments", record_id)}


@router.post("/records/{kind}/{record_id}/responses", status_code=201)
def response_draft(
    kind: Literal["REGULATOR", "CUSTOMER", "AUTHORITY"], record_id: str,
    body: ResponseCreate, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.finding.create")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    parent = _external(db, ctx, kind, record_id, lock=True)
    _version(parent, body.expected_version)
    if parent["status"] not in {"RECEIVED", "RESPONSE_DRAFT"}:
        raise HTTPException(409, "A new external response requires an open received issue.")
    require_evidence_records(db, ctx.amo_id, body.supporting_evidence_ids)
    saved = _insert_record(db, table=_CHILD["responses"], amo_id=ctx.amo_id,
                           actor_user_id=ctx.user_id, payload={
                               "title": body.title, "status": "DRAFT", "description": body.response_text,
                               "payload": {"external_id": record_id, "kind": kind,
                                           "supporting_evidence_ids": body.supporting_evidence_ids},
                           })
    updated = _bump(db, ctx, parent, kind, request, "external_response_drafted",
                    {"last_response_id": str(saved["id"])}, "RESPONSE_DRAFT")
    return {"record": updated, "response": saved}


@router.post("/records/{kind}/{record_id}/approve")
def approve_response(
    kind: Literal["REGULATOR", "CUSTOMER", "AUTHORITY"], record_id: str,
    body: ReviewResponse, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.finding.create")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    parent = _external(db, ctx, kind, record_id, lock=True)
    _version(parent, body.expected_version)
    responses = _children(db, ctx, "responses", record_id)
    response = next((item for item in responses if str(item["id"]) == body.response_id), None)
    if not response or response["status"] != "DRAFT":
        raise HTTPException(409, "Only the current draft response can be approved.")
    if str(parent.get("payload", {}).get("last_response_id")) != str(response["id"]):
        raise HTTPException(409, "Newer response draft exists. Review the latest response.")
    if str(response["created_by"]) == str(ctx.user_id):
        raise HTTPException(403, "Response author cannot approve their own correspondence.")
    data = dict(response.get("payload") or {})
    data.update({"approved_by": ctx.user_id, "approved_at": _now(), "reason": body.rationale})
    db.execute(text(
        "UPDATE qms_external_responses SET status='APPROVED', payload=CAST(:payload AS jsonb), "
        "updated_at=now(), updated_by=:actor WHERE id=:id AND amo_id=:amo_id"
    ), {"id": response["id"], "amo_id": ctx.amo_id, "actor": ctx.user_id, "payload": json.dumps(data)})
    updated = _bump(db, ctx, parent, kind, request, "external_response_approved",
                    {"approved_response_id": str(response["id"])}, "RESPONSE_APPROVED")
    return {"record": updated}


@router.post("/records/{kind}/{record_id}/submit")
def record_submission(
    kind: Literal["REGULATOR", "CUSTOMER", "AUTHORITY"], record_id: str,
    body: SendResponse, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.finding.create")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    parent = _external(db, ctx, kind, record_id, lock=True)
    _version(parent, body.expected_version)
    response = next((item for item in _children(db, ctx, "responses", record_id)
                     if str(item["id"]) == body.response_id), None)
    if parent["status"] != "RESPONSE_APPROVED" or not response or response["status"] != "APPROVED":
        raise HTTPException(409, "Submission proof requires the current independently approved response.")
    if str((parent["payload"] or {}).get("approved_response_id")) != str(response["id"]):
        raise HTTPException(409, "The response to submit is not the approved version.")
    require_evidence_records(db, ctx.amo_id, body.submission_evidence_ids, required=True)
    data = dict(response.get("payload") or {})
    data.update({"submitted_by": ctx.user_id, "submitted_at": _now(),
                 "submitted_on": body.submitted_on.isoformat(),
                 "method": body.method, "external_reference": body.external_reference,
                 "submission_evidence_ids": body.submission_evidence_ids})
    db.execute(text(
        "UPDATE qms_external_responses SET status='SUBMITTED', payload=CAST(:payload AS jsonb), "
        "updated_at=now(), updated_by=:actor WHERE id=:id AND amo_id=:amo_id"
    ), {"id": response["id"], "amo_id": ctx.amo_id, "actor": ctx.user_id, "payload": json.dumps(data)})
    updated = _bump(db, ctx, parent, kind, request, "external_response_submission_recorded",
                    {"submitted_response_id": str(response["id"])}, "RESPONSE_SUBMITTED")
    return {"record": updated}


@router.post("/records/{kind}/{record_id}/commitments", status_code=201)
def create_commitment(
    kind: Literal["REGULATOR", "CUSTOMER", "AUTHORITY"], record_id: str,
    body: CommitmentCreate, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.finding.create")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    parent = _external(db, ctx, kind, record_id, lock=True)
    _version(parent, body.expected_version)
    if parent["status"] != "RESPONSE_SUBMITTED":
        raise HTTPException(409, "Commitments are recorded against a submitted and evidenced response.")
    _user(db, ctx, body.owner_user_id)
    saved = _insert_record(db, table=_CHILD["commitments"], amo_id=ctx.amo_id,
                           actor_user_id=ctx.user_id, payload={
                               "title": body.title, "description": body.description,
                               "status": "OPEN", "owner_user_id": body.owner_user_id,
                               "due_date": body.due_date,
                               "payload": {"external_id": record_id, "kind": kind},
                           })
    updated = _bump(db, ctx, parent, kind, request, "external_commitment_recorded",
                    {"last_commitment_id": str(saved["id"])})
    return {"record": updated, "commitment": saved}


@router.post("/records/{kind}/{record_id}/commitments/{commitment_id}/complete")
def complete_commitment(
    kind: Literal["REGULATOR", "CUSTOMER", "AUTHORITY"], record_id: str,
    commitment_id: str, body: CommitmentComplete, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.finding.view")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    parent = _external(db, ctx, kind, record_id, lock=True)
    if parent["status"] != "RESPONSE_SUBMITTED":
        raise HTTPException(409, "External issue is not awaiting controlled commitment implementation.")
    item = next((item for item in _children(db, ctx, "commitments", record_id)
                 if str(item["id"]) == commitment_id), None)
    if not item:
        raise HTTPException(404, "Commitment not found in this tenant and external issue.")
    if str(item["owner_user_id"]) != str(ctx.user_id):
        raise HTTPException(403, "Only the commitment owner can submit completion evidence.")
    if item["status"] not in {"OPEN", "REWORK"}:
        raise HTTPException(409, "This commitment has already been submitted or verified.")
    require_evidence_records(db, ctx.amo_id, body.evidence_record_ids, required=True)
    data = dict(item.get("payload") or {})
    data.update({"implementation_statement": body.implementation_statement,
                 "evidence_record_ids": body.evidence_record_ids,
                 "implemented_by": ctx.user_id, "implemented_at": _now()})
    db.execute(text(
        "UPDATE qms_external_commitments SET status='AWAITING_VERIFICATION', "
        "payload=CAST(:payload AS jsonb), updated_at=now(), updated_by=:actor "
        "WHERE id=:id AND amo_id=:amo_id"
    ), {"id": commitment_id, "amo_id": ctx.amo_id, "actor": ctx.user_id, "payload": json.dumps(data)})
    updated = _bump(db, ctx, parent, kind, request, "external_commitment_implemented",
                    {"last_implemented_commitment_id": commitment_id})
    return {"record": updated}


@router.post("/records/{kind}/{record_id}/commitments/{commitment_id}/verify")
def verify_commitment(
    kind: Literal["REGULATOR", "CUSTOMER", "AUTHORITY"], record_id: str,
    commitment_id: str, body: CommitmentVerify, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.finding.create")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    parent = _external(db, ctx, kind, record_id, lock=True)
    if parent["status"] != "RESPONSE_SUBMITTED":
        raise HTTPException(409, "External issue is not open for commitment verification.")
    item = next((item for item in _children(db, ctx, "commitments", record_id)
                 if str(item["id"]) == commitment_id), None)
    if not item or item["status"] != "AWAITING_VERIFICATION":
        raise HTTPException(409, "Only submitted commitments can receive an independent decision.")
    if str(item["owner_user_id"]) == str(ctx.user_id):
        raise HTTPException(403, "Commitment owner cannot verify their own implementation.")
    data = dict(item.get("payload") or {})
    next_status = "CLOSED" if body.accepted else "REWORK"
    data.update({"verified_by": ctx.user_id, "verified_at": _now(),
                 "verification_reason": body.reason, "verification_accepted": body.accepted})
    db.execute(text(
        "UPDATE qms_external_commitments SET status=:status, payload=CAST(:payload AS jsonb), "
        "updated_at=now(), updated_by=:actor WHERE id=:id AND amo_id=:amo_id"
    ), {"id": commitment_id, "amo_id": ctx.amo_id, "actor": ctx.user_id,
        "payload": json.dumps(data), "status": next_status})
    updated = _bump(db, ctx, parent, kind, request, "external_commitment_verified" if body.accepted else "external_commitment_rejected",
                    {"last_verified_commitment_id": commitment_id})
    return {"record": updated, "commitment_status": next_status}


@router.post("/records/{kind}/{record_id}/close")
def close_external(
    kind: Literal["REGULATOR", "CUSTOMER", "AUTHORITY"], record_id: str,
    body: CloseExternal, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.finding.create")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    parent = _external(db, ctx, kind, record_id, lock=True)
    _version(parent, body.expected_version)
    if parent["status"] != "RESPONSE_SUBMITTED":
        raise HTTPException(409, "An approved submitted response must exist before closure.")
    if not any(row["status"] == "SUBMITTED" for row in _children(db, ctx, "responses", record_id)):
        raise HTTPException(409, "Submission evidence is not retained for this external issue.")
    if any(row["status"] != "CLOSED" for row in _children(db, ctx, "commitments", record_id)):
        raise HTTPException(409, "Open commitments prevent final closure.")
    if str(parent["created_by"]) == str(ctx.user_id):
        raise HTTPException(403, "Final external issue closure requires independent verification.")
    updated = _bump(db, ctx, parent, kind, request, "external_issue_closed",
                    {"closure_reason": body.reason, "closed_by": ctx.user_id, "closed_at": _now()}, "CLOSED")
    return {"record": updated}
