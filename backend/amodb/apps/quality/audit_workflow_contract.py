"""Authoritative seven-stage Quality audit workflow contract.

The compatibility router historically inferred stage completion from weak proxies
and returned a stage order that differed from the audit workspace.  This module
replaces only the two workflow-read operations while preserving all mutation
handlers in ``router.py``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.entitlements import require_module
from amodb.security import get_current_active_user

from . import models
from .router import (
    _current_amo_id,
    _get_audit_for_amo,
    _serialize_audit,
    router,
)
from .schemas import (
    QMSAuditWorkflowStageOut,
    QMSAuditWorkflowSummaryOut,
    QMSAuditWorkspaceOut,
)


STAGE_ORDER = (
    "war-room",
    "checklist",
    "findings",
    "report",
    "cars",
    "evidence",
    "closeout",
)


@dataclass(frozen=True)
class WorkflowFacts:
    war_room_ready: bool
    checklist_source_present: bool
    checklist_total: int
    checklist_completed: int
    fieldwork_closed: bool
    findings_total: int
    findings_open: int
    nc_findings_total: int
    nc_findings_without_car: int
    report_complete: bool
    report_metric: str
    cars_total: int
    cars_open: int
    evidence_total: int
    required_car_evidence_missing: int
    required_car_evidence_unverified: int
    archive_count: int
    audit_closed: bool


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _audit_setup_ready(audit: models.QMSAudit) -> bool:
    """Return whether the manual-defined audit basis and accountable parties exist."""
    return bool(
        audit.planned_start
        and audit.planned_end
        and (audit.scope or "").strip()
        and (audit.criteria or "").strip()
        and audit.lead_auditor_user_id
        and (audit.auditee or audit.auditee_email or audit.auditee_user_id)
    )


def _stage_definitions(facts: WorkflowFacts, *, audit_ref: str, audit_status: str) -> list[dict[str, Any]]:
    checklist_ready = facts.checklist_source_present or facts.checklist_total > 0
    findings_complete = facts.fieldwork_closed or facts.report_complete
    cars_complete = (
        facts.report_complete
        and facts.nc_findings_without_car == 0
        and facts.cars_open == 0
    )
    baseline_evidence_complete = checklist_ready and facts.report_complete
    evidence_complete = (
        baseline_evidence_complete
        and facts.required_car_evidence_missing == 0
        and facts.required_car_evidence_unverified == 0
    )

    stages = [
        {
            "id": "war-room",
            "label": "War room",
            "complete": facts.war_room_ready,
            "helper": "Schedule, scope, criteria, lead auditor and auditee are assigned.",
            "metric": f"{audit_ref} · {audit_status}",
        },
        {
            "id": "checklist",
            "label": "Checklist",
            "complete": checklist_ready,
            "helper": "A controlled checklist source or structured portal checklist is available.",
            "metric": (
                "Controlled source uploaded"
                if facts.checklist_source_present
                else f"{facts.checklist_total} portal item(s)"
            ),
        },
        {
            "id": "findings",
            "label": "Findings",
            "complete": findings_complete,
            "helper": "Fieldwork is formally completed before the issued report locks findings.",
            "metric": (
                f"{facts.findings_total} finding(s); "
                f"{facts.checklist_completed}/{facts.checklist_total} checklist complete"
            ),
        },
        {
            "id": "report",
            "label": "Report",
            "complete": facts.report_complete,
            "helper": "The issued audit report is uploaded and tracked.",
            "metric": facts.report_metric,
        },
        {
            "id": "cars",
            "label": "CARs",
            "complete": cars_complete,
            "helper": "Every non-conformity has a valid CAR and no CAR remains open.",
            "metric": (
                f"{facts.cars_open} open; {facts.nc_findings_without_car} NC without CAR"
                if facts.nc_findings_total
                else "No CAR required"
            ),
        },
        {
            "id": "evidence",
            "label": "Evidence",
            "complete": evidence_complete,
            "helper": "Checklist and report are present; required CAR evidence is attached and verified.",
            "metric": (
                f"{facts.evidence_total} file(s); "
                f"{facts.required_car_evidence_missing} missing; "
                f"{facts.required_car_evidence_unverified} unverified"
            ),
        },
        {
            "id": "closeout",
            "label": "Closeout",
            "complete": facts.audit_closed,
            "helper": "All backend closure gates passed and the audit was formally closed.",
            "metric": f"{facts.archive_count} archive package(s)" if facts.archive_count else audit_status,
        },
    ]

    if facts.audit_closed:
        for stage in stages:
            stage["complete"] = True
    return stages


def _workflow_facts(db: Session, audit: models.QMSAudit) -> tuple[WorkflowFacts, list[models.QMSAuditFinding]]:
    findings = (
        db.query(models.QMSAuditFinding)
        .filter(
            models.QMSAuditFinding.audit_id == audit.id,
            models.QMSAuditFinding.amo_id == audit.amo_id,
        )
        .all()
    )
    finding_ids = [finding.id for finding in findings]
    cars = (
        db.query(models.CorrectiveActionRequest)
        .filter(
            models.CorrectiveActionRequest.amo_id == audit.amo_id,
            models.CorrectiveActionRequest.finding_id.in_(finding_ids),
        )
        .all()
        if finding_ids
        else []
    )

    checklist_query = db.query(models.QualityAuditChecklistItem).filter(
        models.QualityAuditChecklistItem.audit_id == audit.id,
        models.QualityAuditChecklistItem.amo_id == audit.amo_id,
    )
    checklist_total = checklist_query.count()
    checklist_completed = checklist_query.filter(
        models.QualityAuditChecklistItem.response_status != "PENDING"
    ).count()

    report_tracker = (
        db.query(models.QualityAuditReportTracker)
        .filter(
            models.QualityAuditReportTracker.audit_id == audit.id,
            models.QualityAuditReportTracker.amo_id == audit.amo_id,
        )
        .first()
    )
    report_uploaded = bool(audit.report_file_ref)
    report_tracker_status = _enum_value(getattr(report_tracker, "status", None)).upper()
    report_complete = report_uploaded or report_tracker_status in {"SUBMITTED", "ACCEPTED"}
    report_metric = "Uploaded" if report_uploaded else (report_tracker_status.title() if report_tracker_status else "Pending")

    nc_findings = [
        finding
        for finding in findings
        if _enum_value(getattr(finding, "finding_type", None)).upper() == "NON_CONFORMITY"
        or _enum_value(getattr(finding, "level", None)).upper() in {"LEVEL_1", "LEVEL_2", "LEVEL_3"}
    ]
    valid_car_finding_ids = {
        car.finding_id
        for car in cars
        if _enum_value(car.status).upper() != "CANCELLED"
    }
    nc_findings_without_car = sum(1 for finding in nc_findings if finding.id not in valid_car_finding_ids)

    closed_car_statuses = {"CLOSED", "CANCELLED"}
    cars_open = sum(1 for car in cars if _enum_value(car.status).upper() not in closed_car_statuses)

    car_ids = [car.id for car in cars]
    car_attachments = (
        db.query(models.CARAttachment)
        .filter(models.CARAttachment.car_id.in_(car_ids))
        .all()
        if car_ids
        else []
    )
    car_ids_with_attachments = {attachment.car_id for attachment in car_attachments}
    finding_attachment_total = (
        db.query(models.QMSFindingAttachment)
        .filter(models.QMSFindingAttachment.finding_id.in_(finding_ids))
        .count()
        if finding_ids
        else 0
    )

    required_cars = [car for car in cars if bool(getattr(car, "evidence_required", True)) and _enum_value(car.status).upper() != "CANCELLED"]
    required_car_evidence_missing = sum(
        1
        for car in required_cars
        if not (
            (getattr(car, "evidence_ref", None) or "").strip()
            or getattr(car, "evidence_received_at", None)
            or car.id in car_ids_with_attachments
        )
    )
    required_car_evidence_unverified = sum(
        1 for car in required_cars if getattr(car, "evidence_verified_at", None) is None
    )

    archive_count = (
        db.query(models.QualityArchivePackage)
        .filter(
            models.QualityArchivePackage.audit_id == audit.id,
            models.QualityArchivePackage.amo_id == audit.amo_id,
        )
        .count()
    )
    checklist_source_present = bool(audit.checklist_file_ref)
    evidence_total = (
        int(checklist_source_present)
        + int(report_uploaded)
        + finding_attachment_total
        + len(car_attachments)
    )

    status_value = _enum_value(audit.status).upper()
    facts = WorkflowFacts(
        war_room_ready=_audit_setup_ready(audit),
        checklist_source_present=checklist_source_present,
        checklist_total=checklist_total,
        checklist_completed=checklist_completed,
        fieldwork_closed=bool(audit.actual_end),
        findings_total=len(findings),
        findings_open=sum(1 for finding in findings if not finding.closed_at),
        nc_findings_total=len(nc_findings),
        nc_findings_without_car=nc_findings_without_car,
        report_complete=report_complete,
        report_metric=report_metric,
        cars_total=len(cars),
        cars_open=cars_open,
        evidence_total=evidence_total,
        required_car_evidence_missing=required_car_evidence_missing,
        required_car_evidence_unverified=required_car_evidence_unverified,
        archive_count=archive_count,
        audit_closed=status_value == "CLOSED",
    )
    return facts, findings


def build_authoritative_audit_workflow(db: Session, audit: models.QMSAudit) -> QMSAuditWorkflowSummaryOut:
    facts, findings = _workflow_facts(db, audit)
    audit_status = _enum_value(audit.status)
    definitions = _stage_definitions(facts, audit_ref=audit.audit_ref, audit_status=audit_status)

    if facts.audit_closed:
        current_stage_id = "closeout"
    else:
        current_stage_id = next((stage["id"] for stage in definitions if not stage["complete"]), "closeout")

    stages = [
        QMSAuditWorkflowStageOut(
            id=stage["id"],
            label=stage["label"],
            complete=bool(stage["complete"]),
            active=stage["id"] == current_stage_id,
            helper=stage["helper"],
            metric=stage["metric"],
        )
        for stage in definitions
    ]
    latest_ack = next(
        (
            finding
            for finding in sorted(findings, key=lambda row: row.created_at, reverse=True)
            if finding.acknowledged_by_name or finding.acknowledged_by_email
        ),
        None,
    )
    percent_complete = int(round((sum(1 for stage in stages if stage.complete) / len(STAGE_ORDER)) * 100))

    return QMSAuditWorkflowSummaryOut(
        audit_id=audit.id,
        current_stage_id=current_stage_id,
        current_stage_label=next(stage.label for stage in stages if stage.id == current_stage_id),
        percent_complete=percent_complete,
        findings_total=facts.findings_total,
        findings_open=facts.findings_open,
        cars_total=facts.cars_total,
        cars_open=facts.cars_open,
        checklist_uploaded=facts.checklist_source_present,
        report_uploaded=bool(audit.report_file_ref),
        acknowledged_by_name=getattr(latest_ack, "acknowledged_by_name", None),
        acknowledged_by_email=getattr(latest_ack, "acknowledged_by_email", None),
        created_at=audit.created_at,
        stages=stages,
    )


_extension_router = APIRouter(
    prefix="/quality",
    tags=["Quality / QMS"],
    dependencies=[Depends(require_module("quality"))],
)


@_extension_router.get("/audits/{audit_id}/workspace", response_model=QMSAuditWorkspaceOut)
def get_authoritative_audit_workspace(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    return QMSAuditWorkspaceOut(
        audit=_serialize_audit(audit, db),
        workflow=build_authoritative_audit_workflow(db, audit),
    )


@_extension_router.get("/audits/{audit_id}/workflow-check", response_model=QMSAuditWorkspaceOut)
def get_authoritative_audit_workflow_check(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    return QMSAuditWorkspaceOut(
        audit=_serialize_audit(audit, db),
        workflow=build_authoritative_audit_workflow(db, audit),
    )


_REPLACED_PATHS = {
    "/quality/audits/{audit_id}/workspace",
    "/quality/audits/{audit_id}/workflow-check",
}
router.routes[:] = [
    route
    for route in router.routes
    if not (
        str(getattr(route, "path", "")) in _REPLACED_PATHS
        and "GET" in (getattr(route, "methods", None) or set())
    )
]
router.routes[0:0] = list(_extension_router.routes)
