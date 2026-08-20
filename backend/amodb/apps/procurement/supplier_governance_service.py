from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.quality import models as quality_models

from . import models as procurement_models
from . import schemas as procurement_schemas
from . import service as procurement_service
from . import supplier_governance_models as models
from . import supplier_governance_schemas as schemas


UTC = timezone.utc
APPROVED_EVALUATION_STATES = {"APPROVED", "CONDITIONALLY_APPROVED"}
MUTABLE_EVALUATION_STATES = {"DRAFT", "RETURNED"}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _enum(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _supplier(db: Session, *, amo_id: str, supplier_id: int) -> procurement_models.ProcurementSupplier:
    row = db.query(procurement_models.ProcurementSupplier).filter(
        procurement_models.ProcurementSupplier.amo_id == amo_id,
        procurement_models.ProcurementSupplier.id == supplier_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Supplier was not found in this AMO.")
    return row


def _policy(db: Session, *, amo_id: str, required: bool = True) -> models.SupplierGovernancePolicy | None:
    row = db.query(models.SupplierGovernancePolicy).filter(models.SupplierGovernancePolicy.amo_id == amo_id).first()
    if row is None and required:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "SUPPLIER_GOVERNANCE_NOT_CONFIGURED",
                "message": "Configure the tenant supplier governance policy before starting or approving evaluations.",
            },
        )
    return row


def _evaluation(
    db: Session,
    *,
    amo_id: str,
    evaluation_id: str,
    lock: bool = False,
) -> models.SupplierEvaluation:
    query = db.query(models.SupplierEvaluation).filter(
        models.SupplierEvaluation.amo_id == amo_id,
        models.SupplierEvaluation.id == evaluation_id,
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Supplier evaluation was not found in this AMO.")
    return row


def _template(db: Session, *, amo_id: str, template_id: str) -> models.SupplierEvaluationTemplate:
    row = db.query(models.SupplierEvaluationTemplate).filter(
        models.SupplierEvaluationTemplate.amo_id == amo_id,
        models.SupplierEvaluationTemplate.id == template_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Supplier evaluation template was not found in this AMO.")
    return row


def _snapshot_supplier(supplier: procurement_models.ProcurementSupplier) -> dict[str, Any]:
    return {
        "id": supplier.id,
        "status": _enum(supplier.status),
        "risk_level": _enum(supplier.risk_level),
        "approved_at": supplier.approved_at.isoformat() if supplier.approved_at else None,
        "approved_by_user_id": supplier.approved_by_user_id,
        "suspended_at": supplier.suspended_at.isoformat() if supplier.suspended_at else None,
        "suspension_reason": supplier.suspension_reason,
    }


def _policy_snapshot(policy: models.SupplierGovernancePolicy) -> dict[str, Any]:
    return {
        "policy_id": policy.id,
        "revision_no": policy.revision_no,
        "risk_review_days": dict(policy.risk_review_days or {}),
        "re_evaluation_rules": dict(policy.re_evaluation_rules or {}),
        "require_independent_review": bool(policy.require_independent_review),
        "conditional_approval_allowed": bool(policy.conditional_approval_allowed),
        "effective_from": policy.effective_from.isoformat() if policy.effective_from else None,
    }


def _event(
    db: Session,
    *,
    amo_id: str,
    supplier_id: int,
    action: str,
    actor_user_id: str | None,
    detail: dict[str, Any],
) -> None:
    procurement_service._event(
        db,
        amo_id=amo_id,
        entity_type="supplier_governance",
        entity_id=str(supplier_id),
        action=action,
        actor_user_id=actor_user_id,
        detail=detail,
    )


def read_policy(db: Session, *, amo_id: str) -> models.SupplierGovernancePolicy | None:
    return _policy(db, amo_id=amo_id, required=False)


def update_policy(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.SupplierGovernancePolicyUpdate,
    actor_user_id: str,
) -> models.SupplierGovernancePolicy:
    row = db.query(models.SupplierGovernancePolicy).filter(
        models.SupplierGovernancePolicy.amo_id == amo_id
    ).with_for_update().first()
    values = payload.model_dump(mode="json")
    if row is None:
        row = models.SupplierGovernancePolicy(
            amo_id=amo_id,
            revision_no=1,
            risk_review_days=values["risk_review_days"],
            re_evaluation_rules=values["re_evaluation_rules"],
            require_independent_review=payload.require_independent_review,
            conditional_approval_allowed=payload.conditional_approval_allowed,
            effective_from=payload.effective_from,
            updated_by_user_id=actor_user_id,
        )
        db.add(row)
        action = "POLICY_CONFIGURED"
    else:
        row.revision_no = int(row.revision_no or 0) + 1
        row.risk_review_days = values["risk_review_days"]
        row.re_evaluation_rules = values["re_evaluation_rules"]
        row.require_independent_review = payload.require_independent_review
        row.conditional_approval_allowed = payload.conditional_approval_allowed
        row.effective_from = payload.effective_from
        row.updated_by_user_id = actor_user_id
        action = "POLICY_REVISED"
    db.flush()
    _event(
        db,
        amo_id=amo_id,
        supplier_id=0,
        action=action,
        actor_user_id=actor_user_id,
        detail={"policy_id": row.id, "revision_no": row.revision_no, "snapshot": _policy_snapshot(row)},
    )
    return row


def _template_payload(db: Session, row: models.SupplierEvaluationTemplate) -> dict[str, Any]:
    criteria = db.query(models.SupplierEvaluationCriterion).filter(
        models.SupplierEvaluationCriterion.amo_id == row.amo_id,
        models.SupplierEvaluationCriterion.template_id == row.id,
    ).order_by(models.SupplierEvaluationCriterion.sequence_no.asc()).all()
    return {
        "id": row.id,
        "amo_id": row.amo_id,
        "code": row.code,
        "name": row.name,
        "description": row.description,
        "revision_no": row.revision_no,
        "status": row.status,
        "pass_threshold": row.pass_threshold,
        "manual_references": list(row.manual_references or []),
        "created_by_user_id": row.created_by_user_id,
        "activated_by_user_id": row.activated_by_user_id,
        "activated_at": row.activated_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "criteria": criteria,
    }


def list_templates(db: Session, *, amo_id: str, active_only: bool = False) -> list[dict[str, Any]]:
    query = db.query(models.SupplierEvaluationTemplate).filter(models.SupplierEvaluationTemplate.amo_id == amo_id)
    if active_only:
        query = query.filter(models.SupplierEvaluationTemplate.status == "ACTIVE")
    rows = query.order_by(models.SupplierEvaluationTemplate.code.asc(), models.SupplierEvaluationTemplate.revision_no.desc()).limit(500).all()
    return [_template_payload(db, row) for row in rows]


def create_template(
    db: Session,
    *,
    amo_id: str,
    payload: schemas.SupplierEvaluationTemplateCreate,
    actor_user_id: str,
) -> dict[str, Any]:
    _policy(db, amo_id=amo_id, required=True)
    max_revision = db.query(func.max(models.SupplierEvaluationTemplate.revision_no)).filter(
        models.SupplierEvaluationTemplate.amo_id == amo_id,
        func.upper(models.SupplierEvaluationTemplate.code) == payload.code,
    ).scalar() or 0
    row = models.SupplierEvaluationTemplate(
        amo_id=amo_id,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        revision_no=int(max_revision) + 1,
        status="DRAFT",
        pass_threshold=payload.pass_threshold,
        manual_references=payload.manual_references,
        created_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    for criterion in payload.criteria:
        db.add(models.SupplierEvaluationCriterion(
            amo_id=amo_id,
            template_id=row.id,
            **criterion.model_dump(mode="python"),
        ))
    db.flush()
    _event(
        db,
        amo_id=amo_id,
        supplier_id=0,
        action="EVALUATION_TEMPLATE_CREATED",
        actor_user_id=actor_user_id,
        detail={"template_id": row.id, "code": row.code, "revision_no": row.revision_no},
    )
    return _template_payload(db, row)


def activate_template(
    db: Session,
    *,
    amo_id: str,
    template_id: str,
    rationale: str,
    actor_user_id: str,
) -> dict[str, Any]:
    row = _template(db, amo_id=amo_id, template_id=template_id)
    if row.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only a draft supplier evaluation template may be activated.")
    if row.created_by_user_id and str(row.created_by_user_id) == str(actor_user_id):
        raise HTTPException(status_code=409, detail="The template author cannot independently activate the same supplier evaluation template.")
    criteria = db.query(models.SupplierEvaluationCriterion).filter(
        models.SupplierEvaluationCriterion.amo_id == amo_id,
        models.SupplierEvaluationCriterion.template_id == row.id,
    ).all()
    if not criteria:
        raise HTTPException(status_code=409, detail="A supplier evaluation template requires at least one criterion before activation.")
    if row.pass_threshold is None:
        raise HTTPException(status_code=409, detail="Set the tenant-approved pass threshold before activating the supplier evaluation template.")
    invalid = [
        criterion.criterion_key
        for criterion in criteria
        if Decimal(str(criterion.weight or 0)) > 0
        and not isinstance(criterion.scoring_rule, dict)
    ]
    if invalid:
        raise HTTPException(status_code=409, detail={"code": "SUPPLIER_TEMPLATE_SCORING_RULE_INVALID", "criteria": invalid})
    blocking_without_threshold = [
        criterion.criterion_key
        for criterion in criteria
        if criterion.failure_is_blocking
        and "minimum_score_percent" not in (criterion.scoring_rule or {})
    ]
    if blocking_without_threshold:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SUPPLIER_TEMPLATE_BLOCKING_THRESHOLD_REQUIRED",
                "message": "Blocking criteria must define minimum_score_percent in their tenant scoring rule.",
                "criteria": blocking_without_threshold,
            },
        )
    db.query(models.SupplierEvaluationTemplate).filter(
        models.SupplierEvaluationTemplate.amo_id == amo_id,
        models.SupplierEvaluationTemplate.code == row.code,
        models.SupplierEvaluationTemplate.status == "ACTIVE",
        models.SupplierEvaluationTemplate.id != row.id,
    ).update({"status": "RETIRED"}, synchronize_session=False)
    row.status = "ACTIVE"
    row.activated_by_user_id = actor_user_id
    row.activated_at = _utcnow()
    db.flush()
    _event(
        db,
        amo_id=amo_id,
        supplier_id=0,
        action="EVALUATION_TEMPLATE_ACTIVATED",
        actor_user_id=actor_user_id,
        detail={"template_id": row.id, "code": row.code, "revision_no": row.revision_no, "rationale": rationale},
    )
    return _template_payload(db, row)


def create_evaluation(
    db: Session,
    *,
    amo_id: str,
    supplier_id: int,
    payload: schemas.SupplierEvaluationCreate,
    actor_user_id: str,
) -> models.SupplierEvaluation:
    supplier = _supplier(db, amo_id=amo_id, supplier_id=supplier_id)
    policy = _policy(db, amo_id=amo_id, required=True)
    template = _template(db, amo_id=amo_id, template_id=payload.template_id)
    if template.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Only an active supplier evaluation template may be used.")
    if payload.supersedes_evaluation_id:
        prior = _evaluation(db, amo_id=amo_id, evaluation_id=payload.supersedes_evaluation_id)
        if prior.supplier_id != supplier.id:
            raise HTTPException(status_code=422, detail="The superseded evaluation belongs to another supplier.")
    row = models.SupplierEvaluation(
        amo_id=amo_id,
        supplier_id=supplier.id,
        template_id=template.id,
        template_revision_no=template.revision_no,
        status="DRAFT",
        version=1,
        intended_scope=[item.model_dump(mode="json") for item in payload.intended_scope],
        policy_snapshot=_policy_snapshot(policy),
        created_by_user_id=actor_user_id,
        supersedes_evaluation_id=payload.supersedes_evaluation_id,
    )
    db.add(row)
    db.flush()
    _event(
        db,
        amo_id=amo_id,
        supplier_id=supplier.id,
        action="EVALUATION_CREATED",
        actor_user_id=actor_user_id,
        detail={
            "evaluation_id": row.id,
            "template_id": template.id,
            "template_revision_no": template.revision_no,
            "intended_scope": row.intended_scope,
            "policy_snapshot": row.policy_snapshot,
        },
    )
    return row


def update_responses(
    db: Session,
    *,
    amo_id: str,
    evaluation_id: str,
    payload: schemas.SupplierEvaluationResponsesUpdate,
    actor_user_id: str,
) -> models.SupplierEvaluation:
    row = _evaluation(db, amo_id=amo_id, evaluation_id=evaluation_id, lock=True)
    if row.status not in MUTABLE_EVALUATION_STATES:
        raise HTTPException(status_code=409, detail="Only a draft or returned supplier evaluation may be edited.")
    if row.version != payload.expected_version:
        raise HTTPException(
            status_code=409,
            detail={"code": "SUPPLIER_EVALUATION_STALE_VERSION", "expected": row.version, "provided": payload.expected_version},
        )
    criterion_ids = {str(item.criterion_id) for item in payload.responses}
    criteria = db.query(models.SupplierEvaluationCriterion).filter(
        models.SupplierEvaluationCriterion.amo_id == amo_id,
        models.SupplierEvaluationCriterion.template_id == row.template_id,
        models.SupplierEvaluationCriterion.id.in_(criterion_ids),
    ).all()
    if len(criteria) != len(criterion_ids):
        raise HTTPException(status_code=422, detail="One or more responses do not belong to the frozen evaluation template revision.")
    existing = {
        item.criterion_id: item
        for item in db.query(models.SupplierEvaluationResponse).filter(
            models.SupplierEvaluationResponse.amo_id == amo_id,
            models.SupplierEvaluationResponse.evaluation_id == row.id,
            models.SupplierEvaluationResponse.criterion_id.in_(criterion_ids),
        ).all()
    }
    for item in payload.responses:
        response = existing.get(item.criterion_id)
        values = item.model_dump(mode="python", exclude={"criterion_id"})
        if response is None:
            response = models.SupplierEvaluationResponse(
                amo_id=amo_id,
                evaluation_id=row.id,
                criterion_id=item.criterion_id,
                updated_by_user_id=actor_user_id,
                **values,
            )
            db.add(response)
        else:
            for key, value in values.items():
                setattr(response, key, value)
            response.updated_by_user_id = actor_user_id
    row.version += 1
    db.flush()
    _event(
        db,
        amo_id=amo_id,
        supplier_id=row.supplier_id,
        action="EVALUATION_RESPONSES_UPDATED",
        actor_user_id=actor_user_id,
        detail={"evaluation_id": row.id, "version": row.version, "criterion_ids": sorted(criterion_ids)},
    )
    return row


def _score_evaluation(
    db: Session,
    *,
    row: models.SupplierEvaluation,
) -> tuple[Decimal, str, list[str]]:
    template = _template(db, amo_id=row.amo_id, template_id=row.template_id)
    criteria = db.query(models.SupplierEvaluationCriterion).filter(
        models.SupplierEvaluationCriterion.amo_id == row.amo_id,
        models.SupplierEvaluationCriterion.template_id == row.template_id,
    ).order_by(models.SupplierEvaluationCriterion.sequence_no.asc()).all()
    responses = {
        item.criterion_id: item
        for item in db.query(models.SupplierEvaluationResponse).filter(
            models.SupplierEvaluationResponse.amo_id == row.amo_id,
            models.SupplierEvaluationResponse.evaluation_id == row.id,
        ).all()
    }
    missing: list[str] = []
    missing_evidence: list[str] = []
    missing_score: list[str] = []
    blocking_failures: list[str] = []
    weighted = Decimal("0")
    total_weight = Decimal("0")
    for criterion in criteria:
        response = responses.get(criterion.id)
        if criterion.mandatory and (response is None or response.answer is None or response.answer == ""):
            missing.append(criterion.criterion_key)
            continue
        if response is None:
            continue
        if criterion.evidence_required and not list(response.evidence_references or []):
            missing_evidence.append(criterion.criterion_key)
        weight = Decimal(str(criterion.weight or 0))
        if weight > 0:
            if response.score_percent is None:
                missing_score.append(criterion.criterion_key)
            else:
                weighted += Decimal(str(response.score_percent)) * weight
                total_weight += weight
        if criterion.failure_is_blocking:
            minimum = (criterion.scoring_rule or {}).get("minimum_score_percent")
            if minimum is None:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "SUPPLIER_TEMPLATE_BLOCKING_THRESHOLD_REQUIRED",
                        "criterion": criterion.criterion_key,
                    },
                )
            if response.score_percent is None or Decimal(str(response.score_percent)) < Decimal(str(minimum)):
                blocking_failures.append(criterion.criterion_key)
    if missing or missing_evidence or missing_score:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "SUPPLIER_EVALUATION_INCOMPLETE",
                "missing_responses": missing,
                "missing_evidence": missing_evidence,
                "missing_scores": missing_score,
            },
        )
    if total_weight <= 0:
        raise HTTPException(status_code=409, detail="The supplier evaluation template has no positive scoring weight.")
    if template.pass_threshold is None:
        raise HTTPException(status_code=409, detail="The supplier evaluation template has no governed pass threshold.")
    score = (weighted / total_weight).quantize(Decimal("0.01"))
    outcome = "PASS" if score >= Decimal(str(template.pass_threshold)) and not blocking_failures else "FAIL"
    return score, outcome, blocking_failures


def submit_evaluation(
    db: Session,
    *,
    amo_id: str,
    evaluation_id: str,
    payload: schemas.SupplierEvaluationSubmit,
    actor_user_id: str,
) -> models.SupplierEvaluation:
    row = _evaluation(db, amo_id=amo_id, evaluation_id=evaluation_id, lock=True)
    if row.status not in MUTABLE_EVALUATION_STATES:
        raise HTTPException(status_code=409, detail="Only a draft or returned supplier evaluation may be submitted.")
    if row.version != payload.expected_version:
        raise HTTPException(status_code=409, detail={"code": "SUPPLIER_EVALUATION_STALE_VERSION", "expected": row.version, "provided": payload.expected_version})
    score, outcome, blocking_failures = _score_evaluation(db, row=row)
    row.score = score
    row.outcome = outcome
    row.status = "SUBMITTED"
    row.submitted_by_user_id = actor_user_id
    row.submitted_at = _utcnow()
    row.version += 1
    if payload.submission_note:
        row.review_comment = f"Submission note: {payload.submission_note.strip()}"
    db.flush()
    _event(
        db,
        amo_id=amo_id,
        supplier_id=row.supplier_id,
        action="EVALUATION_SUBMITTED",
        actor_user_id=actor_user_id,
        detail={"evaluation_id": row.id, "version": row.version, "score": str(score), "outcome": outcome, "blocking_failures": blocking_failures},
    )
    return row


def _validate_qms_links(
    db: Session,
    *,
    amo_id: str,
    finding_id: str | None,
    car_id: str | None,
) -> None:
    if finding_id:
        try:
            parsed = uuid.UUID(finding_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="qms_finding_id is not a valid identifier.") from exc
        found = db.query(quality_models.QMSAuditFinding.id).filter(
            quality_models.QMSAuditFinding.amo_id == amo_id,
            quality_models.QMSAuditFinding.id == parsed,
        ).first()
        if not found:
            raise HTTPException(status_code=422, detail="The linked QMS finding does not exist in this AMO.")
    if car_id:
        try:
            parsed = uuid.UUID(car_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="qms_car_id is not a valid identifier.") from exc
        found = db.query(quality_models.CorrectiveActionRequest.id).filter(
            quality_models.CorrectiveActionRequest.amo_id == amo_id,
            quality_models.CorrectiveActionRequest.id == parsed,
        ).first()
        if not found:
            raise HTTPException(status_code=422, detail="The linked QMS CAR does not exist in this AMO.")


def review_evaluation(
    db: Session,
    *,
    amo_id: str,
    evaluation_id: str,
    payload: schemas.SupplierEvaluationReview,
    actor_user_id: str,
) -> models.SupplierEvaluation:
    row = _evaluation(db, amo_id=amo_id, evaluation_id=evaluation_id, lock=True)
    if row.status != "SUBMITTED":
        raise HTTPException(status_code=409, detail="Only a submitted supplier evaluation may be independently reviewed.")
    if row.version != payload.expected_version:
        raise HTTPException(status_code=409, detail={"code": "SUPPLIER_EVALUATION_STALE_VERSION", "expected": row.version, "provided": payload.expected_version})
    policy = _policy(db, amo_id=amo_id, required=True)
    if policy.require_independent_review and str(actor_user_id) in {str(row.created_by_user_id or ""), str(row.submitted_by_user_id or "")}:
        raise HTTPException(status_code=409, detail="The evaluator/submitter cannot independently approve the same supplier evaluation.")
    score, outcome, blocking_failures = _score_evaluation(db, row=row)
    if payload.decision == "APPROVE" and outcome != "PASS":
        raise HTTPException(status_code=409, detail={"code": "SUPPLIER_EVALUATION_FAILED", "message": "A failed evaluation cannot be approved.", "blocking_failures": blocking_failures})
    if payload.decision == "CONDITIONALLY_APPROVE":
        if not policy.conditional_approval_allowed:
            raise HTTPException(status_code=409, detail="Conditional supplier approval is disabled by tenant policy.")
        if blocking_failures:
            raise HTTPException(status_code=409, detail={"code": "SUPPLIER_BLOCKING_CRITERIA_FAILED", "criteria": blocking_failures})
    _validate_qms_links(db, amo_id=amo_id, finding_id=payload.qms_finding_id, car_id=payload.qms_car_id)

    supplier = _supplier(db, amo_id=amo_id, supplier_id=row.supplier_id)
    risk = _enum(supplier.risk_level).upper()
    interval = int((policy.risk_review_days or {}).get(risk) or 0)
    if interval <= 0:
        raise HTTPException(status_code=409, detail=f"Tenant policy has no valid review interval for supplier risk level {risk}.")

    before = {
        "status": row.status,
        "score": str(row.score) if row.score is not None else None,
        "outcome": row.outcome,
        "valid_until": row.valid_until.isoformat() if row.valid_until else None,
    }
    row.score = score
    row.outcome = outcome
    row.reviewed_by_user_id = actor_user_id
    row.reviewed_at = _utcnow()
    row.review_comment = payload.rationale.strip()
    row.qms_finding_id = payload.qms_finding_id
    row.qms_car_id = payload.qms_car_id
    if payload.decision == "APPROVE":
        row.status = "APPROVED"
        row.valid_until = date.today() + timedelta(days=interval)
    elif payload.decision == "CONDITIONALLY_APPROVE":
        row.status = "CONDITIONALLY_APPROVED"
        row.valid_until = date.today() + timedelta(days=interval)
    elif payload.decision == "REJECT":
        row.status = "REJECTED"
        row.valid_until = None
    else:
        row.status = "RETURNED"
        row.valid_until = None
    row.version += 1
    if row.status in APPROVED_EVALUATION_STATES and row.supersedes_evaluation_id:
        prior = db.query(models.SupplierEvaluation).filter(
            models.SupplierEvaluation.amo_id == amo_id,
            models.SupplierEvaluation.id == row.supersedes_evaluation_id,
            models.SupplierEvaluation.supplier_id == row.supplier_id,
            models.SupplierEvaluation.status.in_(list(APPROVED_EVALUATION_STATES)),
        ).first()
        if prior:
            prior.status = "SUPERSEDED"
    after = {
        "status": row.status,
        "score": str(row.score),
        "outcome": row.outcome,
        "valid_until": row.valid_until.isoformat() if row.valid_until else None,
        "conditions": [item.strip() for item in payload.conditions if item.strip()],
        "qms_finding_id": row.qms_finding_id,
        "qms_car_id": row.qms_car_id,
    }
    decision = models.SupplierGovernanceDecision(
        amo_id=amo_id,
        supplier_id=row.supplier_id,
        evaluation_id=row.id,
        action=f"EVALUATION_{payload.decision}",
        rationale=payload.rationale.strip(),
        before_snapshot=before,
        after_snapshot=after,
        evidence_snapshot={
            "template_id": row.template_id,
            "template_revision_no": row.template_revision_no,
            "policy_snapshot": row.policy_snapshot,
            "intended_scope": row.intended_scope,
            "conditions": after["conditions"],
        },
        actor_user_id=actor_user_id,
    )
    db.add(decision)
    db.flush()
    _event(
        db,
        amo_id=amo_id,
        supplier_id=row.supplier_id,
        action="EVALUATION_REVIEWED",
        actor_user_id=actor_user_id,
        detail={"evaluation_id": row.id, "decision_id": decision.id, **after},
    )
    return row


def _responses_for(db: Session, *, amo_id: str, evaluation_id: str) -> list[models.SupplierEvaluationResponse]:
    return db.query(models.SupplierEvaluationResponse).filter(
        models.SupplierEvaluationResponse.amo_id == amo_id,
        models.SupplierEvaluationResponse.evaluation_id == evaluation_id,
    ).order_by(models.SupplierEvaluationResponse.created_at.asc()).all()


def evaluation_payload(db: Session, row: models.SupplierEvaluation) -> dict[str, Any]:
    return {
        "id": row.id,
        "amo_id": row.amo_id,
        "supplier_id": row.supplier_id,
        "template_id": row.template_id,
        "template_revision_no": row.template_revision_no,
        "status": row.status,
        "version": row.version,
        "intended_scope": list(row.intended_scope or []),
        "policy_snapshot": dict(row.policy_snapshot or {}),
        "score": row.score,
        "outcome": row.outcome,
        "valid_until": row.valid_until,
        "qms_finding_id": row.qms_finding_id,
        "qms_car_id": row.qms_car_id,
        "created_by_user_id": row.created_by_user_id,
        "submitted_by_user_id": row.submitted_by_user_id,
        "reviewed_by_user_id": row.reviewed_by_user_id,
        "submitted_at": row.submitted_at,
        "reviewed_at": row.reviewed_at,
        "review_comment": row.review_comment,
        "supersedes_evaluation_id": row.supersedes_evaluation_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "responses": _responses_for(db, amo_id=row.amo_id, evaluation_id=row.id),
    }


def _scope_key(scope: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(scope.get("site_code") or "PRIMARY").strip().upper(),
        str(scope.get("category") or "").strip().upper(),
        str(scope.get("product_family") or "ALL").strip().upper(),
        str(scope.get("manufacturer") or "").strip().upper(),
        str(scope.get("authority") or "TENANT_QMS").strip().upper(),
    )


def create_governed_scope(
    db: Session,
    *,
    amo_id: str,
    supplier_id: int,
    payload: procurement_schemas.ApprovalScopeCreate,
    actor_user_id: str,
) -> procurement_models.SupplierApprovalScope:
    supplier = _supplier(db, amo_id=amo_id, supplier_id=supplier_id)
    if not payload.qms_evaluation_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "SUPPLIER_EVALUATION_REQUIRED", "message": "Approval scope must reference an independently reviewed supplier evaluation."},
        )
    evaluation = _evaluation(db, amo_id=amo_id, evaluation_id=payload.qms_evaluation_id)
    if evaluation.supplier_id != supplier.id:
        raise HTTPException(status_code=422, detail="The referenced evaluation belongs to another supplier.")
    if evaluation.status not in APPROVED_EVALUATION_STATES or not evaluation.valid_until or evaluation.valid_until < date.today():
        raise HTTPException(status_code=409, detail="The referenced supplier evaluation is not currently approved and valid.")
    requested = _scope_key(payload.model_dump(mode="json"))
    allowed = {_scope_key(item) for item in list(evaluation.intended_scope or [])}
    if requested not in allowed:
        raise HTTPException(
            status_code=409,
            detail={"code": "SUPPLIER_SCOPE_OUTSIDE_EVALUATION", "message": "Requested approval scope is outside the independently reviewed evaluation scope."},
        )
    existing = db.query(procurement_models.SupplierApprovalScope).filter(
        procurement_models.SupplierApprovalScope.amo_id == amo_id,
        procurement_models.SupplierApprovalScope.supplier_id == supplier.id,
        procurement_models.SupplierApprovalScope.site_code == payload.site_code,
        procurement_models.SupplierApprovalScope.category == payload.category,
        procurement_models.SupplierApprovalScope.product_family == payload.product_family,
        procurement_models.SupplierApprovalScope.authority == payload.authority,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="That supplier approval scope already exists; revise the governed evaluation rather than duplicating it.")
    row = procurement_models.SupplierApprovalScope(
        amo_id=amo_id,
        supplier_id=supplier.id,
        status=procurement_models.ApprovalScopeStatus.DRAFT,
        **payload.model_dump(),
    )
    row.qms_evaluation_id = evaluation.id
    db.add(row)
    db.flush()
    _event(
        db,
        amo_id=amo_id,
        supplier_id=supplier.id,
        action="APPROVAL_SCOPE_DRAFTED",
        actor_user_id=actor_user_id,
        detail={"scope_id": row.id, "evaluation_id": evaluation.id, "scope": payload.model_dump(mode="json")},
    )
    return row


def _latest_valid_evaluation(
    db: Session,
    *,
    amo_id: str,
    supplier_id: int,
) -> models.SupplierEvaluation | None:
    return db.query(models.SupplierEvaluation).filter(
        models.SupplierEvaluation.amo_id == amo_id,
        models.SupplierEvaluation.supplier_id == supplier_id,
        models.SupplierEvaluation.status.in_(list(APPROVED_EVALUATION_STATES)),
        models.SupplierEvaluation.valid_until.isnot(None),
        models.SupplierEvaluation.valid_until >= date.today(),
    ).order_by(models.SupplierEvaluation.reviewed_at.desc(), models.SupplierEvaluation.created_at.desc()).first()


def decide_supplier(
    db: Session,
    *,
    amo_id: str,
    supplier_id: int,
    payload: procurement_schemas.SupplierDecision,
    actor_user_id: str,
) -> procurement_models.ProcurementSupplier:
    supplier = _supplier(db, amo_id=amo_id, supplier_id=supplier_id)
    action = payload.action.upper()
    reason = (payload.reason or "").strip()
    if len(reason) < 8:
        raise HTTPException(status_code=422, detail="Supplier decisions require an attributable rationale of at least 8 characters.")
    if action not in {"APPROVE", "CONDITIONALLY_APPROVE", "REACTIVATE"}:
        return procurement_service.decide_supplier(
            db,
            amo_id=amo_id,
            supplier_id=supplier_id,
            payload=payload,
            actor_user_id=actor_user_id,
        )

    evaluation = _latest_valid_evaluation(db, amo_id=amo_id, supplier_id=supplier.id)
    if evaluation is None:
        raise HTTPException(status_code=409, detail={"code": "SUPPLIER_EVALUATION_REQUIRED", "message": "A current independently reviewed supplier evaluation is required before approval/reactivation."})
    if action == "APPROVE" and evaluation.status != "APPROVED":
        raise HTTPException(status_code=409, detail="Full supplier approval requires an evaluation with an APPROVED decision.")
    if action == "CONDITIONALLY_APPROVE" and evaluation.status not in APPROVED_EVALUATION_STATES:
        raise HTTPException(status_code=409, detail="Conditional approval requires a current governed evaluation.")

    scopes = db.query(procurement_models.SupplierApprovalScope).filter(
        procurement_models.SupplierApprovalScope.amo_id == amo_id,
        procurement_models.SupplierApprovalScope.supplier_id == supplier.id,
        procurement_models.SupplierApprovalScope.qms_evaluation_id == evaluation.id,
        procurement_models.SupplierApprovalScope.status.in_([
            procurement_models.ApprovalScopeStatus.DRAFT,
            procurement_models.ApprovalScopeStatus.ACTIVE,
        ]),
    ).all()
    if not scopes:
        raise HTTPException(status_code=409, detail={"code": "SUPPLIER_SCOPE_REQUIRED", "message": "Create at least one draft approval scope tied to the approved evaluation before supplier approval."})

    before = _snapshot_supplier(supplier)
    now = _utcnow()
    target_status = (
        procurement_models.SupplierLifecycleStatus.CONDITIONALLY_APPROVED
        if action == "CONDITIONALLY_APPROVE"
        else procurement_models.SupplierLifecycleStatus.APPROVED
    )
    supplier.status = target_status
    supplier.is_active = True
    supplier.approved_at = now
    supplier.approved_by_user_id = actor_user_id
    supplier.suspended_at = None
    supplier.suspended_by_user_id = None
    supplier.suspension_reason = None
    for scope in scopes:
        scope.status = procurement_models.ApprovalScopeStatus.ACTIVE
        scope.approved_at = now
        scope.approved_by_user_id = actor_user_id
        scope.effective_on = scope.effective_on or date.today()
        scope.expires_on = scope.expires_on or evaluation.valid_until
    after = _snapshot_supplier(supplier)
    decision = models.SupplierGovernanceDecision(
        amo_id=amo_id,
        supplier_id=supplier.id,
        evaluation_id=evaluation.id,
        action=action,
        rationale=reason,
        before_snapshot=before,
        after_snapshot=after,
        evidence_snapshot={
            "evaluation_id": evaluation.id,
            "evaluation_status": evaluation.status,
            "evaluation_score": str(evaluation.score) if evaluation.score is not None else None,
            "valid_until": evaluation.valid_until.isoformat() if evaluation.valid_until else None,
            "scope_ids": [scope.id for scope in scopes],
            "policy_snapshot": evaluation.policy_snapshot,
        },
        actor_user_id=actor_user_id,
    )
    db.add(decision)
    db.flush()
    _event(
        db,
        amo_id=amo_id,
        supplier_id=supplier.id,
        action=f"SUPPLIER_{action}",
        actor_user_id=actor_user_id,
        detail={"decision_id": decision.id, "evaluation_id": evaluation.id, "scope_ids": [scope.id for scope in scopes], "reason": reason},
    )
    return supplier


def governance_detail(db: Session, *, amo_id: str, supplier_id: int) -> dict[str, Any]:
    _supplier(db, amo_id=amo_id, supplier_id=supplier_id)
    policy = _policy(db, amo_id=amo_id, required=False)
    evaluations = db.query(models.SupplierEvaluation).filter(
        models.SupplierEvaluation.amo_id == amo_id,
        models.SupplierEvaluation.supplier_id == supplier_id,
    ).order_by(models.SupplierEvaluation.created_at.desc()).limit(100).all()
    decisions = db.query(models.SupplierGovernanceDecision).filter(
        models.SupplierGovernanceDecision.amo_id == amo_id,
        models.SupplierGovernanceDecision.supplier_id == supplier_id,
    ).order_by(models.SupplierGovernanceDecision.created_at.desc()).limit(200).all()
    actions = db.query(models.SupplierReevaluationAction).filter(
        models.SupplierReevaluationAction.amo_id == amo_id,
        models.SupplierReevaluationAction.supplier_id == supplier_id,
    ).order_by(models.SupplierReevaluationAction.created_at.desc()).limit(200).all()
    current = next(
        (
            row for row in evaluations
            if row.status in APPROVED_EVALUATION_STATES and row.valid_until and row.valid_until >= date.today()
        ),
        None,
    )
    return {
        "supplier_id": supplier_id,
        "policy_configured": policy is not None,
        "current_evaluation": evaluation_payload(db, current) if current else None,
        "evaluations": [evaluation_payload(db, row) for row in evaluations],
        "decisions": decisions,
        "re_evaluation_actions": actions,
    }


def scan_re_evaluation(
    db: Session,
    *,
    amo_id: str,
    actor_user_id: str,
) -> dict[str, Any]:
    policy = _policy(db, amo_id=amo_id, required=True)
    rules = schemas.SupplierReevaluationRules.model_validate(policy.re_evaluation_rules)
    today = date.today()
    suppliers = db.query(procurement_models.ProcurementSupplier).filter(
        procurement_models.ProcurementSupplier.amo_id == amo_id,
        procurement_models.ProcurementSupplier.is_active.is_(True),
        procurement_models.ProcurementSupplier.status.in_([
            procurement_models.SupplierLifecycleStatus.APPROVED,
            procurement_models.SupplierLifecycleStatus.CONDITIONALLY_APPROVED,
            procurement_models.SupplierLifecycleStatus.RESTRICTED,
        ]),
    ).order_by(procurement_models.ProcurementSupplier.id.asc()).limit(5000).all()
    supplier_ids = [row.id for row in suppliers]
    if not supplier_ids:
        return {"suppliers_scanned": 0, "actions_created": 0, "actions_existing": 0, "triggers": {}}

    evaluations = db.query(models.SupplierEvaluation).filter(
        models.SupplierEvaluation.amo_id == amo_id,
        models.SupplierEvaluation.supplier_id.in_(supplier_ids),
        models.SupplierEvaluation.status.in_(list(APPROVED_EVALUATION_STATES)),
    ).order_by(models.SupplierEvaluation.supplier_id.asc(), models.SupplierEvaluation.reviewed_at.desc()).all()
    latest: dict[int, models.SupplierEvaluation] = {}
    for item in evaluations:
        latest.setdefault(item.supplier_id, item)

    cutoff = _utcnow() - timedelta(days=rules.lookback_days)
    rejected_rows = db.query(
        procurement_models.ProcurementPurchaseOrder.supplier_id,
        func.count(procurement_models.ProcurementReceivingInspection.id),
    ).join(
        procurement_models.ProcurementReceipt,
        procurement_models.ProcurementReceipt.purchase_order_id == procurement_models.ProcurementPurchaseOrder.id,
    ).join(
        procurement_models.ProcurementReceivingInspection,
        procurement_models.ProcurementReceivingInspection.receipt_id == procurement_models.ProcurementReceipt.id,
    ).filter(
        procurement_models.ProcurementPurchaseOrder.amo_id == amo_id,
        procurement_models.ProcurementPurchaseOrder.supplier_id.in_(supplier_ids),
        procurement_models.ProcurementReceivingInspection.completed_at >= cutoff,
        procurement_models.ProcurementReceivingInspection.disposition.in_([
            procurement_models.InspectionDisposition.REJECTED,
            procurement_models.InspectionDisposition.RETURN_TO_SUPPLIER,
            procurement_models.InspectionDisposition.ESCALATED_TO_QUALITY,
        ]),
    ).group_by(procurement_models.ProcurementPurchaseOrder.supplier_id).all()
    rejected_counts = {int(supplier_id): int(count) for supplier_id, count in rejected_rows}

    direct_hold_rows = db.query(
        procurement_models.ProcurementQualityHold.target_id,
        func.count(procurement_models.ProcurementQualityHold.id),
    ).filter(
        procurement_models.ProcurementQualityHold.amo_id == amo_id,
        procurement_models.ProcurementQualityHold.target_type == "SUPPLIER",
        procurement_models.ProcurementQualityHold.status == procurement_models.QualityHoldStatus.ACTIVE,
    ).group_by(procurement_models.ProcurementQualityHold.target_id).all()
    hold_counts: dict[int, int] = {}
    for target_id, count in direct_hold_rows:
        try:
            hold_counts[int(target_id)] = int(count)
        except (TypeError, ValueError):
            continue

    existing_keys = {
        (row.supplier_id, row.trigger_key)
        for row in db.query(models.SupplierReevaluationAction).filter(
            models.SupplierReevaluationAction.amo_id == amo_id,
            models.SupplierReevaluationAction.supplier_id.in_(supplier_ids),
        ).all()
    }
    actions_created = 0
    actions_existing = 0
    trigger_counts: dict[str, int] = {}

    def materialize(supplier_id: int, evaluation_id: str, trigger_type: str, snapshot: dict[str, Any]) -> None:
        nonlocal actions_created, actions_existing
        trigger_key = f"{trigger_type}:{evaluation_id}"
        trigger_counts[trigger_type] = trigger_counts.get(trigger_type, 0) + 1
        if (supplier_id, trigger_key) in existing_keys:
            actions_existing += 1
            return
        action = models.SupplierReevaluationAction(
            amo_id=amo_id,
            supplier_id=supplier_id,
            trigger_key=trigger_key,
            trigger_type=trigger_type,
            trigger_snapshot=snapshot,
            source_reference=f"supplier-evaluation:{evaluation_id}",
            status="OPEN",
            due_on=today + timedelta(days=rules.action_due_days),
        )
        db.add(action)
        existing_keys.add((supplier_id, trigger_key))
        actions_created += 1
        _event(
            db,
            amo_id=amo_id,
            supplier_id=supplier_id,
            action="REEVALUATION_ACTION_CREATED",
            actor_user_id=actor_user_id,
            detail={"trigger_type": trigger_type, "evaluation_id": evaluation_id, "snapshot": snapshot, "due_on": action.due_on.isoformat()},
        )

    for supplier in suppliers:
        evaluation = latest.get(supplier.id)
        if evaluation is None:
            # Approved-like suppliers without a governed evaluation are legacy exposure.
            synthetic_key = f"LEGACY_GOVERNANCE_GAP:{supplier.id}"
            trigger_counts["LEGACY_GOVERNANCE_GAP"] = trigger_counts.get("LEGACY_GOVERNANCE_GAP", 0) + 1
            if (supplier.id, synthetic_key) in existing_keys:
                actions_existing += 1
            else:
                action = models.SupplierReevaluationAction(
                    amo_id=amo_id,
                    supplier_id=supplier.id,
                    trigger_key=synthetic_key,
                    trigger_type="LEGACY_GOVERNANCE_GAP",
                    trigger_snapshot={"supplier_status": _enum(supplier.status), "reason": "No governed supplier evaluation exists."},
                    source_reference=f"supplier:{supplier.id}",
                    status="OPEN",
                    due_on=today + timedelta(days=rules.action_due_days),
                )
                db.add(action)
                existing_keys.add((supplier.id, synthetic_key))
                actions_created += 1
            continue
        if evaluation.valid_until is None or evaluation.valid_until <= today + timedelta(days=rules.expiry_lead_days):
            materialize(
                supplier.id,
                evaluation.id,
                "EVALUATION_EXPIRY",
                {"valid_until": evaluation.valid_until.isoformat() if evaluation.valid_until else None, "lead_days": rules.expiry_lead_days},
            )
        rejected = rejected_counts.get(supplier.id, 0)
        if rejected >= rules.rejected_inspection_threshold:
            materialize(
                supplier.id,
                evaluation.id,
                "RECEIVING_REJECTIONS",
                {"lookback_days": rules.lookback_days, "rejected_inspections": rejected, "threshold": rules.rejected_inspection_threshold},
            )
        holds = hold_counts.get(supplier.id, 0)
        if holds >= rules.active_hold_threshold:
            materialize(
                supplier.id,
                evaluation.id,
                "ACTIVE_QUALITY_HOLDS",
                {"active_supplier_holds": holds, "threshold": rules.active_hold_threshold},
            )

    db.flush()
    return {
        "suppliers_scanned": len(suppliers),
        "actions_created": actions_created,
        "actions_existing": actions_existing,
        "triggers": trigger_counts,
    }
