"""Reader-side governance APIs layered around the immutable Publications reader."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models
from amodb.database import get_db
from amodb.security import get_current_active_user

from . import governance_models as gm
from .reader_governance_compare import compare_revisions, migration_proposal
from .reader_governance_evidence import evidence_payload, evidence_state_for_hash, reader_manifest, stable_json_sha
from .reader_link_validation import validate_qms_link
from .reader_governance_models import DocumentAnnotationMigration, DocumentEvidenceSnapshot
from .workspace_service import (
    get_manual,
    get_profile,
    get_revision,
    is_control_user,
    require_control_user,
    require_manual_access,
    resolve_tenant,
)


router = APIRouter(prefix="/workspace", tags=["Document Control Reader Governance"])

ANNOTATION_TYPES = {"HIGHLIGHT", "NOTE", "QUESTION", "BOOKMARK", "EVIDENCE", "FINDING"}
ANNOTATION_VISIBILITY = {"PRIVATE", "TEAM", "CONTROL"}
ANNOTATION_STATUS = {"ACTIVE", "RESOLVED", "ARCHIVED"}


class ReaderLocationInput(BaseModel):
    location_type: str = Field(default="PAGE", min_length=2, max_length=32)
    page_number: int | None = Field(default=None, ge=1)
    normalized_rects: list[dict[str, float]] = Field(default_factory=list, max_length=100)
    exact_quote: str | None = Field(default=None, max_length=4000)
    prefix_context: str | None = Field(default=None, max_length=2000)
    suffix_context: str | None = Field(default=None, max_length=2000)
    section_id: str | None = None
    block_id: str | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    sheet_name: str | None = Field(default=None, max_length=255)
    cell_range: str | None = Field(default=None, max_length=128)
    slide_number: int | None = Field(default=None, ge=1)
    object_id: str | None = Field(default=None, max_length=255)
    image_region: dict[str, Any] = Field(default_factory=dict)
    adapter_name: str | None = Field(default=None, max_length=64)
    adapter_version: str = Field(default="1", min_length=1, max_length=64)


class AnnotationCreate(BaseModel):
    expected_source_sha256: str = Field(min_length=64, max_length=64)
    annotation_type: str = Field(min_length=2, max_length=32)
    color: str = Field(default="YELLOW", min_length=2, max_length=16)
    visibility: str = Field(default="PRIVATE", min_length=2, max_length=24)
    note_text: str | None = Field(default=None, max_length=20000)
    tags: list[str] = Field(default_factory=list, max_length=50)
    linked_entity_type: str | None = Field(default=None, max_length=48)
    linked_entity_id: str | None = Field(default=None, max_length=128)
    location: ReaderLocationInput


class AnnotationUpdate(BaseModel):
    note_text: str | None = Field(default=None, max_length=20000)
    tags: list[str] | None = Field(default=None, max_length=50)
    color: str | None = Field(default=None, min_length=2, max_length=16)
    visibility: str | None = Field(default=None, min_length=2, max_length=24)
    status: str | None = Field(default=None, min_length=2, max_length=24)


class MigrationPrepare(BaseModel):
    source_revision_id: str
    target_revision_id: str


class MigrationDecision(BaseModel):
    decision: Literal["ACCEPT", "REJECT"]
    comments: str = Field(min_length=3, max_length=4000)


def _audit(db: Session, tenant: manual_models.Tenant, user: account_models.User, request: Request, action: str, entity_type: str, entity_id: str, diff: dict[str, Any]) -> None:
    db.add(manual_models.ManualAuditLog(
        tenant_id=tenant.id,
        actor_id=user.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_device=f"{request.client.host if request.client else 'unknown'}::{request.headers.get('user-agent', 'n/a')}",
        diff_json=diff,
    ))


def _location_dict(row: gm.DocumentLocation | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": row.id,
        "location_key": row.location_key,
        "location_type": row.location_type,
        "page_number": row.page_number,
        "normalized_rects": list(row.normalized_rects_json or []),
        "exact_quote": row.exact_quote,
        "prefix_context": row.prefix_context,
        "suffix_context": row.suffix_context,
        "section_id": row.section_id,
        "block_id": row.block_id,
        "char_start": row.char_start,
        "char_end": row.char_end,
        "sheet_name": row.sheet_name,
        "cell_range": row.cell_range,
        "slide_number": row.slide_number,
        "object_id": row.object_id,
        "image_region": dict(row.image_region_json or {}),
        "adapter_name": row.adapter_name,
        "adapter_version": row.adapter_version,
        "source_sha256": row.source_sha256,
    }


def _annotation_dict(db: Session, row: gm.DocumentAnnotation, tenant_slug: str) -> dict[str, Any]:
    location = db.query(gm.DocumentLocation).filter(gm.DocumentLocation.id == row.location_id).first()
    anchor = f"#pdf-page-{location.page_number}" if location and location.page_number else ""
    return {
        "id": row.id,
        "manual_id": row.manual_id,
        "revision_id": row.revision_id,
        "annotation_type": row.annotation_type,
        "color": row.color,
        "visibility": row.visibility,
        "note_text": row.note_text,
        "tags": list(row.tags_json or []),
        "linked_entity_type": row.linked_entity_type,
        "linked_entity_id": row.linked_entity_id,
        "status": row.status,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "location": _location_dict(location),
        "reader_url": f"/maintenance/{tenant_slug}/publications/{row.manual_id}/rev/{row.revision_id}/read?annotation={row.id}{anchor}",
    }


def _canonical_location(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _ensure_location(db: Session, *, tenant: manual_models.Tenant, manual: manual_models.Manual, revision: manual_models.ManualRevision, payload: dict[str, Any], key_seed: str | None = None) -> gm.DocumentLocation:
    if not revision.source_sha256:
        raise HTTPException(status_code=409, detail="The revision has no source checksum; governed locations cannot be created")
    canonical = _canonical_location(payload)
    location_key = hashlib.sha256(f"{revision.id}:{key_seed or canonical}".encode()).hexdigest()
    existing = db.query(gm.DocumentLocation).filter(
        gm.DocumentLocation.tenant_id == tenant.amo_id,
        gm.DocumentLocation.revision_id == revision.id,
        gm.DocumentLocation.location_key == location_key,
    ).first()
    if existing:
        if existing.source_sha256 != revision.source_sha256:
            raise HTTPException(status_code=409, detail="Stored location checksum does not match the immutable revision")
        return existing
    section_id = payload.get("section_id")
    if section_id:
        valid_section = db.query(manual_models.ManualSection).filter(
            manual_models.ManualSection.id == section_id,
            manual_models.ManualSection.revision_id == revision.id,
        ).first()
        if not valid_section:
            raise HTTPException(status_code=422, detail="Annotation section is outside the selected revision")
    block_id = payload.get("block_id")
    if block_id:
        valid_block = db.query(manual_models.ManualBlock).join(
            manual_models.ManualSection, manual_models.ManualSection.id == manual_models.ManualBlock.section_id,
        ).filter(
            manual_models.ManualBlock.id == block_id,
            manual_models.ManualSection.revision_id == revision.id,
        ).first()
        if not valid_block:
            raise HTTPException(status_code=422, detail="Annotation block is outside the selected revision")
    adapter = payload.get("adapter_name") or ("PDF_CANONICAL_PAGE" if payload.get("page_number") else "SEMANTIC_SECTION_BLOCK")
    row = gm.DocumentLocation(
        tenant_id=tenant.amo_id,
        manual_id=manual.id,
        revision_id=revision.id,
        source_sha256=revision.source_sha256,
        location_key=location_key,
        location_type=str(payload.get("location_type") or "PAGE").upper(),
        page_number=payload.get("page_number"),
        normalized_rects_json=list(payload.get("normalized_rects") or []),
        exact_quote=payload.get("exact_quote"),
        prefix_context=payload.get("prefix_context"),
        suffix_context=payload.get("suffix_context"),
        section_id=section_id,
        block_id=block_id,
        char_start=payload.get("char_start"),
        char_end=payload.get("char_end"),
        sheet_name=payload.get("sheet_name"),
        cell_range=payload.get("cell_range"),
        slide_number=payload.get("slide_number"),
        object_id=payload.get("object_id"),
        image_region_json=dict(payload.get("image_region") or {}),
        adapter_name=adapter,
        adapter_version=str(payload.get("adapter_version") or "1"),
    )
    db.add(row)
    db.flush()
    return row


def _context(db: Session, tenant_slug: str, manual_id: str, revision_id: str, user: account_models.User):
    tenant = resolve_tenant(db, tenant_slug, user)
    manual = get_manual(db, tenant, manual_id)
    require_manual_access(user, get_profile(db, tenant, manual.id))
    revision = get_revision(db, manual, revision_id)
    return tenant, manual, revision


@router.get("/t/{tenant_slug}/reader/documents/{manual_id}/revisions/{revision_id}/manifest")
def get_manifest(tenant_slug: str, manual_id: str, revision_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    tenant, manual, revision = _context(db, tenant_slug, manual_id, revision_id, current_user)
    revisions = db.query(manual_models.ManualRevision).filter(manual_models.ManualRevision.manual_id == manual.id).order_by(manual_models.ManualRevision.created_at.desc()).all()
    payload = reader_manifest(db, tenant, manual, revision)
    payload["revision_options"] = [{"id": row.id, "revision_number": row.rev_number, "issue_number": row.issue_number, "status": str(getattr(row.status_enum, "value", row.status_enum)), "effective_date": row.effective_date.isoformat() if row.effective_date else None, "source_sha256": row.source_sha256} for row in revisions]
    payload["capabilities"]["control"] = is_control_user(current_user)
    return payload


@router.get("/t/{tenant_slug}/reader/documents/{manual_id}/revisions/{revision_id}/annotations")
def list_annotations(tenant_slug: str, manual_id: str, revision_id: str, status: str = "ACTIVE", db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    tenant, _manual, _revision = _context(db, tenant_slug, manual_id, revision_id, current_user)
    query = db.query(gm.DocumentAnnotation).filter(gm.DocumentAnnotation.tenant_id == tenant.amo_id, gm.DocumentAnnotation.manual_id == manual_id, gm.DocumentAnnotation.revision_id == revision_id)
    if status:
        query = query.filter(gm.DocumentAnnotation.status == status.upper())
    if not is_control_user(current_user):
        query = query.filter(or_(gm.DocumentAnnotation.visibility != "PRIVATE", gm.DocumentAnnotation.created_by_user_id == current_user.id))
    rows = query.order_by(gm.DocumentAnnotation.created_at.desc()).limit(1000).all()
    return {"items": [_annotation_dict(db, row, tenant_slug) for row in rows], "capabilities": {"control": is_control_user(current_user), "create": True}}


@router.post("/t/{tenant_slug}/reader/documents/{manual_id}/revisions/{revision_id}/annotations")
def create_annotation(tenant_slug: str, manual_id: str, revision_id: str, payload: AnnotationCreate, request: Request, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    tenant, manual, revision = _context(db, tenant_slug, manual_id, revision_id, current_user)
    annotation_type = payload.annotation_type.upper()
    visibility = payload.visibility.upper()
    if annotation_type not in ANNOTATION_TYPES or visibility not in ANNOTATION_VISIBILITY:
        raise HTTPException(status_code=422, detail="Unsupported annotation type or visibility")
    if payload.expected_source_sha256.lower() != str(revision.source_sha256 or "").lower():
        raise HTTPException(status_code=409, detail="The source revision changed or has no matching checksum; reopen the document before annotating")
    if (visibility != "PRIVATE" or annotation_type in {"EVIDENCE", "FINDING"}) and not is_control_user(current_user):
        raise HTTPException(status_code=403, detail="Shared, controlled-evidence and finding annotations require Document Control privileges")
    linked = validate_qms_link(db, tenant_id=tenant.amo_id, entity_type=payload.linked_entity_type, entity_id=payload.linked_entity_id)
    location = _ensure_location(db, tenant=tenant, manual=manual, revision=revision, payload=payload.location.model_dump())
    row = gm.DocumentAnnotation(
        tenant_id=tenant.amo_id,
        manual_id=manual.id,
        revision_id=revision.id,
        location_id=location.id,
        source_sha256=revision.source_sha256,
        annotation_type=annotation_type,
        color=payload.color.upper(),
        visibility=visibility,
        note_text=payload.note_text,
        tags_json=list(dict.fromkeys(tag.strip() for tag in payload.tags if tag.strip())),
        linked_entity_type=linked["entity_type"] if linked else None,
        linked_entity_id=linked["entity_id"] if linked else None,
        status="ACTIVE",
        created_by_user_id=current_user.id,
    )
    db.add(row)
    db.flush()
    _audit(db, tenant, current_user, request, "documentation.annotation.created", "document_annotation", row.id, {"manual_id": manual.id, "revision_id": revision.id, "type": annotation_type, "visibility": visibility, "location_id": location.id, "linked_entity": linked})
    db.commit()
    return _annotation_dict(db, row, tenant_slug)


@router.patch("/t/{tenant_slug}/reader/documents/{manual_id}/revisions/{revision_id}/annotations/{annotation_id}")
def update_annotation(tenant_slug: str, manual_id: str, revision_id: str, annotation_id: str, payload: AnnotationUpdate, request: Request, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    tenant, _manual, revision = _context(db, tenant_slug, manual_id, revision_id, current_user)
    row = db.query(gm.DocumentAnnotation).filter(gm.DocumentAnnotation.id == annotation_id, gm.DocumentAnnotation.tenant_id == tenant.amo_id, gm.DocumentAnnotation.manual_id == manual_id, gm.DocumentAnnotation.revision_id == revision.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Annotation not found")
    if row.created_by_user_id != current_user.id and not is_control_user(current_user):
        raise HTTPException(status_code=403, detail="Only the annotation owner or Document Control may update this annotation")
    if row.source_sha256 != revision.source_sha256:
        raise HTTPException(status_code=409, detail="Annotation checksum no longer matches the selected revision")
    update = payload.model_dump(exclude_unset=True)
    if "visibility" in update:
        visibility = str(update["visibility"] or "").upper()
        if visibility not in ANNOTATION_VISIBILITY:
            raise HTTPException(status_code=422, detail="Unsupported annotation visibility")
        if visibility != "PRIVATE" and not is_control_user(current_user):
            raise HTTPException(status_code=403, detail="Only Document Control may publish shared annotations")
        row.visibility = visibility
    if "status" in update:
        status_value = str(update["status"] or "").upper()
        if status_value not in ANNOTATION_STATUS:
            raise HTTPException(status_code=422, detail="Unsupported annotation status")
        row.status = status_value
    if "note_text" in update:
        row.note_text = update["note_text"]
    if "color" in update and update["color"]:
        row.color = str(update["color"]).upper()
    if "tags" in update:
        row.tags_json = list(dict.fromkeys(tag.strip() for tag in (update["tags"] or []) if tag.strip()))
    _audit(db, tenant, current_user, request, "documentation.annotation.updated", "document_annotation", row.id, {"changes": sorted(update)})
    db.commit()
    return _annotation_dict(db, row, tenant_slug)


@router.get("/t/{tenant_slug}/reader/documents/{manual_id}/revisions/{revision_id}/evidence")
def get_evidence(tenant_slug: str, manual_id: str, revision_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    tenant, manual, revision = _context(db, tenant_slug, manual_id, revision_id, current_user)
    payload = evidence_payload(db, tenant, manual, revision, current_user)
    payload["capabilities"] = {"control": is_control_user(current_user), "snapshot": is_control_user(current_user)}
    return payload


@router.get("/t/{tenant_slug}/reader/documents/{manual_id}/revisions/{revision_id}/evidence/snapshots")
def list_evidence_snapshots(tenant_slug: str, manual_id: str, revision_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    tenant, _manual, _revision = _context(db, tenant_slug, manual_id, revision_id, current_user)
    rows = db.query(DocumentEvidenceSnapshot).filter(DocumentEvidenceSnapshot.tenant_id == tenant.amo_id, DocumentEvidenceSnapshot.manual_id == manual_id, DocumentEvidenceSnapshot.revision_id == revision_id).order_by(DocumentEvidenceSnapshot.created_at.desc()).limit(250).all()
    return [{"id": row.id, "snapshot_sha256": row.snapshot_sha256, "source_sha256": row.source_sha256, "schema_version": row.schema_version, "created_by_user_id": row.created_by_user_id, "created_at": row.created_at.isoformat() if row.created_at else None} for row in rows]


@router.get("/t/{tenant_slug}/reader/documents/{manual_id}/revisions/{revision_id}/evidence/snapshots/{snapshot_id}")
def get_evidence_snapshot(tenant_slug: str, manual_id: str, revision_id: str, snapshot_id: str, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    require_control_user(current_user)
    tenant, _manual, _revision = _context(db, tenant_slug, manual_id, revision_id, current_user)
    row = db.query(DocumentEvidenceSnapshot).filter(DocumentEvidenceSnapshot.id == snapshot_id, DocumentEvidenceSnapshot.tenant_id == tenant.amo_id, DocumentEvidenceSnapshot.manual_id == manual_id, DocumentEvidenceSnapshot.revision_id == revision_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Evidence snapshot not found")
    payload = dict(row.payload_json or {})
    recomputed = stable_json_sha(evidence_state_for_hash(payload))
    return {"id": row.id, "snapshot_sha256": row.snapshot_sha256, "source_sha256": row.source_sha256, "schema_version": row.schema_version, "created_by_user_id": row.created_by_user_id, "created_at": row.created_at.isoformat() if row.created_at else None, "integrity_valid": recomputed == row.snapshot_sha256, "recomputed_sha256": recomputed, "payload": payload}


@router.post("/t/{tenant_slug}/reader/documents/{manual_id}/revisions/{revision_id}/evidence/snapshots")
def create_evidence_snapshot(tenant_slug: str, manual_id: str, revision_id: str, request: Request, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    require_control_user(current_user)
    tenant, manual, revision = _context(db, tenant_slug, manual_id, revision_id, current_user)
    payload = evidence_payload(db, tenant, manual, revision, current_user)
    digest = stable_json_sha(evidence_state_for_hash(payload))
    existing = db.query(DocumentEvidenceSnapshot).filter(DocumentEvidenceSnapshot.tenant_id == tenant.amo_id, DocumentEvidenceSnapshot.snapshot_sha256 == digest).first()
    if existing:
        return {"id": existing.id, "snapshot_sha256": existing.snapshot_sha256, "created_at": existing.created_at.isoformat() if existing.created_at else None, "reused": True}
    row = DocumentEvidenceSnapshot(tenant_id=tenant.amo_id, manual_id=manual.id, revision_id=revision.id, source_sha256=revision.source_sha256, snapshot_sha256=digest, schema_version=1, payload_json=payload, created_by_user_id=current_user.id)
    db.add(row)
    db.flush()
    _audit(db, tenant, current_user, request, "documentation.evidence.snapshot_created", "document_evidence_snapshot", row.id, {"revision_id": revision.id, "source_sha256": revision.source_sha256, "snapshot_sha256": digest})
    db.commit()
    return {"id": row.id, "snapshot_sha256": row.snapshot_sha256, "created_at": row.created_at.isoformat() if row.created_at else None, "reused": False}


@router.get("/t/{tenant_slug}/reader/documents/{manual_id}/compare")
def get_revision_comparison(tenant_slug: str, manual_id: str, source_revision_id: str = Query(...), target_revision_id: str = Query(...), db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    require_manual_access(current_user, get_profile(db, tenant, manual.id))
    source = get_revision(db, manual, source_revision_id)
    target = get_revision(db, manual, target_revision_id)
    comparison = compare_revisions(db, source, target)
    annotations = db.query(gm.DocumentAnnotation).filter(gm.DocumentAnnotation.tenant_id == tenant.amo_id, gm.DocumentAnnotation.revision_id == source.id, gm.DocumentAnnotation.status == "ACTIVE").all()
    if not is_control_user(current_user):
        annotations = [row for row in annotations if row.visibility != "PRIVATE" or row.created_by_user_id == current_user.id]
    comparison["annotation_proposals"] = [{"annotation": _annotation_dict(db, row, tenant_slug), "proposal": migration_proposal(db, row, comparison)} for row in annotations]
    comparison["capabilities"] = {"control": is_control_user(current_user), "prepare_migrations": is_control_user(current_user)}
    return comparison


@router.post("/t/{tenant_slug}/reader/documents/{manual_id}/annotation-migrations/prepare")
def prepare_annotation_migrations(tenant_slug: str, manual_id: str, payload: MigrationPrepare, request: Request, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    source = get_revision(db, manual, payload.source_revision_id)
    target = get_revision(db, manual, payload.target_revision_id)
    comparison = compare_revisions(db, source, target)
    annotations = db.query(gm.DocumentAnnotation).filter(gm.DocumentAnnotation.tenant_id == tenant.amo_id, gm.DocumentAnnotation.revision_id == source.id, gm.DocumentAnnotation.status == "ACTIVE").all()
    created = 0
    for annotation in annotations:
        proposal = migration_proposal(db, annotation, comparison)
        row = db.query(DocumentAnnotationMigration).filter(DocumentAnnotationMigration.tenant_id == tenant.amo_id, DocumentAnnotationMigration.source_annotation_id == annotation.id, DocumentAnnotationMigration.target_revision_id == target.id).first()
        if not row:
            row = DocumentAnnotationMigration(tenant_id=tenant.amo_id, manual_id=manual.id, source_annotation_id=annotation.id, source_revision_id=source.id, target_revision_id=target.id)
            db.add(row)
            created += 1
        if row.status == "PENDING":
            row.proposed_location_json = dict(proposal.get("location") or {})
            row.migration_strategy = str(proposal.get("strategy") or "UNRESOLVED")
            row.confidence_percent = int(proposal.get("confidence_percent") or 0)
            row.reason = str(proposal.get("reason") or "")
    _audit(db, tenant, current_user, request, "documentation.annotation_migrations.prepared", "manual_revision", target.id, {"source_revision_id": source.id, "target_revision_id": target.id, "annotation_count": len(annotations), "created": created})
    db.commit()
    return {"source_revision_id": source.id, "target_revision_id": target.id, "prepared": len(annotations), "created": created, "comparison_summary": comparison["summary"]}


@router.get("/t/{tenant_slug}/reader/documents/{manual_id}/annotation-migrations")
def list_annotation_migrations(tenant_slug: str, manual_id: str, target_revision_id: str | None = None, status: str | None = None, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    query = db.query(DocumentAnnotationMigration).filter(DocumentAnnotationMigration.tenant_id == tenant.amo_id, DocumentAnnotationMigration.manual_id == manual.id)
    if target_revision_id:
        get_revision(db, manual, target_revision_id)
        query = query.filter(DocumentAnnotationMigration.target_revision_id == target_revision_id)
    if status:
        query = query.filter(DocumentAnnotationMigration.status == status.upper())
    rows = query.order_by(DocumentAnnotationMigration.created_at.desc()).limit(1000).all()
    return [{"id": row.id, "source_annotation_id": row.source_annotation_id, "source_revision_id": row.source_revision_id, "target_revision_id": row.target_revision_id, "strategy": row.migration_strategy, "confidence_percent": row.confidence_percent, "status": row.status, "reason": row.reason, "proposed_location": dict(row.proposed_location_json or {}), "target_annotation_id": row.target_annotation_id, "reviewed_by_user_id": row.reviewed_by_user_id, "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None} for row in rows]


@router.patch("/t/{tenant_slug}/reader/documents/{manual_id}/annotation-migrations/{migration_id}")
def decide_annotation_migration(tenant_slug: str, manual_id: str, migration_id: str, payload: MigrationDecision, request: Request, db: Session = Depends(get_db), current_user: account_models.User = Depends(get_current_active_user)):
    require_control_user(current_user)
    tenant = resolve_tenant(db, tenant_slug, current_user)
    manual = get_manual(db, tenant, manual_id)
    row = db.query(DocumentAnnotationMigration).filter(DocumentAnnotationMigration.id == migration_id, DocumentAnnotationMigration.tenant_id == tenant.amo_id, DocumentAnnotationMigration.manual_id == manual.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Annotation migration review item not found")
    if row.status != "PENDING":
        raise HTTPException(status_code=409, detail="This migration decision is already terminal")
    source_annotation = db.query(gm.DocumentAnnotation).filter(gm.DocumentAnnotation.id == row.source_annotation_id, gm.DocumentAnnotation.tenant_id == tenant.amo_id).first()
    if not source_annotation:
        raise HTTPException(status_code=409, detail="Source annotation is no longer available")
    target_revision = get_revision(db, manual, row.target_revision_id)
    if payload.decision == "REJECT":
        row.status = "REJECTED"
        row.reason = f"{row.reason or ''}\nReview: {payload.comments}".strip()
    else:
        if not target_revision.source_sha256:
            raise HTTPException(status_code=409, detail="Target revision has no source checksum")
        proposal = dict(row.proposed_location_json or {})
        if row.migration_strategy == "UNRESOLVED" or not proposal:
            raise HTTPException(status_code=409, detail="Unresolved migrations cannot be accepted; establish a target location first")
        location = _ensure_location(db, tenant=tenant, manual=manual, revision=target_revision, payload=proposal, key_seed=f"migration:{row.id}")
        target = gm.DocumentAnnotation(tenant_id=tenant.amo_id, manual_id=manual.id, revision_id=target_revision.id, location_id=location.id, source_sha256=target_revision.source_sha256, annotation_type=source_annotation.annotation_type, color=source_annotation.color, visibility=source_annotation.visibility, note_text=source_annotation.note_text, tags_json=list(source_annotation.tags_json or []), linked_entity_type=source_annotation.linked_entity_type, linked_entity_id=source_annotation.linked_entity_id, status="ACTIVE", created_by_user_id=source_annotation.created_by_user_id)
        db.add(target)
        db.flush()
        row.target_annotation_id = target.id
        row.status = "ACCEPTED"
        row.reason = f"{row.reason or ''}\nReview: {payload.comments}".strip()
    row.reviewed_by_user_id = current_user.id
    row.reviewed_at = datetime.utcnow()
    _audit(db, tenant, current_user, request, "documentation.annotation_migration.reviewed", "document_annotation_migration", row.id, {"decision": payload.decision, "source_annotation_id": row.source_annotation_id, "target_revision_id": row.target_revision_id, "target_annotation_id": row.target_annotation_id, "comments": payload.comments})
    db.commit()
    return {"id": row.id, "status": row.status, "target_annotation_id": row.target_annotation_id, "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None}
