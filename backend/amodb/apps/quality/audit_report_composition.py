from __future__ import annotations

import hashlib
import html
import json
import os
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors
from sqlalchemy.orm import Session

from . import models
from .audit_checklist_execution_models import QualityAuditChecklistExecutionGovernance
from .audit_occurrence_completion_models import QualityAuditClosingNarrative, QualityAuditMeeting
from .audit_report_composition_models import QualityAuditReportArtifact


TEMPLATE_VERSION = "QMS_AUDIT_REPORT_V2"
RENDERER_VERSION = "REPORTLAB_V1"
_STORAGE_ROOT = Path(os.getenv("QMS_GENERATED_AUDIT_REPORT_DIR", "uploads/qms-generated-audit-reports")).resolve()


@dataclass(frozen=True)
class GeneratedAuditReport:
    artifact: QualityAuditReportArtifact
    absolute_path: Path
    snapshot: dict[str, Any]


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        return str(enum_value)
    return value


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(_json_value(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _storage_root() -> Path:
    _STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    return _STORAGE_ROOT


def resolve_report_artifact(storage_ref: str) -> Path:
    root = _storage_root()
    target = (root / str(storage_ref)).resolve()
    if root != target and root not in target.parents:
        raise HTTPException(status_code=404, detail="Generated audit report not found.")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Generated audit report not found.")
    return target


def _audit_or_404(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> models.QMSAudit:
    audit = db.query(models.QMSAudit).filter(
        models.QMSAudit.amo_id == amo_id,
        models.QMSAudit.id == audit_id,
        models.QMSAudit.deleted_at.is_(None),
    ).first()
    if audit is None:
        raise HTTPException(status_code=404, detail="Audit not found.")
    return audit


def build_report_snapshot(db: Session, *, amo_id: str, audit_id: uuid.UUID) -> dict[str, Any]:
    audit = _audit_or_404(db, amo_id=amo_id, audit_id=audit_id)
    checklist = db.query(QualityAuditChecklistExecutionGovernance).filter(
        QualityAuditChecklistExecutionGovernance.amo_id == amo_id,
        QualityAuditChecklistExecutionGovernance.audit_id == audit_id,
    ).order_by(QualityAuditChecklistExecutionGovernance.created_at.asc()).all()
    checklist_item_ids = [row.checklist_item_id for row in checklist]
    checklist_items = db.query(models.QualityAuditChecklistItem).filter(
        models.QualityAuditChecklistItem.amo_id == amo_id,
        models.QualityAuditChecklistItem.audit_id == audit_id,
        models.QualityAuditChecklistItem.id.in_(checklist_item_ids),
    ).all() if checklist_item_ids else []
    checklist_item_by_id = {row.id: row for row in checklist_items}

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

    def checklist_snapshot(row: QualityAuditChecklistExecutionGovernance) -> dict[str, Any]:
        item = checklist_item_by_id.get(row.checklist_item_id)
        return {
            "checklist_item_id": row.checklist_item_id,
            "section": item.section if item else None,
            "checklist_ref": item.checklist_ref if item else None,
            "requirement_ref": item.requirement_ref if item else None,
            "prompt": item.prompt if item else None,
            "sort_order": item.sort_order if item else None,
            "canonical_response_status": row.canonical_response_status,
            "auditor_notes": row.auditor_notes,
            "objective_evidence": row.objective_evidence,
            "evidence_references": row.evidence_references_json or [],
        }

    return _json_value({
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
        "checklist": [checklist_snapshot(row) for row in checklist],
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


def _text(value: Any, fallback: str = "—") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def _p(value: Any, style) -> Paragraph:
    return Paragraph(html.escape(_text(value)), style)


def _render_pdf(snapshot: dict[str, Any], destination: Path) -> None:
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="QmsBody", parent=styles["BodyText"], fontSize=9, leading=12, spaceAfter=4))
    styles.add(ParagraphStyle(name="QmsSmall", parent=styles["BodyText"], fontSize=7.5, leading=10, textColor=colors.HexColor("#475569")))
    styles.add(ParagraphStyle(name="QmsSection", parent=styles["Heading2"], fontSize=13, leading=16, spaceBefore=8, spaceAfter=6))
    styles.add(ParagraphStyle(name="QmsTitle", parent=styles["Title"], fontSize=17, leading=20, alignment=TA_LEFT, spaceAfter=8))

    audit = snapshot["audit"]
    narrative = snapshot.get("closing_narrative") or {}
    meetings = snapshot.get("meetings") or []
    checklist = snapshot["checklist"]
    findings = snapshot["findings"]
    cars = snapshot["cars"]
    counts: dict[str, int] = {}
    for row in checklist:
        key = _text(row.get("canonical_response_status"), "NOT_VERIFIED")
        counts[key] = counts.get(key, 0) + 1

    story: list[Any] = [
        _p("QUALITY AUDIT REPORT", styles["QmsTitle"]),
        _p(f"{_text(audit.get('audit_ref'))} · {_text(audit.get('title'))}", styles["Heading2"]),
        Spacer(1, 3 * mm),
    ]
    summary_rows = [
        ["Audit reference", _text(audit.get("audit_ref")), "Audit type", _text(audit.get("kind"))],
        ["Auditee", _text(audit.get("auditee")), "Status", _text(audit.get("status"))],
        ["Planned start", _text(audit.get("planned_start")), "Planned end", _text(audit.get("planned_end"))],
        ["Actual start", _text(audit.get("actual_start")), "Actual end", _text(audit.get("actual_end"))],
    ]
    summary_table = Table(summary_rows, colWidths=[28 * mm, 58 * mm, 28 * mm, 58 * mm])
    summary_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F1F5F9")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([summary_table, Spacer(1, 4 * mm)])

    story.extend([
        _p("Scope and criteria", styles["QmsSection"]),
        _p(f"Scope: {_text(audit.get('scope'))}", styles["QmsBody"]),
        _p(f"Criteria: {_text(audit.get('criteria'))}", styles["QmsBody"]),
        _p("Management summary", styles["QmsSection"]),
        _p(narrative.get("management_summary"), styles["QmsBody"]),
        _p("Audit conclusion", styles["QmsSection"]),
        _p(narrative.get("conclusion"), styles["QmsBody"]),
        _p("Positive practices", styles["QmsSection"]),
        _p(narrative.get("positive_practices"), styles["QmsBody"]),
    ])

    if meetings:
        story.append(_p("Audit meetings", styles["QmsSection"]))
        meeting_rows = [["Type", "Start", "End", "Location / link"]]
        for row in meetings:
            location = row.get("location") or row.get("conference_url") or "—"
            meeting_rows.append([
                _p(row.get("meeting_type"), styles["QmsSmall"]),
                _p(row.get("scheduled_start"), styles["QmsSmall"]),
                _p(row.get("scheduled_end"), styles["QmsSmall"]),
                _p(location, styles["QmsSmall"]),
            ])
        meeting_table = Table(meeting_rows, colWidths=[28 * mm, 48 * mm, 48 * mm, 46 * mm], repeatRows=1)
        meeting_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(meeting_table)

    story.extend([
        _p("Fieldwork summary", styles["QmsSection"]),
        _p(
            f"Checklist: {len(checklist)} item(s) · Compliant {counts.get('COMPLIANT', 0)} · "
            f"Noncompliant {counts.get('NONCOMPLIANT', 0)} · Observations {counts.get('OBSERVATION', 0)} · "
            f"Not applicable {counts.get('NOT_APPLICABLE', 0)} · Not verified {counts.get('NOT_VERIFIED', 0)}.",
            styles["QmsBody"],
        ),
        _p(f"Findings: {len(findings)} · Corrective action requests: {len(cars)}.", styles["QmsBody"]),
        _p("Findings", styles["QmsSection"]),
    ])

    if findings:
        finding_rows = [["Reference", "Level", "Requirement", "Finding"]]
        for row in findings:
            finding_rows.append([
                _p(row.get("finding_ref") or "Finding", styles["QmsSmall"]),
                _p(row.get("level") or row.get("severity") or "—", styles["QmsSmall"]),
                _p(row.get("requirement_ref"), styles["QmsSmall"]),
                _p(row.get("description"), styles["QmsSmall"]),
            ])
        table = Table(finding_rows, colWidths=[30 * mm, 26 * mm, 38 * mm, 76 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)
    else:
        story.append(_p("No findings were recorded in the frozen report snapshot.", styles["QmsBody"]))

    story.extend([PageBreak(), _p("Checklist execution", styles["QmsSection"])])
    if checklist:
        checklist_rows = [["#", "Checklist / requirement", "Question", "Response", "Evidence / auditor note"]]
        for index, row in enumerate(checklist, 1):
            references = [
                str(value).strip()
                for value in (row.get("section"), row.get("checklist_ref"), row.get("requirement_ref"))
                if str(value or "").strip()
            ]
            evidence_parts = [
                str(value).strip()
                for value in (row.get("objective_evidence"), row.get("auditor_notes"))
                if str(value or "").strip()
            ]
            checklist_rows.append([
                str(index),
                _p(" · ".join(references) or "—", styles["QmsSmall"]),
                _p(row.get("prompt"), styles["QmsSmall"]),
                _p(row.get("canonical_response_status"), styles["QmsSmall"]),
                _p(" | ".join(evidence_parts) or "—", styles["QmsSmall"]),
            ])
        table = Table(checklist_rows, colWidths=[10 * mm, 36 * mm, 58 * mm, 28 * mm, 46 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(table)
    else:
        story.append(_p("No governed checklist execution rows were found.", styles["QmsBody"]))

    story.extend([
        Spacer(1, 5 * mm),
        _p("Controlled report note", styles["QmsSection"]),
        _p(
            "This PDF was generated from an immutable hash of authoritative audit data, the saved closing narrative and occurrence meeting records. Formal review, approval, issue and signature remain governed by the report lifecycle; generation alone does not issue the audit report.",
            styles["QmsSmall"],
        ),
    ])

    document = SimpleDocTemplate(
        str(destination), pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=15 * mm, bottomMargin=15 * mm,
        title=f"{_text(audit.get('audit_ref'))} Audit Report", author="AMO Portal QMS",
    )
    document.build(story)


def generate_report_artifact(
    db: Session,
    *,
    amo_id: str,
    audit_id: uuid.UUID,
    actor_user_id: str | None,
) -> GeneratedAuditReport:
    snapshot = build_report_snapshot(db, amo_id=amo_id, audit_id=audit_id)
    audit = snapshot["audit"]
    if not audit.get("actual_end"):
        raise HTTPException(status_code=409, detail="Fieldwork must be formally completed before the closing report snapshot is generated.")
    pending = sum(1 for row in snapshot["checklist"] if row.get("canonical_response_status") == "NOT_VERIFIED")
    if pending:
        raise HTTPException(status_code=409, detail=f"{pending} checklist item(s) remain NOT_VERIFIED.")
    narrative = snapshot.get("closing_narrative") or {}
    missing_narrative = [label for key, label in (
        ("management_summary", "management summary"),
        ("conclusion", "audit conclusion"),
        ("positive_practices", "positive-practices statement"),
    ) if not str(narrative.get(key) or "").strip()]
    if missing_narrative:
        raise HTTPException(status_code=409, detail=f"Complete the governed closing narrative before report generation: {', '.join(missing_narrative)}.")

    source_hash = _canonical_hash(snapshot)
    root = _storage_root()
    relative_dir = Path(str(amo_id)) / str(audit_id)
    destination_dir = (root / relative_dir).resolve()
    if root != destination_dir and root not in destination_dir.parents:
        raise HTTPException(status_code=400, detail="Invalid generated report storage target.")
    destination_dir.mkdir(parents=True, exist_ok=True)

    safe_ref = "".join(character if character.isalnum() or character in "-_" else "-" for character in _text(audit.get("audit_ref"), "audit"))[:100]
    filename = f"{safe_ref}-closing-report-{source_hash[:12]}.pdf"
    destination = destination_dir / filename
    _render_pdf(snapshot, destination)
    content = destination.read_bytes()
    artifact_hash = hashlib.sha256(content).hexdigest()

    artifact = QualityAuditReportArtifact(
        amo_id=amo_id,
        audit_id=audit_id,
        source_snapshot_hash=source_hash,
        template_version=TEMPLATE_VERSION,
        renderer_version=RENDERER_VERSION,
        filename=filename,
        content_type="application/pdf",
        size_bytes=len(content),
        sha256=artifact_hash,
        storage_ref=(relative_dir / filename).as_posix(),
        generated_by_user_id=actor_user_id,
    )
    db.add(artifact)
    db.flush()
    return GeneratedAuditReport(artifact=artifact, absolute_path=destination, snapshot=snapshot)
