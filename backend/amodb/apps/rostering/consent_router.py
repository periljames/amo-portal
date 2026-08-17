from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ...database import get_db
from ...security import get_current_active_user
from ..accounts import models as account_models
from . import common, consent_service, governance, services
from .consent_models import (
    RosterAssignmentConsent,
    RosterConsentStatus,
    RosterSupervisorDecision,
)

router = APIRouter(prefix="/rostering/consents", tags=["rostering-consent"])


class ConsentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version_id: str
    assignment_id: str
    assignment_revision: int
    assignment_fingerprint: str
    personnel_id: str
    proposed_by_user_id: str | None = None
    reason: str
    duty_type: str
    planned_start: datetime
    planned_end: datetime
    personnel_response: RosterConsentStatus
    personnel_response_at: datetime | None = None
    personnel_comment: str | None = None
    supervisor_required: bool
    supervisor_user_id: str | None = None
    supervisor_decision: RosterSupervisorDecision
    supervisor_decision_at: datetime | None = None
    supervisor_comment: str | None = None
    overtime_rest_day_classification: str | None = None
    replacement_rest_json: dict | None = None
    statutory_compliance_json: dict | None = None
    fatigue_risk_json: dict | None = None
    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class PersonnelDecision(BaseModel):
    decision: Literal["ACCEPT", "DECLINE"]
    assignment_fingerprint: str = Field(min_length=64, max_length=64)
    comment: str | None = Field(default=None, max_length=2000)


class SupervisorDecision(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    assignment_fingerprint: str = Field(min_length=64, max_length=64)
    comment: str | None = Field(default=None, max_length=2000)


def _amo(user: account_models.User) -> str:
    return common.effective_amo_id(user)


def _error(exc: consent_service.RosterWorkflowError) -> HTTPException:
    status_code = 403 if exc.code.endswith("FORBIDDEN") else 409
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.message, "details": exc.details},
    )


def _request_or_404(
    db: Session,
    *,
    amo_id: str,
    consent_id: str,
    lock: bool = False,
) -> RosterAssignmentConsent:
    row = consent_service.current_request(
        db,
        amo_id=amo_id,
        consent_id=consent_id,
        lock=lock,
    )
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "ROSTER_CONSENT_NOT_FOUND"})
    return row


@router.get("/me", response_model=list[ConsentRead])
def my_consent_requests(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    return consent_service.list_for_personnel(
        db,
        amo_id=_amo(current_user),
        personnel_id=current_user.id,
    )


@router.get("/supervisor/pending", response_model=list[ConsentRead])
def pending_supervisor_requests(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _amo(current_user)
    rows = db.query(RosterAssignmentConsent).filter(
        RosterAssignmentConsent.amo_id == amo_id,
        RosterAssignmentConsent.personnel_response == RosterConsentStatus.ACCEPTED,
        RosterAssignmentConsent.supervisor_required.is_(True),
        RosterAssignmentConsent.supervisor_decision == RosterSupervisorDecision.PENDING,
    ).order_by(RosterAssignmentConsent.created_at.asc()).all()
    permitted: list[RosterAssignmentConsent] = []
    for row in rows:
        assignment = common.get_assignment(db, amo_id=amo_id, assignment_id=row.assignment_id)
        if assignment and governance.can_approve_scope(
            db,
            user=current_user,
            department_id=assignment.department_id,
            base_station_id=assignment.base_station_id,
        ):
            permitted.append(row)
    return permitted


@router.get("/versions/{version_id}", response_model=list[ConsentRead])
def version_consent_requests(
    version_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    if not services.can_view_roster(db, user=current_user):
        raise HTTPException(status_code=403, detail="Roster access denied")
    amo_id = _amo(current_user)
    version = common.get_version(db, amo_id=amo_id, version_id=version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Roster version not found")
    return db.query(RosterAssignmentConsent).filter(
        RosterAssignmentConsent.amo_id == amo_id,
        RosterAssignmentConsent.version_id == version_id,
    ).order_by(RosterAssignmentConsent.created_at.asc()).all()


@router.get("/{consent_id}", response_model=ConsentRead)
def get_consent_request(
    consent_id: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _amo(current_user)
    row = _request_or_404(db, amo_id=amo_id, consent_id=consent_id)
    assignment = common.get_assignment(db, amo_id=amo_id, assignment_id=row.assignment_id)
    permitted = row.personnel_id == current_user.id
    if assignment and not permitted:
        permitted = governance.can_approve_scope(
            db,
            user=current_user,
            department_id=assignment.department_id,
            base_station_id=assignment.base_station_id,
        )
    if not permitted:
        raise HTTPException(status_code=403, detail={"code": "ROSTER_CONSENT_FORBIDDEN"})
    common.audit(
        db,
        amo_id=amo_id,
        actor_user_id=current_user.id,
        entity_type="RosterAssignmentConsent",
        entity_id=row.id,
        action="roster_consent_viewed",
        metadata={"assignment_id": row.assignment_id},
    )
    db.commit()
    return row


@router.post("/{consent_id}/respond", response_model=ConsentRead)
def respond_to_consent(
    consent_id: str,
    payload: PersonnelDecision,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _amo(current_user)
    try:
        row = _request_or_404(db, amo_id=amo_id, consent_id=consent_id, lock=True)
        if payload.assignment_fingerprint != row.assignment_fingerprint:
            raise consent_service.RosterWorkflowError(
                "ROSTER_CONSENT_STALE",
                "The assignment shown to the employee no longer matches this request.",
                {"consent_id": consent_id},
            )
        row = consent_service.respond(
            db,
            request=row,
            actor=current_user,
            accept=payload.decision == "ACCEPT",
            comment=payload.comment,
        )
        db.commit()
        db.refresh(row)
        return row
    except consent_service.RosterWorkflowError as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/{consent_id}/supervisor-decision", response_model=ConsentRead)
def decide_consent_as_supervisor(
    consent_id: str,
    payload: SupervisorDecision,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    amo_id = _amo(current_user)
    try:
        row = _request_or_404(db, amo_id=amo_id, consent_id=consent_id, lock=True)
        if payload.assignment_fingerprint != row.assignment_fingerprint:
            raise consent_service.RosterWorkflowError(
                "ROSTER_SUPERVISOR_DECISION_STALE",
                "The assignment changed before the supervisor decision was recorded.",
                {"consent_id": consent_id},
            )
        row = consent_service.supervisor_decide(
            db,
            request=row,
            actor=current_user,
            approve=payload.decision == "APPROVE",
            comment=payload.comment,
        )
        db.commit()
        db.refresh(row)
        return row
    except consent_service.RosterWorkflowError as exc:
        db.rollback()
        raise _error(exc) from exc
