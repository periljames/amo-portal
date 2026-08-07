"""Controlled reader manifest and evidence aggregation."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.accounts import models as account_models
from amodb.apps.manuals import models as manual_models

from . import domain_models as dm
from . import governance_models as gm
from . import knowledge_models as km
from .reader_adapter_registry import resolve_adapter, supported_format_catalogue
from .workspace_service import get_profile, is_control_user


def stable_json_sha(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def evidence_state_for_hash(payload: dict[str, Any]) -> dict[str, Any]:
    """Exclude capture-time metadata so identical governed state reuses one snapshot."""
    return {key: value for key, value in payload.items() if key not in {"captured_at", "capabilities"}}


def reader_manifest(db: Session, tenant: manual_models.Tenant, manual: manual_models.Manual, revision: manual_models.ManualRevision) -> dict[str, Any]:
    section_count = db.query(manual_models.ManualSection).filter(manual_models.ManualSection.revision_id == revision.id).count()
    block_count = (
        db.query(manual_models.ManualBlock)
        .join(manual_models.ManualSection, manual_models.ManualSection.id == manual_models.ManualBlock.section_id)
        .filter(manual_models.ManualSection.revision_id == revision.id)
        .count()
    )
    source_type = str(getattr(getattr(revision, "source_type_enum", None), "value", getattr(revision, "source_type_enum", "")) or "").upper()
    mime = str(revision.source_mime_type or "")
    adapter = resolve_adapter(source_type=source_type, mime_type=mime, filename=revision.source_filename)
    revision_count = db.query(manual_models.ManualRevision).filter(manual_models.ManualRevision.manual_id == manual.id).count()
    semantic = bool(section_count)
    return {
        "manual_id": manual.id,
        "revision_id": revision.id,
        "source_type": source_type or None,
        "mime_type": mime or None,
        "source_filename": revision.source_filename,
        "source_sha256": revision.source_sha256,
        "page_count": revision.source_page_count,
        "semantic_section_count": section_count,
        "semantic_block_count": block_count,
        "renderer": adapter.renderer,
        "location_adapter": adapter.location_adapter,
        "selection_support": adapter.selection_support,
        "adapter": adapter.payload(),
        "supported_formats": supported_format_catalogue(),
        "capabilities": {
            "layout": adapter.supports_layout,
            "semantic_text": semantic,
            "annotations": bool(revision.source_sha256),
            "compare": revision_count > 1,
            "evidence": True,
            "search": adapter.search != "NONE" and (semantic or adapter.name == "PDF_CANONICAL" or adapter.ocr_mode != "NONE"),
            "derivative_rendering": adapter.derivative,
            "source_exact_layout": adapter.source_exact,
            "ocr_metadata_present": bool(revision.ocr_detected_ref or revision.ocr_verified_bool),
            "ocr_authoritative": False,
            "unsupported_safe_fallback": adapter.name == "UNSUPPORTED_SAFE_FALLBACK",
        },
    }


def evidence_payload(db: Session, tenant: manual_models.Tenant, manual: manual_models.Manual, revision: manual_models.ManualRevision, user: account_models.User) -> dict[str, Any]:
    profile = get_profile(db, tenant, manual.id)
    responsibilities = db.query(gm.DocumentResponsibilityAssignment).filter(
        gm.DocumentResponsibilityAssignment.tenant_id == tenant.amo_id,
        gm.DocumentResponsibilityAssignment.manual_id == manual.id,
    ).all()
    relationships = db.query(gm.DocumentGovernedRelationship).filter(
        gm.DocumentGovernedRelationship.tenant_id == tenant.amo_id,
        gm.DocumentGovernedRelationship.source_manual_id == manual.id,
    ).all()
    refs = db.query(km.DocumentationReference).filter(
        km.DocumentationReference.tenant_id == tenant.amo_id,
        km.DocumentationReference.source_revision_id == revision.id,
    ).all()
    index_job = db.query(km.DocumentationIndexJob).filter(
        km.DocumentationIndexJob.tenant_id == tenant.amo_id,
        km.DocumentationIndexJob.revision_id == revision.id,
    ).first()
    annotations = db.query(gm.DocumentAnnotation).filter(
        gm.DocumentAnnotation.tenant_id == tenant.amo_id,
        gm.DocumentAnnotation.revision_id == revision.id,
        gm.DocumentAnnotation.status != "ARCHIVED",
    ).all()
    if not is_control_user(user):
        annotations = [row for row in annotations if row.visibility != "PRIVATE" or row.created_by_user_id == user.id]
    workflow = db.query(dm.DocumentWorkflowInstance).filter(
        dm.DocumentWorkflowInstance.tenant_id == tenant.amo_id,
        dm.DocumentWorkflowInstance.manual_id == manual.id,
        dm.DocumentWorkflowInstance.revision_id == revision.id,
    ).order_by(dm.DocumentWorkflowInstance.created_at.desc()).first()
    audits = db.query(manual_models.ManualAuditLog).filter(
        manual_models.ManualAuditLog.tenant_id == tenant.id,
        manual_models.ManualAuditLog.entity_id.in_([manual.id, revision.id]),
    ).order_by(manual_models.ManualAuditLog.at.desc()).limit(100).all()
    return {
        "schema_version": 1,
        "captured_at": datetime.utcnow().isoformat(),
        "document": {"id": manual.id, "code": manual.code, "title": manual.title, "type": manual.manual_type, "status": manual.status},
        "revision": {
            "id": revision.id,
            "revision_number": revision.rev_number,
            "issue_number": revision.issue_number,
            "status": str(getattr(revision.status_enum, "value", revision.status_enum)),
            "effective_date": revision.effective_date.isoformat() if revision.effective_date else None,
            "published_at": revision.published_at.isoformat() if revision.published_at else None,
            "immutable_locked": bool(revision.immutable_locked),
            "source_sha256": revision.source_sha256,
            "source_filename": revision.source_filename,
            "source_mime_type": revision.source_mime_type,
            "source_page_count": revision.source_page_count,
        },
        "control_profile": {
            "document_class": profile.document_class if profile else "INTERNAL",
            "restricted": bool(profile.restricted_flag) if profile else False,
            "regulated": bool(profile.regulated_flag) if profile else False,
            "review_interval_months": profile.review_interval_months if profile else None,
            "next_review_due": profile.next_review_due.isoformat() if profile and profile.next_review_due else None,
        },
        "responsibilities": [{
            "id": row.id,
            "type": row.responsibility_type,
            "assignee_type": row.assignee_type,
            "user_id": row.assignee_user_id,
            "department_id": row.assignee_department_id,
            "org_unit_id": row.assignee_org_unit_id,
            "role": row.assignee_role,
            "primary": row.is_primary,
            "source": row.assignment_source,
            "confidence_percent": row.confidence_percent,
            "confirmation_status": row.confirmation_status,
            "effective_from": row.effective_from.isoformat(),
            "effective_to": row.effective_to.isoformat() if row.effective_to else None,
        } for row in responsibilities],
        "relationship_summary": dict(Counter(str(row.resolution_status or "UNKNOWN") for row in relationships)),
        "reference_health": dict(Counter(str(row.status or "UNKNOWN") for row in refs)),
        "index": {
            "status": index_job.status,
            "index_version": index_job.index_version,
            "detected_count": index_job.detected_count,
            "resolved_count": index_job.resolved_count,
            "unresolved_count": index_job.unresolved_count,
            "broken_count": index_job.broken_count,
            "source_sha256": index_job.source_sha256,
        } if index_job else None,
        "annotations": {"count": len(annotations), "by_type": dict(Counter(row.annotation_type for row in annotations))},
        "workflow": {"id": workflow.id, "state": workflow.state, "version": workflow.version} if workflow else None,
        "audit_history": [{"id": row.id, "action": row.action, "entity_type": row.entity_type, "entity_id": row.entity_id, "actor_id": row.actor_id, "at": row.at.isoformat() if row.at else None} for row in audits],
        "manifest": reader_manifest(db, tenant, manual, revision),
    }
