from __future__ import annotations

"""Completion layer for the governed Training workflows.

This module deliberately extends the existing Training domain instead of adding a
parallel LMS.  It uses the canonical legacy TrainingRecord/Deferral/File/Event
entities together with the existing TrainingWorkflowInstance, assessment,
experience, invitation and authorization operating models.
"""

import hashlib
import json
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal, Optional

from fastapi import Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ...database import get_db, get_read_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import compliance
from . import models as training_models
from . import operating_models
from .permissions import tenant_id_for

UTC = timezone.utc


def _now() -> datetime:
    return datetime.now(UTC)


def _enum(value: Any) -> str:
    return str(getattr(value, "value", value) or "").upper()


def _iso(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _scoped(db: Session, model: type, record_id: str, amo_id: str, label: str):
    row = db.query(model).filter(model.id == record_id, model.amo_id == amo_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{label} was not found in this tenant.")
    return row


def _workflow(
    db: Session,
    *,
    amo_id: str,
    workflow_type: str,
    idempotency_key: str,
    title: str,
    subject_user_id: str | None = None,
    owner_user_id: str | None = None,
    course_id: str | None = None,
    event_id: str | None = None,
    authorization_case_id: str | None = None,
    create_status: str = "DRAFT",
) -> operating_models.TrainingWorkflowInstance:
    row = db.query(operating_models.TrainingWorkflowInstance).filter(
        operating_models.TrainingWorkflowInstance.amo_id == amo_id,
        operating_models.TrainingWorkflowInstance.workflow_type == workflow_type,
        operating_models.TrainingWorkflowInstance.idempotency_key == idempotency_key,
    ).first()
    if row is not None:
        return row
    row = operating_models.TrainingWorkflowInstance(
        amo_id=amo_id,
        workflow_type=workflow_type,
        title=title,
        status=create_status,
        subject_user_id=subject_user_id,
        owner_user_id=owner_user_id,
        course_id=course_id,
        event_id=event_id,
        authorization_case_id=authorization_case_id,
        data_json={},
        validation_result={},
        provenance={"module": "training", "completion_layer": True},
        idempotency_key=idempotency_key,
        revision_no=1,
    )
    db.add(row)
    db.flush()
    return row


def _workflow_data(row: operating_models.TrainingWorkflowInstance) -> dict[str, Any]:
    return dict(row.data_json or {})


def _save_workflow_data(row: operating_models.TrainingWorkflowInstance, data: dict[str, Any]) -> None:
    row.data_json = dict(data)
    row.revision_no = int(row.revision_no or 0) + 1
    row.updated_at = _now()


def _training_editor(router_module, user: account_models.User) -> None:
    if not router_module._is_training_editor(user):
        raise HTTPException(status_code=403, detail="Training editor permission is required.")


def _audit(router_module, db: Session, *, actor: account_models.User, action: str, entity_type: str, entity_id: str, details: dict[str, Any]) -> None:
    router_module._audit(
        db,
        amo_id=str(actor.amo_id),
        actor_user_id=str(actor.id),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )


def _notify(
    router_module,
    db: Session,
    *,
    amo_id: str,
    user_id: str,
    title: str,
    body: str,
    link_path: str,
    dedupe_key: str,
    actor_user_id: str | None = None,
    warning: bool = False,
) -> None:
    router_module._create_notification(
        db,
        amo_id=amo_id,
        user_id=user_id,
        title=title,
        body=body,
        severity=(
            training_models.TrainingNotificationSeverity.WARNING
            if warning
            else training_models.TrainingNotificationSeverity.ACTION_REQUIRED
        ),
        link_path=link_path,
        dedupe_key=dedupe_key,
        created_by_user_id=actor_user_id,
    )


def _quality_users(db: Session, amo_id: str) -> list[account_models.User]:
    rows = db.query(account_models.User).filter(
        account_models.User.amo_id == amo_id,
        account_models.User.is_active.is_(True),
        account_models.User.is_system_account.is_(False),
    ).all()
    result: list[account_models.User] = []
    for user in rows:
        role = _enum(getattr(user, "role", None))
        department = getattr(getattr(user, "department", None), "code", None)
        if role in {"QUALITY_MANAGER", "AMO_ADMIN", "ADMIN"} or str(department or "").upper() == "QUALITY":
            result.append(user)
    return result


# ---------------------------------------------------------------------------
# Deferral lifecycle
# ---------------------------------------------------------------------------


class DeferralDecisionPayload(BaseModel):
    decision: Literal["APPROVED", "REJECTED", "RETURNED_FOR_INFORMATION"]
    decision_comment: str = Field(..., min_length=2, max_length=4000)
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    risk_summary: str = Field(..., min_length=2, max_length=4000)
    operational_justification: str = Field(..., min_length=2, max_length=4000)
    replacement_event_id: str | None = None
    replacement_plan: str | None = Field(None, max_length=4000)
    evidence_waiver_reason: str | None = Field(None, max_length=2000)


class DeferralResubmitPayload(BaseModel):
    learner_response: str = Field(..., min_length=2, max_length=4000)
    reason_text: str | None = Field(None, max_length=4000)
    requested_new_due_date: date | None = None
    replacement_plan: str | None = Field(None, max_length=4000)


def _deferral_control(db: Session, deferral: training_models.TrainingDeferralRequest) -> operating_models.TrainingWorkflowInstance:
    return _workflow(
        db,
        amo_id=str(deferral.amo_id),
        workflow_type="DEFERRAL_CONTROL",
        idempotency_key=f"deferral:{deferral.id}",
        title="Training deferral control",
        subject_user_id=str(deferral.user_id),
        owner_user_id=str(deferral.requested_by_user_id) if deferral.requested_by_user_id else None,
        course_id=str(deferral.course_id),
        create_status=_enum(deferral.status) or "PENDING",
    )


def _deferral_payload(db: Session, row: training_models.TrainingDeferralRequest) -> dict[str, Any]:
    control = _deferral_control(db, row)
    data = _workflow_data(control)
    evidence = db.query(training_models.TrainingFile).filter(
        training_models.TrainingFile.amo_id == row.amo_id,
        training_models.TrainingFile.deferral_request_id == row.id,
    ).order_by(training_models.TrainingFile.uploaded_at.desc()).all()
    return {
        "id": str(row.id),
        "amo_id": str(row.amo_id),
        "user_id": str(row.user_id),
        "requested_by_user_id": str(row.requested_by_user_id) if row.requested_by_user_id else None,
        "course_id": str(row.course_id),
        "original_due_date": _iso(row.original_due_date),
        "requested_new_due_date": _iso(row.requested_new_due_date),
        "reason_category": _enum(row.reason_category),
        "reason_text": row.reason_text,
        "status": _enum(row.status),
        "requested_at": _iso(row.requested_at),
        "decided_at": _iso(row.decided_at),
        "decided_by_user_id": str(row.decided_by_user_id) if row.decided_by_user_id else None,
        "decision_comment": row.decision_comment,
        "updated_at": _iso(row.updated_at),
        "risk_level": data.get("risk_level"),
        "risk_summary": data.get("risk_summary"),
        "operational_justification": data.get("operational_justification"),
        "replacement_event_id": data.get("replacement_event_id"),
        "replacement_plan": data.get("replacement_plan"),
        "evidence_waiver_reason": data.get("evidence_waiver_reason"),
        "learner_response": data.get("learner_response"),
        "returned_at": data.get("returned_at"),
        "resubmitted_at": data.get("resubmitted_at"),
        "expired_at": data.get("expired_at"),
        "escalation_count": int(data.get("escalation_count") or 0),
        "evidence": [
            {
                "id": str(item.id),
                "filename": item.original_filename,
                "review_status": _enum(item.review_status),
                "review_comment": item.review_comment,
                "uploaded_at": _iso(item.uploaded_at),
            }
            for item in evidence
        ],
    }


def install_training_workflow_completion(router_module) -> None:
    """Register missing governed workflow routes on the canonical Training router."""

    if getattr(router_module.router, "_workflow_completion_installed", False):
        return
    router_module.router._workflow_completion_installed = True
    router = router_module.router

    @router.get("/deferrals/me/enriched")
    def list_my_enriched_deferrals(
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        rows = db.query(training_models.TrainingDeferralRequest).filter(
            training_models.TrainingDeferralRequest.amo_id == current_user.amo_id,
            training_models.TrainingDeferralRequest.user_id == current_user.id,
        ).order_by(training_models.TrainingDeferralRequest.requested_at.desc()).all()
        payload = [_deferral_payload(db, row) for row in rows]
        db.commit()  # persists lazily-created control envelopes only
        return payload

    @router.get("/deferrals/enriched")
    def list_enriched_deferrals(
        status_filter: str | None = None,
        user_id: str | None = None,
        limit: int = Query(100, ge=1, le=500),
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        _training_editor(router_module, current_user)
        query = db.query(training_models.TrainingDeferralRequest).filter(
            training_models.TrainingDeferralRequest.amo_id == current_user.amo_id
        )
        if status_filter:
            query = query.filter(training_models.TrainingDeferralRequest.status == status_filter.upper())
        if user_id:
            query = query.filter(training_models.TrainingDeferralRequest.user_id == user_id)
        rows = query.order_by(training_models.TrainingDeferralRequest.requested_at.desc()).limit(limit).all()
        payload = [_deferral_payload(db, row) for row in rows]
        db.commit()
        return payload

    @router.post("/deferrals/{deferral_id}/decision")
    def decide_deferral_governed(
        deferral_id: str,
        payload: DeferralDecisionPayload,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        _training_editor(router_module, current_user)
        amo_id = str(current_user.amo_id)
        row = _scoped(db, training_models.TrainingDeferralRequest, deferral_id, amo_id, "Deferral request")
        current = _enum(row.status)
        if current not in {"PENDING", "RETURNED_FOR_INFORMATION"}:
            raise HTTPException(status_code=409, detail=f"Deferral in {current} cannot be decided.")
        if str(current_user.id) in {str(row.user_id), str(row.requested_by_user_id or "")}:
            raise HTTPException(status_code=409, detail="The affected learner/requester cannot approve or review their own deferral.")
        if payload.replacement_event_id:
            event = _scoped(db, training_models.TrainingEvent, payload.replacement_event_id, amo_id, "Replacement training event")
            if str(event.course_id) != str(row.course_id):
                raise HTTPException(status_code=422, detail="Replacement session must be for the deferred course.")
        evidence_rows = db.query(training_models.TrainingFile).filter(
            training_models.TrainingFile.amo_id == amo_id,
            training_models.TrainingFile.deferral_request_id == row.id,
        ).all()
        accepted = [item for item in evidence_rows if _enum(item.review_status) == "APPROVED"]
        if payload.decision == "APPROVED" and not accepted and not payload.evidence_waiver_reason:
            raise HTTPException(status_code=409, detail="Approval requires accepted supporting evidence or an auditable evidence waiver reason.")
        if payload.decision == "APPROVED" and payload.risk_level in {"HIGH", "CRITICAL"} and not (payload.replacement_event_id or payload.replacement_plan):
            raise HTTPException(status_code=409, detail="High/critical-risk deferrals require a replacement training session or documented replacement plan.")

        before = current
        row.status = getattr(training_models.DeferralStatus, payload.decision)
        row.decided_at = _now()
        row.decided_by_user_id = str(current_user.id)
        row.decision_comment = payload.decision_comment
        control = _deferral_control(db, row)
        data = _workflow_data(control)
        data.update({
            "risk_level": payload.risk_level,
            "risk_summary": payload.risk_summary,
            "operational_justification": payload.operational_justification,
            "replacement_event_id": payload.replacement_event_id,
            "replacement_plan": payload.replacement_plan,
            "evidence_waiver_reason": payload.evidence_waiver_reason,
            "decision_at": _now().isoformat(),
            "decision_by_user_id": str(current_user.id),
        })
        if payload.decision == "RETURNED_FOR_INFORMATION":
            data["returned_at"] = _now().isoformat()
            control.status = "RETURNED"
        elif payload.decision == "APPROVED":
            control.status = "APPROVED"
            control.due_at = datetime.combine(row.requested_new_due_date, datetime.min.time(), tzinfo=UTC)
        else:
            control.status = "REJECTED"
            control.completed_at = _now()
        _save_workflow_data(control, data)
        db.add(row)
        _audit(router_module, db, actor=current_user, action="DEFERRAL_TRANSITION", entity_type="TrainingDeferralRequest", entity_id=str(row.id), details={"from": before, "to": payload.decision, **payload.model_dump(mode="json")})
        _notify(
            router_module,
            db,
            amo_id=amo_id,
            user_id=str(row.user_id),
            title=("Deferral returned for information" if payload.decision == "RETURNED_FOR_INFORMATION" else f"Deferral {payload.decision.lower()}"),
            body=payload.decision_comment,
            link_path="/profile/training#training-deferrals",
            dedupe_key=f"deferral:{row.id}:decision:{payload.decision}:{control.revision_no}",
            actor_user_id=str(current_user.id),
            warning=payload.decision != "APPROVED",
        )
        db.commit()
        return _deferral_payload(db, row)

    @router.post("/deferrals/{deferral_id}/resubmit")
    def resubmit_deferral(
        deferral_id: str,
        payload: DeferralResubmitPayload,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = str(current_user.amo_id)
        row = _scoped(db, training_models.TrainingDeferralRequest, deferral_id, amo_id, "Deferral request")
        if _enum(row.status) != "RETURNED_FOR_INFORMATION":
            raise HTTPException(status_code=409, detail="Only a returned deferral can be resubmitted.")
        if str(current_user.id) not in {str(row.user_id), str(row.requested_by_user_id or "")} and not router_module._is_training_editor(current_user):
            raise HTTPException(status_code=403, detail="Only the learner/requester may resubmit this deferral.")
        if payload.requested_new_due_date is not None:
            if payload.requested_new_due_date < row.original_due_date:
                raise HTTPException(status_code=422, detail="Requested due date cannot precede the original due date.")
            row.requested_new_due_date = payload.requested_new_due_date
        if payload.reason_text is not None:
            row.reason_text = payload.reason_text
        row.status = training_models.DeferralStatus.PENDING
        row.decided_at = None
        row.decided_by_user_id = None
        control = _deferral_control(db, row)
        data = _workflow_data(control)
        data["learner_response"] = payload.learner_response
        data["replacement_plan"] = payload.replacement_plan or data.get("replacement_plan")
        data["resubmitted_at"] = _now().isoformat()
        control.status = "SUBMITTED"
        _save_workflow_data(control, data)
        _audit(router_module, db, actor=current_user, action="DEFERRAL_RESUBMIT", entity_type="TrainingDeferralRequest", entity_id=str(row.id), details=payload.model_dump(mode="json"))
        for reviewer in _quality_users(db, amo_id):
            if str(reviewer.id) == str(current_user.id):
                continue
            _notify(router_module, db, amo_id=amo_id, user_id=str(reviewer.id), title="Deferral resubmitted", body="A returned Training deferral has been corrected and resubmitted for review.", link_path="/training/deferrals", dedupe_key=f"deferral:{row.id}:resubmitted:{control.revision_no}:{reviewer.id}", actor_user_id=str(current_user.id))
        db.commit()
        return _deferral_payload(db, row)

    # -------------------------------------------------------------------
    # Evidence return/resubmit lineage
    # -------------------------------------------------------------------

    class EvidenceResubmitLink(BaseModel):
        replacement_file_id: str
        learner_comment: str | None = Field(None, max_length=2000)

    @router.post("/files/{file_id}/resubmit-link")
    def link_returned_evidence_replacement(
        file_id: str,
        payload: EvidenceResubmitLink,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = str(current_user.amo_id)
        old = _scoped(db, training_models.TrainingFile, file_id, amo_id, "Returned evidence")
        replacement = _scoped(db, training_models.TrainingFile, payload.replacement_file_id, amo_id, "Replacement evidence")
        if _enum(old.review_status) != "RETURNED":
            raise HTTPException(status_code=409, detail="Only returned evidence may be replaced through this workflow.")
        if str(old.owner_user_id) != str(replacement.owner_user_id):
            raise HTTPException(status_code=422, detail="Replacement evidence must belong to the same learner.")
        if str(current_user.id) != str(old.owner_user_id) and not router_module._is_training_editor(current_user):
            raise HTTPException(status_code=403, detail="Only the learner or an authorised Training editor may resubmit evidence.")
        if replacement.id == old.id:
            raise HTTPException(status_code=422, detail="Replacement evidence must be a new immutable file.")
        if old.course_id and replacement.course_id and str(old.course_id) != str(replacement.course_id):
            raise HTTPException(status_code=422, detail="Replacement evidence must remain linked to the same course.")
        if old.record_id and replacement.record_id and str(old.record_id) != str(replacement.record_id):
            raise HTTPException(status_code=422, detail="Replacement evidence must remain linked to the same Training record.")
        if old.deferral_request_id and replacement.deferral_request_id and str(old.deferral_request_id) != str(replacement.deferral_request_id):
            raise HTTPException(status_code=422, detail="Replacement evidence must remain linked to the same deferral.")
        replacement.review_status = training_models.TrainingFileReviewStatus.PENDING
        replacement.reviewed_at = None
        replacement.reviewed_by_user_id = None
        replacement.review_comment = None
        workflow = _workflow(
            db,
            amo_id=amo_id,
            workflow_type="EVIDENCE_REVIEW",
            idempotency_key=f"evidence-lineage:{old.id}",
            title="Training evidence resubmission",
            subject_user_id=str(old.owner_user_id),
            course_id=str(old.course_id) if old.course_id else None,
            event_id=str(old.event_id) if old.event_id else None,
            create_status="RETURNED",
        )
        data = _workflow_data(workflow)
        replacements = list(data.get("replacements") or [])
        replacements.append({"supersedes_file_id": str(old.id), "replacement_file_id": str(replacement.id), "submitted_at": _now().isoformat(), "submitted_by": str(current_user.id), "comment": payload.learner_comment})
        data["replacements"] = replacements
        data["current_file_id"] = str(replacement.id)
        workflow.status = "SUBMITTED"
        _save_workflow_data(workflow, data)
        _audit(router_module, db, actor=current_user, action="EVIDENCE_RESUBMIT", entity_type="TrainingFile", entity_id=str(replacement.id), details={"supersedes_file_id": str(old.id), "comment": payload.learner_comment})
        for reviewer in _quality_users(db, amo_id):
            if str(reviewer.id) in {str(current_user.id), str(old.owner_user_id)}:
                continue
            _notify(router_module, db, amo_id=amo_id, user_id=str(reviewer.id), title="Training evidence resubmitted", body=f"Replacement evidence '{replacement.original_filename}' is awaiting independent review.", link_path="/training", dedupe_key=f"evidence:{replacement.id}:review-pending:{reviewer.id}", actor_user_id=str(current_user.id))
        db.commit()
        return {"ok": True, "returned_file_id": str(old.id), "replacement_file_id": str(replacement.id), "review_status": _enum(replacement.review_status), "lineage": replacements}

    @router.get("/files/{file_id}/lineage")
    def evidence_lineage(
        file_id: str,
        db: Session = Depends(get_read_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = str(current_user.amo_id)
        file_row = _scoped(db, training_models.TrainingFile, file_id, amo_id, "Training evidence")
        if str(file_row.owner_user_id) != str(current_user.id) and not router_module._is_training_editor(current_user):
            raise HTTPException(status_code=403, detail="Not authorised to view this evidence lineage.")
        rows = db.query(operating_models.TrainingWorkflowInstance).filter(
            operating_models.TrainingWorkflowInstance.amo_id == amo_id,
            operating_models.TrainingWorkflowInstance.workflow_type == "EVIDENCE_REVIEW",
        ).all()
        for workflow in rows:
            data = _workflow_data(workflow)
            ids = {str(item.get("supersedes_file_id")) for item in data.get("replacements") or []} | {str(item.get("replacement_file_id")) for item in data.get("replacements") or []}
            if file_id in ids:
                return {"workflow_id": str(workflow.id), "status": workflow.status, **data}
        return {"workflow_id": None, "status": _enum(file_row.review_status), "current_file_id": str(file_row.id), "replacements": []}

    # -------------------------------------------------------------------
    # External learning request -> approval -> completion verification
    # -------------------------------------------------------------------

    class ExternalLearningCreate(BaseModel):
        course_id: str
        user_id: str | None = None
        provider_name: str = Field(..., min_length=2, max_length=255)
        provider_reference: str | None = Field(None, max_length=255)
        planned_start: date
        planned_end: date | None = None
        reason: str = Field(..., min_length=2, max_length=4000)
        estimated_cost: Decimal | None = Field(None, ge=0)
        currency: str = Field("USD", min_length=3, max_length=3)

    class ExternalLearningTransition(BaseModel):
        action: Literal["APPROVE", "RETURN", "REJECT", "SUBMIT_COMPLETION", "VERIFY_COMPLETION"]
        comment: str = Field(..., min_length=2, max_length=4000)
        completion_date: date | None = None
        certificate_reference: str | None = Field(None, max_length=255)
        evidence_file_ids: list[str] = Field(default_factory=list)
        exam_score: int | None = Field(None, ge=0, le=100)
        hours_completed: int | None = Field(None, ge=0)

    def external_read(workflow: operating_models.TrainingWorkflowInstance) -> dict[str, Any]:
        return {
            "id": str(workflow.id),
            "workflow_type": workflow.workflow_type,
            "status": workflow.status,
            "subject_user_id": workflow.subject_user_id,
            "course_id": workflow.course_id,
            "owner_user_id": workflow.owner_user_id,
            "reviewer_user_id": workflow.reviewer_user_id,
            "due_at": _iso(workflow.due_at),
            "data": _workflow_data(workflow),
            "submitted_at": _iso(workflow.submitted_at),
            "completed_at": _iso(workflow.completed_at),
            "created_at": _iso(workflow.created_at),
            "updated_at": _iso(workflow.updated_at),
        }

    @router.post("/external-learning/requests", status_code=201)
    def create_external_learning_request(
        payload: ExternalLearningCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = str(current_user.amo_id)
        user_id = payload.user_id or str(current_user.id)
        if user_id != str(current_user.id) and not router_module._is_training_editor(current_user):
            raise HTTPException(status_code=403, detail="You may request external learning only for yourself.")
        user = _scoped(db, account_models.User, user_id, amo_id, "Learner")
        course = _scoped(db, training_models.TrainingCourse, payload.course_id, amo_id, "Training course")
        if payload.planned_end and payload.planned_end < payload.planned_start:
            raise HTTPException(status_code=422, detail="External learning end date cannot precede the start date.")
        key_source = f"{amo_id}:{user.id}:{course.id}:{payload.provider_name}:{payload.planned_start.isoformat()}"
        key = hashlib.sha256(key_source.encode()).hexdigest()[:48]
        workflow = _workflow(db, amo_id=amo_id, workflow_type="EXTERNAL_LEARNING", idempotency_key=f"external:{key}", title=f"External learning: {course.course_name}", subject_user_id=str(user.id), owner_user_id=str(current_user.id), course_id=str(course.id), create_status="SUBMITTED")
        if workflow.submitted_at is None:
            workflow.submitted_at = _now()
            workflow.data_json = {
                "provider_name": payload.provider_name,
                "provider_reference": payload.provider_reference,
                "planned_start": payload.planned_start.isoformat(),
                "planned_end": _iso(payload.planned_end),
                "reason": payload.reason,
                "estimated_cost": str(payload.estimated_cost) if payload.estimated_cost is not None else None,
                "currency": payload.currency.upper(),
                "requester_user_id": str(current_user.id),
            }
            _audit(router_module, db, actor=current_user, action="EXTERNAL_LEARNING_SUBMIT", entity_type="TrainingWorkflowInstance", entity_id=str(workflow.id), details=workflow.data_json)
        for reviewer in _quality_users(db, amo_id):
            if str(reviewer.id) == str(current_user.id):
                continue
            _notify(router_module, db, amo_id=amo_id, user_id=str(reviewer.id), title="External learning request", body=f"{user.full_name} requested external learning for {course.course_name}.", link_path="/training", dedupe_key=f"external:{workflow.id}:submitted:{reviewer.id}", actor_user_id=str(current_user.id))
        db.commit()
        return external_read(workflow)

    @router.get("/external-learning/requests/me")
    def my_external_learning_requests(
        db: Session = Depends(get_read_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        rows = db.query(operating_models.TrainingWorkflowInstance).filter(
            operating_models.TrainingWorkflowInstance.amo_id == current_user.amo_id,
            operating_models.TrainingWorkflowInstance.workflow_type == "EXTERNAL_LEARNING",
            operating_models.TrainingWorkflowInstance.subject_user_id == str(current_user.id),
        ).order_by(operating_models.TrainingWorkflowInstance.created_at.desc()).all()
        return [external_read(row) for row in rows]

    @router.get("/external-learning/requests")
    def external_learning_queue(
        workflow_status: str | None = None,
        db: Session = Depends(get_read_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        _training_editor(router_module, current_user)
        query = db.query(operating_models.TrainingWorkflowInstance).filter(
            operating_models.TrainingWorkflowInstance.amo_id == current_user.amo_id,
            operating_models.TrainingWorkflowInstance.workflow_type == "EXTERNAL_LEARNING",
        )
        if workflow_status:
            query = query.filter(operating_models.TrainingWorkflowInstance.status == workflow_status.upper())
        return [external_read(row) for row in query.order_by(operating_models.TrainingWorkflowInstance.created_at.desc()).limit(500).all()]

    @router.post("/external-learning/requests/{workflow_id}/transition")
    def transition_external_learning(
        workflow_id: str,
        payload: ExternalLearningTransition,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = str(current_user.amo_id)
        workflow = _scoped(db, operating_models.TrainingWorkflowInstance, workflow_id, amo_id, "External learning request")
        if workflow.workflow_type != "EXTERNAL_LEARNING":
            raise HTTPException(status_code=404, detail="External learning request was not found.")
        learner_id = str(workflow.subject_user_id or "")
        data = _workflow_data(workflow)
        prior = str(workflow.status)
        reviewer_actions = {"APPROVE", "RETURN", "REJECT", "VERIFY_COMPLETION"}
        if payload.action in reviewer_actions:
            _training_editor(router_module, current_user)
            if str(current_user.id) in {learner_id, str(data.get("requester_user_id") or "")}:
                raise HTTPException(status_code=409, detail="Learner/requester cannot review their own external-learning workflow.")
        elif payload.action == "SUBMIT_COMPLETION":
            if str(current_user.id) != learner_id and not router_module._is_training_editor(current_user):
                raise HTTPException(status_code=403, detail="Only the learner may submit external-learning completion evidence.")

        if payload.action == "APPROVE":
            if prior not in {"SUBMITTED", "RETURNED"}:
                raise HTTPException(status_code=409, detail=f"Cannot approve external learning from {prior}.")
            workflow.status = "APPROVED"
            workflow.reviewer_user_id = str(current_user.id)
            data["request_decision_comment"] = payload.comment
            data["approved_at"] = _now().isoformat()
        elif payload.action == "RETURN":
            if prior not in {"SUBMITTED", "COMPLETION_SUBMITTED"}:
                raise HTTPException(status_code=409, detail=f"Cannot return external learning from {prior}.")
            workflow.status = "RETURNED"
            workflow.reviewer_user_id = str(current_user.id)
            data["return_comment"] = payload.comment
            data["returned_at"] = _now().isoformat()
        elif payload.action == "REJECT":
            workflow.status = "REJECTED"
            workflow.reviewer_user_id = str(current_user.id)
            workflow.completed_at = _now()
            data["rejection_comment"] = payload.comment
        elif payload.action == "SUBMIT_COMPLETION":
            if prior not in {"APPROVED", "RETURNED"}:
                raise HTTPException(status_code=409, detail=f"Cannot submit completion from {prior}.")
            if payload.completion_date is None or not payload.evidence_file_ids:
                raise HTTPException(status_code=422, detail="Completion date and at least one evidence file are required.")
            evidence = db.query(training_models.TrainingFile).filter(
                training_models.TrainingFile.amo_id == amo_id,
                training_models.TrainingFile.id.in_(payload.evidence_file_ids),
                training_models.TrainingFile.owner_user_id == learner_id,
            ).all()
            if len(evidence) != len(set(payload.evidence_file_ids)):
                raise HTTPException(status_code=422, detail="One or more evidence files are invalid for this learner/tenant.")
            data.update({
                "completion_date": payload.completion_date.isoformat(),
                "certificate_reference": payload.certificate_reference,
                "evidence_file_ids": [str(item.id) for item in evidence],
                "exam_score": payload.exam_score,
                "hours_completed": payload.hours_completed,
                "completion_comment": payload.comment,
                "completion_submitted_at": _now().isoformat(),
            })
            workflow.status = "COMPLETION_SUBMITTED"
            workflow.submitted_at = _now()
        elif payload.action == "VERIFY_COMPLETION":
            if prior != "COMPLETION_SUBMITTED":
                raise HTTPException(status_code=409, detail="Only submitted external completion can be verified.")
            evidence_ids = list(data.get("evidence_file_ids") or [])
            evidence = db.query(training_models.TrainingFile).filter(
                training_models.TrainingFile.amo_id == amo_id,
                training_models.TrainingFile.id.in_(evidence_ids or [""]),
            ).all()
            if not evidence or any(_enum(item.review_status) != "APPROVED" for item in evidence):
                raise HTTPException(status_code=409, detail="All external-learning evidence must be independently approved before completion can be verified.")
            if any(str(item.reviewed_by_user_id or "") == learner_id for item in evidence):
                raise HTTPException(status_code=409, detail="Learner-reviewed evidence cannot be used for external-learning credit.")
            course = _scoped(db, training_models.TrainingCourse, str(workflow.course_id), amo_id, "Training course")
            completion_date = date.fromisoformat(str(data["completion_date"]))
            valid_until = compliance.add_months(completion_date, int(course.frequency_months)) if course.frequency_months else None
            record_id = data.get("training_record_id")
            record = db.query(training_models.TrainingRecord).filter(
                training_models.TrainingRecord.amo_id == amo_id,
                training_models.TrainingRecord.id == record_id,
            ).first() if record_id else None
            if record is None:
                record = training_models.TrainingRecord(
                    amo_id=amo_id,
                    user_id=learner_id,
                    course_id=str(course.id),
                    completion_date=completion_date,
                    valid_until=valid_until,
                    hours_completed=data.get("hours_completed"),
                    exam_score=data.get("exam_score"),
                    certificate_reference=data.get("certificate_reference"),
                    remarks=f"Verified external learning. Workflow {workflow.id}. {payload.comment}",
                    verification_status=training_models.TrainingRecordVerificationStatus.VERIFIED,
                    verified_at=_now(),
                    verified_by_user_id=str(current_user.id),
                    created_by_user_id=str(current_user.id),
                    is_manual_entry=False,
                )
                db.add(record)
                db.flush()
                for item in evidence:
                    if item.record_id is None:
                        item.record_id = str(record.id)
                data["training_record_id"] = str(record.id)
            workflow.status = "COMPLETED"
            workflow.reviewer_user_id = str(current_user.id)
            workflow.completed_at = _now()
            data["verification_comment"] = payload.comment
            data["verified_at"] = _now().isoformat()
        _save_workflow_data(workflow, data)
        _audit(router_module, db, actor=current_user, action=f"EXTERNAL_LEARNING_{payload.action}", entity_type="TrainingWorkflowInstance", entity_id=str(workflow.id), details={"from": prior, "to": workflow.status, "comment": payload.comment})
        _notify(router_module, db, amo_id=amo_id, user_id=learner_id, title=f"External learning: {str(workflow.status).replace('_', ' ').title()}", body=payload.comment, link_path="/profile/training", dedupe_key=f"external:{workflow.id}:{workflow.status}:{workflow.revision_no}", actor_user_id=str(current_user.id), warning=workflow.status in {"RETURNED", "REJECTED"})
        db.commit()
        return external_read(workflow)

    # -------------------------------------------------------------------
    # Calendar/RSVP - stable iCalendar object for Google/Outlook import/update
    # -------------------------------------------------------------------

    @router.get("/invitations/{invitation_id}/calendar.ics")
    def invitation_calendar(
        invitation_id: str,
        db: Session = Depends(get_read_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = str(current_user.amo_id)
        invitation = _scoped(db, operating_models.TrainingSessionInvitation, invitation_id, amo_id, "Training invitation")
        if str(invitation.user_id) != str(current_user.id) and not router_module._is_training_editor(current_user):
            raise HTTPException(status_code=403, detail="You may export only your own Training invitation.")
        event = _scoped(db, training_models.TrainingEvent, str(invitation.event_id), amo_id, "Training event")
        course = _scoped(db, training_models.TrainingCourse, str(event.course_id), amo_id, "Training course")
        starts = event.starts_on.strftime("%Y%m%d")
        final_day = event.ends_on or event.starts_on
        ends = (final_day + timedelta(days=1)).strftime("%Y%m%d")
        stamp = _now().strftime("%Y%m%dT%H%M%SZ")
        sequence = int((event.updated_at or event.created_at or _now()).timestamp())
        cancelled = _enum(event.status) == "CANCELLED"
        method = "CANCEL" if cancelled else "REQUEST"
        ics_status = "CANCELLED" if cancelled else "CONFIRMED"
        def esc(value: Any) -> str:
            return str(value or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//AMO Portal//Training//EN",
            f"METHOD:{method}",
            "CALSCALE:GREGORIAN",
            "BEGIN:VEVENT",
            f"UID:training-{event.id}@amo-portal",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{starts}",
            f"DTEND;VALUE=DATE:{ends}",
            f"SEQUENCE:{sequence}",
            f"STATUS:{ics_status}",
            f"SUMMARY:{esc(event.title or course.course_name)}",
            f"DESCRIPTION:{esc(course.course_name)}",
        ]
        if event.location:
            lines.append(f"LOCATION:{esc(event.location)}")
        lines.extend(["END:VEVENT", "END:VCALENDAR", ""])
        content = "\r\n".join(lines)
        return Response(content=content, media_type="text/calendar; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="training-{event.id}.ics"', "Cache-Control": "private, no-store"})

    # -------------------------------------------------------------------
    # Assessment attempt engine (written, practical and oral)
    # -------------------------------------------------------------------

    class AssessmentAutosave(BaseModel):
        answers: dict[str, Any] = Field(default_factory=dict)
        client_revision: int | None = Field(None, ge=0)

    class AssessmentReviewPayload(BaseModel):
        outcome: Literal["PASSED", "FAILED", "REVIEW_REQUIRED"]
        score: Decimal | None = Field(None, ge=0, le=100)
        comments: str = Field(..., min_length=2, max_length=4000)
        proctor_signoff: dict[str, Any] = Field(default_factory=dict)
        moderation_decision: str | None = Field(None, max_length=1000)

    class AssessmentAppealPayload(BaseModel):
        reason: str = Field(..., min_length=2, max_length=4000)

    def assessment_policy(template: operating_models.TrainingAssessmentTemplate) -> dict[str, Any]:
        policy = {"attempt_limit": 3, "time_limit_minutes": 60, "cooldown_hours": 24, "randomize_questions": True, "question_count": None}
        raw = template.mandatory_criteria or []
        if isinstance(raw, dict):
            source = raw.get("attempt_policy") if isinstance(raw.get("attempt_policy"), dict) else raw
            policy.update({key: source[key] for key in policy if key in source})
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict) and isinstance(item.get("attempt_policy"), dict):
                    source = item["attempt_policy"]
                    policy.update({key: source[key] for key in policy if key in source})
        policy["attempt_limit"] = max(1, min(int(policy.get("attempt_limit") or 3), 20))
        policy["time_limit_minutes"] = max(1, min(int(policy.get("time_limit_minutes") or 60), 720))
        policy["cooldown_hours"] = max(0, min(int(policy.get("cooldown_hours") or 24), 720))
        return policy

    def question_snapshot(db: Session, instance: operating_models.TrainingAssessmentInstance, *, attempt_no: int, policy: dict[str, Any]) -> list[dict[str, Any]]:
        questions = db.query(operating_models.TrainingAssessmentQuestion).filter(
            operating_models.TrainingAssessmentQuestion.amo_id == instance.amo_id,
            operating_models.TrainingAssessmentQuestion.template_id == instance.template_id,
            operating_models.TrainingAssessmentQuestion.active.is_(True),
        ).order_by(operating_models.TrainingAssessmentQuestion.sequence_no.asc()).all()
        if policy.get("randomize_questions"):
            seed = int(hashlib.sha256(f"{instance.id}:{attempt_no}".encode()).hexdigest()[:16], 16)
            random.Random(seed).shuffle(questions)
        count = policy.get("question_count")
        if count:
            questions = questions[: max(1, min(int(count), len(questions)))]
        return [{"id": str(q.id), "sequence_no": q.sequence_no, "question_text": q.question_text, "response_type": q.response_type, "answer_options": q.answer_options or [], "marks": float(q.marks or 0), "mandatory": bool(q.mandatory)} for q in questions]

    def assessment_read(db: Session, instance: operating_models.TrainingAssessmentInstance, *, include_answers: bool) -> dict[str, Any]:
        template = _scoped(db, operating_models.TrainingAssessmentTemplate, str(instance.template_id), str(instance.amo_id), "Assessment template")
        results = dict(instance.results or {})
        engine = dict(results.get("_engine") or {})
        payload = {
            "id": str(instance.id), "status": instance.status, "outcome": instance.outcome,
            "score": float(instance.score) if instance.score is not None else None,
            "assessment_type": template.assessment_type, "template_name": template.name,
            "candidate_user_id": str(instance.candidate_user_id), "course_id": instance.course_id,
            "planned_at": _iso(instance.planned_at), "performed_at": _iso(instance.performed_at),
            "attempt": engine, "questions": engine.get("questions") or [], "comments": instance.comments,
        }
        if include_answers:
            payload["answers"] = results.get("answers") or {}
        return payload

    @router.post("/assessments/{assessment_id}/attempt/start")
    def start_assessment_attempt(
        assessment_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = str(current_user.amo_id)
        instance = _scoped(db, operating_models.TrainingAssessmentInstance, assessment_id, amo_id, "Assessment")
        if str(instance.candidate_user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="Only the assigned candidate may start this assessment.")
        template = _scoped(db, operating_models.TrainingAssessmentTemplate, str(instance.template_id), amo_id, "Assessment template")
        policy = assessment_policy(template)
        results = dict(instance.results or {})
        engine = dict(results.get("_engine") or {})
        previous_attempt = int(engine.get("attempt_no") or 0)
        if instance.status == "IN_PROGRESS":
            return assessment_read(db, instance, include_answers=True)
        if previous_attempt >= policy["attempt_limit"]:
            raise HTTPException(status_code=409, detail="Assessment attempt limit has been reached.")
        cooldown_until_raw = engine.get("cooldown_until")
        if cooldown_until_raw:
            cooldown_until = datetime.fromisoformat(str(cooldown_until_raw))
            if cooldown_until.tzinfo is None:
                cooldown_until = cooldown_until.replace(tzinfo=UTC)
            if _now() < cooldown_until:
                raise HTTPException(status_code=409, detail=f"Retake cooldown remains active until {cooldown_until.isoformat()}.")
        attempt_no = previous_attempt + 1
        started = _now()
        deadline = started + timedelta(minutes=policy["time_limit_minutes"])
        questions = question_snapshot(db, instance, attempt_no=attempt_no, policy=policy)
        engine = {
            "attempt_no": attempt_no,
            "attempt_limit": policy["attempt_limit"],
            "started_at": started.isoformat(),
            "deadline_at": deadline.isoformat(),
            "time_limit_minutes": policy["time_limit_minutes"],
            "cooldown_hours": policy["cooldown_hours"],
            "questions": questions,
            "autosave_revision": 0,
        }
        results["_engine"] = engine
        results["answers"] = {}
        results.setdefault("_attempt_history", [])
        instance.results = results
        instance.status = "IN_PROGRESS"
        _audit(router_module, db, actor=current_user, action="ASSESSMENT_ATTEMPT_START", entity_type="TrainingAssessmentInstance", entity_id=str(instance.id), details={"attempt_no": attempt_no, "deadline_at": deadline.isoformat()})
        db.commit()
        return assessment_read(db, instance, include_answers=True)

    def assert_open_attempt(instance: operating_models.TrainingAssessmentInstance, current_user: account_models.User) -> tuple[dict[str, Any], dict[str, Any]]:
        if str(instance.candidate_user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="Only the candidate may modify this assessment attempt.")
        if instance.status != "IN_PROGRESS":
            raise HTTPException(status_code=409, detail="Assessment is not currently in progress.")
        results = dict(instance.results or {})
        engine = dict(results.get("_engine") or {})
        deadline_raw = engine.get("deadline_at")
        if deadline_raw:
            deadline = datetime.fromisoformat(str(deadline_raw))
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
            if _now() > deadline:
                instance.status = "TIMED_OUT"
                instance.outcome = "FAILED"
                instance.performed_at = _now()
                raise HTTPException(status_code=409, detail="Assessment time limit has expired.")
        return results, engine

    @router.put("/assessments/{assessment_id}/attempt/autosave")
    def autosave_assessment_attempt(
        assessment_id: str,
        payload: AssessmentAutosave,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        instance = _scoped(db, operating_models.TrainingAssessmentInstance, assessment_id, str(current_user.amo_id), "Assessment")
        try:
            results, engine = assert_open_attempt(instance, current_user)
        except HTTPException:
            db.commit()
            raise
        allowed_ids = {str(q.get("id")) for q in engine.get("questions") or []}
        unknown = set(payload.answers) - allowed_ids
        if unknown:
            raise HTTPException(status_code=422, detail="Answers contain questions outside this governed attempt snapshot.")
        answers = dict(results.get("answers") or {})
        answers.update(payload.answers)
        results["answers"] = answers
        engine["autosave_revision"] = int(engine.get("autosave_revision") or 0) + 1
        engine["autosaved_at"] = _now().isoformat()
        results["_engine"] = engine
        instance.results = results
        db.commit()
        return {"ok": True, "autosave_revision": engine["autosave_revision"], "saved_at": engine["autosaved_at"]}

    @router.post("/assessments/{assessment_id}/attempt/submit")
    def submit_assessment_attempt(
        assessment_id: str,
        payload: AssessmentAutosave,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = str(current_user.amo_id)
        instance = _scoped(db, operating_models.TrainingAssessmentInstance, assessment_id, amo_id, "Assessment")
        try:
            results, engine = assert_open_attempt(instance, current_user)
        except HTTPException:
            db.commit()
            raise
        answers = dict(results.get("answers") or {})
        answers.update(payload.answers)
        template = _scoped(db, operating_models.TrainingAssessmentTemplate, str(instance.template_id), amo_id, "Assessment template")
        policy = assessment_policy(template)
        question_ids = [str(q.get("id")) for q in engine.get("questions") or []]
        questions = db.query(operating_models.TrainingAssessmentQuestion).filter(
            operating_models.TrainingAssessmentQuestion.amo_id == amo_id,
            operating_models.TrainingAssessmentQuestion.id.in_(question_ids or [""]),
        ).all()
        q_by_id = {str(q.id): q for q in questions}
        earned = Decimal("0")
        total = Decimal("0")
        manual_required = False
        for snapshot in engine.get("questions") or []:
            q = q_by_id.get(str(snapshot.get("id")))
            if q is None:
                continue
            marks = Decimal(str(q.marks or 0))
            total += marks
            answer = answers.get(str(q.id))
            response_type = str(q.response_type or "TEXT").upper()
            if response_type in {"MCQ", "MULTIPLE_CHOICE", "BOOLEAN", "TRUE_FALSE", "NUMBER"} and q.answer_key is not None:
                expected = q.answer_key
                if isinstance(expected, dict) and "value" in expected:
                    expected = expected["value"]
                if str(answer).strip().casefold() == str(expected).strip().casefold():
                    earned += marks
            else:
                manual_required = True
        score = (earned / total * Decimal("100")) if total > 0 and not manual_required else None
        results["answers"] = answers
        history = list(results.get("_attempt_history") or [])
        history.append({"attempt_no": engine.get("attempt_no"), "submitted_at": _now().isoformat(), "answers": answers, "auto_score": float(score) if score is not None else None})
        results["_attempt_history"] = history
        if manual_required:
            instance.status = "SUBMITTED"
            instance.outcome = "REVIEW_REQUIRED"
        else:
            threshold = Decimal(str(template.pass_threshold if template.pass_threshold is not None else 80))
            passed = bool(score is not None and score >= threshold)
            instance.score = score
            instance.outcome = "PASSED" if passed else "FAILED"
            instance.status = "COMPLETED" if passed else "FAILED"
            if not passed and int(engine.get("attempt_no") or 0) < int(policy["attempt_limit"]):
                engine["cooldown_until"] = (_now() + timedelta(hours=policy["cooldown_hours"])).isoformat()
        engine["submitted_at"] = _now().isoformat()
        results["_engine"] = engine
        instance.results = results
        instance.performed_at = _now()
        _audit(router_module, db, actor=current_user, action="ASSESSMENT_ATTEMPT_SUBMIT", entity_type="TrainingAssessmentInstance", entity_id=str(instance.id), details={"attempt_no": engine.get("attempt_no"), "status": instance.status, "outcome": instance.outcome, "score": float(score) if score is not None else None})
        db.commit()
        return assessment_read(db, instance, include_answers=True)

    @router.post("/assessments/{assessment_id}/review")
    def review_assessment_attempt(
        assessment_id: str,
        payload: AssessmentReviewPayload,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        _training_editor(router_module, current_user)
        instance = _scoped(db, operating_models.TrainingAssessmentInstance, assessment_id, str(current_user.amo_id), "Assessment")
        if str(instance.candidate_user_id) == str(current_user.id):
            raise HTTPException(status_code=409, detail="Candidate cannot assess/review their own examination.")
        if instance.status not in {"SUBMITTED", "REVIEW_REQUIRED", "FAILED", "COMPLETED"}:
            raise HTTPException(status_code=409, detail=f"Assessment in {instance.status} is not ready for review.")
        results = dict(instance.results or {})
        engine = dict(results.get("_engine") or {})
        engine["proctor_signoff"] = payload.proctor_signoff
        engine["moderation_decision"] = payload.moderation_decision
        engine["reviewed_by_user_id"] = str(current_user.id)
        engine["reviewed_at"] = _now().isoformat()
        results["_engine"] = engine
        instance.results = results
        instance.score = payload.score
        instance.outcome = payload.outcome
        instance.comments = payload.comments
        instance.review_decision = payload.outcome
        instance.reviewer_user_id = str(current_user.id)
        instance.reviewed_at = _now()
        instance.status = "COMPLETED" if payload.outcome == "PASSED" else ("FAILED" if payload.outcome == "FAILED" else "REVIEW_REQUIRED")
        if payload.outcome == "PASSED":
            instance.approved_at = _now()
        _audit(router_module, db, actor=current_user, action="ASSESSMENT_REVIEW", entity_type="TrainingAssessmentInstance", entity_id=str(instance.id), details=payload.model_dump(mode="json"))
        db.commit()
        return assessment_read(db, instance, include_answers=False)

    @router.post("/assessments/{assessment_id}/appeal", status_code=201)
    def appeal_assessment(
        assessment_id: str,
        payload: AssessmentAppealPayload,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        instance = _scoped(db, operating_models.TrainingAssessmentInstance, assessment_id, str(current_user.amo_id), "Assessment")
        if str(instance.candidate_user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="Only the candidate may appeal this assessment.")
        if instance.outcome not in {"FAILED", "REVIEW_REQUIRED"}:
            raise HTTPException(status_code=409, detail="Only failed/review-required outcomes may be appealed.")
        workflow = _workflow(db, amo_id=str(current_user.amo_id), workflow_type="ASSESSMENT_APPEAL", idempotency_key=f"assessment-appeal:{instance.id}", title="Assessment appeal", subject_user_id=str(current_user.id), course_id=str(instance.course_id) if instance.course_id else None, authorization_case_id=str(instance.authorization_case_id) if instance.authorization_case_id else None, create_status="SUBMITTED")
        workflow.submitted_at = _now()
        workflow.data_json = {"assessment_id": str(instance.id), "reason": payload.reason, "outcome": instance.outcome, "score": float(instance.score) if instance.score is not None else None}
        _audit(router_module, db, actor=current_user, action="ASSESSMENT_APPEAL_SUBMIT", entity_type="TrainingWorkflowInstance", entity_id=str(workflow.id), details=workflow.data_json)
        db.commit()
        return {"id": str(workflow.id), "status": workflow.status, "data": workflow.data_json}

    # -------------------------------------------------------------------
    # OJT / competence self-service
    # -------------------------------------------------------------------

    class OjtLogCreate(BaseModel):
        course_id: str | None = None
        activity: str = Field(..., min_length=2, max_length=4000)
        task_reference: str | None = Field(None, max_length=255)
        activity_date: date
        duration_hours: Decimal | None = Field(None, ge=0, le=24)
        supervisor_user_id: str | None = None
        training_file_id: str | None = None

    class OjtVerifyPayload(BaseModel):
        decision: Literal["VERIFIED", "REJECTED", "RETURNED"]
        comment: str = Field(..., min_length=2, max_length=4000)

    @router.post("/ojt/logs", status_code=201)
    def create_ojt_log(
        payload: OjtLogCreate,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = str(current_user.amo_id)
        if payload.course_id:
            _scoped(db, training_models.TrainingCourse, payload.course_id, amo_id, "Training course")
        if payload.supervisor_user_id:
            _scoped(db, account_models.User, payload.supervisor_user_id, amo_id, "OJT supervisor")
            if payload.supervisor_user_id == str(current_user.id):
                raise HTTPException(status_code=422, detail="OJT supervisor must be another person.")
        if payload.training_file_id:
            evidence = _scoped(db, training_models.TrainingFile, payload.training_file_id, amo_id, "OJT evidence")
            if str(evidence.owner_user_id) != str(current_user.id):
                raise HTTPException(status_code=422, detail="OJT evidence must belong to the candidate.")
        row = operating_models.TrainingExperienceLog(
            amo_id=amo_id,
            candidate_user_id=str(current_user.id),
            log_type="OJT",
            aircraft_component_task=payload.task_reference,
            activity=payload.activity,
            supervisor_user_id=payload.supervisor_user_id,
            activity_date=payload.activity_date,
            duration_hours=payload.duration_hours,
            reference=str(payload.course_id) if payload.course_id else None,
            training_file_id=payload.training_file_id,
            verification_status="PENDING",
        )
        db.add(row); db.flush()
        _audit(router_module, db, actor=current_user, action="OJT_LOG_CREATE", entity_type="TrainingExperienceLog", entity_id=str(row.id), details=payload.model_dump(mode="json"))
        db.commit(); db.refresh(row)
        return {column.name: _iso(getattr(row, column.name)) for column in row.__table__.columns}

    @router.post("/ojt/logs/{log_id}/verify")
    def verify_ojt_log(
        log_id: str,
        payload: OjtVerifyPayload,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = str(current_user.amo_id)
        row = _scoped(db, operating_models.TrainingExperienceLog, log_id, amo_id, "OJT log")
        allowed_supervisor = str(row.supervisor_user_id or "") == str(current_user.id)
        if not allowed_supervisor and not router_module._is_training_editor(current_user):
            raise HTTPException(status_code=403, detail="Only the assigned supervisor or Training editor may verify OJT.")
        if str(row.candidate_user_id) == str(current_user.id):
            raise HTTPException(status_code=409, detail="Candidate cannot verify their own OJT evidence.")
        if row.training_file_id:
            evidence = _scoped(db, training_models.TrainingFile, str(row.training_file_id), amo_id, "OJT evidence")
            if payload.decision == "VERIFIED" and _enum(evidence.review_status) != "APPROVED":
                raise HTTPException(status_code=409, detail="OJT cannot be verified until linked evidence has been independently approved.")
        row.verification_status = payload.decision
        row.verified_by_user_id = str(current_user.id)
        row.verified_at = _now()
        _audit(router_module, db, actor=current_user, action="OJT_VERIFY", entity_type="TrainingExperienceLog", entity_id=str(row.id), details=payload.model_dump(mode="json"))
        db.commit(); db.refresh(row)
        return {column.name: _iso(getattr(row, column.name)) for column in row.__table__.columns}

    @router.get("/ojt/me")
    def my_ojt_log(
        db: Session = Depends(get_read_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        rows = db.query(operating_models.TrainingExperienceLog).filter(
            operating_models.TrainingExperienceLog.amo_id == current_user.amo_id,
            operating_models.TrainingExperienceLog.candidate_user_id == str(current_user.id),
            operating_models.TrainingExperienceLog.log_type == "OJT",
        ).order_by(operating_models.TrainingExperienceLog.activity_date.desc()).all()
        verified_hours = sum(Decimal(str(row.duration_hours or 0)) for row in rows if row.verification_status == "VERIFIED")
        return {"verified_hours": float(verified_hours), "items": [{column.name: _iso(getattr(row, column.name)) for column in row.__table__.columns} for row in rows]}

    # -------------------------------------------------------------------
    # Explainable authorization readiness + renewal
    # -------------------------------------------------------------------

    def authorization_readiness(db: Session, case: operating_models.TrainingAuthorizationCase) -> dict[str, Any]:
        amo_id = str(case.amo_id)
        user = _scoped(db, account_models.User, str(case.candidate_user_id), amo_id, "Authorization candidate")
        evaluation = compliance.evaluate_user_training_policy(db, user, required_only=True, today=date.today())
        blockers: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        for item in evaluation.mandatory_items:
            entry = {"type": "TRAINING", "course_id": item.course_id, "course_name": item.course_name, "status": item.status, "due": _iso(item.extended_due_date or item.valid_until)}
            if item.status in {"OVERDUE", "NOT_DONE"}:
                blockers.append(entry)
            elif item.status in {"DUE_SOON", "DEFERRED", "SCHEDULED_ONLY"}:
                warnings.append(entry)
        deferrals = db.query(training_models.TrainingDeferralRequest).filter(
            training_models.TrainingDeferralRequest.amo_id == amo_id,
            training_models.TrainingDeferralRequest.user_id == case.candidate_user_id,
            training_models.TrainingDeferralRequest.status.in_([training_models.DeferralStatus.PENDING, training_models.DeferralStatus.RETURNED_FOR_INFORMATION, training_models.DeferralStatus.EXPIRED]),
        ).all()
        for deferral in deferrals:
            blockers.append({"type": "DEFERRAL", "deferral_id": str(deferral.id), "course_id": str(deferral.course_id), "status": _enum(deferral.status), "reason": "Training deferral requires resolution before authorization decision."})
        templates = db.query(operating_models.TrainingAssessmentTemplate).filter(
            operating_models.TrainingAssessmentTemplate.amo_id == amo_id,
            operating_models.TrainingAssessmentTemplate.id.in_(
                db.query(operating_models.TrainingAssessmentInstance.template_id).filter(
                    operating_models.TrainingAssessmentInstance.amo_id == amo_id,
                    operating_models.TrainingAssessmentInstance.authorization_case_id == case.id,
                )
            ),
        ).all()
        template_by_id = {str(t.id): t for t in templates}
        instances = db.query(operating_models.TrainingAssessmentInstance).filter(
            operating_models.TrainingAssessmentInstance.amo_id == amo_id,
            operating_models.TrainingAssessmentInstance.authorization_case_id == case.id,
        ).order_by(operating_models.TrainingAssessmentInstance.created_at.desc()).all()
        latest_by_type: dict[str, operating_models.TrainingAssessmentInstance] = {}
        for instance in instances:
            template = template_by_id.get(str(instance.template_id))
            if template:
                latest_by_type.setdefault(str(template.assessment_type).upper(), instance)
        for required_type in case.required_assessment_types or []:
            assessment = latest_by_type.get(str(required_type).upper())
            if assessment is None or _enum(assessment.outcome) != "PASSED":
                blockers.append({"type": "ASSESSMENT", "assessment_type": str(required_type).upper(), "status": assessment.status if assessment else "NOT_ASSIGNED", "outcome": assessment.outcome if assessment else None})
        latest_competence = db.query(operating_models.TrainingCompetenceReview).filter(
            operating_models.TrainingCompetenceReview.amo_id == amo_id,
            operating_models.TrainingCompetenceReview.candidate_user_id == case.candidate_user_id,
        ).order_by(operating_models.TrainingCompetenceReview.period_end.desc()).first()
        if latest_competence is not None and _enum(latest_competence.outcome) not in {"COMPETENT", "SATISFACTORY", "PASSED", "APPROVED"}:
            blockers.append({"type": "COMPETENCE", "review_id": str(latest_competence.id), "outcome": latest_competence.outcome, "status": latest_competence.status})
        snapshot = {"computed_at": _now().isoformat(), "ready": not blockers, "blockers": blockers, "warnings": warnings, "candidate_user_id": str(case.candidate_user_id), "authorization_case_id": str(case.id)}
        case.readiness_snapshot = snapshot
        case.readiness_computed_at = _now()
        if case.status not in {"ISSUED", "RESTRICTED", "SUSPENDED", "EXPIRED", "WITHDRAWN"}:
            case.status = "READY" if not blockers else "NOT_READY"
        return snapshot

    @router.get("/authorization-cases/{case_id}/readiness/explain")
    def explain_authorization_readiness(
        case_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = str(current_user.amo_id)
        case = _scoped(db, operating_models.TrainingAuthorizationCase, case_id, amo_id, "Authorization case")
        if str(case.candidate_user_id) != str(current_user.id) and not router_module._is_training_editor(current_user):
            raise HTTPException(status_code=403, detail="Not authorised to view this authorization readiness case.")
        snapshot = authorization_readiness(db, case)
        db.commit()
        return snapshot

    @router.post("/authorization-cases/{case_id}/renewal", status_code=201)
    def create_authorization_renewal(
        case_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        _training_editor(router_module, current_user)
        amo_id = str(current_user.amo_id)
        prior = _scoped(db, operating_models.TrainingAuthorizationCase, case_id, amo_id, "Authorization case")
        renewal = operating_models.TrainingAuthorizationCase(
            amo_id=amo_id,
            candidate_user_id=str(prior.candidate_user_id),
            authorisation_type_id=str(prior.authorisation_type_id),
            requested_scope=prior.requested_scope,
            requested_privileges=list(prior.requested_privileges or []),
            requested_by_user_id=str(current_user.id),
            owner_user_id=str(current_user.id),
            application_date=date.today(),
            status="NOT_READY",
            required_assessment_types=list(prior.required_assessment_types or []),
            manual_references=list(prior.manual_references or []),
            required_committee_positions=list(prior.required_committee_positions or []),
            readiness_snapshot={"renews_case_id": str(prior.id)},
        )
        db.add(renewal); db.flush()
        snapshot = authorization_readiness(db, renewal)
        _audit(router_module, db, actor=current_user, action="AUTHORIZATION_RENEWAL_CREATE", entity_type="TrainingAuthorizationCase", entity_id=str(renewal.id), details={"renews_case_id": str(prior.id), "readiness": snapshot})
        db.commit(); db.refresh(renewal)
        return {column.name: _iso(getattr(renewal, column.name)) for column in renewal.__table__.columns}

    # -------------------------------------------------------------------
    # Waitlist/capacity/conflict handling
    # -------------------------------------------------------------------

    class EnrollmentPayload(BaseModel):
        user_id: str | None = None

    def event_conflicts(db: Session, *, amo_id: str, event: training_models.TrainingEvent, user_id: str) -> list[dict[str, Any]]:
        end = event.ends_on or event.starts_on
        other = db.query(training_models.TrainingEventParticipant, training_models.TrainingEvent).join(
            training_models.TrainingEvent,
            training_models.TrainingEvent.id == training_models.TrainingEventParticipant.event_id,
        ).filter(
            training_models.TrainingEventParticipant.amo_id == amo_id,
            training_models.TrainingEventParticipant.user_id == user_id,
            training_models.TrainingEventParticipant.event_id != event.id,
            training_models.TrainingEventParticipant.status.in_([training_models.TrainingParticipantStatus.SCHEDULED, training_models.TrainingParticipantStatus.INVITED, training_models.TrainingParticipantStatus.CONFIRMED]),
            training_models.TrainingEvent.status != training_models.TrainingEventStatus.CANCELLED,
            training_models.TrainingEvent.starts_on <= end,
            func.coalesce(training_models.TrainingEvent.ends_on, training_models.TrainingEvent.starts_on) >= event.starts_on,
        ).all()
        return [{"event_id": str(evt.id), "title": evt.title, "starts_on": _iso(evt.starts_on), "ends_on": _iso(evt.ends_on)} for _participant, evt in other]

    @router.get("/events/{event_id}/conflicts")
    def inspect_event_conflicts(
        event_id: str,
        user_id: str | None = None,
        db: Session = Depends(get_read_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = str(current_user.amo_id)
        event = _scoped(db, training_models.TrainingEvent, event_id, amo_id, "Training event")
        target = user_id or str(current_user.id)
        if target != str(current_user.id) and not router_module._is_training_editor(current_user):
            raise HTTPException(status_code=403, detail="Not authorised to inspect another learner's conflicts.")
        conflicts = event_conflicts(db, amo_id=amo_id, event=event, user_id=target)
        course = _scoped(db, training_models.TrainingCourse, str(event.course_id), amo_id, "Training course")
        confirmed_count = db.query(func.count(training_models.TrainingEventParticipant.id)).filter(
            training_models.TrainingEventParticipant.amo_id == amo_id,
            training_models.TrainingEventParticipant.event_id == event.id,
            training_models.TrainingEventParticipant.status.in_([training_models.TrainingParticipantStatus.SCHEDULED, training_models.TrainingParticipantStatus.INVITED, training_models.TrainingParticipantStatus.CONFIRMED]),
        ).scalar() or 0
        capacity = course.default_capacity
        return {"participant_conflicts": conflicts, "capacity": capacity, "reserved": int(confirmed_count), "at_capacity": bool(capacity and confirmed_count >= capacity)}

    @router.post("/events/{event_id}/enrol")
    def enrol_or_waitlist(
        event_id: str,
        payload: EnrollmentPayload,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        amo_id = str(current_user.amo_id)
        event = _scoped(db, training_models.TrainingEvent, event_id, amo_id, "Training event")
        user_id = payload.user_id or str(current_user.id)
        if user_id != str(current_user.id) and not router_module._is_training_editor(current_user):
            raise HTTPException(status_code=403, detail="You may enrol only yourself.")
        _scoped(db, account_models.User, user_id, amo_id, "Learner")
        existing = db.query(training_models.TrainingEventParticipant).filter(
            training_models.TrainingEventParticipant.amo_id == amo_id,
            training_models.TrainingEventParticipant.event_id == event.id,
            training_models.TrainingEventParticipant.user_id == user_id,
        ).first()
        if existing and _enum(existing.status) not in {"CANCELLED", "WAITLISTED"}:
            return {"participant_id": str(existing.id), "status": _enum(existing.status), "duplicate": True}
        conflicts = event_conflicts(db, amo_id=amo_id, event=event, user_id=user_id)
        if conflicts:
            raise HTTPException(status_code=409, detail={"code": "TRAINING_SESSION_CONFLICT", "conflicts": conflicts})
        course = _scoped(db, training_models.TrainingCourse, str(event.course_id), amo_id, "Training course")
        reserved = db.query(func.count(training_models.TrainingEventParticipant.id)).filter(
            training_models.TrainingEventParticipant.amo_id == amo_id,
            training_models.TrainingEventParticipant.event_id == event.id,
            training_models.TrainingEventParticipant.status.in_([training_models.TrainingParticipantStatus.SCHEDULED, training_models.TrainingParticipantStatus.INVITED, training_models.TrainingParticipantStatus.CONFIRMED]),
        ).scalar() or 0
        target_status = training_models.TrainingParticipantStatus.WAITLISTED if course.default_capacity and reserved >= course.default_capacity else training_models.TrainingParticipantStatus.CONFIRMED
        row = existing or training_models.TrainingEventParticipant(amo_id=amo_id, event_id=str(event.id), user_id=user_id)
        row.status = target_status
        db.add(row); db.flush()
        _audit(router_module, db, actor=current_user, action="TRAINING_ENROL", entity_type="TrainingEventParticipant", entity_id=str(row.id), details={"event_id": str(event.id), "user_id": user_id, "status": _enum(target_status)})
        db.commit(); db.refresh(row)
        return {"participant_id": str(row.id), "status": _enum(row.status), "waitlisted": _enum(row.status) == "WAITLISTED"}

    @router.post("/events/{event_id}/waitlist/promote")
    def promote_waitlist(
        event_id: str,
        db: Session = Depends(get_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        _training_editor(router_module, current_user)
        amo_id = str(current_user.amo_id)
        event = _scoped(db, training_models.TrainingEvent, event_id, amo_id, "Training event")
        course = _scoped(db, training_models.TrainingCourse, str(event.course_id), amo_id, "Training course")
        capacity = course.default_capacity
        if not capacity:
            raise HTTPException(status_code=409, detail="Course has no capacity limit; waitlist promotion is not required.")
        reserved = int(db.query(func.count(training_models.TrainingEventParticipant.id)).filter(
            training_models.TrainingEventParticipant.amo_id == amo_id,
            training_models.TrainingEventParticipant.event_id == event.id,
            training_models.TrainingEventParticipant.status.in_([training_models.TrainingParticipantStatus.SCHEDULED, training_models.TrainingParticipantStatus.INVITED, training_models.TrainingParticipantStatus.CONFIRMED]),
        ).scalar() or 0)
        seats = max(0, int(capacity) - reserved)
        waiters = db.query(training_models.TrainingEventParticipant).filter(
            training_models.TrainingEventParticipant.amo_id == amo_id,
            training_models.TrainingEventParticipant.event_id == event.id,
            training_models.TrainingEventParticipant.status == training_models.TrainingParticipantStatus.WAITLISTED,
        ).order_by(training_models.TrainingEventParticipant.created_at.asc()).limit(seats).all()
        promoted: list[str] = []
        for row in waiters:
            row.status = training_models.TrainingParticipantStatus.INVITED
            promoted.append(str(row.user_id))
            _notify(router_module, db, amo_id=amo_id, user_id=str(row.user_id), title="Training seat available", body=f"A seat is now available for {event.title}. Accept the invitation to secure it.", link_path="/profile/training", dedupe_key=f"waitlist:{event.id}:{row.user_id}:promoted", actor_user_id=str(current_user.id))
        _audit(router_module, db, actor=current_user, action="WAITLIST_PROMOTE", entity_type="TrainingEvent", entity_id=str(event.id), details={"promoted_user_ids": promoted, "available_seats": seats})
        db.commit()
        return {"promoted": promoted, "remaining_capacity": max(0, seats - len(promoted))}

    # -------------------------------------------------------------------
    # Role-specific manager/coordinator workspaces
    # -------------------------------------------------------------------

    def workspace_payload(db: Session, current_user: account_models.User, *, coordinator: bool) -> dict[str, Any]:
        amo_id = str(current_user.amo_id)
        if coordinator:
            _training_editor(router_module, current_user)
            people = db.query(account_models.User).filter(account_models.User.amo_id == amo_id, account_models.User.is_active.is_(True), account_models.User.is_system_account.is_(False)).all()
        else:
            department_id = getattr(current_user, "department_id", None)
            people_query = db.query(account_models.User).filter(account_models.User.amo_id == amo_id, account_models.User.is_active.is_(True), account_models.User.is_system_account.is_(False))
            if department_id:
                people_query = people_query.filter(account_models.User.department_id == department_id)
            people = people_query.all()
        health = {"people": len(people), "current": 0, "due_soon": 0, "overdue": 0, "incomplete": 0}
        actions: list[dict[str, Any]] = []
        for person in people:
            evaluation = compliance.evaluate_user_training_policy(db, person, required_only=True, today=date.today())
            statuses = {item.status for item in evaluation.mandatory_items}
            if "OVERDUE" in statuses:
                health["overdue"] += 1
            elif "NOT_DONE" in statuses:
                health["incomplete"] += 1
            elif "DUE_SOON" in statuses:
                health["due_soon"] += 1
            else:
                health["current"] += 1
            for item in evaluation.mandatory_items:
                if item.status in {"OVERDUE", "DUE_SOON", "NOT_DONE"}:
                    actions.append({"priority": 1 if item.status == "OVERDUE" else 3, "type": "TRAINING", "user_id": str(person.id), "person": person.full_name, "course": item.course_name, "status": item.status, "due": _iso(item.extended_due_date or item.valid_until), "action_path": f"/maintenance/{{amo}}/training?course={item.course_id}"})
        deferral_query = db.query(training_models.TrainingDeferralRequest).filter(training_models.TrainingDeferralRequest.amo_id == amo_id, training_models.TrainingDeferralRequest.status.in_([training_models.DeferralStatus.PENDING, training_models.DeferralStatus.RETURNED_FOR_INFORMATION]))
        if not coordinator:
            deferral_query = deferral_query.filter(training_models.TrainingDeferralRequest.user_id.in_([str(person.id) for person in people] or [""]))
        for row in deferral_query.all():
            actions.append({"priority": 2, "type": "DEFERRAL", "user_id": str(row.user_id), "status": _enum(row.status), "due": _iso(row.requested_new_due_date), "action_path": "/training/deferrals"})
        evidence_query = db.query(training_models.TrainingFile).filter(training_models.TrainingFile.amo_id == amo_id, training_models.TrainingFile.review_status.in_([training_models.TrainingFileReviewStatus.PENDING, training_models.TrainingFileReviewStatus.RETURNED]))
        if not coordinator:
            evidence_query = evidence_query.filter(training_models.TrainingFile.owner_user_id.in_([str(person.id) for person in people] or [""]))
        for row in evidence_query.order_by(training_models.TrainingFile.uploaded_at.asc()).limit(100).all():
            actions.append({"priority": 2 if _enum(row.review_status) == "RETURNED" else 4, "type": "EVIDENCE", "user_id": str(row.owner_user_id), "status": _enum(row.review_status), "age_days": max(0, (_now() - (row.uploaded_at if row.uploaded_at.tzinfo else row.uploaded_at.replace(tzinfo=UTC))).days), "action_path": "/training"})
        assessment_query = db.query(operating_models.TrainingAssessmentInstance).filter(operating_models.TrainingAssessmentInstance.amo_id == amo_id, operating_models.TrainingAssessmentInstance.status.in_(["SUBMITTED", "REVIEW_REQUIRED", "FAILED"]))
        if not coordinator:
            assessment_query = assessment_query.filter(operating_models.TrainingAssessmentInstance.candidate_user_id.in_([str(person.id) for person in people] or [""]))
        for row in assessment_query.limit(100).all():
            actions.append({"priority": 3, "type": "ASSESSMENT", "user_id": str(row.candidate_user_id), "status": row.status, "outcome": row.outcome, "action_path": "/training"})
        actions.sort(key=lambda item: (item.get("priority", 9), str(item.get("due") or "9999"), str(item.get("person") or "")))
        return {"workspace": "COORDINATOR" if coordinator else "MANAGER", "generated_at": _now().isoformat(), "team_health": health, "action_queue": actions[:250]}

    @router.get("/workspace/manager")
    def manager_workspace(
        db: Session = Depends(get_read_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        return workspace_payload(db, current_user, coordinator=False)

    @router.get("/workspace/coordinator")
    def coordinator_workspace(
        db: Session = Depends(get_read_db),
        current_user: account_models.User = Depends(get_current_active_user),
    ):
        return workspace_payload(db, current_user, coordinator=True)


def run_workflow_escalations(db: Session, *, now: datetime | None = None) -> dict[str, int]:
    """Expire approved deferrals and escalate stale returned/pending evidence.

    Called by the production Training notification worker.  All notifications are
    deduplicated by stable entity/day keys, so repeated hourly runs are safe.
    """

    from . import router as router_module

    clock = now or _now()
    today = clock.date()
    summary = {"deferrals_expired": 0, "deferrals_escalated": 0, "evidence_escalated": 0}
    settings_rows = db.query(operating_models.TrainingOperatingSettings).all()
    for settings in settings_rows:
        amo_id = str(settings.amo_id)
        policy = settings.notification_policy if isinstance(settings.notification_policy, dict) else {}
        deferral_sla = int(policy.get("deferral_review_sla_days", 3) or 3)
        evidence_sla = int(policy.get("evidence_review_sla_days", 3) or 3)
        deferrals = db.query(training_models.TrainingDeferralRequest).filter(
            training_models.TrainingDeferralRequest.amo_id == amo_id,
            training_models.TrainingDeferralRequest.status.in_([
                training_models.DeferralStatus.PENDING,
                training_models.DeferralStatus.RETURNED_FOR_INFORMATION,
                training_models.DeferralStatus.APPROVED,
            ]),
        ).all()
        for row in deferrals:
            status_value = _enum(row.status)
            if status_value == "APPROVED" and row.requested_new_due_date < today:
                completed_after_original = db.query(training_models.TrainingRecord.id).filter(
                    training_models.TrainingRecord.amo_id == amo_id,
                    training_models.TrainingRecord.user_id == row.user_id,
                    training_models.TrainingRecord.course_id == row.course_id,
                    training_models.TrainingRecord.verification_status == training_models.TrainingRecordVerificationStatus.VERIFIED,
                    training_models.TrainingRecord.completion_date >= row.original_due_date,
                ).first()
                if completed_after_original is None:
                    row.status = training_models.DeferralStatus.EXPIRED
                    control = _deferral_control(db, row)
                    data = _workflow_data(control); data["expired_at"] = clock.isoformat(); control.status = "EXPIRED"; control.completed_at = clock; _save_workflow_data(control, data)
                    _notify(router_module, db, amo_id=amo_id, user_id=str(row.user_id), title="Training deferral expired", body="The approved deferral period ended without a verified completion. The underlying Training requirement is again controlling authorization/compliance readiness.", link_path="/profile/training#training-deferrals", dedupe_key=f"deferral:{row.id}:expired:{today.isoformat()}", warning=True)
                    summary["deferrals_expired"] += 1
            elif status_value in {"PENDING", "RETURNED_FOR_INFORMATION"}:
                requested_at = row.requested_at if row.requested_at.tzinfo else row.requested_at.replace(tzinfo=UTC)
                age = (clock - requested_at).days
                if age >= deferral_sla:
                    control = _deferral_control(db, row); data = _workflow_data(control); data["escalation_count"] = int(data.get("escalation_count") or 0) + 1; data["last_escalated_at"] = clock.isoformat(); _save_workflow_data(control, data)
                    for reviewer in _quality_users(db, amo_id):
                        _notify(router_module, db, amo_id=amo_id, user_id=str(reviewer.id), title="Training deferral SLA exceeded", body=f"A {status_value.lower().replace('_', ' ')} deferral has been unresolved for {age} day(s).", link_path="/training/deferrals", dedupe_key=f"deferral:{row.id}:sla:{age}:{reviewer.id}", warning=True)
                    summary["deferrals_escalated"] += 1
        files = db.query(training_models.TrainingFile).filter(
            training_models.TrainingFile.amo_id == amo_id,
            training_models.TrainingFile.review_status.in_([training_models.TrainingFileReviewStatus.PENDING, training_models.TrainingFileReviewStatus.RETURNED]),
        ).all()
        for file_row in files:
            uploaded = file_row.uploaded_at if file_row.uploaded_at.tzinfo else file_row.uploaded_at.replace(tzinfo=UTC)
            age = (clock - uploaded).days
            if age < evidence_sla:
                continue
            if _enum(file_row.review_status) == "RETURNED":
                _notify(router_module, db, amo_id=amo_id, user_id=str(file_row.owner_user_id), title="Returned Training evidence needs correction", body=file_row.review_comment or "Replace or add the requested evidence.", link_path="/profile/training#training-evidence", dedupe_key=f"evidence:{file_row.id}:returned-sla:{age}", warning=True)
            else:
                for reviewer in _quality_users(db, amo_id):
                    if str(reviewer.id) in {str(file_row.owner_user_id), str(file_row.uploaded_by_user_id or "")}:
                        continue
                    _notify(router_module, db, amo_id=amo_id, user_id=str(reviewer.id), title="Training evidence review SLA exceeded", body=f"Evidence '{file_row.original_filename}' has awaited independent review for {age} day(s).", link_path="/training", dedupe_key=f"evidence:{file_row.id}:pending-sla:{age}:{reviewer.id}", warning=True)
            summary["evidence_escalated"] += 1
    return summary


__all__ = ["install_training_workflow_completion", "run_workflow_escalations"]
