from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.doc_control import domain_models as dm
from amodb.apps.doc_control.workspace_publication_distribution import ensure_automatic_publication_distribution
from amodb.apps.doc_control.workspace_service import (
    audit,
    get_manual,
    get_profile,
    get_revision,
    require_control_user,
    resolve_tenant,
)
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import models


router = APIRouter(
    prefix="/manuals",
    tags=["Approved Publication Intake"],
    dependencies=[Depends(get_current_active_user)],
)


class ApprovedPublicationIntake(BaseModel):
    authority_name: str = Field(default="Kenya Civil Aviation Authority", min_length=2, max_length=255)
    approval_reference: str = Field(min_length=2, max_length=255)
    approval_date: date
    effective_date: date | None = None
    comments: str = Field(min_length=3, max_length=2000)
    acknowledgement_required: bool = True
    notify_eligible_users: bool = True

    @model_validator(mode="after")
    def validate_dates(self):
        if self.approval_date > date.today():
            raise ValueError("approval_date cannot be in the future")
        if self.effective_date and self.effective_date < self.approval_date:
            raise ValueError("effective_date cannot be before approval_date")
        return self


def _source_type(revision: models.ManualRevision) -> str:
    raw = getattr(revision, "source_type_enum", None)
    return str(getattr(raw, "value", raw or "")).upper()


def _require_exact_pdf_source(revision: models.ManualRevision) -> Path:
    if _source_type(revision) != "PDF":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "APPROVED_INTAKE_REQUIRES_PDF",
                "message": (
                    "An already-approved publication must be registered from its final PDF so signatures, "
                    "figures, approval marks, annotations, and form appearances remain exact."
                ),
            },
        )
    raw = str(getattr(revision, "source_storage_path", "") or "").strip()
    path = Path(raw) if raw else None
    if not path or not path.exists() or not path.is_file():
        raise HTTPException(status_code=409, detail="The final approved PDF source is unavailable")
    return path


@router.post("/t/{tenant_slug}/{manual_id}/rev/{revision_id}/approved-intake")
def approve_existing_publication_intake(
    tenant_slug: str,
    manual_id: str,
    revision_id: str,
    payload: ApprovedPublicationIntake,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    revision = get_revision(db, manual, revision_id)
    _require_exact_pdf_source(revision)

    if revision.status_enum == models.ManualRevisionStatus.PUBLISHED and manual.current_published_rev_id == revision.id:
        return {
            "manual_id": manual.id,
            "revision_id": revision.id,
            "status": "PUBLISHED",
            "already_current": True,
        }

    previous = None
    if manual.current_published_rev_id and manual.current_published_rev_id != revision.id:
        previous = (
            db.query(models.ManualRevision)
            .filter(models.ManualRevision.id == manual.current_published_rev_id)
            .first()
        )
    if previous:
        previous.status_enum = models.ManualRevisionStatus.SUPERSEDED
        previous.immutable_locked = True
        previous.superseded_by_rev_id = revision.id

    approval_timestamp = datetime.combine(payload.approval_date, time.min)
    effective_date = payload.effective_date or revision.effective_date or payload.approval_date
    revision.status_enum = models.ManualRevisionStatus.PUBLISHED
    revision.published_at = approval_timestamp
    revision.effective_date = effective_date
    revision.immutable_locked = True
    revision.requires_authority_approval_bool = True
    revision.authority_approval_ref = payload.approval_reference.strip()
    manual.current_published_rev_id = revision.id
    manual.status = "ACTIVE"

    profile = get_profile(db, tenant, manual.id)
    if not profile:
        profile = dm.DocumentControlProfile(
            tenant_id=tenant.amo_id,
            manual_id=manual.id,
            owner_department=(manual.owner_role or "DOCUMENT_CONTROL").strip().upper(),
        )
        db.add(profile)
    metadata = dict(profile.metadata_json or {})
    metadata["approved_intake"] = {
        "authority_name": payload.authority_name.strip(),
        "approval_reference": payload.approval_reference.strip(),
        "approval_date": payload.approval_date.isoformat(),
        "effective_date": effective_date.isoformat(),
        "recorded_by_user_id": current_user.id,
        "recorded_at": datetime.utcnow().isoformat(),
        "source_preservation": "EXACT_PDF",
    }
    if payload.notify_eligible_users:
        distribution_policy = dict(metadata.get("distribution_policy") or {})
        distribution_policy["auto_issue_on_publish"] = True
        distribution_policy.setdefault("audience_mode", "ALL_ELIGIBLE_USERS")
        distribution_policy.setdefault("acknowledgement_due_days", 10)
        metadata["distribution_policy"] = distribution_policy
    profile.metadata_json = metadata
    profile.regulated_flag = True
    profile.requires_authority_approval = True
    profile.acknowledgement_required = payload.acknowledgement_required
    profile.version = max(1, int(profile.version or 0) + 1)

    workflow = (
        db.query(dm.DocumentWorkflowInstance)
        .filter(
            dm.DocumentWorkflowInstance.tenant_id == tenant.amo_id,
            dm.DocumentWorkflowInstance.revision_id == revision.id,
        )
        .first()
    )
    if not workflow:
        workflow = dm.DocumentWorkflowInstance(
            tenant_id=tenant.amo_id,
            manual_id=manual.id,
            revision_id=revision.id,
            created_by_user_id=current_user.id,
        )
        db.add(workflow)
        db.flush()
    from_state = workflow.state
    workflow.state = "PUBLISHED"
    workflow.requires_authority = True
    workflow.training_readiness_status = "NOT_REQUIRED"
    workflow.qms_readiness_status = "READY"
    workflow.distribution_readiness_status = "PENDING" if payload.notify_eligible_users else "NOT_REQUIRED"
    workflow.effective_at = datetime.combine(effective_date, time.min)
    workflow.version = max(1, int(workflow.version or 0) + 1)
    workflow.updated_at = datetime.utcnow()

    db.add(
        dm.DocumentWorkflowDecision(
            tenant_id=tenant.amo_id,
            workflow_id=workflow.id,
            step_code="APPROVED_SOURCE_INTAKE",
            decision="APPROVED_AND_PUBLISHED",
            actor_user_id=current_user.id,
            from_state=from_state,
            to_state="PUBLISHED",
            comments=payload.comments.strip(),
            evidence_json=[
                {
                    "reference": payload.approval_reference.strip(),
                    "authority": payload.authority_name.strip(),
                    "approval_date": payload.approval_date.isoformat(),
                    "source_sha256": revision.source_sha256,
                }
            ],
        )
    )

    authority_record = (
        db.query(dm.DocumentAuthoritySubmission)
        .filter(
            dm.DocumentAuthoritySubmission.tenant_id == tenant.amo_id,
            dm.DocumentAuthoritySubmission.revision_id == revision.id,
            dm.DocumentAuthoritySubmission.submission_reference == payload.approval_reference.strip(),
        )
        .first()
    )
    if not authority_record:
        db.add(
            dm.DocumentAuthoritySubmission(
                tenant_id=tenant.amo_id,
                manual_id=manual.id,
                revision_id=revision.id,
                workflow_id=workflow.id,
                authority_name=payload.authority_name.strip(),
                submission_reference=payload.approval_reference.strip(),
                status="APPROVED",
                submitted_at=approval_timestamp,
                submitted_by_user_id=current_user.id,
                approved_at=approval_timestamp,
                response_summary=payload.comments.strip(),
                evidence_json=[
                    {
                        "reference": payload.approval_reference.strip(),
                        "source_sha256": revision.source_sha256,
                    }
                ],
            )
        )

    db.add(
        models.ManualAIHookEvent(
            tenant_id=tenant.id,
            revision_id=revision.id,
            event_name="revision.approved_intake",
            payload_json={
                "manual_id": manual.id,
                "authority": payload.authority_name.strip(),
                "approval_reference": payload.approval_reference.strip(),
            },
        )
    )
    audit(
        db,
        tenant,
        request,
        "document.revision.approved_intake",
        "manual_revision",
        revision.id,
        {
            "manual_id": manual.id,
            "from_state": from_state,
            "authority_name": payload.authority_name.strip(),
            "approval_reference": payload.approval_reference.strip(),
            "approval_date": payload.approval_date.isoformat(),
            "effective_date": effective_date.isoformat(),
            "notify_eligible_users": payload.notify_eligible_users,
            "acknowledgement_required": payload.acknowledgement_required,
            "source_preservation": "EXACT_PDF",
        },
    )

    campaign = None
    if payload.notify_eligible_users:
        campaign = ensure_automatic_publication_distribution(
            db,
            tenant_slug=tenant_slug,
            tenant=tenant,
            workflow=workflow,
            manual=manual,
            revision=revision,
            current_user=current_user,
            request=request,
        )
    db.commit()
    return {
        "manual_id": manual.id,
        "revision_id": revision.id,
        "status": "PUBLISHED",
        "approval_reference": revision.authority_approval_ref,
        "effective_date": revision.effective_date.isoformat() if revision.effective_date else None,
        "campaign_id": campaign.id if campaign else None,
        "notifications_issued": bool(campaign),
        "source_preservation": "EXACT_PDF",
    }
