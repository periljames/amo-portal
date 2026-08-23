"""Lease-owned processing for legacy Manual revision actions."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from amodb.apps.doc_control import knowledge_models as knowledge_models
from amodb.apps.manuals import models as manual_models
from amodb.apps.manuals.pdf_reader_precompute import cached_pdf_inspection
from amodb.apps.platform import saas_models


JOB_TYPES = {"MANUAL_REVISION_PROCESS", "MANUAL_REVISION_OCR"}


def _revision(db: Session, job: saas_models.SaaSJob) -> tuple[manual_models.Tenant, manual_models.Manual, manual_models.ManualRevision]:
    payload = dict(job.payload_json or {})
    revision_id = str(payload.get("revision_id") or "").strip()
    manual_id = str(payload.get("manual_id") or "").strip()
    revision = db.query(manual_models.ManualRevision).filter(
        manual_models.ManualRevision.id == revision_id,
        manual_models.ManualRevision.manual_id == manual_id,
    ).first()
    if revision is None:
        raise ValueError("Manual revision no longer exists")
    manual = db.query(manual_models.Manual).filter(manual_models.Manual.id == revision.manual_id).first()
    tenant = db.query(manual_models.Tenant).filter(manual_models.Tenant.id == manual.tenant_id).first() if manual else None
    if manual is None or tenant is None or str(tenant.amo_id) != str(job.tenant_id):
        raise ValueError("Manual revision tenant scope is invalid")
    return tenant, manual, revision


def _audit(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    job: saas_models.SaaSJob,
    action: str,
    revision_id: str,
    details: dict[str, Any],
) -> None:
    db.add(manual_models.ManualAuditLog(
        tenant_id=tenant.id,
        actor_id=job.created_by,
        action=action,
        entity_type="manual_revision",
        entity_id=revision_id,
        ip_device="durable-worker",
        diff_json={"job_id": job.id, **details},
    ))


def _process_revision(db: Session, job: saas_models.SaaSJob) -> dict[str, Any]:
    tenant, manual, revision = _revision(db, job)
    source_type = str(getattr(revision.source_type_enum, "value", revision.source_type_enum or "")).upper()
    result: dict[str, Any] = {
        "manual_id": manual.id,
        "revision_id": revision.id,
        "source_type": source_type,
    }
    if source_type == "PDF":
        inspection = cached_pdf_inspection(revision, prepare_safe_reader=True)
        result["pdf"] = {
            "engine": inspection.engine,
            "page_count": inspection.page_count,
            "has_acroform": inspection.has_acroform,
            "has_javascript": inspection.has_javascript,
            "can_flatten": inspection.can_flatten,
        }

    index_job = db.query(knowledge_models.DocumentationIndexJob).filter(
        knowledge_models.DocumentationIndexJob.tenant_id == tenant.amo_id,
        knowledge_models.DocumentationIndexJob.revision_id == revision.id,
    ).first()
    if index_job is None:
        index_job = knowledge_models.DocumentationIndexJob(
            tenant_id=tenant.amo_id,
            manual_id=manual.id,
            revision_id=revision.id,
        )
        db.add(index_job)
    if index_job.status != "RUNNING":
        index_job.status = "PENDING"
        index_job.source_sha256 = revision.source_sha256
        index_job.error_summary = None
        index_job.completed_at = None
    result["reference_indexing"] = "PENDING" if index_job.status != "RUNNING" else "RUNNING"
    _audit(
        db,
        tenant=tenant,
        job=job,
        action="revision.processing.completed",
        revision_id=revision.id,
        details=result,
    )
    db.flush()
    return result


def _process_ocr(db: Session, job: saas_models.SaaSJob) -> dict[str, Any]:
    tenant, manual, revision = _revision(db, job)
    source_type = str(getattr(revision.source_type_enum, "value", revision.source_type_enum or "")).upper()
    if source_type != "PDF":
        raise ValueError("Controlled OCR is available only for PDF revisions")
    source = Path(str(revision.source_storage_path or "")).resolve()
    if not source.is_file():
        raise ValueError("The immutable PDF source is unavailable")

    # Imported lazily to avoid making router initialization depend on optional
    # OCR libraries. The extraction routine itself produces a precise failure if
    # the deployment lacks its OCR adapter.
    from amodb.apps.manuals.core_router import (
        _extract_first_date,
        _extract_kcaa_reference,
        _extract_text_from_pdf_bytes,
    )

    extracted = _extract_text_from_pdf_bytes(source.read_bytes())
    detected_ref = _extract_kcaa_reference(extracted)
    detected_date = _extract_first_date(extracted)
    revision.ocr_detected_ref = detected_ref
    revision.ocr_detected_date = detected_date
    # Detection is an aid. A controller must still use the verify endpoint
    # before OCR metadata becomes authoritative publication evidence.
    revision.ocr_verified_bool = False
    revision.ocr_verified_at = None
    db.add(revision)
    result = {
        "manual_id": manual.id,
        "revision_id": revision.id,
        "detected_ref": detected_ref,
        "detected_date": detected_date.isoformat() if detected_date else None,
        "text_characters": len(extracted),
        "verification_required": True,
    }
    _audit(
        db,
        tenant=tenant,
        job=job,
        action="revision.ocr.completed",
        revision_id=revision.id,
        details=result,
    )
    db.flush()
    return result


def process_job(db: Session, job: saas_models.SaaSJob) -> dict[str, Any]:
    if job.job_type == "MANUAL_REVISION_PROCESS":
        return _process_revision(db, job)
    if job.job_type == "MANUAL_REVISION_OCR":
        return _process_ocr(db, job)
    raise ValueError(f"Unsupported Manual revision job type: {job.job_type}")
