"""Explicit, retryable email handoff for an already released finding's CAR."""
from __future__ import annotations

from fastapi import HTTPException

from amodb.apps.accounts import models as accounts
from amodb.apps.notifications import service as notifications

from . import models
from .audit_external_access_models import QualityAuditFindingReleaseEvent
from .service import build_car_invite_link


def deliver_released_car_invite(db, *, ctx, audit_id, finding_id):
    audit = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == ctx.amo_id, models.QMSAudit.id == audit_id,
        models.QMSAudit.deleted_at.is_(None),
    ).first()
    finding = db.query(models.QMSAuditFinding).filter(
        models.QMSAuditFinding.amo_id == ctx.amo_id,
        models.QMSAuditFinding.audit_id == audit_id, models.QMSAuditFinding.id == finding_id,
    ).first()
    if audit is None or finding is None:
        raise HTTPException(status_code=404, detail="Audit finding not found.")
    release = db.query(QualityAuditFindingReleaseEvent).filter(
        QualityAuditFindingReleaseEvent.amo_id == ctx.amo_id,
        QualityAuditFindingReleaseEvent.audit_id == audit_id,
        QualityAuditFindingReleaseEvent.finding_id == finding_id,
    ).order_by(QualityAuditFindingReleaseEvent.created_at.desc(), QualityAuditFindingReleaseEvent.id.desc()).first()
    if release is None or release.action != "RELEASED":
        raise HTTPException(status_code=409, detail="Release this finding before emailing its CAR.")
    car = db.query(models.CorrectiveActionRequest).filter(
        models.CorrectiveActionRequest.amo_id == ctx.amo_id,
        models.CorrectiveActionRequest.finding_id == finding_id,
    ).first()
    if car is None:
        raise HTTPException(status_code=409, detail="This finding has no linked CAR to email.")
    assignee = db.query(accounts.User).filter(
        accounts.User.amo_id == ctx.amo_id, accounts.User.id == car.assigned_to_user_id,
        accounts.User.is_active.is_(True),
    ).first() if car.assigned_to_user_id else None
    recipient = str(getattr(assignee, "email", None) or audit.auditee_email or "").strip()
    if not recipient:
        raise HTTPException(status_code=409, detail="Assign an active auditee with an email address before sending the CAR.")
    summary = finding.description
    if finding.requirement_ref:
        summary += f"\nRequirement/reference: {finding.requirement_ref}"
    if release.include_objective_evidence and finding.objective_evidence:
        summary += f"\nObjective evidence: {finding.objective_evidence}"
    log = notifications.send_email(
        template_key="qms_car_auditee_invite", recipient=recipient,
        subject=f"CAR/CAPA response required · {car.car_number}",
        context={"car_number": car.car_number, "title": car.title, "summary": summary,
            "priority": getattr(car.priority, "value", car.priority),
            "due_date": car.due_date.isoformat() if car.due_date else None,
            "audit_ref": audit.audit_ref, "audit_title": audit.title,
            "auditee": getattr(assignee, "full_name", None) or audit.auditee,
            "invite_url": build_car_invite_link(car)},
        correlation_id=f"car-release:{car.id}:{release.id}",
        email_class="CRITICAL", amo_id=ctx.amo_id, db=db,
    )
    db.commit()
    status = getattr(log.status, "value", log.status)
    return {"car_number": car.car_number, "recipient": recipient, "status": status,
        "sent": status == "SENT", "message_id": log.provider_message_id,
        "message": "CAR email accepted by the configured provider." if status == "SENT"
            else "CAR remains released. Email was not accepted; retry delivery after checking email configuration."}
