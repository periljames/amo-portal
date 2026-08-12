from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import workspace_schemas as schemas
from .workspace_evidence_router import validate_evidence_references
from .workspace_router import (
    create_external_revision_receipt as _create_external_revision_receipt,
    create_external_source as _create_external_source,
)
from .workspace_service import (
    audit,
    get_manual,
    get_profile,
    require_control_user,
    resolve_tenant,
)


router = APIRouter(prefix="/workspace", tags=["Document Control External Sources"])


def validate_external_receipt(
    source: dm.ExternalDocumentSource,
    payload: schemas.ExternalRevisionReceiptCreate,
) -> None:
    if source.status != "ACTIVE":
        raise HTTPException(
            status_code=409,
            detail="Revisions cannot be received against an inactive external source",
        )
    if payload.publication_date and payload.publication_date > date.today():
        raise HTTPException(
            status_code=422,
            detail="External revision publication date cannot be in the future",
        )
    if payload.checksum_sha256 and not re.fullmatch(
        r"[0-9a-fA-F]{64}", payload.checksum_sha256
    ):
        raise HTTPException(
            status_code=422,
            detail="External revision checksum must be a 64-character SHA-256 hexadecimal digest",
        )

    retained_evidence = bool(payload.evidence or payload.checksum_sha256)
    if payload.currency_status == "CURRENT" and not retained_evidence:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "EXTERNAL_CURRENCY_EVIDENCE_REQUIRED",
                "message": "A checksum or retained source evidence is required before an external revision is marked current.",
            },
        )
    if payload.applicability_status in {
        "APPLICABLE",
        "NOT_APPLICABLE",
        "PARTIAL",
    } and not payload.evidence:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "EXTERNAL_APPLICABILITY_EVIDENCE_REQUIRED",
                "message": "A concluded applicability assessment requires retained evidence.",
            },
        )
    if payload.currency_status == "UNKNOWN" and not str(payload.notes or "").strip():
        raise HTTPException(
            status_code=422,
            detail="Unknown external revision currency requires an explanatory note",
        )


@router.post("/t/{tenant_slug}/external-sources", include_in_schema=False)
def create_classified_external_source(
    tenant_slug: str,
    payload: schemas.ExternalSourceCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, payload.manual_id)
    profile = get_profile(db, tenant, manual.id)
    if not profile or profile.document_class != "EXTERNAL":
        raise HTTPException(
            status_code=409,
            detail="Classify the document as EXTERNAL before registering its technical-data source",
        )
    return _create_external_source(
        tenant_slug=tenant_slug,
        payload=payload,
        request=request,
        db=db,
        current_user=current_user,
    )


@router.post(
    "/t/{tenant_slug}/external-sources/{source_id}/receipts",
    include_in_schema=False,
)
def create_evidenced_external_revision_receipt(
    tenant_slug: str,
    source_id: str,
    payload: schemas.ExternalRevisionReceiptCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    source = (
        db.query(dm.ExternalDocumentSource)
        .filter(
            dm.ExternalDocumentSource.tenant_id == tenant.amo_id,
            dm.ExternalDocumentSource.id == source_id,
        )
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="External document source not found")
    normalized_evidence = validate_evidence_references(
        db,
        tenant_id=tenant.amo_id,
        manual_id=source.manual_id,
        evidence=list(payload.evidence or []),
    )
    payload = payload.model_copy(update={"evidence": normalized_evidence})
    validate_external_receipt(source, payload)
    if payload.checksum_sha256:
        payload = payload.model_copy(
            update={"checksum_sha256": payload.checksum_sha256.lower()}
        )

    duplicate = (
        db.query(dm.ExternalRevisionReceipt)
        .filter(
            dm.ExternalRevisionReceipt.tenant_id == tenant.amo_id,
            dm.ExternalRevisionReceipt.source_id == source.id,
            func.lower(dm.ExternalRevisionReceipt.revision_label)
            == payload.revision_label.strip().lower(),
        )
        .first()
    )
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "EXTERNAL_REVISION_ALREADY_RECEIVED",
                "message": "This external revision label has already been recorded for the source.",
                "receipt_id": duplicate.id,
            },
        )

    if payload.currency_status == "CURRENT":
        previous_current = (
            db.query(dm.ExternalRevisionReceipt)
            .filter(
                dm.ExternalRevisionReceipt.tenant_id == tenant.amo_id,
                dm.ExternalRevisionReceipt.source_id == source.id,
                dm.ExternalRevisionReceipt.currency_status == "CURRENT",
            )
            .all()
        )
        for previous in previous_current:
            previous.currency_status = "SUPERSEDED"
            audit(
                db,
                tenant,
                request,
                "document.external_revision.superseded",
                "external_revision_receipt",
                previous.id,
                {
                    "superseded_by_revision_label": payload.revision_label.strip(),
                    "source_id": source.id,
                },
            )

    return _create_external_revision_receipt(
        tenant_slug=tenant_slug,
        source_id=source_id,
        payload=payload,
        request=request,
        db=db,
        current_user=current_user,
    )
