from __future__ import annotations

from datetime import datetime, timedelta
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_actor_id, get_current_active_user
from amodb.apps.accounts.models import AMO

from . import models
from .schemas import (
    AcknowledgeRequest,
    DiffSummaryOut,
    ExportCreate,
    ManualCreate,
    ManualOut,
    MasterListEntry,
    PrintLogCreate,
    RevisionCreate,
    RevisionOut,
    TransitionRequest,
    WorkflowOut,
)

router = APIRouter(prefix="/manuals", tags=["Manuals"], dependencies=[Depends(get_current_active_user)])


def _tenant_by_slug(db: Session, tenant_slug: str) -> models.Tenant:
    tenant = db.query(models.Tenant).filter(models.Tenant.slug == tenant_slug).first()
    if tenant:
        return tenant
    amo = db.query(AMO).filter(AMO.login_slug == tenant_slug).first()
    if not amo:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tenant = models.Tenant(amo_id=amo.id, slug=tenant_slug, name=amo.name, settings_json={"ack_due_days": 10})
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def _audit(db: Session, tenant_id: str, actor_id: str | None, action: str, entity_type: str, entity_id: str, request: Request, diff: dict | None = None) -> None:
    db.add(models.ManualAuditLog(
        tenant_id=tenant_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_device=f"{request.client.host if request.client else 'unknown'}::{request.headers.get('user-agent', 'n/a')}",
        diff_json=diff or {},
    ))


@router.get("/t/{tenant_slug}", response_model=list[ManualOut])
def list_manuals(tenant_slug: str, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    return db.query(models.Manual).filter(models.Manual.tenant_id == tenant.id).all()


@router.post("/t/{tenant_slug}", response_model=ManualOut)
def create_manual(tenant_slug: str, payload: ManualCreate, request: Request, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    manual = models.Manual(tenant_id=tenant.id, code=payload.code, title=payload.title, manual_type=payload.manual_type, owner_role=payload.owner_role)
    db.add(manual)
    db.flush()
    _audit(db, tenant.id, get_current_actor_id(), "manual.created", "manual", manual.id, request)
    db.commit()
    db.refresh(manual)
    return manual


@router.get("/t/{tenant_slug}/{manual_id}", response_model=ManualOut)
def get_manual(tenant_slug: str, manual_id: str, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    manual = db.query(models.Manual).filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id).first()
    if not manual:
        raise HTTPException(status_code=404, detail="Manual not found")
    return manual




@router.get("/t/{tenant_slug}/{manual_id}/revisions", response_model=list[RevisionOut])
def list_revisions(tenant_slug: str, manual_id: str, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    revisions = (
        db.query(models.ManualRevision)
        .join(models.Manual, models.Manual.id == models.ManualRevision.manual_id)
        .filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id)
        .order_by(models.ManualRevision.created_at.desc())
        .all()
    )
    return [RevisionOut(**rev.__dict__, status_enum=rev.status_enum.value) for rev in revisions]

@router.post("/t/{tenant_slug}/{manual_id}/revisions", response_model=RevisionOut)
def create_revision(tenant_slug: str, manual_id: str, payload: RevisionCreate, request: Request, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    manual = db.query(models.Manual).filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id).first()
    if not manual:
        raise HTTPException(status_code=404, detail="Manual not found")
    rev = models.ManualRevision(
        manual_id=manual.id,
        rev_number=payload.rev_number,
        issue_number=payload.issue_number,
        effective_date=payload.effective_date,
        notes=payload.notes,
        requires_authority_approval_bool=payload.requires_authority_approval_bool,
        created_by=get_current_actor_id(),
    )
    db.add(rev)
    db.flush()
    _audit(db, tenant.id, get_current_actor_id(), "revision.created", "manual_revision", rev.id, request, {"rev_number": payload.rev_number})
    db.commit()
    db.refresh(rev)
    return RevisionOut(**rev.__dict__, status_enum=rev.status_enum.value)


@router.post("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/workflow", response_model=WorkflowOut)
def transition_revision(tenant_slug: str, manual_id: str, rev_id: str, payload: TransitionRequest, request: Request, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    rev = db.query(models.ManualRevision).join(models.Manual, models.Manual.id == models.ManualRevision.manual_id).filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id, models.ManualRevision.id == rev_id).first()
    if not rev:
        raise HTTPException(status_code=404, detail="Revision not found")

    transitions = {
        "submit_department_review": models.ManualRevisionStatus.DEPARTMENT_REVIEW,
        "approve_quality": models.ManualRevisionStatus.QUALITY_APPROVAL,
        "approve_regulator": models.ManualRevisionStatus.REGULATOR_SIGNOFF,
        "archive": models.ManualRevisionStatus.ARCHIVED,
    }
    if payload.action == "publish":
        if rev.requires_authority_approval_bool and rev.status_enum != models.ManualRevisionStatus.REGULATOR_SIGNOFF:
            raise HTTPException(status_code=400, detail="Regulator sign-off required before publishing")
        rev.status_enum = models.ManualRevisionStatus.PUBLISHED
        rev.published_at = datetime.utcnow()
        rev.immutable_locked = True
        manual = db.query(models.Manual).filter(models.Manual.id == manual_id).first()
        previous = None
        if manual and manual.current_published_rev_id:
            previous = db.query(models.ManualRevision).filter(models.ManualRevision.id == manual.current_published_rev_id).first()
        if previous:
            previous.status_enum = models.ManualRevisionStatus.SUPERSEDED
            previous.superseded_by_rev_id = rev.id
        if manual:
            manual.current_published_rev_id = rev.id
        due_days = int((tenant.settings_json or {}).get("ack_due_days", 10))
        db.add(models.Acknowledgement(revision_id=rev.id, holder_user_id=rev.created_by, due_at=datetime.utcnow() + timedelta(days=due_days)))
        db.add(models.ManualAIHookEvent(tenant_id=tenant.id, revision_id=rev.id, event_name="revision.published", payload_json={"manual_id": manual_id}))
    else:
        new_status = transitions.get(payload.action)
        if not new_status:
            raise HTTPException(status_code=400, detail="Unsupported action")
        rev.status_enum = new_status

    _audit(db, tenant.id, get_current_actor_id(), f"revision.workflow.{payload.action}", "manual_revision", rev.id, request, {"comment": payload.comment})
    db.commit()

    history = db.query(models.ManualAuditLog).filter(models.ManualAuditLog.entity_id == rev.id).order_by(models.ManualAuditLog.at.desc()).limit(20).all()
    return WorkflowOut(revision_id=rev.id, status=rev.status_enum.value, requires_authority_approval=rev.requires_authority_approval_bool, history=[{"action": item.action, "at": item.at.isoformat(), "actor_id": item.actor_id} for item in history])


@router.get("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/read")
def read_revision(tenant_slug: str, manual_id: str, rev_id: str, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    rev = db.query(models.ManualRevision).join(models.Manual, models.Manual.id == models.ManualRevision.manual_id).filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id, models.ManualRevision.id == rev_id).first()
    if not rev:
        raise HTTPException(status_code=404, detail="Revision not found")
    sections = db.query(models.ManualSection).filter(models.ManualSection.revision_id == rev_id).order_by(models.ManualSection.order_index.asc()).all()
    blocks = db.query(models.ManualBlock).join(models.ManualSection, models.ManualSection.id == models.ManualBlock.section_id).filter(models.ManualSection.revision_id == rev_id).order_by(models.ManualBlock.order_index.asc()).all()
    return {
        "revision_id": rev.id,
        "status": rev.status_enum.value,
        "not_published": rev.status_enum != models.ManualRevisionStatus.PUBLISHED,
        "sections": [{"id": s.id, "heading": s.heading, "anchor_slug": s.anchor_slug, "level": s.level} for s in sections],
        "blocks": [{"section_id": b.section_id, "html": b.html_sanitized, "text": b.text_plain, "change_hash": b.change_hash} for b in blocks],
    }


@router.get("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/diff", response_model=DiffSummaryOut)
def revision_diff(tenant_slug: str, manual_id: str, rev_id: str, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    _ = db.query(models.Manual).filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id).first()
    diff = db.query(models.RevisionDiffIndex).filter(models.RevisionDiffIndex.revision_id == rev_id).first()
    if not diff:
        diff = models.RevisionDiffIndex(revision_id=rev_id, baseline_revision_id=None, summary_json={"changed_sections": 0, "changed_blocks": 0, "added": 0, "removed": 0})
        db.add(diff)
        db.commit()
        db.refresh(diff)
    return DiffSummaryOut(revision_id=diff.revision_id, baseline_revision_id=diff.baseline_revision_id, summary_json=diff.summary_json)


@router.get("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/workflow", response_model=WorkflowOut)
def get_workflow(tenant_slug: str, manual_id: str, rev_id: str, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    rev = db.query(models.ManualRevision).join(models.Manual, models.Manual.id == models.ManualRevision.manual_id).filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id, models.ManualRevision.id == rev_id).first()
    if not rev:
        raise HTTPException(status_code=404, detail="Revision not found")
    history = db.query(models.ManualAuditLog).filter(models.ManualAuditLog.entity_id == rev.id).order_by(models.ManualAuditLog.at.desc()).limit(20).all()
    return WorkflowOut(revision_id=rev.id, status=rev.status_enum.value, requires_authority_approval=rev.requires_authority_approval_bool, history=[{"action": item.action, "at": item.at.isoformat(), "actor_id": item.actor_id} for item in history])


@router.post("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/acknowledge")
def acknowledge_revision(tenant_slug: str, manual_id: str, rev_id: str, payload: AcknowledgeRequest, request: Request, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    actor_id = get_current_actor_id()
    ack = db.query(models.Acknowledgement).filter(models.Acknowledgement.revision_id == rev_id, models.Acknowledgement.holder_user_id == actor_id).first()
    if not ack:
        ack = models.Acknowledgement(revision_id=rev_id, holder_user_id=actor_id, due_at=datetime.utcnow() + timedelta(days=10))
        db.add(ack)
    ack.acknowledged_at = datetime.utcnow()
    ack.acknowledgement_text = payload.acknowledgement_text
    ack.status_enum = "ACKNOWLEDGED"
    _audit(db, tenant.id, actor_id, "revision.acknowledged", "acknowledgement", ack.id, request)
    db.commit()
    return {"status": "ok", "acknowledged_at": ack.acknowledged_at}


@router.post("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/exports")
def create_export(tenant_slug: str, manual_id: str, rev_id: str, payload: ExportCreate, request: Request, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    actor_id = get_current_actor_id()
    source = f"{tenant_slug}:{manual_id}:{rev_id}:{payload.version_label}:{payload.controlled_bool}:{payload.watermark_uncontrolled_bool}:{datetime.utcnow().isoformat()}"
    sha = hashlib.sha256(source.encode("utf-8")).hexdigest()
    exp = models.PrintExport(
        revision_id=rev_id,
        controlled_bool=payload.controlled_bool,
        watermark_uncontrolled_bool=payload.watermark_uncontrolled_bool,
        generated_by=actor_id,
        storage_uri=f"s3://manuals/{tenant_slug}/{manual_id}/{rev_id}/{sha}.pdf",
        sha256=sha,
        render_profile_json={"change_bars": True, "watermark_uncontrolled": payload.watermark_uncontrolled_bool},
        version_label=payload.version_label,
    )
    db.add(exp)
    db.flush()
    _audit(db, tenant.id, actor_id, "revision.exported", "print_export", exp.id, request)
    db.commit()
    return {"id": exp.id, "sha256": exp.sha256, "storage_uri": exp.storage_uri}


@router.get("/t/{tenant_slug}/{manual_id}/rev/{rev_id}/exports")
def list_exports(tenant_slug: str, manual_id: str, rev_id: str, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    _ = db.query(models.Manual).filter(models.Manual.id == manual_id, models.Manual.tenant_id == tenant.id).first()
    rows = db.query(models.PrintExport).filter(models.PrintExport.revision_id == rev_id).order_by(models.PrintExport.generated_at.desc()).all()
    return [{"id": r.id, "controlled": r.controlled_bool, "watermark_uncontrolled": r.watermark_uncontrolled_bool, "generated_at": r.generated_at, "sha256": r.sha256} for r in rows]


@router.post("/exports/{export_id}/print-log")
def create_print_log(export_id: str, payload: PrintLogCreate, db: Session = Depends(get_db)):
    exp = db.query(models.PrintExport).filter(models.PrintExport.id == export_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Export not found")
    log = models.PrintLog(export_id=export_id, printed_by=get_current_actor_id(), controlled_copy_no=payload.controlled_copy_no, recipient=payload.recipient, purpose=payload.purpose)
    db.add(log)
    db.commit()
    db.refresh(log)
    return {"id": log.id, "status": log.status_enum}


@router.post("/exports/{export_id}/recall")
def recall_print(export_id: str, db: Session = Depends(get_db)):
    rows = db.query(models.PrintLog).filter(models.PrintLog.export_id == export_id).all()
    for row in rows:
        row.status_enum = "RECALLED"
    db.commit()
    return {"updated": len(rows)}


@router.get("/t/{tenant_slug}/master-list", response_model=list[MasterListEntry])
def master_list(tenant_slug: str, db: Session = Depends(get_db)):
    tenant = _tenant_by_slug(db, tenant_slug)
    manuals = db.query(models.Manual).filter(models.Manual.tenant_id == tenant.id).all()
    result = []
    for manual in manuals:
        current_rev = None
        pending = 0
        if manual.current_published_rev_id:
            current_rev = db.query(models.ManualRevision).filter(models.ManualRevision.id == manual.current_published_rev_id).first()
            pending = db.query(models.Acknowledgement).filter(models.Acknowledgement.revision_id == manual.current_published_rev_id, models.Acknowledgement.status_enum != "ACKNOWLEDGED").count()
        result.append(MasterListEntry(manual_id=manual.id, code=manual.code, title=manual.title, current_revision=current_rev.rev_number if current_rev else None, current_status=current_rev.status_enum.value if current_rev else "NO_PUBLISHED_REV", pending_ack_count=pending))
    return result
