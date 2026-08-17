from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from amodb.database import get_read_db

from . import models
from .audit_closure_models import QualityAuditClosureState
from .audit_preparation_models import QualityAuditPreparationRevision
from .audit_workflow_contract import build_authoritative_audit_workflow
from .tenant_security import TenantContext, require_quality_permission, set_postgres_tenant_context


router = APIRouter(tags=["Quality live audit session"])

SESSION_STAGE_ORDER = ("setup", "prepare", "live", "closing", "follow-up", "archive")
SESSION_STAGE_LABELS = {
    "setup": "Setup",
    "prepare": "Prepare",
    "live": "Live",
    "closing": "Closing",
    "follow-up": "Follow-up",
    "archive": "Archive",
}
SESSION_STAGE_TABS = {
    "setup": "war-room",
    "prepare": "checklist",
    "live": "checklist",
    "closing": "report",
    "follow-up": "cars",
    "archive": "evidence",
}


def _workflow_stage(workflow: Any, stage_id: str) -> Any | None:
    return next((stage for stage in workflow.stages if stage.id == stage_id), None)


def _audit_payload(audit: models.QMSAudit) -> dict[str, Any]:
    return {
        "id": str(audit.id),
        "domain": getattr(getattr(audit, "domain", None), "value", audit.domain),
        "kind": getattr(getattr(audit, "kind", None), "value", audit.kind),
        "audit_scope_id": str(audit.audit_scope_id) if getattr(audit, "audit_scope_id", None) else None,
        "audit_scope_code": getattr(audit, "audit_scope_code", None),
        "status": getattr(getattr(audit, "status", None), "value", audit.status),
        "audit_ref": audit.audit_ref,
        "title": audit.title,
        "scope": audit.scope,
        "criteria": audit.criteria,
        "auditee": audit.auditee,
        "auditee_email": audit.auditee_email,
        "auditee_user_id": audit.auditee_user_id,
        "lead_auditor_user_id": audit.lead_auditor_user_id,
        "observer_auditor_user_id": audit.observer_auditor_user_id,
        "assistant_auditor_user_id": audit.assistant_auditor_user_id,
        "external_auditees": audit.external_auditees,
        "notify_auditors": audit.notify_auditors,
        "notify_auditees": audit.notify_auditees,
        "reminder_interval_days": audit.reminder_interval_days,
        "planned_start": audit.planned_start.isoformat() if audit.planned_start else None,
        "planned_end": audit.planned_end.isoformat() if audit.planned_end else None,
        "actual_start": audit.actual_start.isoformat() if audit.actual_start else None,
        "actual_end": audit.actual_end.isoformat() if audit.actual_end else None,
        "report_file_ref": audit.report_file_ref,
        "checklist_file_ref": audit.checklist_file_ref,
        "retention_until": audit.retention_until.isoformat() if audit.retention_until else None,
        "upcoming_notice_sent_at": audit.upcoming_notice_sent_at.isoformat() if audit.upcoming_notice_sent_at else None,
        "day_of_notice_sent_at": audit.day_of_notice_sent_at.isoformat() if audit.day_of_notice_sent_at else None,
        "created_at": audit.created_at.isoformat() if audit.created_at else None,
        "deleted_at": audit.deleted_at.isoformat() if audit.deleted_at else None,
        "deleted_by_user_id": audit.deleted_by_user_id,
        "delete_reason": audit.delete_reason,
    }


def _resolve_audit(db: Session, *, amo_id: str, audit_key: str) -> models.QMSAudit:
    key = audit_key.strip()
    if not key:
        raise HTTPException(status_code=404, detail="Audit occurrence not found.")
    id_value: uuid.UUID | None = None
    try:
        id_value = uuid.UUID(key)
    except (TypeError, ValueError):
        pass
    identity_filters = [models.QMSAudit.audit_ref == key]
    if id_value is not None:
        identity_filters.append(models.QMSAudit.id == id_value)
    audit = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == amo_id,
        models.QMSAudit.deleted_at.is_(None),
        or_(*identity_filters),
    ).first()
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit occurrence not found.")
    return audit


@router.get("/audits/resolve/{audit_key}")
def resolve_audit_occurrence(
    audit_key: str,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    """Resolve exactly one tenant audit by immutable ID or human audit reference."""
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    return _audit_payload(_resolve_audit(db, amo_id=ctx.amo_id, audit_key=audit_key))


def project_audit_session(
    workflow: Any,
    *,
    preparation_issued: bool,
    execution_status: str,
    follow_up_status: str,
    archive_count: int,
) -> dict[str, Any]:
    war_room = _workflow_stage(workflow, "war-room")
    checklist = _workflow_stage(workflow, "checklist")
    findings = _workflow_stage(workflow, "findings")
    report = _workflow_stage(workflow, "report")

    complete_by_stage = {
        "setup": bool(war_room and war_room.complete),
        "prepare": bool(preparation_issued and checklist and checklist.complete),
        "live": bool(findings and findings.complete),
        "closing": execution_status.upper() == "CLOSED",
        "follow-up": follow_up_status.upper() == "COMPLETE",
        "archive": archive_count > 0,
    }
    helper_by_stage = {
        "setup": getattr(war_room, "helper", "Schedule, scope, audit team and auditee must be ready."),
        "prepare": "An issued preparation snapshot and governed checklist must exist before fieldwork.",
        "live": getattr(findings, "helper", "Complete fieldwork and finalize released findings."),
        "closing": getattr(report, "helper", "Issue the governed report and record audit execution closure."),
        "follow-up": "Findings, CAR/CAPA and effectiveness obligations must be resolved before assurance follow-up completes.",
        "archive": "Create the controlled audit work package after assurance follow-up is complete.",
    }

    current_stage = next((stage for stage in SESSION_STAGE_ORDER if not complete_by_stage[stage]), "archive")
    completed = sum(1 for stage in SESSION_STAGE_ORDER if complete_by_stage[stage])
    stages = [{
        "id": stage,
        "label": SESSION_STAGE_LABELS[stage],
        "complete": complete_by_stage[stage],
        "active": stage == current_stage,
        "legacy_tab": SESSION_STAGE_TABS[stage],
        "helper": helper_by_stage[stage],
    } for stage in SESSION_STAGE_ORDER]
    return {
        "audit_id": str(workflow.audit_id),
        "current_stage_id": current_stage,
        "current_stage_label": SESSION_STAGE_LABELS[current_stage],
        "percent_complete": int(round((completed / len(SESSION_STAGE_ORDER)) * 100)),
        "stages": stages,
        "source_workflow_stage_id": workflow.current_stage_id,
        "source_workflow_percent_complete": workflow.percent_complete,
        "preparation_issued": preparation_issued,
        "execution_status": execution_status,
        "follow_up_status": follow_up_status,
        "archive_count": archive_count,
    }


@router.get("/audits/{audit_id}/session")
def get_audit_session(
    audit_id: uuid.UUID,
    ctx: TenantContext = Depends(require_quality_permission("qms.audit.view")),
    db: Session = Depends(get_read_db),
) -> dict[str, Any]:
    set_postgres_tenant_context(db, amo_id=ctx.amo_id, user_id=ctx.user_id)
    audit = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == ctx.amo_id,
        models.QMSAudit.id == audit_id,
        models.QMSAudit.deleted_at.is_(None),
    ).first()
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found.")

    workflow = build_authoritative_audit_workflow(db, audit)
    preparation_issued = db.query(QualityAuditPreparationRevision.id).filter(
        QualityAuditPreparationRevision.amo_id == ctx.amo_id,
        QualityAuditPreparationRevision.audit_id == audit.id,
        QualityAuditPreparationRevision.status == "ISSUED",
    ).first() is not None
    closure = db.query(QualityAuditClosureState).filter(
        QualityAuditClosureState.amo_id == ctx.amo_id,
        QualityAuditClosureState.audit_id == audit.id,
    ).first()
    archive_count = db.query(models.QualityArchivePackage).filter(
        models.QualityArchivePackage.amo_id == ctx.amo_id,
        models.QualityArchivePackage.audit_id == audit.id,
    ).count()

    return project_audit_session(
        workflow,
        preparation_issued=preparation_issued,
        execution_status=closure.execution_status if closure else "OPEN",
        follow_up_status=closure.follow_up_status if closure else "OPEN",
        archive_count=archive_count,
    )
