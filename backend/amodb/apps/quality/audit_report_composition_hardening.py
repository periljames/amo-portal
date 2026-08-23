from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy import and_
from sqlalchemy.orm import Session

from . import audit_report_composition as composition
from . import models
from .audit_checklist_execution_models import QualityAuditChecklistExecutionGovernance
from .audit_occurrence_completion_models import QualityAuditClosingNarrative, QualityAuditMeeting


_original_render_pdf = composition._render_pdf


def build_report_snapshot(db: Session, *, amo_id: str, audit_id) -> dict[str, Any]:
    """Build the report snapshot from execution rows plus their governed questions.

    Checklist execution governance deliberately stores mutable execution state,
    while the authoritative checklist item stores the question/reference/evidence
    context. Joining them in one bounded query avoids N+1 reads and prevents a
    report from containing responses that cannot be traced back to a question.
    """

    audit = composition._audit_or_404(db, amo_id=amo_id, audit_id=audit_id)

    checklist_pairs = db.query(
        QualityAuditChecklistExecutionGovernance,
        models.QualityAuditChecklistItem,
    ).join(
        models.QualityAuditChecklistItem,
        and_(
            models.QualityAuditChecklistItem.id == QualityAuditChecklistExecutionGovernance.checklist_item_id,
            models.QualityAuditChecklistItem.amo_id == QualityAuditChecklistExecutionGovernance.amo_id,
            models.QualityAuditChecklistItem.audit_id == QualityAuditChecklistExecutionGovernance.audit_id,
        ),
    ).filter(
        QualityAuditChecklistExecutionGovernance.amo_id == amo_id,
        QualityAuditChecklistExecutionGovernance.audit_id == audit_id,
        models.QualityAuditChecklistItem.amo_id == amo_id,
        models.QualityAuditChecklistItem.audit_id == audit_id,
    ).order_by(
        models.QualityAuditChecklistItem.sort_order.asc(),
        models.QualityAuditChecklistItem.created_at.asc(),
        models.QualityAuditChecklistItem.id.asc(),
    ).all()

    findings = db.query(models.QMSAuditFinding).filter(
        models.QMSAuditFinding.amo_id == amo_id,
        models.QMSAuditFinding.audit_id == audit_id,
    ).order_by(models.QMSAuditFinding.created_at.asc()).all()
    finding_ids = [row.id for row in findings]
    cars = db.query(models.CorrectiveActionRequest).filter(
        models.CorrectiveActionRequest.amo_id == amo_id,
        models.CorrectiveActionRequest.finding_id.in_(finding_ids),
    ).order_by(models.CorrectiveActionRequest.created_at.asc()).all() if finding_ids else []
    document_requests = db.query(models.QualityAuditDocumentRequest).filter(
        models.QualityAuditDocumentRequest.amo_id == amo_id,
        models.QualityAuditDocumentRequest.audit_id == audit_id,
    ).order_by(models.QualityAuditDocumentRequest.created_at.asc()).all()
    meetings = db.query(QualityAuditMeeting).filter(
        QualityAuditMeeting.amo_id == amo_id,
        QualityAuditMeeting.audit_id == audit_id,
        QualityAuditMeeting.status != "CANCELLED",
    ).order_by(QualityAuditMeeting.scheduled_start.asc()).all()
    narrative = db.query(QualityAuditClosingNarrative).filter(
        QualityAuditClosingNarrative.amo_id == amo_id,
        QualityAuditClosingNarrative.audit_id == audit_id,
    ).first()

    return composition._json_value({
        "schema": "QMS_AUDIT_REPORT_SNAPSHOT_V2",
        "audit": {
            "id": audit.id,
            "audit_ref": audit.audit_ref,
            "title": audit.title,
            "domain": audit.domain,
            "kind": audit.kind,
            "status": audit.status,
            "scope": audit.scope,
            "criteria": audit.criteria,
            "auditee": audit.auditee,
            "auditee_email": audit.auditee_email,
            "planned_start": audit.planned_start,
            "planned_end": audit.planned_end,
            "actual_start": audit.actual_start,
            "actual_end": audit.actual_end,
            "lead_auditor_user_id": audit.lead_auditor_user_id,
            "observer_auditor_user_id": audit.observer_auditor_user_id,
            "assistant_auditor_user_id": audit.assistant_auditor_user_id,
        },
        "closing_narrative": {
            "management_summary": narrative.management_summary if narrative else None,
            "conclusion": narrative.conclusion if narrative else None,
            "positive_practices": narrative.positive_practices if narrative else None,
            "updated_at": narrative.updated_at if narrative else None,
            "updated_by_user_id": narrative.updated_by_user_id if narrative else None,
        },
        "meetings": [
            {
                "id": row.id,
                "meeting_type": row.meeting_type,
                "scheduled_start": row.scheduled_start,
                "scheduled_end": row.scheduled_end,
                "location": row.location,
                "conference_url": row.conference_url,
                "agenda": row.agenda,
                "status": row.status,
            }
            for row in meetings
        ],
        "checklist": [
            {
                "checklist_item_id": execution.checklist_item_id,
                "section": item.section,
                "checklist_ref": item.checklist_ref,
                "requirement_ref": item.requirement_ref,
                "prompt": item.prompt,
                "sort_order": item.sort_order,
                "finding_id": item.finding_id,
                "canonical_response_status": execution.canonical_response_status,
                "auditor_notes": execution.auditor_notes,
                "objective_evidence": item.objective_evidence,
                "evidence_references": execution.evidence_references or [],
                "entity_version": execution.entity_version,
            }
            for execution, item in checklist_pairs
        ],
        "findings": [
            {
                "id": row.id,
                "finding_ref": row.finding_ref,
                "finding_type": row.finding_type,
                "severity": row.severity,
                "level": row.level,
                "requirement_ref": row.requirement_ref,
                "description": row.description,
                "objective_evidence": row.objective_evidence,
                "acknowledged_at": row.acknowledged_at,
                "closed_at": row.closed_at,
                "verified_at": row.verified_at,
            }
            for row in findings
        ],
        "cars": [
            {
                "id": row.id,
                "car_number": row.car_number,
                "finding_id": row.finding_id,
                "title": row.title,
                "status": row.status,
                "due_date": row.due_date,
                "target_closure_date": row.target_closure_date,
            }
            for row in cars
        ],
        "preparation_documents": [
            {
                "id": row.id,
                "title": row.title,
                "status": row.status,
                "due_date": row.due_date,
                "uploaded_at": row.uploaded_at,
                "reviewed_at": row.reviewed_at,
            }
            for row in document_requests
        ],
    })


def render_pdf(snapshot: dict[str, Any], destination) -> None:
    """Render traceable checklist context without changing the base PDF lifecycle.

    The existing renderer owns page layout. Feed it a render-only snapshot whose
    checklist evidence cell contains the frozen reference, requirement, question,
    and the actual evidence/note. The governed source snapshot remains structured
    with those fields separately and is what is hashed for integrity.
    """

    rendered = deepcopy(snapshot)
    for row in rendered.get("checklist", []):
        references = [
            str(row.get("checklist_ref") or "").strip(),
            str(row.get("requirement_ref") or "").strip(),
        ]
        reference_line = " · ".join(value for value in references if value) or "No checklist/requirement reference"
        prompt = str(row.get("prompt") or "Question text unavailable").strip()
        evidence = str(row.get("objective_evidence") or row.get("auditor_notes") or "—").strip()
        row["objective_evidence"] = f"{reference_line}\nQuestion: {prompt}\nEvidence / auditor note: {evidence}"
        row["auditor_notes"] = None
    _original_render_pdf(rendered, destination)


# Patch before audit_report_composition_router imports these symbols. The base
# generation/adoption lifecycle remains unchanged and resolves these module
# globals at call time.
composition.build_report_snapshot = build_report_snapshot
composition._render_pdf = render_pdf
