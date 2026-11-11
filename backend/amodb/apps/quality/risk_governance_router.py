"""Risk / opportunity decisions on canonical QMS tables, never a parallel SMS risk engine.

Assessment labels and rating interpretations are supplied by the tenant's governed
risk matrix, not a platform-wide assumption. Residual acceptance is a human
decision with attributable evidence, not an inferred compliance state.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_read_db, get_write_db
from .canonical_core_router import _insert_record, _log_qms_activity, _table_columns
from .qms_evidence_reference_validation import require_evidence_records
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context

router = APIRouter(prefix="/risk/governance", tags=["QMS governed risk and opportunities"])
_TABLES = {"RISK": "qms_risks", "OPPORTUNITY": "qms_opportunities"}
_CHILD = {"controls": "qms_risk_controls", "actions": "qms_risk_actions"}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateRisk(Strict):
    kind: Literal["RISK", "OPPORTUNITY"]
    title: str = Field(min_length=4, max_length=255)
    description: str = Field(min_length=12, max_length=5000)
    owner_user_id: str = Field(min_length=1, max_length=36)
    reassess_by: date
    source_reference: str | None = Field(default=None, max_length=255)
    source_system: Literal["QUALITY", "SMS_LINKED"] = "QUALITY"


class Versioned(Strict):
    expected_version: int = Field(ge=1)


class Assessment(Versioned):
    assessment_type: Literal["INITIAL", "RESIDUAL"]
    matrix_version: str = Field(min_length=1, max_length=100)
    likelihood: str = Field(min_length=1, max_length=100)
    consequence: str = Field(min_length=1, max_length=100)
    rating: str = Field(min_length=1, max_length=100)
    evidence_basis: str = Field(min_length=12, max_length=8000)
    evidence_record_ids: list[str] = Field(default_factory=list, max_length=30)


class Control(Versioned):
    title: str = Field(min_length=4, max_length=255)
    description: str = Field(min_length=8, max_length=4000)
    effectiveness_measure: str = Field(min_length=8, max_length=4000)


class Treatment(Versioned):
    title: str = Field(min_length=4, max_length=255)
    description: str = Field(min_length=8, max_length=4000)
    owner_user_id: str = Field(min_length=1, max_length=36)
    due_date: date


class AcceptResidual(Versioned):
    reason: str = Field(min_length=16, max_length=8000)
    acceptance_evidence_ids: list[str] = Field(min_length=1, max_length=30)


class CompleteTreatment(Strict):
    statement: str = Field(min_length=8, max_length=5000)
    evidence_record_ids: list[str] = Field(min_length=1, max_length=30)


class VerifyTreatment(Strict):
    accepted: bool
    reason: str = Field(min_length=8, max_length=4000)


class Reopen(Versioned):
    reason: str = Field(min_length=12, max_length=8000)
    reassess_by: date


def _init(db: Session, ctx: TenantContext) -> None:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)


def _user(db: Session, ctx: TenantContext, user_id: str) -> None:
    exists = db.query(account_models.User.id).filter(
        account_models.User.id == user_id,
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).first()
    if not exists:
        raise HTTPException(422, "Risk owner must be an active user of this organisation.")


def _risk(db: Session, ctx: TenantContext, kind: str, risk_id: str, lock=False) -> dict[str, Any]:
    table = _TABLES[kind]
    sql = f"SELECT * FROM {table} WHERE id=:id AND amo_id=:amo_id AND deleted_at IS NULL"
    if lock:
        sql += " FOR UPDATE"
    record = db.execute(text(sql), {"id": risk_id, "amo_id": ctx.amo_id}).mappings().first()
    if not record:
        raise HTTPException(404, "Risk or opportunity record not found in this tenant.")
    return dict(record)


def _version(row: dict[str, Any], expected: int) -> None:
    value = int((row.get("payload") or {}).get("version", 1))
    if value != expected:
        raise HTTPException(409, {"code": "RISK_VERSION_CONFLICT", "expected": expected, "current": value})


def _matrix(db: Session, ctx: TenantContext) -> dict[str, Any]:
    fields = _table_columns(db, "qms_settings")
    projection = "payload, risk_matrix" if "risk_matrix" in fields else "payload"
    row = db.execute(text(
        f"SELECT {projection} FROM qms_settings WHERE amo_id=:amo_id AND deleted_at IS NULL "
        "ORDER BY created_at DESC, id DESC LIMIT 1"
    ), {"amo_id": ctx.amo_id}).mappings().first()
    matrix = ((row.get("risk_matrix") if "risk_matrix" in fields else None)
              or (row.get("payload") or {}).get("risk_matrix")) if row else None
    if not isinstance(matrix, dict):
        return {}
    return matrix


def _require_matrix(db: Session, ctx: TenantContext, payload: Assessment) -> None:
    matrix = _matrix(db, ctx)
    if not matrix or not str(matrix.get("version") or "").strip():
        raise HTTPException(409, "Configure and approve a tenant risk matrix with a governed version before assessment.")
    if str(matrix["version"]) != payload.matrix_version:
        raise HTTPException(409, "Risk matrix version changed. Refresh and reassess against the active tenant matrix.")
    for key, supplied in (("likelihood_levels", payload.likelihood),
                          ("consequence_levels", payload.consequence),
                          ("rating_levels", payload.rating)):
        choices = matrix.get(key)
        if not isinstance(choices, list) or not choices or supplied not in choices:
            raise HTTPException(422, f"Risk {key} must match a configured tenant matrix option.")
    # Do not permit a client to arbitrarily select a low residual rating from
    # the list: the configured, versioned matrix must determine the actual cell.
    # Matrices without a complete, explicit likelihood×consequence mapping
    # remain unavailable for assessment rather than inventing an algorithm.
    cells = matrix.get("rating_cells")
    if not isinstance(cells, dict):
        raise HTTPException(409, "Tenant risk matrix has no governed rating_cells mapping. Configure the lookup before assessment.")
    row = cells.get(payload.likelihood)
    if not isinstance(row, dict) or row.get(payload.consequence) not in matrix["rating_levels"]:
        raise HTTPException(409, "The tenant risk matrix is incomplete for the selected likelihood and consequence.")
    expected_rating = row[payload.consequence]
    if payload.rating != expected_rating:
        raise HTTPException(422, "Submitted rating does not equal the versioned tenant matrix result.")


def _verify_evidence(db: Session, ctx: TenantContext, references: list[str]) -> None:
    require_evidence_records(db, ctx.amo_id, references)


def _children(db: Session, ctx: TenantContext, kind: str, risk_id: str) -> list[dict[str, Any]]:
    table = _CHILD[kind]
    rows = db.execute(text(
        f"SELECT * FROM {table} WHERE amo_id=:amo_id AND deleted_at IS NULL "
        "AND payload->>'parent_id'=:id ORDER BY created_at LIMIT 201"
    ), {"amo_id": ctx.amo_id, "id": risk_id}).mappings().all()
    if len(rows) > 200:
        raise HTTPException(409, "Risk records exceed the bounded read limit. Paginate before approval.")
    return [dict(row) for row in rows]


def _commit(db: Session, ctx: TenantContext, row: dict[str, Any], request: Request,
            action: str, data: dict[str, Any], status: str | None = None,
            *, kind: str, due_date: date | None = None) -> dict[str, Any]:
    payload = dict(row.get("payload") or {})
    payload.update(data)
    payload["version"] = int(payload.get("version", 1)) + 1
    payload["kind"] = kind
    table = _TABLES[kind]
    saved = db.execute(text(
        f"UPDATE {table} SET payload=CAST(:payload AS jsonb), status=:status, "
        "due_date=COALESCE(:due_date, due_date), updated_at=now(), updated_by=:actor "
        "WHERE id=:id AND amo_id=:amo_id AND deleted_at IS NULL RETURNING *"
    ), {"payload": json.dumps(payload), "status": status or row["status"],
        "actor": ctx.user_id, "id": row["id"], "amo_id": ctx.amo_id,
        "due_date": due_date}).mappings().one()
    _log_qms_activity(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id,
                      action=action, module="risk", entity_type=table,
                      entity_id=str(row["id"]), new_value={"version": payload["version"], "change": data},
                      request=request)
    db.commit()
    return dict(saved)


@router.get("/participants")
def risk_participants(
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    rows = db.query(account_models.User).filter(
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).order_by(account_models.User.full_name).limit(100).all()
    return {"items": [{"id": user.id, "name": user.full_name} for user in rows]}


@router.get("/matrix")
def risk_matrix(
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    return {"matrix": _matrix(db, ctx), "authority": "TENANT_QMS_CONFIGURATION"}


@router.get("/records")
def risk_list(
    kind: Literal["RISK", "OPPORTUNITY"] = "RISK",
    limit: int = Query(default=25, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=100000),
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    table = _TABLES[kind]
    params = {"amo_id": ctx.amo_id, "limit": limit, "offset": offset}
    total = db.execute(text(f"SELECT COUNT(*) FROM {table} WHERE amo_id=:amo_id AND deleted_at IS NULL"),
                       params).scalar_one()
    records = db.execute(text(
        f"SELECT * FROM {table} WHERE amo_id=:amo_id AND deleted_at IS NULL "
        "ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
    ), params).mappings().all()
    return {"kind": kind, "items": [dict(row) for row in records], "total": total,
            "limit": limit, "offset": offset}


@router.post("/records", status_code=201)
def create_risk(
    body: CreateRisk, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    _user(db, ctx, body.owner_user_id)
    if body.source_system == "SMS_LINKED" and not body.source_reference:
        raise HTTPException(422, "Reference the SMS-owned record; Quality must not duplicate its risk authority.")
    row = _insert_record(db, table=_TABLES[body.kind], amo_id=ctx.amo_id,
                         actor_user_id=ctx.user_id, payload={
                             "title": body.title, "description": body.description,
                             "owner_user_id": body.owner_user_id, "status": "IDENTIFIED",
                             "due_date": body.reassess_by,
                             "payload": {"kind": body.kind, "version": 1, "source_system": body.source_system,
                                         "source_reference": body.source_reference, "assessment_history": []},
                         })
    _log_qms_activity(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id,
                      action="risk_identified", module="risk",
                      entity_type=_TABLES[body.kind], entity_id=str(row["id"]),
                      new_value=row, request=request)
    db.commit()
    return {"record": row}


@router.get("/records/{kind}/{risk_id}")
def risk_detail(
    kind: Literal["RISK", "OPPORTUNITY"], risk_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _risk(db, ctx, kind, risk_id)
    return {"record": row, "controls": _children(db, ctx, "controls", risk_id),
            "actions": _children(db, ctx, "actions", risk_id)}


@router.post("/records/{kind}/{risk_id}/assess")
def assess_risk(
    kind: Literal["RISK", "OPPORTUNITY"], risk_id: str, body: Assessment, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _risk(db, ctx, kind, risk_id, lock=True)
    _version(row, body.expected_version)
    _require_matrix(db, ctx, body)
    _verify_evidence(db, ctx, body.evidence_record_ids)
    existing = list((row["payload"] or {}).get("assessment_history") or [])
    if row["status"] in {"ACCEPTED", "CLOSED"}:
        raise HTTPException(409, "Accepted risk cannot be altered without governed reassessment.")
    if body.assessment_type == "RESIDUAL" and not _children(db, ctx, "controls", risk_id):
        raise HTTPException(409, "Record active treatment controls before asserting a residual assessment.")
    existing.append({
        "type": body.assessment_type, "matrix_version": body.matrix_version,
        "likelihood": body.likelihood, "consequence": body.consequence, "rating": body.rating,
        "basis": body.evidence_basis, "evidence_record_ids": body.evidence_record_ids,
        "actor_user_id": ctx.user_id, "recorded_at": datetime.now(timezone.utc).isoformat(),
    })
    updated = _commit(db, ctx, row, request, "risk_assessed",
                      {"assessment_history": existing}, "ASSESSED" if body.assessment_type == "INITIAL" else "RESIDUAL_PENDING", kind=kind)
    return {"record": updated}


@router.post("/records/{kind}/{risk_id}/controls")
def add_risk_control(
    kind: Literal["RISK", "OPPORTUNITY"], risk_id: str, body: Control, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _risk(db, ctx, kind, risk_id, lock=True)
    _version(row, body.expected_version)
    if row["status"] not in {"IDENTIFIED", "ASSESSED", "TREATING"}:
        raise HTTPException(409, "Control changes require an identified, assessed or active treatment risk.")
    child = _insert_record(db, table=_CHILD["controls"], amo_id=ctx.amo_id,
                           actor_user_id=ctx.user_id, payload={
                               "title": body.title, "description": body.description, "status": "ACTIVE",
                               "payload": {"parent_id": risk_id, "kind": kind, "effectiveness_measure": body.effectiveness_measure},
                           })
    updated = _commit(db, ctx, row, request, "risk_control_recorded", {"last_control_id": str(child["id"])}, "TREATING", kind=kind)
    return {"record": updated, "control": child}


@router.post("/records/{kind}/{risk_id}/actions")
def add_treatment(
    kind: Literal["RISK", "OPPORTUNITY"], risk_id: str, body: Treatment, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _risk(db, ctx, kind, risk_id, lock=True)
    _version(row, body.expected_version)
    _user(db, ctx, body.owner_user_id)
    if row["status"] not in {"ASSESSED", "TREATING"}:
        raise HTTPException(409, "Treatment requires an assessed risk with an active action period.")
    child = _insert_record(db, table=_CHILD["actions"], amo_id=ctx.amo_id,
                           actor_user_id=ctx.user_id, payload={
                               "title": body.title, "description": body.description, "status": "OPEN",
                               "owner_user_id": body.owner_user_id, "due_date": body.due_date,
                               "payload": {"parent_id": risk_id, "kind": kind},
                           })
    updated = _commit(db, ctx, row, request, "risk_treatment_assigned", {"last_action_id": str(child["id"])}, "TREATING", kind=kind)
    return {"record": updated, "action": child}


@router.post("/records/{kind}/{risk_id}/actions/{action_id}/complete")
def complete_treatment(
    kind: Literal["RISK", "OPPORTUNITY"], risk_id: str, action_id: str,
    body: CompleteTreatment, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.view")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _risk(db, ctx, kind, risk_id, lock=True)
    if row["status"] not in {"TREATING", "RESIDUAL_PENDING"}:
        raise HTTPException(409, "The risk must be in governed treatment.")
    item = next((item for item in _children(db, ctx, "actions", risk_id) if str(item["id"]) == action_id), None)
    if not item:
        raise HTTPException(404, "Treatment action not found in this tenant and parent risk.")
    if str(item["owner_user_id"]) != str(ctx.user_id):
        raise HTTPException(403, "Only the action owner may submit treatment evidence.")
    if item["status"] not in {"OPEN", "REWORK"}:
        raise HTTPException(409, "Treatment action is not open for implementation.")
    _verify_evidence(db, ctx, body.evidence_record_ids)
    data = dict(item.get("payload") or {})
    data.update({"implemented_by": ctx.user_id, "implemented_at": datetime.now(timezone.utc).isoformat(),
                 "statement": body.statement, "evidence_record_ids": body.evidence_record_ids})
    db.execute(text(
        "UPDATE qms_risk_actions SET status='AWAITING_VERIFICATION', payload=CAST(:payload AS jsonb), "
        "updated_at=now(), updated_by=:actor WHERE id=:id AND amo_id=:amo_id"
    ), {"payload": json.dumps(data), "actor": ctx.user_id, "id": action_id, "amo_id": ctx.amo_id})
    updated = _commit(db, ctx, row, request, "risk_treatment_implemented",
                      {"last_implementation_action_id": action_id}, kind=kind)
    return {"action_id": action_id, "status": "AWAITING_VERIFICATION", "risk_version": updated["payload"]["version"]}


@router.post("/records/{kind}/{risk_id}/actions/{action_id}/verify")
def verify_treatment(
    kind: Literal["RISK", "OPPORTUNITY"], risk_id: str, action_id: str,
    body: VerifyTreatment, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _risk(db, ctx, kind, risk_id, lock=True)
    if row["status"] not in {"TREATING", "RESIDUAL_PENDING"}:
        raise HTTPException(409, "Risk must remain active during treatment verification.")
    item = next((item for item in _children(db, ctx, "actions", risk_id) if str(item["id"]) == action_id), None)
    if not item or item["status"] != "AWAITING_VERIFICATION":
        raise HTTPException(409, "Only a submitted treatment action may be verified.")
    if str(item["owner_user_id"]) == str(ctx.user_id):
        raise HTTPException(403, "Treatment owner cannot verify their own action.")
    data = dict(item.get("payload") or {})
    data.update({"verified_by": ctx.user_id, "verified_at": datetime.now(timezone.utc).isoformat(),
                 "verification_reason": body.reason, "verification_accepted": body.accepted})
    next_status = "VERIFIED" if body.accepted else "REWORK"
    db.execute(text(
        "UPDATE qms_risk_actions SET status=:status, payload=CAST(:payload AS jsonb), "
        "updated_at=now(), updated_by=:actor WHERE id=:id AND amo_id=:amo_id"
    ), {"status": next_status, "payload": json.dumps(data), "actor": ctx.user_id,
        "id": action_id, "amo_id": ctx.amo_id})
    updated = _commit(db, ctx, row, request, "risk_treatment_verified" if body.accepted else "risk_treatment_rejected",
                      {"last_verification_action_id": action_id}, kind=kind)
    return {"action_id": action_id, "status": next_status, "risk_version": updated["payload"]["version"]}


@router.post("/records/{kind}/{risk_id}/accept")
def accept_residual(
    kind: Literal["RISK", "OPPORTUNITY"], risk_id: str, body: AcceptResidual, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _risk(db, ctx, kind, risk_id, lock=True)
    _version(row, body.expected_version)
    if row["status"] != "RESIDUAL_PENDING":
        raise HTTPException(409, "A current residual assessment is required for acceptance.")
    if (row.get("payload") or {}).get("source_system") == "SMS_LINKED":
        raise HTTPException(409, "Quality may monitor a linked SMS record but cannot accept a risk owned by Safety Management.")
    if str(row["owner_user_id"]) == str(ctx.user_id) or str(row["created_by"]) == str(ctx.user_id):
        raise HTTPException(403, "The risk originator or treatment owner cannot independently accept residual risk.")
    checks = (row.get("payload") or {}).get("assessment_history") or []
    if not checks or checks[-1].get("type") != "RESIDUAL":
        raise HTTPException(409, "Residual assessment evidence is missing.")
    if not body.acceptance_evidence_ids or any(not ref.strip() for ref in body.acceptance_evidence_ids):
        raise HTTPException(422, "Retained evidence IDs are required.")
    _verify_evidence(db, ctx, body.acceptance_evidence_ids)
    treatments = _children(db, ctx, "actions", risk_id)
    if not treatments or any(action["status"] != "VERIFIED" for action in treatments):
        raise HTTPException(409, "Residual acceptance requires at least one implemented and independently verified treatment action.")
    return {"record": _commit(db, ctx, row, request, "risk_residual_accepted",
                              {"accepted_by": ctx.user_id, "accepted_at": datetime.now(timezone.utc).isoformat(),
                               "acceptance_reason": body.reason, "acceptance_evidence_ids": body.acceptance_evidence_ids},
                              "ACCEPTED", kind=kind)}


@router.post("/records/{kind}/{risk_id}/reassess")
def reopen_risk(
    kind: Literal["RISK", "OPPORTUNITY"], risk_id: str, body: Reopen, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _risk(db, ctx, kind, risk_id, lock=True)
    _version(row, body.expected_version)
    if row["status"] not in {"ACCEPTED", "RESIDUAL_PENDING", "ASSESSED", "TREATING"}:
        raise HTTPException(409, "Only assessed or accepted risks can be reopened for reassessment.")
    data = {"reopened_by": ctx.user_id, "reopen_reason": body.reason,
            "reassess_by": body.reassess_by.isoformat(),
            "previous_acceptance": (row.get("payload") or {}).get("accepted_at")}
    updated = _commit(db, ctx, row, request, "risk_reassessment_opened", data, "IDENTIFIED",
                      kind=kind, due_date=body.reassess_by)
    return {"record": updated}
