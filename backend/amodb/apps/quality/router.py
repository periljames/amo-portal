# backend/amodb/apps/quality/router.py
from __future__ import annotations

from datetime import date
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.database import get_db

from . import models
from .schemas import (
    QMSDashboardOut,
    QMSDocumentCreate, QMSDocumentUpdate, QMSDocumentOut,
    QMSDocumentRevisionCreate, QMSDocumentRevisionOut, QMSPublishRevision,
    QMSDistributionCreate, QMSDistributionOut,
    QMSChangeRequestCreate, QMSChangeRequestUpdate, QMSChangeRequestOut,
    QMSAuditCreate, QMSAuditUpdate, QMSAuditOut,
    QMSFindingCreate, QMSFindingOut,
    QMSCAPUpsert, QMSCAPOut,
)
from .enums import QMSDomain, QMSAuditStatus
from .service import get_dashboard, normalize_finding_level, compute_target_close_date

router = APIRouter(prefix="/quality", tags=["Quality / QMS"])


def get_actor() -> Optional[str]:
    """
    Replace with your JWT dependency.
    Return a stable user id string (e.g., UUID or int as str).
    """
    return None


@router.get("/qms/dashboard", response_model=QMSDashboardOut)
def qms_dashboard(
    db: Session = Depends(get_db),
    domain: Optional[QMSDomain] = Query(default=None),
):
    return get_dashboard(db, domain=domain)


# -----------------------------
# Documents
# -----------------------------
@router.post("/qms/documents", response_model=QMSDocumentOut, status_code=status.HTTP_201_CREATED)
def create_document(payload: QMSDocumentCreate, db: Session = Depends(get_db)):
    doc = models.QMSDocument(
        domain=payload.domain,
        doc_type=payload.doc_type,
        doc_code=payload.doc_code.strip(),
        title=payload.title.strip(),
        description=payload.description,
        restricted_access=payload.restricted_access,
        created_by_user_id=get_actor(),
        updated_by_user_id=get_actor(),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/qms/documents", response_model=List[QMSDocumentOut])
def list_documents(
    db: Session = Depends(get_db),
    domain: Optional[QMSDomain] = None,
    doc_type: Optional[models.QMSDocType] = None,
    status_: Optional[models.QMSDocStatus] = None,
    q: Optional[str] = None,
):
    qs = db.query(models.QMSDocument)

    if domain:
        qs = qs.filter(models.QMSDocument.domain == domain)
    if doc_type:
        qs = qs.filter(models.QMSDocument.doc_type == doc_type)
    if status_:
        qs = qs.filter(models.QMSDocument.status == status_)
    if q:
        like = f"%{q.strip()}%"
        qs = qs.filter((models.QMSDocument.title.ilike(like)) | (models.QMSDocument.doc_code.ilike(like)))

    return qs.order_by(models.QMSDocument.updated_at.desc()).all()


@router.get("/qms/documents/{doc_id}", response_model=QMSDocumentOut)
def get_document(doc_id: UUID, db: Session = Depends(get_db)):
    doc = db.query(models.QMSDocument).filter(models.QMSDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.patch("/qms/documents/{doc_id}", response_model=QMSDocumentOut)
def update_document(doc_id: UUID, payload: QMSDocumentUpdate, db: Session = Depends(get_db)):
    doc = db.query(models.QMSDocument).filter(models.QMSDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if payload.title is not None:
        doc.title = payload.title.strip()
    if payload.description is not None:
        doc.description = payload.description
    if payload.restricted_access is not None:
        doc.restricted_access = payload.restricted_access
    if payload.status is not None:
        doc.status = payload.status

    doc.updated_by_user_id = get_actor()
    db.commit()
    db.refresh(doc)
    return doc


@router.post("/qms/documents/{doc_id}/revisions", response_model=QMSDocumentRevisionOut, status_code=status.HTTP_201_CREATED)
def add_revision(doc_id: UUID, payload: QMSDocumentRevisionCreate, db: Session = Depends(get_db)):
    doc = db.query(models.QMSDocument).filter(models.QMSDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if payload.is_temporary and not payload.temporary_expires_on:
        raise HTTPException(status_code=400, detail="temporary_expires_on is required for temporary revisions")

    rev = models.QMSDocumentRevision(
        document_id=doc.id,
        issue_no=payload.issue_no,
        rev_no=payload.rev_no,
        issued_date=payload.issued_date,
        entered_date=payload.entered_date,
        pages_affected=payload.pages_affected,
        tracking_serial=payload.tracking_serial,
        change_summary=payload.change_summary,
        is_temporary=payload.is_temporary,
        temporary_expires_on=payload.temporary_expires_on,
        file_ref=payload.file_ref,
        approved_by_authority=payload.approved_by_authority,
        authority_ref=payload.authority_ref,
        created_by_user_id=get_actor(),
    )
    db.add(rev)
    db.commit()
    db.refresh(rev)
    return rev


@router.get("/qms/documents/{doc_id}/revisions", response_model=List[QMSDocumentRevisionOut])
def list_revisions(doc_id: UUID, db: Session = Depends(get_db)):
    return (
        db.query(models.QMSDocumentRevision)
        .filter(models.QMSDocumentRevision.document_id == doc_id)
        .order_by(models.QMSDocumentRevision.created_at.desc())
        .all()
    )


@router.post("/qms/documents/{doc_id}/publish/{revision_id}", response_model=QMSDocumentOut)
def publish_revision(doc_id: UUID, revision_id: UUID, payload: QMSPublishRevision, db: Session = Depends(get_db)):
    doc = db.query(models.QMSDocument).filter(models.QMSDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    rev = (
        db.query(models.QMSDocumentRevision)
        .filter(models.QMSDocumentRevision.id == revision_id, models.QMSDocumentRevision.document_id == doc_id)
        .first()
    )
    if not rev:
        raise HTTPException(status_code=404, detail="Revision not found")

    doc.current_issue_no = rev.issue_no
    doc.current_rev_no = rev.rev_no
    doc.effective_date = payload.effective_date
    doc.current_file_ref = payload.current_file_ref or rev.file_ref
    doc.status = models.QMSDocStatus.ACTIVE
    doc.updated_by_user_id = get_actor()

    db.commit()
    db.refresh(doc)
    return doc


@router.post("/qms/distributions", response_model=QMSDistributionOut, status_code=status.HTTP_201_CREATED)
def create_distribution(payload: QMSDistributionCreate, db: Session = Depends(get_db)):
    doc = db.query(models.QMSDocument).filter(models.QMSDocument.id == payload.document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    dist = models.QMSDocumentDistribution(
        document_id=payload.document_id,
        revision_id=payload.revision_id,
        copy_number=payload.copy_number,
        holder_label=payload.holder_label.strip(),
        holder_user_id=payload.holder_user_id,
        dist_format=payload.dist_format,
        requires_ack=payload.requires_ack,
    )
    db.add(dist)
    db.commit()
    db.refresh(dist)
    return dist


@router.get("/qms/distributions", response_model=List[QMSDistributionOut])
def list_distributions(
    db: Session = Depends(get_db),
    document_id: Optional[UUID] = None,
    holder_user_id: Optional[str] = None,
    outstanding_only: bool = False,
):
    qs = db.query(models.QMSDocumentDistribution)
    if document_id:
        qs = qs.filter(models.QMSDocumentDistribution.document_id == document_id)
    if holder_user_id:
        qs = qs.filter(models.QMSDocumentDistribution.holder_user_id == holder_user_id)
    if outstanding_only:
        qs = qs.filter(
            models.QMSDocumentDistribution.requires_ack.is_(True),
            models.QMSDocumentDistribution.acked_at.is_(None),
        )
    return qs.order_by(models.QMSDocumentDistribution.distributed_at.desc()).all()


@router.post("/qms/distributions/{dist_id}/ack", response_model=QMSDistributionOut)
def acknowledge_distribution(dist_id: UUID, db: Session = Depends(get_db)):
    dist = db.query(models.QMSDocumentDistribution).filter(models.QMSDocumentDistribution.id == dist_id).first()
    if not dist:
        raise HTTPException(status_code=404, detail="Distribution record not found")
    if not dist.requires_ack:
        return dist
    if dist.acked_at:
        return dist

    dist.acked_at = func.now()
    dist.acked_by_user_id = get_actor()
    db.commit()
    db.refresh(dist)
    return dist


# -----------------------------
# Manual Change Requests
# -----------------------------
@router.post("/qms/change-requests", response_model=QMSChangeRequestOut, status_code=status.HTTP_201_CREATED)
def create_change_request(payload: QMSChangeRequestCreate, db: Session = Depends(get_db)):
    cr = models.QMSManualChangeRequest(
        domain=payload.domain,
        petitioner_name=payload.petitioner_name.strip(),
        petitioner_email=payload.petitioner_email,
        petitioner_phone=payload.petitioner_phone,
        petitioner_department=payload.petitioner_department,
        manual_title=payload.manual_title.strip(),
        manual_reference=payload.manual_reference,
        manual_copy_no=payload.manual_copy_no,
        manual_rev=payload.manual_rev,
        manual_location=payload.manual_location,
        media_source=payload.media_source,
        remarks=payload.remarks,
        change_request_text=payload.change_request_text,
        created_by_user_id=get_actor(),
    )
    db.add(cr)
    db.commit()
    db.refresh(cr)
    return cr


@router.get("/qms/change-requests", response_model=List[QMSChangeRequestOut])
def list_change_requests(db: Session = Depends(get_db), domain: Optional[QMSDomain] = None):
    qs = db.query(models.QMSManualChangeRequest)
    if domain:
        qs = qs.filter(models.QMSManualChangeRequest.domain == domain)
    return qs.order_by(models.QMSManualChangeRequest.submitted_at.desc()).all()


@router.patch("/qms/change-requests/{cr_id}", response_model=QMSChangeRequestOut)
def update_change_request(cr_id: UUID, payload: QMSChangeRequestUpdate, db: Session = Depends(get_db)):
    cr = db.query(models.QMSManualChangeRequest).filter(models.QMSManualChangeRequest.id == cr_id).first()
    if not cr:
        raise HTTPException(status_code=404, detail="Change request not found")

    for field in ("status", "manual_owner_decision", "qa_decision", "librarian_decision", "review_feedback"):
        val = getattr(payload, field)
        if val is not None:
            setattr(cr, field, val)

    db.commit()
    db.refresh(cr)
    return cr


# -----------------------------
# Audits / Findings / CAP
# -----------------------------
@router.post("/audits", response_model=QMSAuditOut, status_code=status.HTTP_201_CREATED)
def create_audit(payload: QMSAuditCreate, db: Session = Depends(get_db)):
    audit = models.QMSAudit(
        domain=payload.domain,
        kind=payload.kind,
        audit_ref=payload.audit_ref.strip(),
        title=payload.title.strip(),
        scope=payload.scope,
        criteria=payload.criteria,
        auditee=payload.auditee,
        planned_start=payload.planned_start,
        planned_end=payload.planned_end,
        created_by_user_id=get_actor(),
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit


@router.get("/audits", response_model=List[QMSAuditOut])
def list_audits(
    db: Session = Depends(get_db),
    domain: Optional[QMSDomain] = None,
    status_: Optional[models.QMSAuditStatus] = None,
):
    qs = db.query(models.QMSAudit)
    if domain:
        qs = qs.filter(models.QMSAudit.domain == domain)
    if status_:
        qs = qs.filter(models.QMSAudit.status == status_)
    return qs.order_by(models.QMSAudit.created_at.desc()).all()


@router.patch("/audits/{audit_id}", response_model=QMSAuditOut)
def update_audit(audit_id: UUID, payload: QMSAuditUpdate, db: Session = Depends(get_db)):
    audit = db.query(models.QMSAudit).filter(models.QMSAudit.id == audit_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    for field in (
        "status", "scope", "criteria", "auditee",
        "planned_start", "planned_end", "actual_start", "actual_end",
        "report_file_ref",
    ):
        val = getattr(payload, field)
        if val is not None:
            setattr(audit, field, val)

    # If closing, set retention_until = +5 years
    if payload.status == QMSAuditStatus.CLOSED:
        if audit.actual_end:
            audit.retention_until = date(audit.actual_end.year + 5, audit.actual_end.month, audit.actual_end.day)
        elif audit.planned_end:
            audit.retention_until = date(audit.planned_end.year + 5, audit.planned_end.month, audit.planned_end.day)

    db.commit()
    db.refresh(audit)
    return audit


@router.post("/audits/{audit_id}/findings", response_model=QMSFindingOut, status_code=status.HTTP_201_CREATED)
def add_finding(audit_id: UUID, payload: QMSFindingCreate, db: Session = Depends(get_db)):
    audit = db.query(models.QMSAudit).filter(models.QMSAudit.id == audit_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    level = normalize_finding_level(payload.severity, payload.level)

    target_close_date = payload.target_close_date
    if target_close_date is None:
        target_close_date = compute_target_close_date(level)

    finding = models.QMSAuditFinding(
        audit_id=audit_id,
        finding_ref=payload.finding_ref,
        finding_type=payload.finding_type,
        severity=payload.severity,
        level=level,
        requirement_ref=payload.requirement_ref,
        description=payload.description,
        objective_evidence=payload.objective_evidence,
        safety_sensitive=payload.safety_sensitive,
        target_close_date=target_close_date,
    )
    db.add(finding)
    db.commit()
    db.refresh(finding)

    # If any finding exists, CAP is effectively open
    if audit.status in (models.QMSAuditStatus.PLANNED, models.QMSAuditStatus.IN_PROGRESS):
        audit.status = models.QMSAuditStatus.CAP_OPEN
        db.commit()

    return finding


@router.get("/audits/{audit_id}/findings", response_model=List[QMSFindingOut])
def list_findings(audit_id: UUID, db: Session = Depends(get_db)):
    return (
        db.query(models.QMSAuditFinding)
        .filter(models.QMSAuditFinding.audit_id == audit_id)
        .order_by(models.QMSAuditFinding.created_at.desc())
        .all()
    )


@router.put("/findings/{finding_id}/cap", response_model=QMSCAPOut)
def upsert_cap(finding_id: UUID, payload: QMSCAPUpsert, db: Session = Depends(get_db)):
    finding = db.query(models.QMSAuditFinding).filter(models.QMSAuditFinding.id == finding_id).first()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    cap = db.query(models.QMSCorrectiveAction).filter(models.QMSCorrectiveAction.finding_id == finding_id).first()
    if not cap:
        cap = models.QMSCorrectiveAction(finding_id=finding_id)
        db.add(cap)

    for field in (
        "root_cause", "containment_action", "corrective_action", "preventive_action",
        "responsible_user_id", "due_date", "evidence_ref", "status",
    ):
        val = getattr(payload, field)
        if val is not None:
            setattr(cap, field, val)

    db.commit()
    db.refresh(cap)
    return cap
