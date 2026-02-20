from __future__ import annotations

from datetime import date, datetime, timedelta
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.doc_control import models, schemas
from amodb.apps.events.broker import EventEnvelope, publish_event
from amodb.database import get_db
from amodb.entitlements import require_module
from amodb.security import get_current_active_user

router = APIRouter(prefix="/doc-control", tags=["doc_control"], dependencies=[Depends(require_module("quality"))])


def _log(db: Session, *, tenant_id: str, actor_user_id: str | None, object_type: str, object_id: str, action: str, before: Any, after: Any):
    db.add(models.AuditEvent(
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        object_type=object_type,
        object_id=object_id,
        action=action,
        diff_json={"before": before, "after": after},
    ))


def _tenant_id(user: account_models.User) -> str:
    return str(user.amo_id)


@router.get("/dashboard", response_model=schemas.DashboardOut)
def dashboard(db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    tenant_id = _tenant_id(current_user)
    now = date.today()
    return schemas.DashboardOut(
        pending_internal_approvals=db.query(models.Draft).filter_by(tenant_id=tenant_id, status="Review").count(),
        pending_authority_approval=db.query(models.ControlledDocument).filter_by(tenant_id=tenant_id, regulated_flag=True, authority_approval_status="Pending").count(),
        trs_in_force=db.query(models.TemporaryRevision).filter_by(tenant_id=tenant_id, status="InForce").count(),
        trs_expiring_30_days=db.query(models.TemporaryRevision).filter(models.TemporaryRevision.tenant_id == tenant_id, models.TemporaryRevision.status == "InForce", models.TemporaryRevision.expiry_date <= now + timedelta(days=30)).count(),
        manuals_due_review_60_days=db.query(models.ControlledDocument).filter(models.ControlledDocument.tenant_id == tenant_id, models.ControlledDocument.next_review_due <= now + timedelta(days=60)).count(),
        outstanding_acknowledgements=db.query(models.DistributionRecipient).outerjoin(models.Acknowledgement, models.DistributionRecipient.event_id == models.Acknowledgement.event_id).filter(models.DistributionRecipient.tenant_id == tenant_id, models.Acknowledgement.ack_id.is_(None)).count(),
        recently_published_revisions_30_days=db.query(models.RevisionPackage).filter(models.RevisionPackage.tenant_id == tenant_id, models.RevisionPackage.published_at >= datetime.utcnow() - timedelta(days=30)).count(),
    )


@router.get("/settings", response_model=schemas.DocControlSettingsOut)
def get_settings(db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    tenant_id = _tenant_id(current_user)
    settings = db.query(models.DocControlSettings).filter_by(tenant_id=tenant_id).first()
    if not settings:
        settings = models.DocControlSettings(tenant_id=tenant_id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


@router.put("/settings", response_model=schemas.DocControlSettingsOut)
def put_settings(payload: schemas.DocControlSettingsIn, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    tenant_id = _tenant_id(current_user)
    settings = db.query(models.DocControlSettings).filter_by(tenant_id=tenant_id).first()
    before = settings.__dict__.copy() if settings else None
    if not settings:
        settings = models.DocControlSettings(tenant_id=tenant_id)
        db.add(settings)
    settings.default_retention_years = payload.default_retention_years
    settings.default_review_interval_months = payload.default_review_interval_months
    settings.regulated_workflow_enabled = payload.regulated_workflow_enabled
    settings.default_ack_required = payload.default_ack_required
    _log(db, tenant_id=tenant_id, actor_user_id=current_user.id, object_type="DocControlSettings", object_id=tenant_id, action="upsert", before=before, after=payload.model_dump())
    db.commit()
    db.refresh(settings)
    return settings


@router.post("/documents", response_model=schemas.ControlledDocumentOut)
def create_document(payload: schemas.ControlledDocumentIn, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    tenant_id = _tenant_id(current_user)
    doc = models.ControlledDocument(tenant_id=tenant_id, **payload.model_dump())
    if doc.effective_date:
        doc.next_review_due = doc.effective_date + timedelta(days=30 * 24)
    db.add(doc)
    _log(db, tenant_id=tenant_id, actor_user_id=current_user.id, object_type="ControlledDocument", object_id=doc.doc_id, action="create", before=None, after=payload.model_dump())
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/documents", response_model=list[schemas.ControlledDocumentOut])
def list_documents(status: str | None = None, doc_type: str | None = None, owner_department: str | None = None, regulated: bool | None = None, restricted: bool | None = None, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    tenant_id = _tenant_id(current_user)
    qs = db.query(models.ControlledDocument).filter_by(tenant_id=tenant_id)
    if status:
        qs = qs.filter(models.ControlledDocument.status == status)
    if doc_type:
        qs = qs.filter(models.ControlledDocument.doc_type == doc_type)
    if owner_department:
        qs = qs.filter(models.ControlledDocument.owner_department == owner_department)
    if regulated is not None:
        qs = qs.filter(models.ControlledDocument.regulated_flag == regulated)
    if restricted is not None:
        qs = qs.filter(models.ControlledDocument.restricted_flag == restricted)
    return qs.order_by(models.ControlledDocument.doc_id.asc()).all()


@router.get("/documents/{doc_id}", response_model=schemas.ControlledDocumentOut)
def get_document(doc_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    doc = db.query(models.ControlledDocument).filter_by(tenant_id=_tenant_id(current_user), doc_id=doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.restricted_flag and not (current_user.is_superuser or current_user.is_amo_admin):
        raise HTTPException(403, "Restricted document")
    return doc


@router.post("/drafts", response_model=schemas.GenericOut)
def create_draft(payload: schemas.DraftIn, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    draft = models.Draft(tenant_id=_tenant_id(current_user), **payload.model_dump())
    db.add(draft)
    _log(db, tenant_id=_tenant_id(current_user), actor_user_id=current_user.id, object_type="Draft", object_id=draft.draft_id, action="create", before=None, after=payload.model_dump())
    db.commit()
    return {"id": draft.draft_id}


@router.get("/drafts")
def list_drafts(db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    return db.query(models.Draft).filter_by(tenant_id=_tenant_id(current_user)).all()


@router.post("/change-proposals", response_model=schemas.GenericOut)
def create_change_proposal(payload: schemas.ChangeProposalIn, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    row = models.ChangeProposal(tenant_id=_tenant_id(current_user), proposer_user_id=current_user.id, **payload.model_dump())
    db.add(row)
    _log(db, tenant_id=_tenant_id(current_user), actor_user_id=current_user.id, object_type="ChangeProposal", object_id=row.proposal_id, action="create", before=None, after=payload.model_dump())
    db.commit()
    return {"id": row.proposal_id}


@router.get("/change-proposals")
def list_change_proposals(db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    return db.query(models.ChangeProposal).filter_by(tenant_id=_tenant_id(current_user)).all()


@router.post("/leps", response_model=schemas.GenericOut)
def create_lep(payload: schemas.LEPIn, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    row = models.LEP(tenant_id=_tenant_id(current_user), **payload.model_dump())
    db.add(row)
    _log(db, tenant_id=_tenant_id(current_user), actor_user_id=current_user.id, object_type="LEP", object_id=row.lep_id, action="create", before=None, after=payload.model_dump())
    db.commit()
    return {"id": row.lep_id}


@router.get("/lep/{doc_id}")
def get_lep(doc_id: str, revision_no: int = Query(...), db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    row = db.query(models.LEP).filter_by(tenant_id=_tenant_id(current_user), doc_id=doc_id, revision_no=revision_no).first()
    if not row:
        raise HTTPException(404, "LEP not found")
    return row


@router.post("/revisions", response_model=schemas.GenericOut)
def create_revision_package(payload: schemas.RevisionPackageIn, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    row = models.RevisionPackage(tenant_id=_tenant_id(current_user), **payload.model_dump())
    db.add(row)
    _log(db, tenant_id=_tenant_id(current_user), actor_user_id=current_user.id, object_type="RevisionPackage", object_id=row.package_id, action="create", before=None, after=payload.model_dump())
    db.commit()
    return {"id": row.package_id}


@router.post("/revisions/{package_id}/publish")
def publish_revision(package_id: str, payload: schemas.PublishRevisionIn, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    tenant_id = _tenant_id(current_user)
    package = db.query(models.RevisionPackage).filter_by(tenant_id=tenant_id, package_id=package_id).first()
    if not package:
        raise HTTPException(404, "Revision package not found")
    doc = db.query(models.ControlledDocument).filter_by(tenant_id=tenant_id, doc_id=package.doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    if package.internal_approval_status != "Approved":
        raise HTTPException(400, "Internal approval required")
    if doc.regulated_flag and not (package.authority_status == "Approved" and package.authority_evidence_asset_id):
        raise HTTPException(400, "Authority approval required")
    lep = db.query(models.LEP).filter_by(tenant_id=tenant_id, doc_id=package.doc_id, revision_no=package.revision_no).first()
    if not lep:
        raise HTTPException(400, "LEP required before publishing")

    if doc.status == "Active":
        settings = db.query(models.DocControlSettings).filter_by(tenant_id=tenant_id).first() or models.DocControlSettings(tenant_id=tenant_id)
        retention_until = date.today() + timedelta(days=365 * settings.default_retention_years)
        db.add(models.ArchiveRecord(
            tenant_id=tenant_id,
            doc_id=doc.doc_id,
            revision_no=doc.revision_no,
            archival_marking=f"Rev {doc.revision_no} archived {date.today().isoformat()}",
            retention_until=retention_until,
        ))
        doc.status = "Superseded"

    before = {"revision_no": doc.revision_no, "effective_date": str(doc.effective_date) if doc.effective_date else None, "status": doc.status}
    doc.revision_no = package.revision_no
    doc.effective_date = package.effective_date
    doc.current_asset_id = payload.current_asset_id
    doc.status = "Active"
    package.published_at = datetime.utcnow()

    dist = models.DistributionEvent(
        tenant_id=tenant_id,
        doc_id=doc.doc_id,
        source_type="RevisionPackage",
        source_id=package.package_id,
        method="Portal",
        acknowledgement_required=True,
        status="Draft",
    )
    db.add(dist)
    _log(db, tenant_id=tenant_id, actor_user_id=current_user.id, object_type="ControlledDocument", object_id=doc.doc_id, action="publish_revision", before=before, after={"revision_no": doc.revision_no, "effective_date": str(doc.effective_date), "status": doc.status})
    db.commit()

    publish_event(EventEnvelope(id=str(uuid.uuid4()), type="doc_control.document_published", entityType="doc_control_document", entityId=doc.doc_id, action="published", timestamp=datetime.utcnow().isoformat(), actor={"userId": current_user.id}, metadata={"amoId": tenant_id, "doc_id": doc.doc_id, "revision_no": doc.revision_no, "package_id": package.package_id}))
    return {"status": "ok", "distribution_event_id": dist.event_id}


@router.post("/tr", response_model=schemas.GenericOut)
def create_tr(payload: schemas.TemporaryRevisionIn, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    row = models.TemporaryRevision(tenant_id=_tenant_id(current_user), **payload.model_dump())
    db.add(row)
    _log(db, tenant_id=_tenant_id(current_user), actor_user_id=current_user.id, object_type="TemporaryRevision", object_id=row.tr_id, action="create", before=None, after=payload.model_dump(mode="json"))
    db.commit()
    return {"id": row.tr_id}


@router.post("/tr/{tr_id}/transition")
def transition_tr(tr_id: str, payload: schemas.PublishTRIn, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    row = db.query(models.TemporaryRevision).filter_by(tenant_id=_tenant_id(current_user), tr_id=tr_id).first()
    if not row:
        raise HTTPException(404, "TR not found")
    if payload.status == "InForce" and not row.updated_lep_asset_id:
        raise HTTPException(400, "updated_lep_asset_id required for InForce")
    if payload.status == "Incorporated" and not payload.incorporated_revision_package_id:
        raise HTTPException(400, "incorporated revision package required")
    before = {"status": row.status}
    row.status = payload.status
    row.incorporated_revision_package_id = payload.incorporated_revision_package_id
    if payload.status == "InForce":
        publish_event(EventEnvelope(id=str(uuid.uuid4()), type="doc_control.tr_in_force", entityType="doc_control_tr", entityId=row.tr_id, action="in_force", timestamp=datetime.utcnow().isoformat(), actor={"userId": current_user.id}, metadata={"amoId": _tenant_id(current_user), "tr_id": row.tr_id, "doc_id": row.doc_id}))
    _log(db, tenant_id=_tenant_id(current_user), actor_user_id=current_user.id, object_type="TemporaryRevision", object_id=row.tr_id, action="transition", before=before, after={"status": row.status})
    db.commit()
    return {"status": "ok"}


@router.post("/tr/expire")
def expire_trs(db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    rows = db.query(models.TemporaryRevision).filter(models.TemporaryRevision.tenant_id == _tenant_id(current_user), models.TemporaryRevision.status == "InForce", models.TemporaryRevision.expiry_date < date.today()).all()
    expired = []
    for row in rows:
        row.status = "Expired"
        expired.append(row.tr_id)
        publish_event(EventEnvelope(id=str(uuid.uuid4()), type="doc_control.tr_expired", entityType="doc_control_tr", entityId=row.tr_id, action="expired", timestamp=datetime.utcnow().isoformat(), actor={"userId": current_user.id}, metadata={"amoId": _tenant_id(current_user), "tr_id": row.tr_id, "doc_id": row.doc_id}))
        _log(db, tenant_id=_tenant_id(current_user), actor_user_id=current_user.id, object_type="TemporaryRevision", object_id=row.tr_id, action="auto_expire", before={"status": "InForce"}, after={"status": "Expired"})
    db.commit()
    return {"expired": expired}


@router.post("/distribution-events", response_model=schemas.GenericOut)
def create_distribution_event(payload: schemas.DistributionEventIn, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    event = models.DistributionEvent(tenant_id=_tenant_id(current_user), status="Draft", **payload.model_dump())
    db.add(event)
    _log(db, tenant_id=_tenant_id(current_user), actor_user_id=current_user.id, object_type="DistributionEvent", object_id=event.event_id, action="create", before=None, after=payload.model_dump())
    db.commit()
    return {"id": event.event_id}


@router.post("/distribution-events/{event_id}/send")
def send_distribution_event(event_id: str, method: str = Query("Portal"), db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    event = db.query(models.DistributionEvent).filter_by(tenant_id=_tenant_id(current_user), event_id=event_id).first()
    if not event:
        raise HTTPException(404, "Distribution event not found")
    event.method = method
    event.status = "Sent"
    event.sent_at = datetime.utcnow()
    _log(db, tenant_id=_tenant_id(current_user), actor_user_id=current_user.id, object_type="DistributionEvent", object_id=event.event_id, action="send", before={"status": "Draft"}, after={"status": "Sent", "sent_at": event.sent_at.isoformat()})
    db.commit()
    return {"status": "ok"}


@router.post("/acknowledgements", response_model=schemas.GenericOut)
def create_ack(payload: schemas.AcknowledgementIn, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    ack = models.Acknowledgement(tenant_id=_tenant_id(current_user), acknowledged_at=datetime.utcnow(), **payload.model_dump())
    db.add(ack)
    _log(db, tenant_id=_tenant_id(current_user), actor_user_id=current_user.id, object_type="Acknowledgement", object_id=ack.ack_id, action="create", before=None, after=payload.model_dump())
    db.commit()
    return {"id": ack.ack_id}


@router.get("/documents/{doc_id}/active-revision")
def get_active_revision(doc_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    doc = db.query(models.ControlledDocument).filter_by(tenant_id=_tenant_id(current_user), doc_id=doc_id, status="Active").first()
    if not doc:
        raise HTTPException(404, "No active revision")
    return {"doc_id": doc.doc_id, "revision_no": doc.revision_no, "effective_date": doc.effective_date}


@router.get("/documents/{doc_id}/template")
def get_template_form(doc_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    doc = db.query(models.ControlledDocument).filter_by(tenant_id=_tenant_id(current_user), doc_id=doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    return {"doc_id": doc.doc_id, "current_asset_id": doc.current_asset_id}
