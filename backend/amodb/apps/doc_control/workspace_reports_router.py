from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import domain_models as dm
from . import models as legacy_models
from .workspace_service import (
    audit,
    can_read_manual,
    get_manual,
    get_profile,
    get_revision,
    is_control_user,
    latest_revision,
    require_control_user,
    require_manual_access,
    resolve_tenant,
    serialize_revision,
    status_value,
    utcnow,
)


router = APIRouter(prefix="/workspace", tags=["Document Control Reports and Settings"])


class WorkspaceSettingsIn(BaseModel):
    default_retention_years: int = Field(default=5, ge=1, le=100)
    default_review_interval_months: int = Field(default=24, ge=1, le=120)
    regulated_workflow_enabled: bool = False
    default_ack_required: bool = True


class DocumentMetadataUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=64)
    manual_type: str | None = Field(default=None, min_length=1, max_length=64)
    owner_role: str | None = Field(default=None, min_length=1, max_length=64)


@router.get("/t/{tenant_slug}/settings")
def get_workspace_settings(
    tenant_slug: str,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = db.query(legacy_models.DocControlSettings).filter(legacy_models.DocControlSettings.tenant_id == tenant.amo_id).first()
    if not row:
        return {
            "tenant_id": tenant.amo_id,
            "default_retention_years": 5,
            "default_review_interval_months": 24,
            "regulated_workflow_enabled": False,
            "default_ack_required": True,
            "configured": False,
        }
    return {
        "tenant_id": row.tenant_id,
        "default_retention_years": row.default_retention_years,
        "default_review_interval_months": row.default_review_interval_months,
        "regulated_workflow_enabled": row.regulated_workflow_enabled,
        "default_ack_required": row.default_ack_required,
        "configured": True,
    }


@router.put("/t/{tenant_slug}/settings")
def update_workspace_settings(
    tenant_slug: str,
    payload: WorkspaceSettingsIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    row = db.query(legacy_models.DocControlSettings).filter(legacy_models.DocControlSettings.tenant_id == tenant.amo_id).first()
    before = None
    if row:
        before = {
            "default_retention_years": row.default_retention_years,
            "default_review_interval_months": row.default_review_interval_months,
            "regulated_workflow_enabled": row.regulated_workflow_enabled,
            "default_ack_required": row.default_ack_required,
        }
    else:
        row = legacy_models.DocControlSettings(tenant_id=tenant.amo_id)
        db.add(row)
    row.default_retention_years = payload.default_retention_years
    row.default_review_interval_months = payload.default_review_interval_months
    row.regulated_workflow_enabled = payload.regulated_workflow_enabled
    row.default_ack_required = payload.default_ack_required
    after = payload.model_dump()
    audit(db, tenant, request, "document.settings.updated", "document_control_settings", tenant.amo_id, {"before": before, "after": after})
    db.commit()
    return {"tenant_id": tenant.amo_id, **after, "configured": True}


@router.patch("/t/{tenant_slug}/documents/{manual_id}/metadata")
def update_document_metadata(
    tenant_slug: str,
    manual_id: str,
    payload: DocumentMetadataUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    before = {
        "code": manual.code,
        "title": manual.title,
        "manual_type": manual.manual_type,
        "owner_role": manual.owner_role,
    }
    update = payload.model_dump(exclude_unset=True)
    for key, value in update.items():
        if value is not None:
            setattr(manual, key, value.strip())
    try:
        db.flush()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="The publication code must be unique within the tenant") from exc
    after = {
        "id": manual.id,
        "code": manual.code,
        "title": manual.title,
        "manual_type": manual.manual_type,
        "owner_role": manual.owner_role,
    }
    audit(db, tenant, request, "document.metadata.updated", "manual", manual.id, {"before": before, "after": after})
    db.commit()
    return after


@router.get("/t/{tenant_slug}/archive")
def archive_register(
    tenant_slug: str,
    manual_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    query = (
        db.query(manual_models.ManualRevision, manual_models.Manual)
        .join(manual_models.Manual, manual_models.Manual.id == manual_models.ManualRevision.manual_id)
        .filter(
            manual_models.Manual.tenant_id == tenant.id,
            manual_models.ManualRevision.status_enum.in_([
                manual_models.ManualRevisionStatus.SUPERSEDED,
                manual_models.ManualRevisionStatus.ARCHIVED,
            ]),
        )
    )
    if manual_id:
        manual = get_manual(db, tenant, manual_id)
        require_manual_access(current_user, get_profile(db, tenant, manual.id))
        query = query.filter(manual_models.ManualRevision.manual_id == manual.id)
    items = []
    for revision, manual in query.order_by(manual_models.ManualRevision.created_at.desc()).all():
        profile = get_profile(db, tenant, manual.id)
        if not can_read_manual(current_user, profile):
            continue
        legacy_archive = (
            db.query(legacy_models.ArchiveRecord)
            .filter(
                legacy_models.ArchiveRecord.tenant_id == tenant.amo_id,
                legacy_models.ArchiveRecord.doc_id == manual.code,
                legacy_models.ArchiveRecord.revision_no == _numeric_revision(revision.rev_number),
            )
            .order_by(legacy_models.ArchiveRecord.archived_at.desc())
            .first()
        )
        items.append({
            "manual": {"id": manual.id, "code": manual.code, "title": manual.title},
            "revision": serialize_revision(revision),
            "superseded_by_revision_id": revision.superseded_by_rev_id,
            "archive_evidence": {
                "id": legacy_archive.archive_id,
                "archived_at": legacy_archive.archived_at.isoformat() if legacy_archive.archived_at else None,
                "archival_marking": legacy_archive.archival_marking,
                "retention_until": legacy_archive.retention_until.isoformat(),
                "disposal_status": legacy_archive.disposal_status,
                "evidence_asset_id": legacy_archive.evidence_asset_id,
            } if legacy_archive else None,
        })
    return {"items": items, "total": len(items)}


def _numeric_revision(value: str | None) -> int:
    try:
        return int(str(value or "0").strip())
    except ValueError:
        return 0


@router.get("/t/{tenant_slug}/documents/{manual_id}/lep")
def list_effective_pages(
    tenant_slug: str,
    manual_id: str,
    revision_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    require_manual_access(current_user, get_profile(db, tenant, manual.id))
    revision = get_revision(db, manual, revision_id) if revision_id else (
        get_revision(db, manual, manual.current_published_rev_id)
        if manual.current_published_rev_id
        else latest_revision(db, manual)
    )
    if not revision:
        raise HTTPException(status_code=404, detail="No revision is available for the List of Effective Pages")
    sections = (
        db.query(manual_models.ManualSection)
        .filter(manual_models.ManualSection.revision_id == revision.id)
        .order_by(manual_models.ManualSection.order_index.asc())
        .all()
    )
    rows = []
    seen_pages: set[int] = set()
    for section in sections:
        metadata = dict(section.metadata_json or {})
        start = _positive_int(metadata.get("page_start") or metadata.get("page") or metadata.get("source_page"))
        end = _positive_int(metadata.get("page_end")) or start
        if start:
            for page_number in range(start, max(start, end) + 1):
                if page_number in seen_pages:
                    continue
                seen_pages.add(page_number)
                rows.append({
                    "page_number": page_number,
                    "section_id": section.id,
                    "section": section.heading,
                    "issue_number": revision.issue_number,
                    "revision_number": revision.rev_number,
                    "effective_date": revision.effective_date.isoformat() if revision.effective_date else None,
                    "source": "extracted-page-map",
                })
    page_count = int(revision.source_page_count or 0)
    if not rows and page_count:
        rows = [
            {
                "page_number": page_number,
                "section_id": None,
                "section": None,
                "issue_number": revision.issue_number,
                "revision_number": revision.rev_number,
                "effective_date": revision.effective_date.isoformat() if revision.effective_date else None,
                "source": "source-page-count",
            }
            for page_number in range(1, page_count + 1)
        ]
    return {
        "manual": {"id": manual.id, "code": manual.code, "title": manual.title},
        "revision": serialize_revision(revision),
        "generated_at": utcnow().isoformat(),
        "rows": rows,
        "complete_page_map": bool(rows and len(rows) == page_count) if page_count else bool(rows),
        "warning": None if rows else "The source revision has no dependable page map. The original PDF remains authoritative.",
    }


def _positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


@router.get("/t/{tenant_slug}/documents/{manual_id}/regulation-links")
def regulation_links(
    tenant_slug: str,
    manual_id: str,
    revision_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: account_models.User = Depends(get_current_active_user),
):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    require_manual_access(current_user, get_profile(db, tenant, manual.id))
    revision_ids = [revision_id] if revision_id else [
        row.id for row in db.query(manual_models.ManualRevision.id).filter(manual_models.ManualRevision.manual_id == manual.id).all()
    ]
    links = (
        db.query(
            manual_models.ManualRequirementLink,
            manual_models.RegulationRequirement,
            manual_models.RegulationCatalog,
            manual_models.ManualSection,
        )
        .join(manual_models.RegulationRequirement, manual_models.RegulationRequirement.id == manual_models.ManualRequirementLink.requirement_id)
        .join(manual_models.RegulationCatalog, manual_models.RegulationCatalog.id == manual_models.RegulationRequirement.catalog_id)
        .outerjoin(manual_models.ManualSection, manual_models.ManualSection.id == manual_models.ManualRequirementLink.section_id)
        .filter(manual_models.ManualRequirementLink.revision_id.in_(revision_ids or ["-"]))
        .all()
    )
    return [
        {
            "id": link.id,
            "revision_id": link.revision_id,
            "section_id": link.section_id,
            "section": section.heading if section else None,
            "requirement": {
                "id": requirement.id,
                "code": requirement.code,
                "text": requirement.requirement_text,
                "applicability_tags": list(requirement.applicability_tags or []),
            },
            "instrument": {
                "id": catalog.id,
                "authority": catalog.authority,
                "name": catalog.instrument_name,
                "version": catalog.instrument_version,
                "citation": catalog.citation_text,
                "reference": catalog.url_reference,
            },
            "compliance_note": link.compliance_note,
        }
        for link, requirement, catalog, section in links
    ]
