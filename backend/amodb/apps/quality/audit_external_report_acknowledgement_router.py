from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from amodb.database import get_db

from .audit_external_access_models import QualityAuditAccessEvent, QualityAuditAccessGrant
from .audit_external_access_router import _GUEST_COOKIE, _active_grant, _append_access_event
from .audit_report_governance_models import QualityAuditReportRevision
from .audit_report_governance_router import _safe_report_path, _sha256
from .router import public_router


_public_extension = APIRouter(prefix="/quality", tags=["Quality / External Audit Report"])
_ACK_STATEMENT = "I acknowledge receipt of this issued audit report revision. This acknowledgement records receipt and does not waive any response, corrective-action, review or appeal rights."


def _latest_issued_report(db: Session, grant: QualityAuditAccessGrant) -> QualityAuditReportRevision | None:
    return (
        db.query(QualityAuditReportRevision)
        .filter(
            QualityAuditReportRevision.amo_id == grant.amo_id,
            QualityAuditReportRevision.audit_id == grant.audit_id,
            QualityAuditReportRevision.status == "ISSUED",
        )
        .order_by(QualityAuditReportRevision.revision_no.desc(), QualityAuditReportRevision.issued_at.desc())
        .first()
    )


def _require_auditee(grant: QualityAuditAccessGrant, permission: str) -> None:
    participant = grant.participant
    if participant is None or participant.participant_type != "AUDITEE_GUEST":
        raise HTTPException(status_code=403, detail="Issued audit report access is reserved for the auditee workspace.")
    if permission not in set(grant.scope_json or []):
        raise HTTPException(status_code=403, detail="This audit access does not permit the requested report action.")


def _ack_reason(report: QualityAuditReportRevision) -> str:
    return f"Issued audit report revision {report.id} (SHA-256 {report.sha256}) acknowledged as received."


def _existing_acknowledgement(
    db: Session,
    grant: QualityAuditAccessGrant,
    report: QualityAuditReportRevision,
) -> QualityAuditAccessEvent | None:
    return (
        db.query(QualityAuditAccessEvent)
        .filter(
            QualityAuditAccessEvent.amo_id == grant.amo_id,
            QualityAuditAccessEvent.audit_id == grant.audit_id,
            QualityAuditAccessEvent.participant_id == grant.participant_id,
            QualityAuditAccessEvent.event_type == "ACKNOWLEDGED",
            QualityAuditAccessEvent.reason == _ack_reason(report),
        )
        .order_by(QualityAuditAccessEvent.created_at.desc())
        .first()
    )


def _status_payload(db: Session, grant: QualityAuditAccessGrant) -> dict[str, Any]:
    report = _latest_issued_report(db, grant)
    if report is None:
        return {"available": False, "report": None, "acknowledgement_statement": _ACK_STATEMENT}
    acknowledgement = _existing_acknowledgement(db, grant, report)
    return {
        "available": True,
        "report": {
            "id": str(report.id),
            "revision_no": int(report.revision_no),
            "filename": report.filename,
            "content_type": report.content_type,
            "size_bytes": int(report.size_bytes or 0),
            "sha256": report.sha256,
            "issued_at": report.issued_at.isoformat() if report.issued_at else None,
            "acknowledged_at": acknowledgement.created_at.isoformat() if acknowledgement else None,
        },
        "acknowledgement_statement": _ACK_STATEMENT,
    }


@_public_extension.get("/audit-access/issued-report")
def get_issued_report_status(
    db: Session = Depends(get_db),
    amo_qms_audit_guest: str | None = Cookie(default=None, alias=_GUEST_COOKIE),
) -> dict[str, Any]:
    if not amo_qms_audit_guest:
        raise HTTPException(status_code=401, detail="Audit access session is required.")
    grant = _active_grant(db, amo_qms_audit_guest)
    _require_auditee(grant, "audit:read_summary")
    return _status_payload(db, grant)


@_public_extension.get("/audit-access/issued-report/download")
def download_issued_report(
    db: Session = Depends(get_db),
    amo_qms_audit_guest: str | None = Cookie(default=None, alias=_GUEST_COOKIE),
) -> FileResponse:
    if not amo_qms_audit_guest:
        raise HTTPException(status_code=401, detail="Audit access session is required.")
    grant = _active_grant(db, amo_qms_audit_guest)
    _require_auditee(grant, "audit:read_summary")
    report = _latest_issued_report(db, grant)
    if report is None:
        raise HTTPException(status_code=404, detail="No issued audit report is available for this audit.")

    path = _safe_report_path(report.file_ref)
    if _sha256(path) != report.sha256:
        raise HTTPException(status_code=409, detail="The issued audit report failed integrity verification.")

    _append_access_event(db, grant, "READ", f"Issued audit report revision {report.id} downloaded.")
    db.commit()
    return FileResponse(
        path=path,
        media_type=report.content_type or "application/pdf",
        filename=report.filename or f"audit-report-revision-{report.revision_no}.pdf",
    )


@_public_extension.post("/audit-access/issued-report/acknowledge")
def acknowledge_issued_report(
    db: Session = Depends(get_db),
    amo_qms_audit_guest: str | None = Cookie(default=None, alias=_GUEST_COOKIE),
) -> dict[str, Any]:
    if not amo_qms_audit_guest:
        raise HTTPException(status_code=401, detail="Audit access session is required.")
    grant = _active_grant(db, amo_qms_audit_guest)
    _require_auditee(grant, "audit:acknowledge")
    report = _latest_issued_report(db, grant)
    if report is None:
        raise HTTPException(status_code=404, detail="No issued audit report is available for acknowledgement.")

    existing = _existing_acknowledgement(db, grant, report)
    if existing is None:
        _append_access_event(db, grant, "ACKNOWLEDGED", _ack_reason(report))
        db.commit()
        existing = _existing_acknowledgement(db, grant, report)
    if existing is None:
        raise HTTPException(status_code=500, detail="The issued report acknowledgement could not be recorded.")

    return {
        "report_revision_id": str(report.id),
        "report_sha256": report.sha256,
        "acknowledged_at": existing.created_at.isoformat(),
        "acknowledgement_statement": _ACK_STATEMENT,
    }


# Side-effect registration mirrors the existing external-audit public extension.
# These routes remain session/token scoped and never expose internal report drafts.
public_router.routes[0:0] = list(_public_extension.routes)
