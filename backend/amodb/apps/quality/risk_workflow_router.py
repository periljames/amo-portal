"""Source-backed Quality risk and opportunities lifecycle on canonical QMS tables.

This is *not* an SMS risk authority. Escalation to SMS requires the safety owner
to manage the safety decision; Quality cannot override SMS with a QMS acceptance.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_read_db, get_write_db
from .canonical_core_router import _insert_record, _log_qms_activity
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context

router = APIRouter(prefix="/risk", tags=["QMS governed risk"])

_SOURCE_TABLES = {
    "AUDIT": "qms_audits",
    "CAR": "quality_cars",
    "FINDING": "qms_findings",
    "PROCESS": "qms_processes",
    "SUPPLIER": "qms_suppliers",
    "MANUAL": "manuals",
}
_RISK_STATUSES = {"DRAFT", "TREATMENT", "PENDING_ACCEPTANCE", "ACCEPTED", "MONITORING"}
_INTEGRITY_FIELDS = {"status", "payload", "owner_user_id", "title"}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NewRisk(Strict):
    title: str = Field(min_length=4, max_length=255)
    description: str = Field(min_length=12, max_length=8000)
    owner_user_id: str = Field(min_length=1, max_length=36)
    source_type: Literal["AUDIT", "CAR", "FINDING", "PROCESS", "SUPPLIER", "MANUAL"]
    source_id: str = Field(min_length=1, max_length=80)
    consequence: str = Field(min_length=8, max_length=4000)
    likelihood: int = Field(ge=1, le=5)
    severity: int = Field(ge=1, le=5)
    assessment_basis: str = Field(min_length=12, max_length=4000)
    safety_boundary: Literal["QUALITY_ONLY", "SMS_ESCALATION_REQUIRED"] = "QUALITY_ONLY"


class ChangeRisk(Strict):
    expected_version: int = Field(ge=1)
    likelihood: int = Field(ge=1, le=5)
    severity: int = Field(ge=1, le=5)
    consequence: str = Field(min_length=8, max_length=4000)
    assessment_basis: str = Field(min_length=12, max_length=4000)
    reason_for_reassessment: str = Field(min_length=8, max_length=4000)


class RiskControl(Strict):
    expected_version: int = Field(ge=1)
    title: str = Field(min_length=4, max_length=255)
    description: str = Field(min_length=8, max_length=8000)
    owner_user_id: str = Field(min_length=1, max_length=36)
    due_date: date
    expected_outcome: str = Field(min_length=8, max_length=4000)


class ControlEvidence(Strict):
    effective: bool
    rationale: str = Field(min_length=8, max_length=4000)
    evidence_id: str = Field(min_length=1, max_length=80)


class SubmitResidual(Strict):
    expected_version: int = Field(ge=1)
    residual_likelihood: int = Field(ge=1, le=5)
    residual_severity: int = Field(ge=1, le=5)
    treatment_summary: str = Field(min_length=12, max_length=8000)
    policy_reference: str = Field(min_length=4, max_length=255)
    evidence_id: str = Field(min_length=1, max_length=80)


class RiskDecision(Strict):
    expected_version: int = Field(ge=1)
    accept: bool
    rationale: str = Field(min_length=12, max_length=8000)
    evidence_id: str = Field(min_length=1, max_length=80)


class RiskReview(Strict):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=12, max_length=4000)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _init(db: Session, ctx: TenantContext) -> None:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)


def _user(db: Session, ctx: TenantContext, user_id: str) -> None:
    present = db.query(account_models.User.id).filter(
        account_models.User.id == user_id,
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).first()
    if not present:
        raise HTTPException(422, "Risk owner is not an active person in this organisation.")


def _source(db: Session, ctx: TenantContext, kind: str, source_id: str) -> None:
    table = _SOURCE_TABLES[kind]
    found = db.execute(text(
        f"SELECT id FROM {table} WHERE CAST(id AS text) = :id AND amo_id = :amo_id"
    ), {"id": source_id, "amo_id": ctx.amo_id}).first()
    if not found:
        raise HTTPException(422, "Risk source is unavailable or belongs to another tenant.")


def _evidence(db: Session, ctx: TenantContext, evidence_id: str) -> None:
    found = db.execute(text(
        "SELECT id FROM qms_evidence_files WHERE CAST(id AS text)=:id "
        "AND amo_id=:amo_id AND deleted_at IS NULL"
    ), {"id": evidence_id, "amo_id": ctx.amo_id}).first()
    if not found:
        raise HTTPException(422, "The retained evidence record was not found for this tenant.")


def _risk(db: Session, ctx: TenantContext, risk_id: str, lock: bool = False) -> dict[str, Any]:
    sql = "SELECT * FROM qms_risks WHERE id=:id AND amo_id=:amo_id AND deleted_at IS NULL"
    if lock:
        sql += " FOR UPDATE"
    row = db.execute(text(sql), {"id": risk_id, "amo_id": ctx.amo_id}).mappings().first()
    if row is None:
        raise HTTPException(404, "Risk record not found for this organisation.")
    return dict(row)


def _controls(db: Session, ctx: TenantContext, risk_id: str) -> list[dict[str, Any]]:
    results = db.execute(text(
        "SELECT * FROM qms_risk_controls WHERE amo_id=:amo_id AND deleted_at IS NULL "
        "AND payload ->> 'risk_id' = :risk_id ORDER BY created_at, id LIMIT 251"
    ), {"amo_id": ctx.amo_id, "risk_id": risk_id}).mappings().all()
    if len(results) > 250:
        raise HTTPException(409, "Risk control list exceeds the current verified bound.")
    return [dict(result) for result in results]


def _version(row: dict[str, Any], expected: int) -> None:
    current = int((row["payload"] or {}).get("version", 1))
    if current != expected:
        raise HTTPException(409, {"code": "RISK_VERSION_CONFLICT", "expected": expected, "current": current})


def _save(db: Session, ctx: TenantContext, row: dict[str, Any], data: dict[str, Any],
          status: str | None, request: Request, event: str) -> dict[str, Any]:
    current = dict(row["payload"] or {})
    current.update(data)
    current["version"] = int(current.get("version", 1)) + 1
    result = db.execute(text(
        "UPDATE qms_risks SET payload=CAST(:payload AS jsonb), status=:status, "
        "updated_at=now(), updated_by=:actor WHERE id=:id AND amo_id=:amo_id "
        "AND deleted_at IS NULL RETURNING *"
    ), {
        "payload": json.dumps(current), "status": status or row["status"],
        "actor": ctx.user_id, "amo_id": ctx.amo_id, "id": row["id"],
    }).mappings().one()
    saved = dict(result)
    _log_qms_activity(
        db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id,
        action=event, module="risk", entity_type="qms_risks",
        entity_id=str(row["id"]), previous_value=row, new_value=saved,
        request=request,
    )
    db.commit()
    return saved


@router.get("/register")
def list_risks(
    limit: int = Query(default=25, ge=1, le=50), offset: int = Query(default=0, ge=0, le=100000),
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    params = {"amo_id": ctx.amo_id, "limit": limit, "offset": offset}
    count = db.execute(text(
        "SELECT COUNT(*) FROM qms_risks WHERE amo_id=:amo_id AND deleted_at IS NULL"
    ), params).scalar_one()
    rows = db.execute(text(
        "SELECT * FROM qms_risks WHERE amo_id=:amo_id AND deleted_at IS NULL "
        "ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
    ), params).mappings().all()
    return {"items": [dict(row) for row in rows], "total": count, "limit": limit, "offset": offset}


@router.get("/sources")
def list_sources(
    source_type: Literal["AUDIT", "CAR", "FINDING", "PROCESS", "SUPPLIER", "MANUAL"],
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    table = _SOURCE_TABLES[source_type]
    rows = db.execute(text(
        f"SELECT id, title, name FROM {table} WHERE amo_id=:amo_id ORDER BY id DESC LIMIT 50"
    ), {"amo_id": ctx.amo_id}).mappings().all()
    return {"items": [{"id": str(row["id"]), "title": row.get("title") or row.get("name") or str(row["id"])}
                      for row in rows]}


@router.get("/owners")
def list_owners(
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    rows = db.query(account_models.User).filter(
        account_models.User.amo_id == ctx.amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).order_by(account_models.User.full_name).limit(100).all()
    return {"items": [{"id": row.id, "name": row.full_name} for row in rows]}


@router.post("/register", status_code=201)
def create_risk(
    payload: NewRisk, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    _user(db, ctx, payload.owner_user_id)
    _source(db, ctx, payload.source_type, payload.source_id)
    score = payload.likelihood * payload.severity
    row = _insert_record(db, table="qms_risks", amo_id=ctx.amo_id,
                         actor_user_id=ctx.user_id, payload={
                             "title": payload.title, "description": payload.description,
                             "status": "DRAFT", "owner_user_id": payload.owner_user_id,
                             "payload": {
                                 "version": 1, "source_type": payload.source_type, "source_id": payload.source_id,
                                 "safety_boundary": payload.safety_boundary,
                                 "assessment": {"likelihood": payload.likelihood, "severity": payload.severity,
                                                "score": score, "consequence": payload.consequence,
                                                "basis": payload.assessment_basis, "assessed_by": ctx.user_id,
                                                "assessed_at": _utc()},
                                 "assessment_history": [],
                             },
                         })
    _log_qms_activity(db, amo_id=ctx.amo_id, actor_user_id=ctx.user_id,
                      action="qms_risk_created", module="risk", entity_type="qms_risks",
                      entity_id=str(row["id"]), new_value=row, request=request)
    db.commit()
    return {"risk": row}


@router.get("/register/{risk_id}")
def risk_detail(
    risk_id: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    _init(db, ctx)
    return {"risk": _risk(db, ctx, risk_id), "controls": _controls(db, ctx, risk_id)}


@router.post("/register/{risk_id}/controls", status_code=201)
def add_control(
    risk_id: str, payload: RiskControl, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _risk(db, ctx, risk_id, lock=True)
    _version(row, payload.expected_version)
    if row["status"] not in {"DRAFT", "TREATMENT"}:
        raise HTTPException(409, "Add controls before residual acceptance is requested.")
    _user(db, ctx, payload.owner_user_id)
    record = _insert_record(db, table="qms_risk_controls", amo_id=ctx.amo_id,
                            actor_user_id=ctx.user_id, payload={
                                "title": payload.title, "description": payload.description,
                                "status": "ASSIGNED", "owner_user_id": payload.owner_user_id,
                                "due_date": payload.due_date,
                                "payload": {"risk_id": risk_id, "expected_outcome": payload.expected_outcome,
                                            "created_at": _utc(), "created_by": ctx.user_id},
                            })
    risk = _save(db, ctx, row, {}, "TREATMENT", request, "qms_risk_control_assigned")
    return {"control": record, "risk": risk}


@router.post("/register/{risk_id}/controls/{control_id}/verify")
def verify_control(
    risk_id: str, control_id: str, payload: ControlEvidence, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _risk(db, ctx, risk_id, lock=True)
    if row["status"] not in {"DRAFT", "TREATMENT"}:
        raise HTTPException(409, "Controls cannot change during or after residual acceptance.")
    control = next((x for x in _controls(db, ctx, risk_id) if str(x["id"]) == control_id), None)
    if control is None:
        raise HTTPException(404, "Control is not linked to this risk.")
    if str(control["owner_user_id"]) == str(ctx.user_id):
        raise HTTPException(403, "A control owner cannot independently verify their own control.")
    if control["status"] != "ASSIGNED":
        raise HTTPException(409, "Control has already been verified or rejected.")
    _evidence(db, ctx, payload.evidence_id)
    state = "VERIFIED" if payload.effective else "INEFFECTIVE"
    data = dict(control["payload"] or {})
    data["verification"] = {"evidence_id": payload.evidence_id, "effective": payload.effective,
                            "rationale": payload.rationale, "verified_by": ctx.user_id, "verified_at": _utc()}
    db.execute(text(
        "UPDATE qms_risk_controls SET status=:status, payload=CAST(:payload AS jsonb), "
        "updated_at=now(), updated_by=:actor WHERE id=:id AND amo_id=:amo_id"
    ), {"status": state, "payload": json.dumps(data), "actor": ctx.user_id,
        "id": control_id, "amo_id": ctx.amo_id})
    saved = _save(db, ctx, row, {}, "TREATMENT", request, "qms_risk_control_verified")
    return {"risk": saved, "control_status": state}


@router.post("/register/{risk_id}/reassess")
def reassess(
    risk_id: str, payload: ChangeRisk, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _risk(db, ctx, risk_id, lock=True)
    _version(row, payload.expected_version)
    if row["status"] not in _RISK_STATUSES:
        raise HTTPException(409, "Closed or inactive risk records cannot be reassessed.")
    current = dict(row["payload"] or {})
    previous = current.get("assessment")
    history = list(current.get("assessment_history") or [])
    if len(history) >= 100:
        raise HTTPException(409, "Risk reassessment history requires archival before additional updates.")
    history.append({"previous": previous, "reason": payload.reason_for_reassessment,
                    "changed_at": _utc(), "changed_by": ctx.user_id})
    assessment = {"likelihood": payload.likelihood, "severity": payload.severity,
                  "score": payload.likelihood * payload.severity, "basis": payload.assessment_basis,
                  "consequence": payload.consequence, "assessed_at": _utc(), "assessed_by": ctx.user_id}
    row = _save(db, ctx, row, {"assessment": assessment,
                        "assessment_history": history, "residual_request": None,
                        "residual_decision": None}, "TREATMENT", request, "qms_risk_reassessed")
    return {"risk": row}


@router.post("/register/{risk_id}/submit-residual")
def submit_residual(
    risk_id: str, payload: SubmitResidual, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _risk(db, ctx, risk_id, lock=True)
    _version(row, payload.expected_version)
    if row["status"] not in {"DRAFT", "TREATMENT"}:
        raise HTTPException(409, "Risk is not awaiting a residual decision.")
    if (row["payload"] or {}).get("safety_boundary") == "SMS_ESCALATION_REQUIRED":
        raise HTTPException(409, "Safety management escalation required; Quality cannot accept an SMS risk.")
    controls = _controls(db, ctx, risk_id)
    if not controls or any(control["status"] != "VERIFIED" for control in controls):
        raise HTTPException(409, "Every treatment control must be independently verified before residual-risk submission.")
    _evidence(db, ctx, payload.evidence_id)
    request_snapshot = {"likelihood": payload.residual_likelihood, "severity": payload.residual_severity,
                        "score": payload.residual_likelihood * payload.residual_severity,
                        "treatment_summary": payload.treatment_summary,
                        "policy_reference": payload.policy_reference,
                        "evidence_id": payload.evidence_id, "submitted_by": ctx.user_id,
                        "submitted_at": _utc()}
    risk = _save(db, ctx, row, {"residual_request": request_snapshot},
                 "PENDING_ACCEPTANCE", request, "qms_risk_residual_submitted")
    return {"risk": risk}


@router.post("/register/{risk_id}/decide-residual")
def decide_residual(
    risk_id: str, payload: RiskDecision, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _risk(db, ctx, risk_id, lock=True)
    _version(row, payload.expected_version)
    if row["status"] != "PENDING_ACCEPTANCE":
        raise HTTPException(409, "Risk is not pending acceptance.")
    if str(row["owner_user_id"]) == str(ctx.user_id) or str(row["created_by"]) == str(ctx.user_id):
        raise HTTPException(403, "Risk originator or owner cannot independently approve their own residual risk.")
    _evidence(db, ctx, payload.evidence_id)
    decision = {"accepted": payload.accept, "rationale": payload.rationale,
                "evidence_id": payload.evidence_id, "decided_by": ctx.user_id,
                "decided_at": _utc()}
    saved = _save(db, ctx, row, {"residual_decision": decision},
                  "ACCEPTED" if payload.accept else "TREATMENT", request,
                  "qms_risk_residual_accepted" if payload.accept else "qms_risk_residual_rejected")
    return {"risk": saved}


@router.post("/register/{risk_id}/monitor")
def start_monitoring(
    risk_id: str, payload: RiskReview, request: Request,
    ctx: TenantContext = Depends(require_quality_permission("qms.risk.manage")),
    db: Session = Depends(get_write_db),
) -> dict[str, Any]:
    _init(db, ctx)
    row = _risk(db, ctx, risk_id, lock=True)
    _version(row, payload.expected_version)
    if row["status"] != "ACCEPTED":
        raise HTTPException(409, "Only a formally accepted residual risk can begin monitoring.")
    saved = _save(db, ctx, row, {"monitoring": {"reason": payload.reason,
                "initiated_by": ctx.user_id, "initiated_at": _utc()}},
                "MONITORING", request, "qms_risk_monitoring_started")
    return {"risk": saved}
