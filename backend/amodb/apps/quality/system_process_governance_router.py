"""Governed Quality process definitions and independent performance reviews.

The process is the canonical qms_processes record. Its quality objectives are
qms_quality_objectives, while periodic measurement records have an additive
tenant-scoped child table. Process changes remain with the authorised change
workflow, never arbitrary generic table edits.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_read_db, get_write_db
from .canonical_core_router import _insert_record, _log_qms_activity
from .qms_evidence_reference_validation import require_evidence_records
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context

router = APIRouter(prefix="/system/governance", tags=["QMS process governance"])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Metric(Strict):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_-]{1,40}$")
    title: str = Field(min_length=4, max_length=255)
    measure: str = Field(min_length=8, max_length=4000)
    target: Decimal
    direction: Literal["AT_LEAST", "AT_MOST", "EQUAL"]
    unit: str = Field(min_length=1, max_length=50)


class NewProcess(Strict):
    title: str = Field(min_length=4, max_length=255)
    scope: str = Field(min_length=12, max_length=8000)
    owner_user_id: str = Field(min_length=1, max_length=36)
    process_purpose: str = Field(min_length=8, max_length=4000)
    review_due: date
    metrics: list[Metric] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def codes_are_unique(self):
        codes = [metric.code for metric in self.metrics]
        if len(codes) != len(set(codes)):
            raise ValueError("Process objective codes must be unique.")
        return self


class Decision(Strict):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=12, max_length=4000)


class PerformanceMeasure(Strict):
    objective_id: str = Field(min_length=1, max_length=36)
    actual: Decimal
    explanation: str = Field(min_length=8, max_length=4000)


class SubmitPerformance(Decision):
    period_start: date
    period_end: date
    evidence_ids: list[str] = Field(min_length=1, max_length=30)
    measures: list[PerformanceMeasure] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def valid_period(self):
        if self.period_end < self.period_start:
            raise ValueError("Performance period must end on or after its start.")
        return self


class VerifyPerformance(Strict):
    accepted: bool
    reason: str = Field(min_length=12, max_length=4000)
    evidence_ids: list[str] = Field(min_length=1, max_length=30)
    next_review_due: date | None = None
    followup_owner_user_id: str | None = None
    followup_due_date: date | None = None
    followup_action: str | None = Field(default=None, max_length=4000)


def _init(db: Session, ctx: TenantContext) -> None:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)


def _person(db: Session, ctx: TenantContext, user_id: str) -> None:
    present = db.query(account_models.User.id).filter(
        account_models.User.id == user_id,
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).first()
    if not present:
        raise HTTPException(422, "Process owner must be a human, active tenant user.")


def _row(db: Session, ctx: TenantContext, process_id: str, lock: bool = False) -> dict[str, Any]:
    sql = "SELECT * FROM qms_processes WHERE id=:id AND amo_id=:amo_id AND deleted_at IS NULL"
    if lock:
        sql += " FOR UPDATE"
    result = db.execute(text(sql), {"id": process_id, "amo_id": ctx.amo_id}).mappings().first()
    if result is None:
        raise HTTPException(404, "The process was not found in this tenant.")
    return dict(result)


def _objectives(db: Session, ctx: TenantContext, process_id: str) -> list[dict[str, Any]]:
    records = db.execute(text(
        "SELECT * FROM qms_quality_objectives WHERE amo_id=:amo_id AND deleted_at IS NULL "
        "AND payload->>'process_id'=:process_id AND payload->>'kind'='PROCESS_OBJECTIVE' "
        "ORDER BY created_at, id LIMIT 21"
    ), {"amo_id": ctx.amo_id, "process_id": process_id}).mappings().all()
    if len(records) > 20:
        raise HTTPException(409, "Process objective limit exceeded. Resolve the legacy record mapping.")
    return [dict(record) for record in records]


def _reviews(db: Session, ctx: TenantContext, process_id: str) -> list[dict[str, Any]]:
    records = db.execute(text(
        "SELECT * FROM qms_process_performance_reviews WHERE amo_id=:amo_id "
        "AND process_id=:process_id ORDER BY created_at DESC, id DESC LIMIT 51"
    ), {"amo_id": ctx.amo_id, "process_id": process_id}).mappings().all()
    if len(records) > 50:
        raise HTTPException(409, "Performance review history is too large for this bounded detail view.")
    return [dict(record) for record in records]


def _version(row: dict[str, Any], expected: int) -> None:
    actual = int((row.get("payload") or {}).get("version", 1))
    if actual != expected:
        raise HTTPException(409, {"code": "PROCESS_VERSION_CONFLICT", "expected": expected, "current": actual})


def _update(db: Session, ctx: TenantContext, row: dict[str, Any], status: str, event: str,
            details: dict[str, Any], request: Request, next_review_due: date | None = None) -> dict[str, Any]:
    state = dict(row.get("payload") or {})
    state.update(details)
    state["version"] = int(state.get("version", 1)) + 1
    result = db.execute(text(
        "UPDATE qms_processes SET status=:status, payload=CAST(:payload AS jsonb), "
        "due_date=COALESCE(:due, due_date), updated_at=now(), updated_by=:actor "
        "WHERE id=:id AND amo_id=:amo_id AND deleted_at IS NULL RETURNING *"
    ), {"status": status, "payload": json.dumps(state), "actor": ctx.user_id,
        "due": next_review_due, "id": row["id"], "amo_id": ctx.amo_id}).mappings().one()
    saved = dict(result)
    _log_qms_activity(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id,
                      action=event, module="system", entity_type="qms_processes",
                      entity_id=str(row["id"]), previous_value=row, new_value=saved,
                      request=request)
    db.commit()
    return saved


@router.get("/participants")
def participants(
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    users = db.query(account_models.User).filter(
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).order_by(account_models.User.full_name).limit(100).all()
    return {"items": [{"id": user.id, "name": user.full_name} for user in users]}


@router.get("/processes")
def list_processes(
    limit: int = Query(default=25, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=100000),
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    params = {"amo_id": ctx.amo_id, "limit": limit, "offset": offset}
    total = db.execute(text(
        "SELECT COUNT(*) FROM qms_processes WHERE amo_id=:amo_id AND deleted_at IS NULL"
    ), params).scalar_one()
    rows = db.execute(text(
        "SELECT * FROM qms_processes WHERE amo_id=:amo_id AND deleted_at IS NULL "
        "ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
    ), params).mappings().all()
    return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.post("/processes", status_code=201)
def create_process(
    body: NewProcess, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    _person(db, ctx, body.owner_user_id)
    process = _insert_record(db, table="qms_processes", amo_id=ctx.amo_id,
                             actor_user_id=ctx.user_id, payload={
                                 "title": body.title, "description": body.scope,
                                 "status": "DRAFT", "owner_user_id": body.owner_user_id,
                                 "due_date": body.review_due,
                                 "payload": {"version": 1, "purpose": body.process_purpose,
                                             "review_due": body.review_due.isoformat(),
                                             "governance": "VERSIONED_OBJECTIVES",
                                             "created_by": ctx.user_id},
                             })
    objectives = []
    for metric in body.metrics:
        objectives.append(_insert_record(db, table="qms_quality_objectives",
                                         amo_id=ctx.amo_id, actor_user_id=ctx.user_id, payload={
                                             "title": metric.title, "description": metric.measure,
                                             "status": "DRAFT", "owner_user_id": body.owner_user_id,
                                             "payload": {"kind": "PROCESS_OBJECTIVE",
                                                         "process_id": str(process["id"]), "code": metric.code,
                                                         "target": str(metric.target), "direction": metric.direction,
                                                         "unit": metric.unit},
                                         }))
    _log_qms_activity(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id,
                      action="qms_process_created_with_objectives", module="system",
                      entity_type="qms_processes", entity_id=str(process["id"]),
                      new_value={"process": process, "objective_ids": [x["id"] for x in objectives]}, request=request)
    db.commit()
    return {"process": process, "objectives": objectives}


@router.get("/processes/{process_id}")
def process_detail(
    process_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    return {"process": _row(db, ctx, process_id),
            "objectives": _objectives(db, ctx, process_id),
            "reviews": _reviews(db, ctx, process_id)}


@router.post("/processes/{process_id}/submit")
def submit_process(
    process_id: str, body: Decision, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _row(db, ctx, process_id, lock=True)
    _version(row, body.expected_version)
    if row["status"] != "DRAFT" or not _objectives(db, ctx, process_id):
        raise HTTPException(409, "Submit a draft with at least one attributable metric and owner.")
    updated = _update(db, ctx, row, "PENDING_APPROVAL", "qms_process_submitted",
                      {"submission_reason": body.reason, "submitted_by": ctx.user_id}, request)
    return {"process": updated}


@router.post("/processes/{process_id}/approve")
def approve_process(
    process_id: str, body: Decision, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _row(db, ctx, process_id, lock=True)
    _version(row, body.expected_version)
    if row["status"] != "PENDING_APPROVAL":
        raise HTTPException(409, "Process is not awaiting governed approval.")
    if str(ctx.user_id) in {str(row["owner_user_id"]), str(row["created_by"])}:
        raise HTTPException(403, "The process originator or owner cannot independently approve it.")
    for item in _objectives(db, ctx, process_id):
        db.execute(text(
            "UPDATE qms_quality_objectives SET status='ACTIVE', updated_at=now(), updated_by=:actor "
            "WHERE amo_id=:amo_id AND id=:id AND status='DRAFT'"
        ), {"amo_id": ctx.amo_id, "id": item["id"], "actor": ctx.user_id})
    saved = _update(db, ctx, row, "ACTIVE", "qms_process_approved",
                    {"approval": {"approved_by": ctx.user_id, "at": datetime.now(timezone.utc).isoformat(),
                                  "reason": body.reason}}, request)
    return {"process": saved}


@router.post("/processes/{process_id}/reviews", status_code=201)
def submit_review(
    process_id: str, body: SubmitPerformance, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.view")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _row(db, ctx, process_id, lock=True)
    _version(row, body.expected_version)
    if row["status"] != "ACTIVE":
        raise HTTPException(409, "A process must be independently approved before performance review.")
    if str(row["owner_user_id"]) != str(ctx.user_id):
        raise HTTPException(403, "Only the accountable process owner may submit performance evidence.")
    require_evidence_records(db, ctx.amo_id, body.evidence_ids, required=True)
    objectives = _objectives(db, ctx, process_id)
    index = {str(item["id"]): item for item in objectives}
    if len(body.measures) != len(index) or {item.objective_id for item in body.measures} != set(index):
        raise HTTPException(422, "The review must assess every current approved process objective exactly once.")
    measurements = []
    for entry in body.measures:
        item = index[entry.objective_id]
        defined = item["payload"]
        target = Decimal(str(defined["target"]))
        passed = {
            "AT_LEAST": entry.actual >= target,
            "AT_MOST": entry.actual <= target,
            "EQUAL": entry.actual == target,
        }[defined["direction"]]
        measurements.append({
            "objective_id": entry.objective_id, "code": defined["code"],
            "actual": str(entry.actual), "target": str(target), "unit": defined["unit"],
            "direction": defined["direction"], "target_met": passed,
            "explanation": entry.explanation,
        })
    inserted = db.execute(text(
        "INSERT INTO qms_process_performance_reviews "
        "(id, amo_id, process_id, owner_user_id, period_start, period_end, "
        "status, measurements, evidence_ids, owner_reason, created_by, created_at) "
        "VALUES (:id,:amo_id,:process_id,:owner,:start,:end,'PENDING_VERIFICATION',"
        "CAST(:measures AS jsonb),CAST(:evidence AS jsonb),:reason,:created_by,NOW()) RETURNING *"
    ), {
        "id": str(uuid4()), "amo_id": ctx.amo_id, "process_id": process_id,
        "owner": ctx.user_id, "start": body.period_start, "end": body.period_end,
        "measures": json.dumps(measurements), "evidence": json.dumps(body.evidence_ids),
        "reason": body.reason, "created_by": ctx.user_id,
    }).mappings().one()
    saved = _update(db, ctx, row, "ACTIVE", "qms_process_performance_submitted",
                    {"last_review_id": str(inserted["id"])}, request)
    return {"review": dict(inserted), "process": saved}


@router.post("/processes/{process_id}/reviews/{review_id}/verify")
def verify_review(
    process_id: str, review_id: str, body: VerifyPerformance, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _row(db, ctx, process_id, lock=True)
    if row["status"] != "ACTIVE":
        raise HTTPException(409, "The process is not active.")
    review = db.execute(text(
        "SELECT * FROM qms_process_performance_reviews "
        "WHERE id=:id AND amo_id=:amo_id AND process_id=:process_id FOR UPDATE"
    ), {"id": review_id, "amo_id": ctx.amo_id, "process_id": process_id}).mappings().first()
    if not review or review["status"] != "PENDING_VERIFICATION":
        raise HTTPException(409, "Only unverified process reviews may be independently decided.")
    if str(ctx.user_id) in {str(row["owner_user_id"]), str(review["created_by"])}:
        raise HTTPException(403, "The performance author cannot independently verify their own measurements.")
    require_evidence_records(db, ctx.amo_id, body.evidence_ids, required=True)
    missed = [item for item in review["measurements"] if not item["target_met"]]
    if body.accepted and missed:
        if not body.followup_owner_user_id or not body.followup_due_date or not body.followup_action:
            raise HTTPException(409, "Unmet process objectives require an accountable follow-up task and due date.")
        _person(db, ctx, body.followup_owner_user_id)
        followup = _insert_record(db, table="qms_tasks", amo_id=ctx.amo_id,
                                  actor_user_id=ctx.user_id, payload={
                                      "title": "Follow-up: process objectives not met",
                                      "description": body.followup_action,
                                      "owner_user_id": body.followup_owner_user_id,
                                      "due_date": body.followup_due_date,
                                      "status": "OPEN",
                                      "payload": {"source": "PROCESS_REVIEW", "process_id": process_id,
                                                  "performance_review_id": review_id,
                                                  "unmet_objective_ids": [item["objective_id"] for item in missed]},
                                  })
    else:
        followup = None
    if body.accepted and not body.next_review_due:
        raise HTTPException(422, "A verified review requires the next process review due date.")
    db.execute(text(
        "UPDATE qms_process_performance_reviews SET status=:status, reviewed_by=:actor, "
        "review_reason=:reason, verification_evidence_ids=CAST(:evidence AS jsonb), "
        "reviewed_at=now() WHERE id=:id AND amo_id=:amo_id AND process_id=:process_id"
    ), {
        "status": "VERIFIED" if body.accepted else "REWORK",
        "actor": ctx.user_id, "reason": body.reason, "evidence": json.dumps(body.evidence_ids),
        "id": review_id, "amo_id": ctx.amo_id, "process_id": process_id,
    })
    updated = _update(
        db, ctx, row, "ACTIVE", "qms_process_performance_verified" if body.accepted else "qms_process_performance_rejected",
        {"last_review_decision": {"review_id": review_id, "accepted": body.accepted,
                                  "verified_by": ctx.user_id, "verified_at": datetime.now(timezone.utc).isoformat(),
                                  "followup_task_id": str(followup["id"]) if followup else None}},
        request, next_review_due=body.next_review_due if body.accepted else None,
    )
    return {"process": updated, "review_status": "VERIFIED" if body.accepted else "REWORK",
            "followup_task_id": str(followup["id"]) if followup else None}
