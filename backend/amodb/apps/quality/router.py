# backend/amodb/apps/quality/router.py
from __future__ import annotations

from datetime import date
from pathlib import Path
import shutil
from typing import Optional, List
from uuid import UUID
import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Query, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, ProgrammingError

from amodb.entitlements import require_module
from amodb.security import get_current_actor_id, get_current_active_user
from amodb.apps.accounts import models as account_models
from amodb.database import get_db

from . import models
from .schemas import (
    CARActionCreate,
    CARActionOut,
    CARAssigneeOut,
    CARCreate,
    CARInviteOut,
    CARInviteUpdate,
    CARAttachmentOut,
    CAROut,
    CARUpdate,
    CARReviewUpdate,
    AuditorStatsOut,
    QMSNotificationOut,
    QMSDashboardOut,
    QMSDocumentCreate, QMSDocumentUpdate, QMSDocumentOut,
    QMSDocumentRevisionCreate, QMSDocumentRevisionOut, QMSPublishRevision,
    QMSDistributionCreate, QMSDistributionOut,
    QMSChangeRequestCreate, QMSChangeRequestUpdate, QMSChangeRequestOut,
    QMSAuditCreate, QMSAuditUpdate, QMSAuditOut,
    QMSFindingCreate, QMSFindingOut,
    QMSCAPUpsert, QMSCAPOut,
)
from .enums import CARStatus, QMSDomain, QMSAuditStatus
from .service import (
    add_car_action,
    build_car_invite_link,
    compute_target_close_date,
    create_car,
    generate_car_form_pdf,
    get_dashboard,
    normalize_finding_level,
    schedule_next_reminder,
)

router = APIRouter(
    prefix="/quality",
    tags=["Quality / QMS"],
    dependencies=[Depends(require_module("quality"))],
)

CAR_ATTACHMENT_DIR = Path(__file__).resolve().parents[2] / "generated" / "quality" / "car_attachments"
CAR_ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)
MAX_CAR_ATTACHMENT_BYTES = 10 * 1024 * 1024


def _serialize_attachment(invite_token: str, attachment: models.CARAttachment) -> CARAttachmentOut:
    return CARAttachmentOut(
        id=attachment.id,
        car_id=attachment.car_id,
        filename=attachment.filename,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        uploaded_at=attachment.uploaded_at,
        download_url=f"/quality/cars/invite/{invite_token}/attachments/{attachment.id}/download",
    )


def get_actor() -> Optional[str]:
    """
    Replace with your JWT dependency.
    Return a stable user id string (e.g., UUID or int as str).
    """
    return get_current_actor_id()


def _notify_user(db: Session, user_id: Optional[str], message: str, severity=models.QMSNotificationSeverity):
    if not user_id:
        return
    note = models.QMSNotification(
        user_id=user_id,
        message=message,
        severity=severity,
        created_by_user_id=get_actor(),
    )
    db.add(note)


def _is_quality_admin(current_user: account_models.User) -> bool:
    return bool(
        getattr(current_user, "is_superuser", False)
        or getattr(current_user, "is_amo_admin", False)
        or current_user.role
        in {
            account_models.AccountRole.SUPERUSER,
            account_models.AccountRole.AMO_ADMIN,
            account_models.AccountRole.QUALITY_MANAGER,
        }
    )


def _audit_allows_user(db: Session, finding_id: Optional[UUID], user_id: str) -> bool:
    if not finding_id:
        return False
    audit = (
        db.query(models.QMSAudit)
        .join(models.QMSAuditFinding)
        .filter(models.QMSAuditFinding.id == finding_id)
        .first()
    )
    if not audit:
        return False
    return user_id in {
        audit.lead_auditor_user_id,
        audit.observer_auditor_user_id,
        audit.assistant_auditor_user_id,
    }


def _require_car_write_access(
    db: Session,
    current_user: account_models.User,
    finding_id: Optional[UUID],
    car: Optional[models.CorrectiveActionRequest] = None,
    allow_assignee: bool = False,
) -> None:
    if _is_quality_admin(current_user):
        return
    if _audit_allows_user(db, finding_id, current_user.id):
        return
    if car and current_user.id == car.requested_by_user_id:
        return
    if allow_assignee and car and current_user.id == car.assigned_to_user_id:
        return
    raise HTTPException(status_code=403, detail="Insufficient privileges to modify CARs")


def _assignee_can_request_extension(
    db: Session,
    car: models.CorrectiveActionRequest,
    requested_date: date,
) -> bool:
    if not car.finding_id:
        return False
    finding = (
        db.query(models.QMSAuditFinding)
        .filter(models.QMSAuditFinding.id == car.finding_id)
        .first()
    )
    if not finding:
        return False
    baseline = finding.target_close_date
    if baseline is None:
        baseline = compute_target_close_date(finding.level, base=finding.created_at.date())
    return requested_date > baseline


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
        auditee_email=payload.auditee_email,
        lead_auditor_user_id=payload.lead_auditor_user_id,
        observer_auditor_user_id=payload.observer_auditor_user_id,
        assistant_auditor_user_id=payload.assistant_auditor_user_id,
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
        "status", "scope", "criteria", "auditee", "auditee_email",
        "planned_start", "planned_end", "actual_start", "actual_end",
        "report_file_ref",
        "lead_auditor_user_id",
        "observer_auditor_user_id",
        "assistant_auditor_user_id",
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
        note_msg = f"Audit {audit.audit_ref} closed. Please send closure pack to {audit.auditee_email or 'auditee'}."
        _notify_user(db, audit.lead_auditor_user_id, note_msg, models.QMSNotificationSeverity.INFO)

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

    if payload.status in (models.QMSCAPStatus.CLOSED, models.QMSCAPStatus.REJECTED):
        audit = db.query(models.QMSAudit).filter(models.QMSAudit.id == finding.audit_id).first()
        if audit:
            note_msg = (
                f"CAP {payload.status.value} for audit {audit.audit_ref} ({audit.title})."
            )
            for auditor_id in (
                audit.lead_auditor_user_id,
                audit.observer_auditor_user_id,
                audit.assistant_auditor_user_id,
            ):
                _notify_user(db, auditor_id, note_msg, models.QMSNotificationSeverity.WARNING)

    db.commit()
    db.refresh(cap)
    return cap


# -----------------------------
# Corrective Action Requests (CAR)
# -----------------------------


@router.post("/cars", response_model=CAROut, status_code=status.HTTP_201_CREATED)
def create_car_request(
    payload: CARCreate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    _require_car_write_access(db, current_user, payload.finding_id)
    try:
        car = create_car(
            db=db,
            program=payload.program,
            title=payload.title.strip(),
            summary=payload.summary.strip(),
            priority=payload.priority,
            requested_by_user_id=get_actor(),
            assigned_to_user_id=payload.assigned_to_user_id,
            due_date=payload.due_date,
            target_closure_date=payload.target_closure_date,
            finding_id=payload.finding_id,
        )
        db.commit()
        db.refresh(car)
        return car
    except (OperationalError, ProgrammingError) as exc:
        if _is_missing_table_error(exc):
            raise HTTPException(
                status_code=503,
                detail="CARs are unavailable because the database schema is missing. Run alembic upgrade heads.",
            ) from exc
        raise


@router.get("/cars", response_model=List[CAROut])
def list_cars(
    db: Session = Depends(get_db),
    program: Optional[models.CARProgram] = None,
    status_: Optional[models.CARStatus] = None,
    assigned_to_user_id: Optional[str] = None,
):
    try:
        qs = db.query(models.CorrectiveActionRequest)
        if program:
            qs = qs.filter(models.CorrectiveActionRequest.program == program)
        if status_:
            qs = qs.filter(models.CorrectiveActionRequest.status == status_)
        if assigned_to_user_id:
            qs = qs.filter(models.CorrectiveActionRequest.assigned_to_user_id == assigned_to_user_id)
        return qs.order_by(models.CorrectiveActionRequest.created_at.desc()).all()
    except (OperationalError, ProgrammingError) as exc:
        if _is_missing_table_error(exc):
            return []
        raise


@router.get("/cars/assignees", response_model=List[CARAssigneeOut])
def list_car_assignees(
    db: Session = Depends(get_db),
    department_id: Optional[str] = None,
    search: Optional[str] = None,
    current_user: account_models.User = Depends(get_current_active_user),
):
    q = (
        db.query(account_models.User, account_models.Department)
        .outerjoin(account_models.Department, account_models.User.department_id == account_models.Department.id)
        .filter(account_models.User.amo_id == current_user.amo_id)
        .filter(account_models.User.is_active.is_(True))
    )
    if department_id:
        q = q.filter(account_models.User.department_id == department_id)
    if search and search.strip():
        like = f"%{search.strip()}%"
        q = q.filter(
            (account_models.User.full_name.ilike(like))
            | (account_models.User.email.ilike(like))
            | (account_models.User.staff_code.ilike(like))
        )
    q = q.order_by(account_models.User.full_name.asc())
    results = []
    for user, dept in q.all():
        results.append(
            CARAssigneeOut(
                id=user.id,
                full_name=user.full_name,
                email=user.email,
                staff_code=user.staff_code,
                role=user.role,
                department_id=user.department_id,
                department_code=dept.code if dept else None,
                department_name=dept.name if dept else None,
            )
        )
    return results


@router.patch("/cars/{car_id}", response_model=CAROut)
def update_car(
    car_id: UUID,
    payload: CARUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")
    is_assignee = current_user.id == car.assigned_to_user_id
    _require_car_write_access(db, current_user, car.finding_id, car=car, allow_assignee=is_assignee)

    data = payload.model_dump(exclude_unset=True)
    if not data:
        return car

    changed_status = False
    assignee_allowed = {
        "root_cause",
        "corrective_action",
        "preventive_action",
        "target_closure_date",
    }

    if is_assignee and not _is_quality_admin(current_user) and not _audit_allows_user(
        db, car.finding_id, current_user.id
    ):
        disallowed = set(data) - assignee_allowed
        if disallowed:
            raise HTTPException(
                status_code=403,
                detail="Assignees may only update root cause, CAP/PAP, or request extra time.",
            )
        if "target_closure_date" in data:
            requested_date = data["target_closure_date"]
            if requested_date is None or not _assignee_can_request_extension(db, car, requested_date):
                raise HTTPException(
                    status_code=403,
                    detail="Additional time can only be requested when exceeding the level due date.",
                )
            car.target_closure_date = requested_date
            add_car_action(
                db=db,
                car=car,
                action_type=models.CARActionType.COMMENT,
                message=f"Assignee requested extension to {requested_date.isoformat()}",
                actor_user_id=get_actor(),
            )
        updated_fields = {}
        for field in ("root_cause", "corrective_action", "preventive_action"):
            if field in data:
                setattr(car, field, data[field])
                updated_fields[field] = data[field]
        if updated_fields:
            response = models.CARResponse(
                car_id=car.id,
                containment_action=car.containment_action,
                root_cause=car.root_cause,
                corrective_action=car.corrective_action,
                preventive_action=car.preventive_action,
                evidence_ref=car.evidence_ref,
                submitted_by_name=current_user.full_name,
                submitted_by_email=current_user.email,
                status=models.CARResponseStatus.SUBMITTED,
            )
            db.add(response)
    else:
        for field, val in data.items():
            setattr(car, field, val)
            if field == "status":
                changed_status = True

    if changed_status:
        add_car_action(
            db=db,
            car=car,
            action_type=models.CARActionType.STATUS_CHANGE,
            message=f"Status changed to {car.status}",
            actor_user_id=get_actor(),
        )

    db.commit()
    db.refresh(car)
    return car


@router.delete("/cars/{car_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_car(
    car_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")
    _require_car_write_access(db, current_user, car.finding_id, car=car)
    db.delete(car)
    db.commit()
    return None


@router.get("/cars/{car_id}/print", response_class=FileResponse)
def print_car_form(
    car_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")
    _require_car_write_access(db, current_user, car.finding_id, car=car, allow_assignee=True)

    assigned_name = None
    requested_name = None
    if car.assigned_to_user_id:
        assigned_user = (
            db.query(account_models.User)
            .filter(account_models.User.id == car.assigned_to_user_id)
            .first()
        )
        assigned_name = assigned_user.full_name if assigned_user else None
    if car.requested_by_user_id:
        requested_user = (
            db.query(account_models.User)
            .filter(account_models.User.id == car.requested_by_user_id)
            .first()
        )
        requested_name = requested_user.full_name if requested_user else None

    try:
        file_path = generate_car_form_pdf(
            car=car,
            invite_url=build_car_invite_link(car),
            requested_by_name=requested_name,
            assigned_to_name=assigned_name,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return FileResponse(
        path=file_path,
        filename=f"{car.car_number}.pdf",
        media_type="application/pdf",
    )


@router.post("/cars/{car_id}/escalate", response_model=CAROut)
def escalate_car(car_id: UUID, db: Session = Depends(get_db)):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")

    car.status = models.CARStatus.ESCALATED
    car.escalated_at = func.now()
    add_car_action(
        db=db,
        car=car,
        action_type=models.CARActionType.ESCALATION,
        message="Escalated due to inactivity or overdue status",
        actor_user_id=get_actor(),
    )
    db.commit()
    db.refresh(car)
    return car


@router.post("/cars/{car_id}/reminders", response_model=CAROut)
def reschedule_car_reminder(car_id: UUID, reminder_interval_days: int = 7, db: Session = Depends(get_db)):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")
    if reminder_interval_days < 1 or reminder_interval_days > 90:
        raise HTTPException(status_code=400, detail="Reminder interval must be between 1 and 90 days")
    schedule_next_reminder(car, reminder_interval_days)
    add_car_action(
        db=db,
        car=car,
        action_type=models.CARActionType.REMINDER,
        message=f"Reminder window set to every {reminder_interval_days} days",
        actor_user_id=get_actor(),
    )
    db.commit()
    db.refresh(car)
    return car


@router.get("/cars/{car_id}/invite", response_model=CARInviteOut)
def get_car_invite(car_id: UUID, db: Session = Depends(get_db)):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")
    url = build_car_invite_link(car)
    return {
        "car_id": car.id,
        "invite_token": car.invite_token,
        "invite_url": url,
        "next_reminder_at": car.next_reminder_at,
        "car_number": car.car_number,
        "title": car.title,
        "summary": car.summary,
        "priority": car.priority,
        "status": car.status,
        "due_date": car.due_date,
        "target_closure_date": car.target_closure_date,
    }


@router.get("/cars/invite/{invite_token}", response_model=CARInviteOut)
def get_car_invite_by_token(invite_token: str, db: Session = Depends(get_db)):
    car = (
        db.query(models.CorrectiveActionRequest)
        .filter(models.CorrectiveActionRequest.invite_token == invite_token)
        .first()
    )
    if not car:
        raise HTTPException(status_code=404, detail="Invite not found")
    url = build_car_invite_link(car)
    return {
        "car_id": car.id,
        "invite_token": car.invite_token,
        "invite_url": url,
        "next_reminder_at": car.next_reminder_at,
        "car_number": car.car_number,
        "title": car.title,
        "summary": car.summary,
        "priority": car.priority,
        "status": car.status,
        "due_date": car.due_date,
        "target_closure_date": car.target_closure_date,
    }


@router.patch("/cars/invite/{invite_token}", response_model=CAROut)
def submit_car_from_invite(invite_token: str, payload: CARInviteUpdate, db: Session = Depends(get_db)):
    car = (
        db.query(models.CorrectiveActionRequest)
        .filter(models.CorrectiveActionRequest.invite_token == invite_token)
        .first()
    )
    if not car:
        raise HTTPException(status_code=404, detail="Invite not found")

    for field in (
        "containment_action",
        "root_cause",
        "corrective_action",
        "preventive_action",
        "evidence_ref",
        "target_closure_date",
        "due_date",
        "submitted_by_name",
        "submitted_by_email",
    ):
        val = getattr(payload, field)
        if val is not None:
            setattr(car, field, val)

    car.submitted_at = func.now()
    if car.status in (models.CARStatus.OPEN, models.CARStatus.DRAFT):
        car.status = models.CARStatus.IN_PROGRESS

    add_car_action(
        db=db,
        car=car,
        action_type=models.CARActionType.COMMENT,
        message="Auditee submitted CAR response via invite link",
        actor_user_id=None,
    )

    response = models.CARResponse(
        car_id=car.id,
        containment_action=car.containment_action,
        root_cause=car.root_cause,
        corrective_action=car.corrective_action,
        preventive_action=car.preventive_action,
        evidence_ref=car.evidence_ref,
        submitted_by_name=car.submitted_by_name,
        submitted_by_email=car.submitted_by_email,
        submitted_at=car.submitted_at or func.now(),
        status=models.CARResponseStatus.SUBMITTED,
    )
    db.add(response)

    if car.finding_id:
        audit = (
            db.query(models.QMSAudit)
            .join(models.QMSAuditFinding)
            .filter(models.QMSAuditFinding.id == car.finding_id)
            .first()
        )
    else:
        audit = None

    note_msg = f"CAR response submitted for {car.car_number} ({car.title})."
    if audit:
        note_msg = f"{note_msg} Audit {audit.audit_ref}."
        for auditor_id in (
            audit.lead_auditor_user_id,
            audit.observer_auditor_user_id,
            audit.assistant_auditor_user_id,
        ):
            _notify_user(db, auditor_id, note_msg, models.QMSNotificationSeverity.ACTION_REQUIRED)
    _notify_user(db, car.assigned_to_user_id, note_msg, models.QMSNotificationSeverity.ACTION_REQUIRED)

    db.commit()
    db.refresh(car)
    return car


@router.get("/cars/invite/{invite_token}/attachments", response_model=List[CARAttachmentOut])
def list_car_invite_attachments(invite_token: str, db: Session = Depends(get_db)):
    car = (
        db.query(models.CorrectiveActionRequest)
        .filter(models.CorrectiveActionRequest.invite_token == invite_token)
        .first()
    )
    if not car:
        raise HTTPException(status_code=404, detail="Invite not found")
    return [_serialize_attachment(invite_token, attachment) for attachment in car.attachments]


@router.post(
    "/cars/invite/{invite_token}/attachments",
    response_model=CARAttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_car_invite_attachment(
    invite_token: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    car = (
        db.query(models.CorrectiveActionRequest)
        .filter(models.CorrectiveActionRequest.invite_token == invite_token)
        .first()
    )
    if not car:
        raise HTTPException(status_code=404, detail="Invite not found")

    original_name = Path(file.filename or "attachment").name
    unique_name = f"{uuid.uuid4().hex}_{original_name}"
    target_dir = CAR_ATTACHMENT_DIR / str(car.id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / unique_name

    with target_path.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)

    size_bytes = target_path.stat().st_size
    if size_bytes > MAX_CAR_ATTACHMENT_BYTES:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail="Attachment exceeds the 10MB limit.")

    attachment = models.CARAttachment(
        car_id=car.id,
        filename=original_name,
        file_ref=str(target_path),
        content_type=file.content_type,
        size_bytes=size_bytes,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return _serialize_attachment(invite_token, attachment)


@router.get(
    "/cars/invite/{invite_token}/attachments/{attachment_id}/download",
    response_class=FileResponse,
)
def download_car_invite_attachment(
    invite_token: str,
    attachment_id: UUID,
    db: Session = Depends(get_db),
):
    car = (
        db.query(models.CorrectiveActionRequest)
        .filter(models.CorrectiveActionRequest.invite_token == invite_token)
        .first()
    )
    if not car:
        raise HTTPException(status_code=404, detail="Invite not found")
    attachment = (
        db.query(models.CARAttachment)
        .filter(
            models.CARAttachment.id == attachment_id,
            models.CARAttachment.car_id == car.id,
        )
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    file_path = Path(attachment.file_ref)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Attachment file missing on server.")
    return FileResponse(
        path=file_path,
        filename=attachment.filename,
        media_type=attachment.content_type or "application/octet-stream",
    )


@router.post("/cars/{car_id}/review", response_model=CAROut)
def review_car_response(
    car_id: UUID,
    payload: CARReviewUpdate,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")
    if not (_is_quality_admin(current_user) or _audit_allows_user(db, car.finding_id, current_user.id)):
        raise HTTPException(status_code=403, detail="Insufficient privileges to review CARs")

    latest_response = (
        db.query(models.CARResponse)
        .filter(models.CARResponse.car_id == car.id)
        .order_by(models.CARResponse.submitted_at.desc())
        .first()
    )
    if not latest_response:
        raise HTTPException(status_code=404, detail="No CAR response found for review")

    note_msg = None
    if payload.root_cause_status == "REJECTED":
        latest_response.status = models.CARResponseStatus.ROOT_CAUSE_REJECTED
        note_msg = (
            f"Root cause rejected for CAR {car.car_number}. "
            "CAP/PAP rejected automatically. Please resubmit with corrections."
        )
    elif payload.root_cause_status == "ACCEPTED":
        latest_response.status = models.CARResponseStatus.ROOT_CAUSE_ACCEPTED
        note_msg = f"Root cause accepted for CAR {car.car_number}."
        if payload.cap_status == "REJECTED":
            latest_response.status = models.CARResponseStatus.CAP_REJECTED
            note_msg = (
                f"CAP/PAP rejected for CAR {car.car_number}. "
                "Please resubmit the CAR response with corrections."
            )
        elif payload.cap_status == "ACCEPTED":
            latest_response.status = models.CARResponseStatus.CAP_ACCEPTED
            note_msg = f"CAP/PAP accepted for CAR {car.car_number}."

    if payload.message:
        add_car_action(
            db=db,
            car=car,
            action_type=models.CARActionType.COMMENT,
            message=payload.message.strip(),
            actor_user_id=get_actor(),
        )

    if note_msg:
        _notify_user(db, car.assigned_to_user_id, note_msg, models.QMSNotificationSeverity.ACTION_REQUIRED)

    db.commit()
    db.refresh(car)
    return car


@router.get("/auditors/{user_id}/stats", response_model=AuditorStatsOut)
def get_auditor_stats(user_id: str, db: Session = Depends(get_db)):
    qs = db.query(models.QMSAudit)
    audits_total = qs.filter(
        (models.QMSAudit.lead_auditor_user_id == user_id)
        | (models.QMSAudit.observer_auditor_user_id == user_id)
        | (models.QMSAudit.assistant_auditor_user_id == user_id)
    ).count()

    audits_open = qs.filter(
        (models.QMSAudit.lead_auditor_user_id == user_id)
        | (models.QMSAudit.observer_auditor_user_id == user_id)
        | (models.QMSAudit.assistant_auditor_user_id == user_id),
        models.QMSAudit.status != models.QMSAuditStatus.CLOSED,
    ).count()

    audits_closed = qs.filter(
        (models.QMSAudit.lead_auditor_user_id == user_id)
        | (models.QMSAudit.observer_auditor_user_id == user_id)
        | (models.QMSAudit.assistant_auditor_user_id == user_id),
        models.QMSAudit.status == models.QMSAuditStatus.CLOSED,
    ).count()

    lead_audits = qs.filter(models.QMSAudit.lead_auditor_user_id == user_id).count()
    observer_audits = qs.filter(models.QMSAudit.observer_auditor_user_id == user_id).count()
    assistant_audits = qs.filter(models.QMSAudit.assistant_auditor_user_id == user_id).count()

    return {
        "user_id": user_id,
        "audits_total": audits_total,
        "audits_open": audits_open,
        "audits_closed": audits_closed,
        "lead_audits": lead_audits,
        "observer_audits": observer_audits,
        "assistant_audits": assistant_audits,
    }


@router.get("/notifications/me", response_model=List[QMSNotificationOut])
def list_my_notifications(
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    user_id = get_actor() or str(current_user.id)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        notes = (
            db.query(models.QMSNotification)
            .filter(models.QMSNotification.user_id == user_id)
            .filter(models.QMSNotification.read_at.is_(None))
            .order_by(models.QMSNotification.created_at.desc())
            .limit(20)
            .all()
        )
    except (OperationalError, ProgrammingError) as exc:
        if _is_missing_table_error(exc):
            return []
        raise
    return notes


@router.post("/notifications/{notification_id}/read", response_model=QMSNotificationOut)
def mark_notification_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    user_id = get_actor() or str(current_user.id)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        note = (
            db.query(models.QMSNotification)
            .filter(models.QMSNotification.id == notification_id, models.QMSNotification.user_id == user_id)
            .first()
        )
    except (OperationalError, ProgrammingError) as exc:
        if _is_missing_table_error(exc):
            raise HTTPException(
                status_code=503,
                detail="Notifications are not available because the database schema is missing.",
            ) from exc
        raise
    if not note:
        raise HTTPException(status_code=404, detail="Notification not found")
    note.read_at = func.now()
    db.commit()
    db.refresh(note)
    return note


def _is_missing_table_error(exc: Exception) -> bool:
    message = str(getattr(exc, "orig", exc)).lower()
    return ("relation" in message and "does not exist" in message) or "no such table" in message


@router.post("/cars/{car_id}/actions", response_model=CARActionOut, status_code=status.HTTP_201_CREATED)
def add_car_action_log(car_id: UUID, payload: CARActionCreate, db: Session = Depends(get_db)):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")

    log = add_car_action(
        db=db,
        car=car,
        action_type=payload.action_type,
        message=payload.message.strip(),
        actor_user_id=get_actor(),
    )
    db.commit()
    db.refresh(log)
    return log


@router.get("/cars/{car_id}/actions", response_model=List[CARActionOut])
def list_car_actions(car_id: UUID, db: Session = Depends(get_db)):
    car = db.query(models.CorrectiveActionRequest).filter(models.CorrectiveActionRequest.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")
    return (
        db.query(models.CARActionLog)
        .filter(models.CARActionLog.car_id == car_id)
        .order_by(models.CARActionLog.created_at.desc())
        .all()
    )
