from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.audit import models as audit_models
from amodb.apps.audit import services as audit_services
from amodb.database import get_db
from amodb.entitlements import require_module
from amodb.security import get_current_active_user

from . import models
from .audit_file_controls import (
    _audit_status_value,
    _require_checklist_editor,
    _validate_checklist_signature,
)
from .audit_lifecycle_models import (
    QualityAuditChecklistDocument,
    QualityAuditEvidenceReview,
    QualityAuditReportDocument,
    QualityAuditStageRecord,
)
from .audit_lifecycle_schemas import (
    QualityAuditActionItemOut,
    QualityAuditCarryoverFindingOut,
    QualityAuditChecklistCommitIn,
    QualityAuditChecklistMetadataOut,
    QualityAuditDocumentOut,
    QualityAuditEvidenceReviewIn,
    QualityAuditEvidenceReviewOut,
    QualityAuditNoticeEventOut,
    QualityAuditPreviousAuditOut,
    QualityAuditPreviousReportOut,
    QualityAuditReadinessOut,
    QualityAuditReportIssueIn,
    QualityAuditReportMetadataOut,
    QualityAuditStageActionOut,
    QualityAuditStageOut,
    QualityAuditStageTransitionIn,
    QualityAuditWarRoomContextOut,
    QualityAuditWorkflowV2Out,
    QualityAuditWorkspaceV2Out,
)
from .router import (
    AUDIT_CHECKLIST_ALLOWED_EXTENSIONS,
    AUDIT_CHECKLIST_ALLOWED_MIME_TYPES,
    AUDIT_CHECKLIST_DIR,
    AUDIT_REPORT_DIR,
    MAX_AUDIT_CHECKLIST_BYTES,
    MAX_AUDIT_REPORT_BYTES,
    _audit_metadata,
    _current_amo_id,
    _get_audit_for_amo,
    _is_quality_admin,
    _normalized_upload_mime,
    _require_audit_access,
    _sanitize_checklist_filename,
    _serialize_audit,
    router,
)


STAGE_ORDER = ("war-room", "checklist", "findings", "cars", "evidence", "report", "closeout")
STAGE_LABELS = {
    "war-room": "War room",
    "checklist": "Checklist",
    "findings": "Findings",
    "cars": "CARs",
    "evidence": "Evidence",
    "report": "Report",
    "closeout": "Closeout",
}
CLOSED_CAR_STATUSES = {"CLOSED", "CANCELLED"}
REPORT_ALLOWED_EXTENSIONS = {".pdf"}
REPORT_ALLOWED_MIME_TYPES = {"application/pdf", "application/octet-stream"}
PDF_MAGIC = b"%PDF-"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


def _safe_name(value: str | None, fallback: str) -> str:
    raw = str(value or "").replace("\\", "/")
    name = Path(raw).name.strip() or fallback
    name = re.sub(r"^[a-f0-9]{32,64}[_-]+", "", name, flags=re.I)
    name = re.sub(r"[^A-Za-z0-9._() -]+", "_", name).strip(" .")
    return (name or fallback)[:255]


def _approved_path(storage_key: str, root: Path, audit_id: UUID) -> Path:
    candidate = Path(storage_key).resolve()
    expected_root = (root / str(audit_id)).resolve()
    try:
        candidate.relative_to(expected_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Controlled document is outside approved Quality storage.") from exc
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Controlled document file is missing.")
    return candidate


def _require_audit_editor(current_user: account_models.User, audit: models.QMSAudit) -> None:
    if _is_quality_admin(current_user):
        return
    assigned = {
        str(value)
        for value in (
            audit.lead_auditor_user_id,
            audit.observer_auditor_user_id,
            audit.assistant_auditor_user_id,
        )
        if value
    }
    if str(current_user.id) in assigned:
        return
    raise HTTPException(status_code=403, detail="Only the assigned audit team or a Quality administrator may control this audit lifecycle.")


def _require_mutable_audit(current_user: account_models.User, audit: models.QMSAudit) -> None:
    _require_audit_editor(current_user, audit)
    if _audit_status_value(audit) == "CLOSED":
        raise HTTPException(status_code=409, detail="This audit is closed and retained as an immutable record.")


def _next_version(db: Session, model: type, audit_id: UUID) -> int:
    current = db.query(func.max(model.version_number)).filter(model.audit_id == audit_id).scalar()
    return int(current or 0) + 1


def _latest_checklist_versions(db: Session, audit_id: UUID) -> list[QualityAuditChecklistDocument]:
    return (
        db.query(QualityAuditChecklistDocument)
        .filter(QualityAuditChecklistDocument.audit_id == audit_id)
        .order_by(QualityAuditChecklistDocument.version_number.desc())
        .all()
    )


def _latest_report_versions(db: Session, audit_id: UUID) -> list[QualityAuditReportDocument]:
    return (
        db.query(QualityAuditReportDocument)
        .filter(QualityAuditReportDocument.audit_id == audit_id)
        .order_by(QualityAuditReportDocument.version_number.desc())
        .all()
    )


def _latest_stage_records(db: Session, audit_id: UUID) -> dict[str, QualityAuditStageRecord]:
    rows = (
        db.query(QualityAuditStageRecord)
        .filter(QualityAuditStageRecord.audit_id == audit_id)
        .order_by(QualityAuditStageRecord.occurred_at.desc())
        .all()
    )
    result: dict[str, QualityAuditStageRecord] = {}
    for row in rows:
        result.setdefault(row.stage_id, row)
    return result


def _document_out(row: QualityAuditChecklistDocument | QualityAuditReportDocument, *, kind: str) -> QualityAuditDocumentOut:
    base = {
        "id": row.id,
        "audit_id": row.audit_id,
        "version_number": row.version_number,
        "parent_version_id": row.parent_version_id,
        "filename": row.filename,
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
        "sha256": row.sha256,
        "lifecycle_status": row.lifecycle_status,
        "created_at": row.created_at,
        "created_by_user_id": row.uploaded_by_user_id,
        "committed_at": getattr(row, "committed_at", None),
        "issued_at": getattr(row, "issued_at", None),
        "issued_by_user_id": getattr(row, "issued_by_user_id", None),
        "source_type": getattr(row, "source_type", None),
        "fillable": getattr(row, "fillable", None),
        "field_count": getattr(row, "field_count", None),
        "issue_label": getattr(row, "issue_label", None),
        "distribution_status": getattr(row, "distribution_status", None),
        "download_url": f"/quality/audits/{row.audit_id}/documents/{kind}/versions/{row.id}/download",
    }
    return QualityAuditDocumentOut(**base)


def _checklist_metadata(db: Session, audit: models.QMSAudit, current_user: account_models.User) -> QualityAuditChecklistMetadataOut:
    versions = _latest_checklist_versions(db, audit.id)
    current = next((row for row in versions if row.lifecycle_status in {"COMMITTED", "SOURCE"}), versions[0] if versions else None)
    source = next((row for row in versions if row.lifecycle_status == "SOURCE"), None)
    item_query = db.query(models.QualityAuditChecklistItem).filter(
        models.QualityAuditChecklistItem.audit_id == audit.id,
        models.QualityAuditChecklistItem.amo_id == audit.amo_id,
    )
    total = item_query.count()
    completed = item_query.filter(models.QualityAuditChecklistItem.response_status != "PENDING").count()
    stage = _latest_stage_records(db, audit.id).get("checklist")
    role_allowed = _is_quality_admin(current_user) or str(current_user.id) in {
        str(value)
        for value in (audit.lead_auditor_user_id, audit.observer_auditor_user_id, audit.assistant_auditor_user_id)
        if value
    }
    read_only_reason = None
    if _audit_status_value(audit) == "CLOSED":
        read_only_reason = "This audit is closed. Checklist versions are retained as read-only records."
    elif _issued_report(versions=None, report_versions=_latest_report_versions(db, audit.id)) is not None:
        read_only_reason = "The audit report has been issued. Checklist versions are now read-only."
    elif not role_allowed:
        read_only_reason = "Only the assigned audit team or a Quality administrator may edit the checklist."
    return QualityAuditChecklistMetadataOut(
        available=bool(versions or total),
        current=_document_out(current, kind="checklist") if current else None,
        source=_document_out(source, kind="checklist") if source else None,
        versions=[_document_out(row, kind="checklist") for row in versions],
        portal_item_count=total,
        portal_completed_count=completed,
        explicitly_completed=bool(stage and stage.state == "COMPLETE"),
        read_only=read_only_reason is not None,
        read_only_reason=read_only_reason,
    )


def _issued_report(*, versions: list[QualityAuditChecklistDocument] | None = None, report_versions: list[QualityAuditReportDocument]) -> QualityAuditReportDocument | None:
    del versions
    return next((row for row in report_versions if row.lifecycle_status == "ISSUED" and row.issued_at), None)


def _report_metadata(db: Session, audit: models.QMSAudit, current_user: account_models.User) -> QualityAuditReportMetadataOut:
    versions = _latest_report_versions(db, audit.id)
    issued = _issued_report(report_versions=versions)
    draft = next((row for row in versions if row.lifecycle_status == "DRAFT"), None)
    role_allowed = _is_quality_admin(current_user) or str(current_user.id) in {
        str(value)
        for value in (audit.lead_auditor_user_id, audit.observer_auditor_user_id, audit.assistant_auditor_user_id)
        if value
    }
    reason = None
    if _audit_status_value(audit) == "CLOSED":
        reason = "This audit is closed. The issued report is retained as read-only."
    elif issued:
        reason = "A controlled report version has been issued. Upload a new revision only through the report revision workflow."
    elif not role_allowed:
        reason = "Only the assigned audit team or a Quality administrator may manage the report."
    return QualityAuditReportMetadataOut(
        available=bool(versions),
        current_draft=_document_out(draft, kind="report") if draft else None,
        issued=_document_out(issued, kind="report") if issued else None,
        versions=[_document_out(row, kind="report") for row in versions],
        read_only=reason is not None,
        read_only_reason=reason,
    )


def _query_facts(db: Session, audit: models.QMSAudit) -> dict[str, Any]:
    findings = (
        db.query(models.QMSAuditFinding)
        .filter(models.QMSAuditFinding.audit_id == audit.id, models.QMSAuditFinding.amo_id == audit.amo_id)
        .all()
    )
    finding_ids = [row.id for row in findings]
    cars = (
        db.query(models.CorrectiveActionRequest)
        .filter(models.CorrectiveActionRequest.amo_id == audit.amo_id, models.CorrectiveActionRequest.finding_id.in_(finding_ids))
        .all()
        if finding_ids
        else []
    )
    checklist_items = (
        db.query(models.QualityAuditChecklistItem)
        .filter(models.QualityAuditChecklistItem.audit_id == audit.id, models.QualityAuditChecklistItem.amo_id == audit.amo_id)
        .all()
    )
    finding_attachments = (
        db.query(models.QMSFindingAttachment).filter(models.QMSFindingAttachment.finding_id.in_(finding_ids)).all()
        if finding_ids
        else []
    )
    car_ids = [row.id for row in cars]
    car_attachments = (
        db.query(models.CARAttachment).filter(models.CARAttachment.car_id.in_(car_ids)).all()
        if car_ids
        else []
    )
    checklist_versions = _latest_checklist_versions(db, audit.id)
    report_versions = _latest_report_versions(db, audit.id)
    stage_records = _latest_stage_records(db, audit.id)
    reviews = (
        db.query(QualityAuditEvidenceReview)
        .filter(QualityAuditEvidenceReview.audit_id == audit.id, QualityAuditEvidenceReview.amo_id == audit.amo_id)
        .all()
    )
    review_map = {(row.entity_type, row.entity_id): row for row in reviews}
    nc_findings = [
        finding
        for finding in findings
        if _enum_value(finding.finding_type).upper() == "NON_CONFORMITY"
        or _enum_value(finding.level).upper() in {"LEVEL_1", "LEVEL_2", "LEVEL_3"}
    ]
    car_by_finding = {row.finding_id: row for row in cars if _enum_value(row.status).upper() != "CANCELLED"}
    nc_without_car = [row for row in nc_findings if row.id not in car_by_finding]
    open_cars = [row for row in cars if _enum_value(row.status).upper() not in CLOSED_CAR_STATUSES]
    open_findings = [row for row in findings if not row.closed_at]
    current_checklist = next((row for row in checklist_versions if row.lifecycle_status in {"COMMITTED", "SOURCE"}), None)
    evidence_entities: list[tuple[str, str]] = []
    if current_checklist:
        evidence_entities.append(("CHECKLIST_VERSION", str(current_checklist.id)))
    evidence_entities.extend(("FINDING_ATTACHMENT", str(row.id)) for row in finding_attachments)
    evidence_entities.extend(("CAR_ATTACHMENT", str(row.id)) for row in car_attachments)
    evidence_pending = 0
    evidence_rejected = 0
    evidence_accepted = 0
    for key in evidence_entities:
        review = review_map.get(key)
        status = str(getattr(review, "status", "PENDING") or "PENDING").upper()
        if status == "ACCEPTED":
            evidence_accepted += 1
        elif status == "REJECTED":
            evidence_rejected += 1
        else:
            evidence_pending += 1
    return {
        "findings": findings,
        "cars": cars,
        "checklist_items": checklist_items,
        "finding_attachments": finding_attachments,
        "car_attachments": car_attachments,
        "checklist_versions": checklist_versions,
        "report_versions": report_versions,
        "stage_records": stage_records,
        "reviews": reviews,
        "nc_findings": nc_findings,
        "nc_without_car": nc_without_car,
        "open_cars": open_cars,
        "open_findings": open_findings,
        "current_checklist": current_checklist,
        "issued_report": _issued_report(report_versions=report_versions),
        "draft_report": next((row for row in report_versions if row.lifecycle_status == "DRAFT"), None),
        "evidence_entities": evidence_entities,
        "evidence_pending": evidence_pending,
        "evidence_rejected": evidence_rejected,
        "evidence_accepted": evidence_accepted,
    }


def _stage_action(stage_id: str, state: str) -> QualityAuditStageActionOut | None:
    actions = {
        "war-room": ("start-audit", "Start opening brief", "POST", "/lifecycle/start"),
        "checklist": ("open-checklist", "Open checklist", "GET", "?tab=checklist"),
        "findings": ("complete-fieldwork", "Complete fieldwork", "POST", "/lifecycle/fieldwork/complete"),
        "cars": ("issue-cars", "Review required CARs", "GET", "?tab=cars"),
        "evidence": ("verify-evidence", "Review evidence", "GET", "?tab=evidence"),
        "report": ("issue-report", "Prepare issued report", "GET", "?tab=report"),
        "closeout": ("close-audit", "Complete closeout", "POST", "/lifecycle/closeout"),
    }
    if state in {"COMPLETE", "LOCKED", "NOT_READY"}:
        return None
    action_id, label, method, path = actions[stage_id]
    return QualityAuditStageActionOut(id=action_id, label=label, method=method, path=path, enabled=state != "BLOCKED")


def build_workflow_v2(db: Session, audit: models.QMSAudit) -> QualityAuditWorkflowV2Out:
    facts = _query_facts(db, audit)
    closed = _audit_status_value(audit) == "CLOSED"
    stages: list[QualityAuditStageOut] = []

    war_blockers: list[str] = []
    if not audit.scope:
        war_blockers.append("Audit scope is not defined.")
    if not audit.criteria:
        war_blockers.append("Audit criteria are not defined.")
    if not audit.planned_start or not audit.planned_end:
        war_blockers.append("Planned audit dates are incomplete.")
    if not audit.lead_auditor_user_id:
        war_blockers.append("Lead auditor is not assigned.")
    if not (audit.auditee_user_id or audit.auditee or audit.auditee_email):
        war_blockers.append("Auditee is not assigned.")
    war_record = facts["stage_records"].get("war-room")
    war_complete = closed or bool(audit.actual_start) or bool(war_record and war_record.state == "COMPLETE")
    war_state = "LOCKED" if closed else "COMPLETE" if war_complete else "READY" if not war_blockers else "BLOCKED"
    stages.append(QualityAuditStageOut(
        id="war-room",
        label="War room",
        state=war_state,
        complete=war_complete,
        active=False,
        metric="Opening brief recorded" if war_complete else "Ready to start" if not war_blockers else f"{len(war_blockers)} blocker(s)",
        helper="Confirm the audit brief, previous audit intelligence, team and notices before starting fieldwork.",
        blockers=war_blockers,
        completed_at=war_record.occurred_at if war_record and war_record.state == "COMPLETE" else None,
        completed_by_user_id=war_record.actor_user_id if war_record and war_record.state == "COMPLETE" else None,
        primary_action=_stage_action("war-room", war_state),
    ))

    checklist_record = facts["stage_records"].get("checklist")
    checklist_source = bool(facts["checklist_versions"] or facts["checklist_items"])
    checklist_rows_complete = bool(facts["checklist_items"]) and all(row.response_status != "PENDING" for row in facts["checklist_items"])
    checklist_complete = closed or bool(checklist_record and checklist_record.state == "COMPLETE")
    checklist_blockers: list[str] = []
    if not checklist_source:
        checklist_blockers.append("Upload a controlled checklist source or create portal checklist rows.")
    if facts["checklist_items"] and not checklist_rows_complete:
        pending = sum(1 for row in facts["checklist_items"] if row.response_status == "PENDING")
        checklist_blockers.append(f"{pending} checklist item(s) remain pending.")
    if not war_complete:
        checklist_state = "NOT_READY"
    elif checklist_complete:
        checklist_state = "LOCKED" if closed else "COMPLETE"
    elif checklist_source:
        checklist_state = "IN_PROGRESS" if audit.actual_start else "READY"
    else:
        checklist_state = "BLOCKED"
    stages.append(QualityAuditStageOut(
        id="checklist",
        label="Checklist",
        state=checklist_state,
        complete=checklist_complete,
        active=False,
        metric=(
            f"{sum(1 for row in facts['checklist_items'] if row.response_status != 'PENDING')}/{len(facts['checklist_items'])} portal items"
            if facts["checklist_items"]
            else f"{len(facts['checklist_versions'])} retained version(s)"
        ),
        helper="A source document is readiness only. Completion requires an explicit controlled checklist-complete action.",
        blockers=checklist_blockers if checklist_state in {"BLOCKED", "IN_PROGRESS"} else [],
        completed_at=checklist_record.occurred_at if checklist_record and checklist_record.state == "COMPLETE" else None,
        completed_by_user_id=checklist_record.actor_user_id if checklist_record and checklist_record.state == "COMPLETE" else None,
        primary_action=_stage_action("checklist", checklist_state),
    ))

    finding_record = facts["stage_records"].get("findings")
    findings_complete = closed or bool(audit.actual_end) or bool(finding_record and finding_record.state == "COMPLETE")
    if not checklist_complete:
        findings_state = "NOT_READY"
    elif findings_complete:
        findings_state = "LOCKED" if closed else "COMPLETE"
    elif audit.actual_start:
        findings_state = "IN_PROGRESS"
    else:
        findings_state = "READY"
    stages.append(QualityAuditStageOut(
        id="findings",
        label="Findings",
        state=findings_state,
        complete=findings_complete,
        active=False,
        metric=f"{len(facts['findings'])} finding(s); {len(facts['open_findings'])} open",
        helper="Fieldwork is complete only after the assigned auditor explicitly closes fieldwork.",
        blockers=[],
        completed_at=finding_record.occurred_at if finding_record and finding_record.state == "COMPLETE" else None,
        completed_by_user_id=finding_record.actor_user_id if finding_record and finding_record.state == "COMPLETE" else None,
        primary_action=_stage_action("findings", findings_state),
    ))

    cars_complete = closed or (findings_complete and not facts["nc_without_car"])
    car_blockers = [f"{len(facts['nc_without_car'])} non-conformity finding(s) do not have an issued CAR."] if facts["nc_without_car"] else []
    if not findings_complete:
        cars_state = "NOT_READY"
    elif cars_complete:
        cars_state = "LOCKED" if closed else "COMPLETE"
    else:
        cars_state = "BLOCKED"
    car_warnings = [f"{len(facts['open_cars'])} CAR(s) remain open and will continue through closeout."] if facts["open_cars"] else []
    stages.append(QualityAuditStageOut(
        id="cars",
        label="CARs",
        state=cars_state,
        complete=cars_complete,
        active=False,
        metric=f"{len(facts['cars'])} issued; {len(facts['open_cars'])} open",
        helper="Report progression requires CAR issuance for every Level 1-3 non-conformity; final CAR closure is a closeout gate.",
        blockers=car_blockers,
        warnings=car_warnings,
        primary_action=_stage_action("cars", cars_state),
    ))

    evidence_total = len(facts["evidence_entities"])
    evidence_complete = closed or (
        cars_complete
        and checklist_complete
        and evidence_total > 0
        and facts["evidence_pending"] == 0
        and facts["evidence_rejected"] == 0
    )
    if not cars_complete:
        evidence_state = "NOT_READY"
    elif evidence_complete:
        evidence_state = "LOCKED" if closed else "COMPLETE"
    elif facts["evidence_rejected"]:
        evidence_state = "BLOCKED"
    else:
        evidence_state = "IN_PROGRESS" if evidence_total else "BLOCKED"
    evidence_blockers: list[str] = []
    if evidence_total == 0:
        evidence_blockers.append("No controlled checklist or supporting evidence is available for review.")
    if facts["evidence_rejected"]:
        evidence_blockers.append(f"{facts['evidence_rejected']} evidence item(s) were rejected.")
    evidence_warnings = [f"{facts['evidence_pending']} evidence item(s) await auditor verification."] if facts["evidence_pending"] else []
    stages.append(QualityAuditStageOut(
        id="evidence",
        label="Evidence",
        state=evidence_state,
        complete=evidence_complete,
        active=False,
        metric=f"{facts['evidence_accepted']}/{evidence_total} accepted",
        helper="Evidence completion is based on explicit acceptance, not file presence.",
        blockers=evidence_blockers,
        warnings=evidence_warnings,
        primary_action=_stage_action("evidence", evidence_state),
    ))

    issued_report = facts["issued_report"]
    report_complete = closed or bool(issued_report and evidence_complete and cars_complete)
    report_warnings: list[str] = []
    if issued_report and not evidence_complete:
        report_warnings.append("An issued report exists before the current evidence lifecycle is complete. Review the retained legacy state.")
    if not evidence_complete or not cars_complete:
        report_state = "BLOCKED" if issued_report else "NOT_READY"
    elif report_complete:
        report_state = "LOCKED" if closed else "COMPLETE"
    elif facts["draft_report"]:
        report_state = "IN_PROGRESS"
    else:
        report_state = "READY"
    stages.append(QualityAuditStageOut(
        id="report",
        label="Report",
        state=report_state,
        complete=report_complete,
        active=False,
        metric=(f"Issued {issued_report.issued_at.date().isoformat()}" if issued_report and issued_report.issued_at else "Draft uploaded" if facts["draft_report"] else "Not issued"),
        helper="A report is complete only when a controlled report version is explicitly issued.",
        blockers=[] if report_state not in {"BLOCKED", "NOT_READY"} else ["Complete CAR issuance and evidence verification before issuing the report."],
        warnings=report_warnings,
        completed_at=issued_report.issued_at if report_complete and issued_report else None,
        completed_by_user_id=issued_report.issued_by_user_id if report_complete and issued_report else None,
        primary_action=_stage_action("report", report_state),
    ))

    archive_count = db.query(models.QualityArchivePackage).filter(
        models.QualityArchivePackage.audit_id == audit.id,
        models.QualityArchivePackage.amo_id == audit.amo_id,
    ).count()
    closeout_blockers: list[str] = []
    if not report_complete:
        closeout_blockers.append("Issued audit report is not complete.")
    if facts["open_findings"]:
        closeout_blockers.append(f"{len(facts['open_findings'])} finding(s) remain open.")
    if facts["open_cars"]:
        closeout_blockers.append(f"{len(facts['open_cars'])} CAR(s) remain open.")
    if facts["evidence_pending"] or facts["evidence_rejected"]:
        closeout_blockers.append("Evidence verification is incomplete.")
    closeout_complete = closed
    if closed:
        closeout_state = "LOCKED"
    elif not report_complete:
        closeout_state = "NOT_READY"
    elif closeout_blockers:
        closeout_state = "BLOCKED"
    else:
        closeout_state = "READY"
    close_record = facts["stage_records"].get("closeout")
    stages.append(QualityAuditStageOut(
        id="closeout",
        label="Closeout",
        state=closeout_state,
        complete=closeout_complete,
        active=False,
        metric=f"{archive_count} archive package(s)" if archive_count else "Closure not approved",
        helper="Closeout requires closed findings and CARs, accepted evidence, formal approval and archive generation.",
        blockers=closeout_blockers,
        completed_at=close_record.occurred_at if close_record and close_record.state == "COMPLETE" else None,
        completed_by_user_id=close_record.actor_user_id if close_record and close_record.state == "COMPLETE" else None,
        primary_action=_stage_action("closeout", closeout_state),
    ))

    if closed:
        for stage in stages:
            stage.complete = True
            stage.state = "LOCKED"
            stage.primary_action = None

    current = next((stage for stage in stages if not stage.complete and stage.state != "LOCKED"), stages[-1])
    current.active = True
    percent = int(round(sum(1 for stage in stages if stage.complete) / len(STAGE_ORDER) * 100))
    return QualityAuditWorkflowV2Out(
        audit_id=audit.id,
        current_stage_id=current.id,
        current_stage_label=current.label,
        lifecycle_status=_audit_status_value(audit),
        percent_complete=percent,
        findings_total=len(facts["findings"]),
        findings_open=len(facts["open_findings"]),
        cars_total=len(facts["cars"]),
        cars_open=len(facts["open_cars"]),
        evidence_total=evidence_total,
        evidence_pending=facts["evidence_pending"] + facts["evidence_rejected"],
        checklist_uploaded=bool(facts["checklist_versions"]),
        checklist_complete=checklist_complete,
        report_uploaded=bool(facts["report_versions"]),
        report_issued=bool(issued_report),
        stages=stages,
    )


def _write_upload(
    *,
    upload: UploadFile,
    target_dir: Path,
    max_bytes: int,
    allowed_extensions: set[str],
    allowed_mimes: set[str],
    validate_checklist: bool,
) -> tuple[Path, str, str, int, str]:
    original_name = _safe_name(upload.filename, "document")
    extension = Path(original_name).suffix.lower()
    if extension not in allowed_extensions:
        raise HTTPException(status_code=415, detail=f"File extension {extension or '(none)'} is not allowed.")
    mime_type = _normalized_upload_mime(upload)
    if mime_type not in allowed_mimes:
        raise HTTPException(status_code=415, detail="File MIME type is not allowed.")
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{uuid4().hex}_{original_name}"
    digest = hashlib.sha256()
    size = 0
    try:
        with target_path.open("xb") as handle:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(status_code=413, detail=f"File exceeds the {max_bytes // (1024 * 1024)}MB limit.")
                digest.update(chunk)
                handle.write(chunk)
        if size <= 0:
            raise HTTPException(status_code=422, detail="Uploaded file is empty.")
        if validate_checklist:
            _validate_checklist_signature(target_path, extension)
        elif extension == ".pdf":
            with target_path.open("rb") as handle:
                if not handle.read(5).startswith(PDF_MAGIC):
                    raise HTTPException(status_code=415, detail="The uploaded report is not a valid PDF document.")
    except Exception:
        target_path.unlink(missing_ok=True)
        raise
    return target_path, original_name, mime_type, size, digest.hexdigest()


def _record_stage(
    db: Session,
    *,
    audit: models.QMSAudit,
    stage_id: str,
    state: str,
    current_user: account_models.User,
    note: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> QualityAuditStageRecord:
    record = QualityAuditStageRecord(
        amo_id=audit.amo_id,
        audit_id=audit.id,
        stage_id=stage_id,
        state=state,
        actor_user_id=current_user.id,
        note=(note or "").strip() or None,
        metadata_json=metadata,
    )
    db.add(record)
    return record


def _log(
    db: Session,
    request: Request | None,
    *,
    audit: models.QMSAudit,
    current_user: account_models.User,
    action: str,
    after: dict[str, Any] | None = None,
    critical: bool = False,
) -> None:
    audit_services.log_event(
        db,
        amo_id=audit.amo_id,
        actor_user_id=current_user.id,
        entity_type="qms_audit",
        entity_id=str(audit.id),
        action=action,
        after=after,
        correlation_id=str(uuid4()),
        metadata=_audit_metadata(request) if request else None,
        critical=critical,
    )


def _audit_person_name(db: Session, user_id: str | None) -> str | None:
    if not user_id:
        return None
    user = db.query(account_models.User).filter(account_models.User.id == user_id).first()
    if not user:
        return None
    return str(getattr(user, "full_name", None) or getattr(user, "name", None) or getattr(user, "email", None) or user_id)


def _normalize_requirement(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _email_domain(value: str | None) -> str:
    email = str(value or "").strip().lower()
    return email.rsplit("@", 1)[-1] if "@" in email else ""


def _audit_match_score(current: models.QMSAudit, candidate: models.QMSAudit) -> tuple[int, str]:
    if current.audit_scope_id and candidate.audit_scope_id == current.audit_scope_id:
        return 100, "Same audit scope"
    if current.auditee_user_id and candidate.auditee_user_id == current.auditee_user_id:
        return 90, "Same auditee"
    current_domain = _email_domain(current.auditee_email)
    candidate_domain = _email_domain(candidate.auditee_email)
    if current_domain and current_domain == candidate_domain:
        return 80, "Same auditee organisation"
    if current.audit_scope_code and candidate.audit_scope_code == current.audit_scope_code:
        return 70, "Same scope code"
    if current.auditee and candidate.auditee and current.auditee.strip().lower() == candidate.auditee.strip().lower():
        return 60, "Same auditee name"
    return 0, ""


def _previous_audits(db: Session, audit: models.QMSAudit) -> tuple[list[QualityAuditPreviousAuditOut], list[QualityAuditCarryoverFindingOut]]:
    candidates = (
        db.query(models.QMSAudit)
        .filter(
            models.QMSAudit.amo_id == audit.amo_id,
            models.QMSAudit.id != audit.id,
            models.QMSAudit.deleted_at.is_(None),
            or_(models.QMSAudit.status == "CLOSED", models.QMSAudit.actual_end.isnot(None)),
        )
        .order_by(models.QMSAudit.actual_end.desc().nullslast(), models.QMSAudit.created_at.desc())
        .limit(100)
        .all()
    )
    scored: list[tuple[int, str, models.QMSAudit]] = []
    for candidate in candidates:
        score, reason = _audit_match_score(audit, candidate)
        if score:
            scored.append((score, reason, candidate))
    scored.sort(key=lambda item: (item[0], item[2].actual_end or item[2].planned_end or date.min, item[2].created_at), reverse=True)

    output: list[QualityAuditPreviousAuditOut] = []
    carryovers: list[QualityAuditCarryoverFindingOut] = []
    for index, (score, reason, candidate) in enumerate(scored[:3]):
        del score
        report_versions = _latest_report_versions(db, candidate.id)
        issued = _issued_report(report_versions=report_versions)
        if not issued:
            continue
        findings = db.query(models.QMSAuditFinding).filter(models.QMSAuditFinding.audit_id == candidate.id).all()
        finding_ids = [row.id for row in findings]
        cars = (
            db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.finding_id.in_(finding_ids)).all()
            if finding_ids
            else []
        )
        car_by_finding = {row.finding_id: row for row in cars}
        open_rows = [
            row
            for row in findings
            if not row.closed_at or (
                row.id in car_by_finding and _enum_value(car_by_finding[row.id].status).upper() not in CLOSED_CAR_STATUSES
            )
        ]
        earlier_ids = [item[2].id for item in scored[index + 1 :] if item[2].audit_scope_id == candidate.audit_scope_id][:20]
        earlier_refs: set[str] = set()
        if earlier_ids:
            earlier_findings = db.query(models.QMSAuditFinding.requirement_ref).filter(models.QMSAuditFinding.audit_id.in_(earlier_ids)).all()
            earlier_refs = {_normalize_requirement(value) for (value,) in earlier_findings if _normalize_requirement(value)}
        repeat_count = sum(1 for row in findings if _normalize_requirement(row.requirement_ref) in earlier_refs)
        output.append(QualityAuditPreviousAuditOut(
            id=candidate.id,
            audit_ref=candidate.audit_ref,
            title=candidate.title,
            status=_audit_status_value(candidate),
            planned_start=candidate.planned_start,
            actual_end=candidate.actual_end,
            lead_auditor_name=_audit_person_name(db, candidate.lead_auditor_user_id),
            findings_total=len(findings),
            open_carryovers=len(open_rows),
            possible_repeat_findings=repeat_count,
            match_reason=reason,
            report=QualityAuditPreviousReportOut(
                available=True,
                document_id=issued.id,
                filename=issued.filename,
                issued_at=issued.issued_at,
                issue_label=issued.issue_label,
                download_url=f"/quality/audits/{candidate.id}/documents/report/versions/{issued.id}/download",
            ),
            workspace_path=f"/quality/audits/{candidate.audit_ref}",
        ))
        if index == 0:
            for row in open_rows:
                car = car_by_finding.get(row.id)
                due = getattr(car, "due_date", None) or row.target_close_date
                carryovers.append(QualityAuditCarryoverFindingOut(
                    finding_id=row.id,
                    finding_ref=row.finding_ref,
                    level=_enum_value(row.level),
                    requirement_ref=row.requirement_ref,
                    description=row.description,
                    target_close_date=due,
                    car_id=car.id if car else None,
                    car_number=car.car_number if car else None,
                    car_status=_enum_value(car.status) if car else None,
                    overdue=bool(due and due < date.today() and (not car or _enum_value(car.status).upper() not in CLOSED_CAR_STATUSES)),
                ))
    return output, carryovers


def _notice_history(db: Session, audit: models.QMSAudit) -> list[QualityAuditNoticeEventOut]:
    rows = (
        db.query(audit_models.AuditEvent)
        .filter(
            audit_models.AuditEvent.amo_id == audit.amo_id,
            audit_models.AuditEvent.entity_type == "qms_audit",
            audit_models.AuditEvent.entity_id == str(audit.id),
            audit_models.AuditEvent.action.in_([
                "issue_audit_notice",
                "issue_notice",
                "send_audit_reminder",
                "audit_notice_acknowledged",
                "share_report",
            ]),
        )
        .order_by(audit_models.AuditEvent.occurred_at.desc())
        .limit(30)
        .all()
    )
    labels = {
        "issue_audit_notice": "Audit notice issued",
        "issue_notice": "Audit notice issued",
        "send_audit_reminder": "Audit reminder sent",
        "audit_notice_acknowledged": "Auditee acknowledged notice",
        "share_report": "Audit report distributed",
    }
    user_ids = {row.actor_user_id for row in rows if row.actor_user_id}
    users = db.query(account_models.User).filter(account_models.User.id.in_(user_ids)).all() if user_ids else []
    names = {
        user.id: str(getattr(user, "full_name", None) or getattr(user, "email", None) or user.id)
        for user in users
    }
    return [
        QualityAuditNoticeEventOut(
            id=str(row.id),
            action=row.action,
            label=labels.get(row.action, row.action.replace("_", " ").title()),
            occurred_at=row.occurred_at,
            actor_user_id=row.actor_user_id,
            actor_name=names.get(row.actor_user_id),
            detail=str((row.after or {}).get("message") or (row.metadata_json or {}).get("message") or "") or None,
        )
        for row in rows
    ]


def _action_queue(
    audit: models.QMSAudit,
    workflow: QualityAuditWorkflowV2Out,
    previous: list[QualityAuditPreviousAuditOut],
    notice_history: list[QualityAuditNoticeEventOut],
) -> list[QualityAuditActionItemOut]:
    stage = {row.id: row for row in workflow.stages}
    return [
        QualityAuditActionItemOut(
            id="review-previous-report",
            label="Review previous audit report",
            state="READY" if previous else "COMPLETE",
            owner_label="Lead auditor",
            helper="No comparable issued report was found." if not previous else f"Review {previous[0].audit_ref} before fieldwork.",
            action_path=previous[0].report.download_url if previous else None,
        ),
        QualityAuditActionItemOut(
            id="confirm-scope-criteria",
            label="Confirm scope and criteria",
            state="COMPLETE" if audit.scope and audit.criteria else "BLOCKED",
            owner_label="Lead auditor",
            helper="Both scope and criteria must be explicit.",
        ),
        QualityAuditActionItemOut(
            id="confirm-team",
            label="Confirm audit team",
            state="COMPLETE" if audit.lead_auditor_user_id else "BLOCKED",
            owner_label="Quality manager",
            helper="Lead auditor is mandatory; observer and assistant are optional.",
        ),
        QualityAuditActionItemOut(
            id="notice-acknowledgement",
            label="Confirm notice and acknowledgement",
            state="COMPLETE" if any(row.action == "audit_notice_acknowledged" for row in notice_history) else "WARNING" if notice_history else "PENDING",
            owner_label="Lead auditor",
            helper="Issue the notice and follow up until the auditee acknowledgement is recorded.",
        ),
        QualityAuditActionItemOut(
            id="checklist-source",
            label="Confirm checklist source and revision",
            state="COMPLETE" if workflow.checklist_uploaded else "PENDING",
            owner_label="Audit team",
            action_path="?tab=checklist",
        ),
        QualityAuditActionItemOut(
            id="opening-brief",
            label="Record opening brief",
            state="COMPLETE" if stage["war-room"].complete else "READY" if stage["war-room"].state == "READY" else "BLOCKED",
            owner_label="Lead auditor",
            action_path=stage["war-room"].primary_action.path if stage["war-room"].primary_action else None,
        ),
        QualityAuditActionItemOut(
            id="begin-fieldwork",
            label="Begin fieldwork",
            state="COMPLETE" if audit.actual_start else "READY" if stage["war-room"].state == "READY" else "BLOCKED",
            owner_label="Audit team",
            action_path="?tab=checklist",
        ),
    ]


_extension_router = APIRouter(
    prefix="/quality",
    tags=["Quality / audit lifecycle"],
    dependencies=[Depends(require_module("quality"))],
)


@_extension_router.get("/audits/{audit_id}/workspace", response_model=QualityAuditWorkspaceV2Out)
def get_audit_workspace_v2(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_audit_access(current_user, audit, allow_auditee=True)
    return QualityAuditWorkspaceV2Out(audit=_serialize_audit(audit, db), workflow=build_workflow_v2(db, audit))


@_extension_router.get("/audits/{audit_id}/workflow-check", response_model=QualityAuditWorkspaceV2Out)
def get_audit_workflow_check_v2(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    return get_audit_workspace_v2(audit_id=audit_id, db=db, current_user=current_user)


@_extension_router.get("/audits/{audit_id}/war-room-context", response_model=QualityAuditWarRoomContextOut)
def get_audit_war_room_context(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_audit_access(current_user, audit, allow_auditee=True)
    workflow = build_workflow_v2(db, audit)
    previous, carryovers = _previous_audits(db, audit)
    notices = _notice_history(db, audit)
    war = next(stage for stage in workflow.stages if stage.id == "war-room")
    return QualityAuditWarRoomContextOut(
        audit=_serialize_audit(audit, db),
        workflow=workflow,
        readiness=QualityAuditReadinessOut(ready=war.state == "READY" or war.complete, blockers=war.blockers, warnings=war.warnings),
        previous_audits=previous,
        carryover_findings=carryovers,
        notice_history=notices,
        action_queue=_action_queue(audit, workflow, previous, notices),
        checklist=_checklist_metadata(db, audit, current_user),
        report=_report_metadata(db, audit, current_user),
    )


@_extension_router.get("/audits/{audit_id}/documents/checklist", response_model=QualityAuditChecklistMetadataOut)
def get_checklist_metadata(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_audit_access(current_user, audit, allow_auditee=True)
    return _checklist_metadata(db, audit, current_user)


@_extension_router.get("/audits/{audit_id}/documents/report", response_model=QualityAuditReportMetadataOut)
def get_report_metadata(
    audit_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_audit_access(current_user, audit, allow_auditee=True)
    return _report_metadata(db, audit, current_user)


@_extension_router.get("/audits/{audit_id}/documents/checklist/versions/{version_id}/download", response_class=FileResponse)
def download_checklist_version(
    audit_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_audit_access(current_user, audit, allow_auditee=True)
    row = db.query(QualityAuditChecklistDocument).filter(
        QualityAuditChecklistDocument.id == version_id,
        QualityAuditChecklistDocument.audit_id == audit.id,
        QualityAuditChecklistDocument.amo_id == audit.amo_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Checklist version not found.")
    path = _approved_path(row.storage_key, AUDIT_CHECKLIST_DIR, audit.id)
    return FileResponse(path=path, filename=row.filename, media_type=row.content_type, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@_extension_router.get("/audits/{audit_id}/documents/report/versions/{version_id}/download", response_class=FileResponse)
def download_report_version(
    audit_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_audit_access(current_user, audit, allow_auditee=True)
    row = db.query(QualityAuditReportDocument).filter(
        QualityAuditReportDocument.id == version_id,
        QualityAuditReportDocument.audit_id == audit.id,
        QualityAuditReportDocument.amo_id == audit.amo_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Report version not found.")
    path = _approved_path(row.storage_key, AUDIT_REPORT_DIR, audit.id)
    return FileResponse(path=path, filename=row.filename, media_type=row.content_type, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


def _create_checklist_version(
    *,
    audit: models.QMSAudit,
    current_user: account_models.User,
    db: Session,
    request: Request,
    file: UploadFile,
    lifecycle_status: str,
    source_type: str,
    fillable: str,
    field_count: int | None,
) -> QualityAuditChecklistDocument:
    _require_mutable_audit(current_user, audit)
    if _issued_report(report_versions=_latest_report_versions(db, audit.id)):
        raise HTTPException(status_code=409, detail="The audit report has been issued. The checklist is read-only.")
    path, name, mime, size, digest = _write_upload(
        upload=file,
        target_dir=AUDIT_CHECKLIST_DIR / str(audit.id),
        max_bytes=MAX_AUDIT_CHECKLIST_BYTES,
        allowed_extensions=set(AUDIT_CHECKLIST_ALLOWED_EXTENSIONS),
        allowed_mimes=set(AUDIT_CHECKLIST_ALLOWED_MIME_TYPES),
        validate_checklist=True,
    )
    versions = _latest_checklist_versions(db, audit.id)
    parent = versions[0] if versions else None
    version = QualityAuditChecklistDocument(
        amo_id=audit.amo_id,
        audit_id=audit.id,
        version_number=_next_version(db, QualityAuditChecklistDocument, audit.id),
        parent_version_id=parent.id if parent else None,
        filename=name,
        storage_key=str(path),
        content_type=mime,
        size_bytes=size,
        sha256=digest,
        source_type=source_type,
        fillable=fillable,
        field_count=field_count,
        lifecycle_status=lifecycle_status,
        uploaded_by_user_id=current_user.id,
        committed_at=_utcnow() if lifecycle_status in {"SOURCE", "COMMITTED"} else None,
    )
    if lifecycle_status == "SOURCE":
        for row in versions:
            if row.lifecycle_status == "SOURCE":
                row.lifecycle_status = "RETAINED"
                row.superseded_at = _utcnow()
    elif lifecycle_status == "COMMITTED":
        for row in versions:
            if row.lifecycle_status == "COMMITTED":
                row.lifecycle_status = "SUPERSEDED"
                row.superseded_at = _utcnow()
    db.add(version)
    if lifecycle_status in {"SOURCE", "COMMITTED"}:
        audit.checklist_file_ref = str(path)
    _log(db, request, audit=audit, current_user=current_user, action=f"checklist_{lifecycle_status.lower()}", after={
        "version_number": version.version_number,
        "filename": name,
        "size_bytes": size,
        "sha256": digest,
        "fillable": fillable,
        "field_count": field_count,
    }, critical=lifecycle_status in {"SOURCE", "COMMITTED"})
    db.commit()
    db.refresh(version)
    return version


@_extension_router.post("/audits/{audit_id}/documents/checklist/source", response_model=QualityAuditDocumentOut)
def upload_checklist_source(
    audit_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    fillable: str = Form(default="UNKNOWN"),
    field_count: int | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    fillable_value = fillable.upper() if fillable.upper() in {"UNKNOWN", "YES", "NO"} else "UNKNOWN"
    row = _create_checklist_version(
        audit=audit,
        current_user=current_user,
        db=db,
        request=request,
        file=file,
        lifecycle_status="SOURCE",
        source_type="UPLOAD",
        fillable=fillable_value,
        field_count=field_count,
    )
    return _document_out(row, kind="checklist")


@_extension_router.post("/audits/{audit_id}/documents/checklist/draft", response_model=QualityAuditDocumentOut)
def save_checklist_draft(
    audit_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    fillable: str = Form(default="UNKNOWN"),
    field_count: int | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    fillable_value = fillable.upper() if fillable.upper() in {"UNKNOWN", "YES", "NO"} else "UNKNOWN"
    row = _create_checklist_version(
        audit=audit,
        current_user=current_user,
        db=db,
        request=request,
        file=file,
        lifecycle_status="WORKING_DRAFT",
        source_type="PDF_FORM_SAVE",
        fillable=fillable_value,
        field_count=field_count,
    )
    return _document_out(row, kind="checklist")


@_extension_router.post("/audits/{audit_id}/documents/checklist/commit", response_model=QualityAuditDocumentOut)
def commit_checklist_version(
    audit_id: UUID,
    request: Request,
    payload: QualityAuditChecklistCommitIn,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_mutable_audit(current_user, audit)
    if _issued_report(report_versions=_latest_report_versions(db, audit.id)):
        raise HTTPException(status_code=409, detail="The audit report has been issued. The checklist is read-only.")
    row = db.query(QualityAuditChecklistDocument).filter(
        QualityAuditChecklistDocument.id == payload.version_id,
        QualityAuditChecklistDocument.audit_id == audit.id,
        QualityAuditChecklistDocument.amo_id == audit.amo_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Checklist version not found.")
    if row.lifecycle_status not in {"WORKING_DRAFT", "SOURCE"}:
        raise HTTPException(status_code=409, detail="Only a source or working draft can be committed.")
    now = _utcnow()
    for previous in _latest_checklist_versions(db, audit.id):
        if previous.id != row.id and previous.lifecycle_status == "COMMITTED":
            previous.lifecycle_status = "SUPERSEDED"
            previous.superseded_at = now
    row.lifecycle_status = "COMMITTED"
    row.committed_at = now
    row.fillable = payload.fillable
    row.field_count = payload.field_count
    audit.checklist_file_ref = row.storage_key
    _log(db, request, audit=audit, current_user=current_user, action="commit_checklist_version", after={
        "version_id": str(row.id),
        "version_number": row.version_number,
        "filename": row.filename,
        "fillable": row.fillable,
        "field_count": row.field_count,
        "note": payload.note,
    }, critical=True)
    db.commit()
    db.refresh(row)
    return _document_out(row, kind="checklist")


@_extension_router.post("/audits/{audit_id}/checklist", response_model=QualityAuditWorkspaceV2Out)
def legacy_save_checklist_as_retained_version(
    audit_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    existing = _latest_checklist_versions(db, audit.id)
    _create_checklist_version(
        audit=audit,
        current_user=current_user,
        db=db,
        request=request,
        file=file,
        lifecycle_status="COMMITTED" if existing else "SOURCE",
        source_type="COMPATIBILITY_SAVE",
        fillable="UNKNOWN",
        field_count=None,
    )
    db.refresh(audit)
    return QualityAuditWorkspaceV2Out(audit=_serialize_audit(audit, db), workflow=build_workflow_v2(db, audit))


@_extension_router.post("/audits/{audit_id}/lifecycle/start", response_model=QualityAuditWorkspaceV2Out)
def start_audit_lifecycle(
    audit_id: UUID,
    request: Request,
    payload: QualityAuditStageTransitionIn = Body(default_factory=QualityAuditStageTransitionIn),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_mutable_audit(current_user, audit)
    workflow = build_workflow_v2(db, audit)
    war = next(stage for stage in workflow.stages if stage.id == "war-room")
    if war.blockers:
        raise HTTPException(status_code=409, detail={"message": "War room is not ready.", "blockers": war.blockers})
    if not audit.actual_start:
        audit.actual_start = date.today()
    audit.status = "IN_PROGRESS"
    _record_stage(db, audit=audit, stage_id="war-room", state="COMPLETE", current_user=current_user, note=payload.note, metadata=payload.metadata)
    _record_stage(db, audit=audit, stage_id="checklist", state="IN_PROGRESS", current_user=current_user, note="Fieldwork checklist opened.")
    _log(db, request, audit=audit, current_user=current_user, action="start_audit_lifecycle", after={"actual_start": audit.actual_start.isoformat(), "note": payload.note}, critical=True)
    db.commit()
    db.refresh(audit)
    return QualityAuditWorkspaceV2Out(audit=_serialize_audit(audit, db), workflow=build_workflow_v2(db, audit))


@_extension_router.post("/audits/{audit_id}/lifecycle/checklist/complete", response_model=QualityAuditWorkspaceV2Out)
def complete_checklist_lifecycle(
    audit_id: UUID,
    request: Request,
    payload: QualityAuditStageTransitionIn = Body(default_factory=QualityAuditStageTransitionIn),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_mutable_audit(current_user, audit)
    if not audit.actual_start:
        raise HTTPException(status_code=409, detail="Start the audit and record the opening brief before completing the checklist.")
    versions = _latest_checklist_versions(db, audit.id)
    items = db.query(models.QualityAuditChecklistItem).filter(models.QualityAuditChecklistItem.audit_id == audit.id).all()
    committed = next((row for row in versions if row.lifecycle_status == "COMMITTED"), None)
    if not committed and not items:
        raise HTTPException(status_code=409, detail="A committed checklist version or portal checklist is required.")
    pending = [row for row in items if row.response_status == "PENDING"]
    if pending:
        raise HTTPException(status_code=409, detail=f"{len(pending)} checklist item(s) remain pending.")
    _record_stage(db, audit=audit, stage_id="checklist", state="COMPLETE", current_user=current_user, note=payload.note, metadata={
        **(payload.metadata or {}),
        "committed_version_id": str(committed.id) if committed else None,
        "portal_item_count": len(items),
    })
    _record_stage(db, audit=audit, stage_id="findings", state="IN_PROGRESS", current_user=current_user, note="Checklist completed; fieldwork findings remain open.")
    _log(db, request, audit=audit, current_user=current_user, action="complete_audit_checklist", after={"portal_items": len(items), "version_id": str(committed.id) if committed else None}, critical=True)
    db.commit()
    return QualityAuditWorkspaceV2Out(audit=_serialize_audit(audit, db), workflow=build_workflow_v2(db, audit))


@_extension_router.post("/audits/{audit_id}/lifecycle/fieldwork/complete", response_model=QualityAuditWorkspaceV2Out)
def complete_fieldwork_lifecycle(
    audit_id: UUID,
    request: Request,
    payload: QualityAuditStageTransitionIn = Body(default_factory=QualityAuditStageTransitionIn),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_mutable_audit(current_user, audit)
    workflow = build_workflow_v2(db, audit)
    checklist = next(stage for stage in workflow.stages if stage.id == "checklist")
    if not checklist.complete:
        raise HTTPException(status_code=409, detail="Complete the controlled checklist before closing fieldwork.")
    unresolved_items = db.query(models.QualityAuditChecklistItem).filter(
        models.QualityAuditChecklistItem.audit_id == audit.id,
        models.QualityAuditChecklistItem.response_status == "NON_CONFORMING",
        models.QualityAuditChecklistItem.finding_id.is_(None),
    ).count()
    if unresolved_items:
        raise HTTPException(status_code=409, detail=f"{unresolved_items} non-conforming checklist item(s) are not linked to a finding.")
    audit.actual_end = date.today()
    _record_stage(db, audit=audit, stage_id="findings", state="COMPLETE", current_user=current_user, note=payload.note, metadata=payload.metadata)
    _log(db, request, audit=audit, current_user=current_user, action="complete_audit_fieldwork", after={"actual_end": audit.actual_end.isoformat(), "note": payload.note}, critical=True)
    db.commit()
    db.refresh(audit)
    return QualityAuditWorkspaceV2Out(audit=_serialize_audit(audit, db), workflow=build_workflow_v2(db, audit))


@_extension_router.post("/audits/{audit_id}/evidence/reviews", response_model=QualityAuditEvidenceReviewOut)
def review_audit_evidence(
    audit_id: UUID,
    request: Request,
    payload: QualityAuditEvidenceReviewIn,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_mutable_audit(current_user, audit)
    row = db.query(QualityAuditEvidenceReview).filter(
        QualityAuditEvidenceReview.audit_id == audit.id,
        QualityAuditEvidenceReview.entity_type == payload.entity_type,
        QualityAuditEvidenceReview.entity_id == payload.entity_id,
    ).first()
    now = _utcnow()
    if not row:
        row = QualityAuditEvidenceReview(
            amo_id=audit.amo_id,
            audit_id=audit.id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
        )
        db.add(row)
    row.status = payload.status
    row.note = payload.note
    row.reviewed_by_user_id = current_user.id
    row.reviewed_at = now if payload.status != "PENDING" else None
    _log(db, request, audit=audit, current_user=current_user, action="review_audit_evidence", after=payload.model_dump(), critical=payload.status in {"ACCEPTED", "REJECTED"})
    db.commit()
    db.refresh(row)
    return row


def _create_report_draft(
    *,
    audit: models.QMSAudit,
    current_user: account_models.User,
    db: Session,
    request: Request,
    file: UploadFile,
) -> QualityAuditReportDocument:
    _require_mutable_audit(current_user, audit)
    path, name, mime, size, digest = _write_upload(
        upload=file,
        target_dir=AUDIT_REPORT_DIR / str(audit.id),
        max_bytes=MAX_AUDIT_REPORT_BYTES,
        allowed_extensions=REPORT_ALLOWED_EXTENSIONS,
        allowed_mimes=REPORT_ALLOWED_MIME_TYPES,
        validate_checklist=False,
    )
    versions = _latest_report_versions(db, audit.id)
    parent = versions[0] if versions else None
    row = QualityAuditReportDocument(
        amo_id=audit.amo_id,
        audit_id=audit.id,
        version_number=_next_version(db, QualityAuditReportDocument, audit.id),
        parent_version_id=parent.id if parent else None,
        filename=name,
        storage_key=str(path),
        content_type=mime or mimetypes.guess_type(name)[0] or "application/pdf",
        size_bytes=size,
        sha256=digest,
        lifecycle_status="DRAFT",
        uploaded_by_user_id=current_user.id,
    )
    db.add(row)
    _log(db, request, audit=audit, current_user=current_user, action="upload_report_draft", after={"version_number": row.version_number, "filename": name, "size_bytes": size, "sha256": digest})
    db.commit()
    db.refresh(row)
    return row


@_extension_router.post("/audits/{audit_id}/documents/report/draft", response_model=QualityAuditDocumentOut)
def upload_report_draft(
    audit_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    return _document_out(_create_report_draft(audit=audit, current_user=current_user, db=db, request=request, file=file), kind="report")


@_extension_router.post("/audits/{audit_id}/report", response_model=QualityAuditWorkspaceV2Out)
def legacy_upload_report_as_draft(
    audit_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _create_report_draft(audit=audit, current_user=current_user, db=db, request=request, file=file)
    db.refresh(audit)
    return QualityAuditWorkspaceV2Out(audit=_serialize_audit(audit, db), workflow=build_workflow_v2(db, audit))


@_extension_router.post("/audits/{audit_id}/documents/report/issue", response_model=QualityAuditDocumentOut)
def issue_report_version(
    audit_id: UUID,
    request: Request,
    payload: QualityAuditReportIssueIn,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_mutable_audit(current_user, audit)
    workflow = build_workflow_v2(db, audit)
    blockers = []
    for stage_id in ("cars", "evidence"):
        stage = next(row for row in workflow.stages if row.id == stage_id)
        if not stage.complete:
            blockers.extend(stage.blockers or [f"{stage.label} is not complete."])
    if blockers:
        raise HTTPException(status_code=409, detail={"message": "Report cannot be issued.", "blockers": blockers})
    row = db.query(QualityAuditReportDocument).filter(
        QualityAuditReportDocument.id == payload.version_id,
        QualityAuditReportDocument.audit_id == audit.id,
        QualityAuditReportDocument.amo_id == audit.amo_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Report draft not found.")
    if row.lifecycle_status != "DRAFT":
        raise HTTPException(status_code=409, detail="Only a report draft can be issued.")
    now = _utcnow()
    for previous in _latest_report_versions(db, audit.id):
        if previous.id != row.id and previous.lifecycle_status == "ISSUED":
            previous.lifecycle_status = "SUPERSEDED"
            previous.superseded_at = now
    row.lifecycle_status = "ISSUED"
    row.issue_label = payload.issue_label
    row.issued_by_user_id = current_user.id
    row.issued_at = now
    audit.report_file_ref = row.storage_key
    tracker = db.query(models.QualityAuditReportTracker).filter(models.QualityAuditReportTracker.audit_id == audit.id).first()
    if tracker:
        tracker.report_submitted_at = now
        tracker.status = "SUBMITTED"
        tracker.next_reminder_at = None
    _record_stage(db, audit=audit, stage_id="report", state="COMPLETE", current_user=current_user, note=payload.note, metadata={"version_id": str(row.id), "issue_label": payload.issue_label})
    _log(db, request, audit=audit, current_user=current_user, action="issue_audit_report", after={"version_id": str(row.id), "issue_label": payload.issue_label, "sha256": row.sha256}, critical=True)
    db.commit()
    db.refresh(row)
    return _document_out(row, kind="report")


@_extension_router.post("/audits/{audit_id}/lifecycle/closeout", response_model=QualityAuditWorkspaceV2Out)
def close_audit_lifecycle(
    audit_id: UUID,
    request: Request,
    payload: QualityAuditStageTransitionIn = Body(default_factory=QualityAuditStageTransitionIn),
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    audit = _get_audit_for_amo(db, amo_id=_current_amo_id(current_user), audit_id=audit_id)
    _require_mutable_audit(current_user, audit)
    workflow = build_workflow_v2(db, audit)
    closeout = next(stage for stage in workflow.stages if stage.id == "closeout")
    if closeout.state != "READY":
        raise HTTPException(status_code=409, detail={"message": "Audit is not ready for closeout.", "blockers": closeout.blockers})
    archive = models.QualityArchivePackage(
        amo_id=audit.amo_id,
        audit_id=audit.id,
        package_ref=f"{audit.audit_ref}-CLOSEOUT-{_utcnow().strftime('%Y%m%d%H%M%S')}",
        status="LOCKED",
        file_ref=None,
        metrics_snapshot_json=json.dumps(workflow.model_dump(mode="json"), default=str),
        generated_by_user_id=current_user.id,
    )
    db.add(archive)
    audit.status = "CLOSED"
    _record_stage(db, audit=audit, stage_id="closeout", state="COMPLETE", current_user=current_user, note=payload.note, metadata={"archive_package_ref": archive.package_ref, **(payload.metadata or {})})
    _log(db, request, audit=audit, current_user=current_user, action="close_audit_lifecycle", after={"archive_package_ref": archive.package_ref, "note": payload.note}, critical=True)
    db.commit()
    db.refresh(audit)
    return QualityAuditWorkspaceV2Out(audit=_serialize_audit(audit, db), workflow=build_workflow_v2(db, audit))


_REPLACED_ROUTES = {
    ("/quality/audits/{audit_id}/workspace", "GET"),
    ("/quality/audits/{audit_id}/workflow-check", "GET"),
    ("/quality/audits/{audit_id}/checklist", "POST"),
    ("/quality/audits/{audit_id}/report", "POST"),
}
router.routes[:] = [
    route
    for route in router.routes
    if not any(
        str(getattr(route, "path", "")) == path and method in (getattr(route, "methods", None) or set())
        for path, method in _REPLACED_ROUTES
    )
]
router.routes[0:0] = list(_extension_router.routes)
