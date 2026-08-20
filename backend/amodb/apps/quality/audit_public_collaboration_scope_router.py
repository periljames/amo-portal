from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from amodb.database import get_db

from . import models
from .audit_external_access_router import _GUEST_COOKIE, _active_grant, _latest_release_events
from .audit_occurrence_completion_models import QualityAuditClosingNarrative, QualityAuditMeeting
from .audit_occurrence_completion_router import _enum_value, _meeting_dict, _narrative_dict


router = APIRouter(prefix="/quality/audit-access", tags=["Quality / Audit Occurrence Collaboration"])
_SUMMARY_SCOPES = {"audit:read_summary", "audit:read_assigned"}
_CAR_SCOPES = {"car:respond", "audit:read_released_findings"}


@router.get("/collaboration")
def get_public_occurrence_collaboration_scoped(
    db: Session = Depends(get_db),
    amo_qms_audit_guest: str | None = Cookie(default=None, alias=_GUEST_COOKIE),
) -> dict[str, Any]:
    """Return only collaboration projections explicitly permitted by the grant.

    Meetings and closing narrative are summary/assignment data. CAR data is
    auditee-only and remains bounded to CAR-response or released-finding scopes.
    A mutation-only/document-only grant therefore receives no summary data.
    """

    if not amo_qms_audit_guest:
        raise HTTPException(status_code=401, detail="Audit access session is required.")

    grant = _active_grant(db, amo_qms_audit_guest)
    participant = grant.participant
    scope = set(grant.scope_json or [])

    meetings: list[QualityAuditMeeting] = []
    narrative: QualityAuditClosingNarrative | None = None
    if scope & _SUMMARY_SCOPES:
        meetings = db.query(QualityAuditMeeting).filter(
            QualityAuditMeeting.amo_id == grant.amo_id,
            QualityAuditMeeting.audit_id == grant.audit_id,
            QualityAuditMeeting.status != "CANCELLED",
        ).order_by(QualityAuditMeeting.scheduled_start.asc()).all()
        narrative = db.query(QualityAuditClosingNarrative).filter(
            QualityAuditClosingNarrative.amo_id == grant.amo_id,
            QualityAuditClosingNarrative.audit_id == grant.audit_id,
        ).first()

    cars: list[dict[str, Any]] = []
    if (
        participant
        and participant.participant_type == "AUDITEE_GUEST"
        and bool(scope & _CAR_SCOPES)
    ):
        latest_releases = _latest_release_events(db, amo_id=grant.amo_id, audit_id=grant.audit_id)
        released_finding_ids = [
            finding_id
            for finding_id, event in latest_releases.items()
            if event.action == "RELEASED"
        ]
        if released_finding_ids:
            rows = db.query(models.CorrectiveActionRequest, models.QMSAuditFinding).join(
                models.QMSAuditFinding,
                models.QMSAuditFinding.id == models.CorrectiveActionRequest.finding_id,
            ).filter(
                models.CorrectiveActionRequest.amo_id == grant.amo_id,
                models.QMSAuditFinding.audit_id == grant.audit_id,
                models.QMSAuditFinding.id.in_(released_finding_ids),
            ).order_by(models.CorrectiveActionRequest.created_at.asc()).all()
            for car, finding in rows:
                cars.append({
                    "id": str(car.id),
                    "car_number": car.car_number,
                    "title": car.title,
                    "summary": car.summary,
                    "priority": _enum_value(car.priority),
                    "status": _enum_value(car.status),
                    "due_date": car.due_date.isoformat() if car.due_date else None,
                    "target_closure_date": car.target_closure_date.isoformat() if car.target_closure_date else None,
                    "closed_at": car.closed_at.isoformat() if car.closed_at else None,
                    "finding_id": str(finding.id),
                    "finding_ref": finding.finding_ref,
                })

    return {
        "meetings": [_meeting_dict(row, public=True) for row in meetings],
        "cars": cars,
        "closing_narrative": _narrative_dict(narrative) if scope & _SUMMARY_SCOPES else {},
    }
