from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session

from amodb import storage
from amodb.apps.manuals import models as manual_models
from amodb.apps.platform import saas_lease, saas_models, saas_queue
from amodb.database import WriteSessionLocal, close_session_safely

from . import domain_models as dm
from . import evidence_models as em
from . import retention_models as rm
from . import workspace_evidence_pack_router as pack
from .evidence_pack_runtime_guard import _read_verified_file


logger = logging.getLogger(__name__)
JOB_TYPE = "DOCUMENT_EVIDENCE_PACK"
QUEUE_NAME = "document-control"
ASYNC_MAX_ATTACHMENT_BYTES = int(os.getenv("DOCUMENT_EVIDENCE_PACK_ASYNC_MAX_BYTES", str(2 * 1024 * 1024 * 1024)))
ASYNC_MAX_ATTACHMENTS = int(os.getenv("DOCUMENT_EVIDENCE_PACK_ASYNC_MAX_ATTACHMENTS", "5000"))
ASYNC_MAX_ROWS = int(os.getenv("DOCUMENT_EVIDENCE_PACK_ASYNC_MAX_ROWS", "100000"))
OUTPUT_ROOT = Path(os.getenv("DOCUMENT_EVIDENCE_PACK_JOB_DIR", "uploads/document-control-evidence-packs")).resolve()
WORKER_INTERVAL_SECONDS = max(1.0, min(float(os.getenv("DOCUMENT_EVIDENCE_PACK_WORKER_SECONDS", "2")), 60.0))
LEASE_SECONDS = max(120, min(int(os.getenv("DOCUMENT_EVIDENCE_PACK_LEASE_SECONDS", "1800")), 3600))
_stop_event = threading.Event()
_thread: threading.Thread | None = None
_thread_lock = threading.Lock()


def _bounded_query(query, *, dataset: str) -> list[Any]:
    rows = query.limit(ASYNC_MAX_ROWS + 1).all()
    if len(rows) > ASYNC_MAX_ROWS:
        raise ValueError(f"Evidence pack dataset {dataset} exceeds asynchronous row ceiling {ASYNC_MAX_ROWS}")
    return rows


def _datasets(db: Session, *, amo_id: str, manual_id: str, revision_id: str | None) -> dict[str, list[Any]]:
    def query(model, *, revision_scoped: bool = True) -> list[Any]:
        q = db.query(model).filter(model.tenant_id == amo_id, model.manual_id == manual_id)
        if revision_id and revision_scoped and hasattr(model, "revision_id"):
            q = q.filter(model.revision_id == revision_id)
        return _bounded_query(q, dataset=model.__tablename__)

    campaigns = query(dm.DocumentDistributionCampaign)
    campaign_ids = [row.id for row in campaigns]
    recipients: list[Any] = []
    acknowledgements: list[Any] = []
    if campaign_ids:
        recipients = _bounded_query(
            db.query(dm.DocumentDistributionRecipient).filter(
                dm.DocumentDistributionRecipient.tenant_id == amo_id,
                dm.DocumentDistributionRecipient.campaign_id.in_(campaign_ids),
            ),
            dataset="distribution_recipients",
        )
        recipient_ids = [row.id for row in recipients]
        if recipient_ids:
            acknowledgements = _bounded_query(
                db.query(dm.DocumentAcknowledgement).filter(
                    dm.DocumentAcknowledgement.tenant_id == amo_id,
                    dm.DocumentAcknowledgement.recipient_id.in_(recipient_ids),
                ),
                dataset="acknowledgements",
            )

    copies = query(dm.DocumentControlledCopy)
    copy_ids = [row.id for row in copies]
    copy_events = (
        _bounded_query(
            db.query(dm.DocumentControlledCopyEvent).filter(
                dm.DocumentControlledCopyEvent.tenant_id == amo_id,
                dm.DocumentControlledCopyEvent.controlled_copy_id.in_(copy_ids),
            ),
            dataset="controlled_copy_events",
        )
        if copy_ids else []
    )

    external_sources = query(dm.ExternalDocumentSource, revision_scoped=False)
    source_ids = [row.id for row in external_sources]
    external_receipts = (
        _bounded_query(
            db.query(dm.ExternalRevisionReceipt).filter(
                dm.ExternalRevisionReceipt.tenant_id == amo_id,
                dm.ExternalRevisionReceipt.source_id.in_(source_ids),
            ),
            dataset="external_revision_receipts",
        )
        if source_ids else []
    )

    retention_query = db.query(rm.DocumentRetentionDisposition).filter(
        rm.DocumentRetentionDisposition.tenant_id == amo_id,
        rm.DocumentRetentionDisposition.manual_id == manual_id,
    )
    if revision_id:
        retention_query = retention_query.filter(
            (rm.DocumentRetentionDisposition.revision_id == revision_id)
            | (rm.DocumentRetentionDisposition.revision_id.is_(None))
        )

    result: dict[str, list[Any]] = {
        "change_requests": query(dm.DocumentChangeRequest),
        "workflows": query(dm.DocumentWorkflowInstance),
        "authority_submissions": query(dm.DocumentAuthoritySubmission),
        "temporary_revisions": query(dm.DocumentTemporaryRevision),
        "distribution_campaigns": campaigns,
        "distribution_recipients": recipients,
        "acknowledgements": acknowledgements,
        "controlled_copies": copies,
        "controlled_copy_events": copy_events,
        "periodic_reviews": query(dm.DocumentReviewPlan),
        "external_sources": external_sources,
        "external_revision_receipts": external_receipts,
        "applicability": query(dm.DocumentApplicabilityRule),
        "integration_links": query(dm.DocumentIntegrationLink),
        "retention_dispositions": _bounded_query(retention_query, dataset="retention_dispositions"),
    }
    generated_model = getattr(dm, "DocumentGeneratedRecord", None)
    if generated_model is not None:
        result["generated_records"] = query(generated_model)
    return result


def _known_entity_ids(db: Session, *, amo_id: str, manual_id: str) -> set[str]:
    ids = {manual_id}
    for model in (
        dm.DocumentChangeRequest,
        dm.DocumentWorkflowInstance,
        dm.DocumentAuthoritySubmission,
        dm.DocumentTemporaryRevision,
        dm.DocumentDistributionCampaign,
        dm.DocumentControlledCopy,
        dm.DocumentReviewPlan,
        dm.ExternalDocumentSource,
        dm.DocumentApplicabilityRule,
        dm.DocumentIntegrationLink,
        rm.DocumentRetentionDisposition,
    ):
        if not hasattr(model, "manual_id"):
            continue
        rows = _bounded_query(
            db.query(model.id).filter(model.tenant_id == amo_id, model.manual_id == manual_id),
            dataset=f"{model.__tablename__}_audit_index",
        )
        ids.update(str(row[0]) for row in rows if row[0])
    return ids


def _audit_rows(db: Session, *, tenant: manual_models.Tenant, manual_id: str) -> list[Any]:
    entity_ids = _known_entity_ids(db, amo_id=tenant.amo_id, manual_id=manual_id)
    return _bounded_query(
        db.query(manual_models.ManualAuditLog)
        .filter(
            manual_models.ManualAuditLog.tenant_id == tenant.id,
            or_(
                manual_models.ManualAuditLog.entity_id.in_(entity_ids),
                cast(manual_models.ManualAuditLog.diff_json, String).like(f"%{manual_id}%"),
            ),
        )
        .order_by(manual_models.ManualAuditLog.at.asc(), manual_models.ManualAuditLog.id.asc()),
        dataset="audit_history",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_output_path(*, amo_id: str, manual_id: str, job_id: str) -> Path:
    path = (OUTPUT_ROOT / amo_id / manual_id / f"{job_id}.zip").resolve()
    if OUTPUT_ROOT != path and OUTPUT_ROOT not in path.parents:
        raise ValueError("Evidence pack output escaped configured storage root")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _persist_completed_output(*, output: Path, amo_id: str, manual_id: str, job_id: str) -> str:
    """Persist a completed archive where every API replica can retrieve it.

    Local development keeps the existing retained path because all supervised
    processes share one host filesystem. Horizontal/production deployments use
    the configured object-storage backend and store only the durable object URI
    in the job result, so a worker pod/container never leaks a container-local
    path to an API replica.
    """
    if not storage.shared_storage_enabled():
        return str(output)

    stored = storage.put_file(
        output,
        key=f"document-control/evidence-packs/{amo_id}/{manual_id}/{job_id}.zip",
        content_type="application/zip",
    )
    output.unlink(missing_ok=True)
    return stored.uri


def build_large_evidence_pack(db: Session, job: saas_models.SaaSJob) -> dict[str, Any]:
    payload = dict(job.payload_json or {})
    manual_id = str(payload.get("manual_id") or "")
    revision_id = str(payload.get("revision_id") or "") or None
    requester_id = str(payload.get("requested_by_user_id") or job.created_by or "") or None
    if not job.tenant_id or not manual_id:
        raise ValueError("Evidence pack job is missing tenant/document scope")

    manual = db.query(manual_models.Manual).filter(manual_models.Manual.id == manual_id).first()
    if not manual:
        raise ValueError("Controlled document no longer exists")
    tenant = db.query(manual_models.Tenant).filter(
        manual_models.Tenant.id == manual.tenant_id,
        manual_models.Tenant.amo_id == job.tenant_id,
    ).first()
    if not tenant:
        raise ValueError("Evidence pack job tenant/document scope is invalid")

    revisions_query = db.query(manual_models.ManualRevision).filter(manual_models.ManualRevision.manual_id == manual.id)
    selected_revision = None
    if revision_id:
        selected_revision = revisions_query.filter(manual_models.ManualRevision.id == revision_id).first()
        if not selected_revision:
            raise ValueError("Selected document revision no longer exists")
        revisions_query = revisions_query.filter(manual_models.ManualRevision.id == revision_id)
    revisions = _bounded_query(
        revisions_query.order_by(manual_models.ManualRevision.created_at.asc(), manual_models.ManualRevision.id.asc()),
        dataset="revisions",
    )
    datasets = _datasets(db, amo_id=tenant.amo_id, manual_id=manual.id, revision_id=revision_id)
    evidence_query = db.query(em.DocumentEvidenceAsset).filter(
        em.DocumentEvidenceAsset.tenant_id == tenant.amo_id,
        em.DocumentEvidenceAsset.manual_id == manual.id,
    )
    if revision_id:
        evidence_query = evidence_query.filter(
            (em.DocumentEvidenceAsset.revision_id == revision_id)
            | (em.DocumentEvidenceAsset.revision_id.is_(None))
        )
    evidence_assets = _bounded_query(
        evidence_query.order_by(em.DocumentEvidenceAsset.created_at.asc(), em.DocumentEvidenceAsset.id.asc()),
        dataset="evidence_assets",
    )
    audit_rows = _audit_rows(db, tenant=tenant, manual_id=manual.id)

    attachment_count = len(evidence_assets) + sum(1 for row in revisions if row.source_storage_path and row.source_sha256)
    if attachment_count > ASYNC_MAX_ATTACHMENTS:
        raise ValueError(f"Evidence pack exceeds asynchronous attachment ceiling {ASYNC_MAX_ATTACHMENTS}")

    output = _safe_output_path(amo_id=tenant.amo_id, manual_id=manual.id, job_id=job.id)
    temporary = output.with_suffix(".zip.tmp")
    generated_at = datetime.now(timezone.utc)
    file_manifest: list[dict[str, Any]] = []
    dataset_manifest: dict[str, dict[str, Any]] = {}
    total_attachment_bytes = 0
    try:
        with zipfile.ZipFile(temporary, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            readme = (
                "AMO Portal Document Control large evidence pack\n"
                f"Document: {manual.code} — {manual.title}\n"
                f"Generated: {generated_at.isoformat()}\n"
                "This package was generated by the durable Document Control export queue.\n"
            ).encode("utf-8")
            archive.writestr("README.txt", readme)
            file_manifest.append({"path": "README.txt", "sha256": hashlib.sha256(readme).hexdigest(), "size_bytes": len(readme), "kind": "README"})

            document_payload = {
                "document": pack._serialize_row(manual),
                "selected_revision_id": revision_id,
                "generated_at": generated_at.isoformat(),
                "generated_by_user_id": requester_id,
                "tenant_id": tenant.amo_id,
                "tenant_slug": tenant.slug,
                "job_id": job.id,
            }
            dataset_manifest["document"] = {
                "path": "data/document.json",
                "rows": 1,
                "sha256": pack._write_json(archive, "data/document.json", document_payload),
            }

            revision_payload = [pack._serialize_row(row, exclude={"source_storage_path"}) for row in revisions]
            dataset_manifest["revisions"] = {
                "path": "data/revisions.json",
                "csv_path": "data/revisions.csv",
                "rows": len(revision_payload),
                "sha256": pack._write_json(archive, "data/revisions.json", revision_payload),
                "csv_sha256": pack._write_csv(archive, "data/revisions.csv", revision_payload),
            }
            for name, rows in datasets.items():
                rows_payload = [pack._serialize_row(row) for row in rows]
                dataset_manifest[name] = {
                    "path": f"data/{name}.json",
                    "csv_path": f"data/{name}.csv",
                    "rows": len(rows_payload),
                    "sha256": pack._write_json(archive, f"data/{name}.json", rows_payload),
                    "csv_sha256": pack._write_csv(archive, f"data/{name}.csv", rows_payload),
                }
            audit_payload = [pack._serialize_row(row) for row in audit_rows]
            dataset_manifest["audit_history"] = {
                "path": "data/audit_history.json",
                "csv_path": "data/audit_history.csv",
                "rows": len(audit_payload),
                "sha256": pack._write_json(archive, "data/audit_history.json", audit_payload),
                "csv_sha256": pack._write_csv(archive, "data/audit_history.csv", audit_payload),
            }
            evidence_payload = [pack._serialize_row(row, exclude={"storage_path", "source_context_json"}) for row in evidence_assets]
            dataset_manifest["evidence_assets"] = {
                "path": "data/evidence_assets.json",
                "rows": len(evidence_payload),
                "sha256": pack._write_json(archive, "data/evidence_assets.json", evidence_payload),
            }

            for row in revisions:
                if not row.source_storage_path or not row.source_sha256:
                    continue
                content = _read_verified_file(row.source_storage_path, row.source_sha256, label=f"revision {row.rev_number}")
                total_attachment_bytes += len(content)
                if total_attachment_bytes > ASYNC_MAX_ATTACHMENT_BYTES:
                    raise ValueError(f"Evidence pack exceeds asynchronous retained-file ceiling {ASYNC_MAX_ATTACHMENT_BYTES} bytes")
                filename = row.source_filename or f"revision-{row.rev_number}.bin"
                path = pack._attachment_name("controlled-revisions", row.id, filename)
                archive.writestr(path, content)
                file_manifest.append({"path": path, "sha256": row.source_sha256, "size_bytes": len(content), "kind": "CONTROLLED_REVISION_SOURCE", "revision_id": row.id})

            for row in evidence_assets:
                content = _read_verified_file(row.storage_path, row.sha256, label=row.filename)
                total_attachment_bytes += len(content)
                if total_attachment_bytes > ASYNC_MAX_ATTACHMENT_BYTES:
                    raise ValueError(f"Evidence pack exceeds asynchronous retained-file ceiling {ASYNC_MAX_ATTACHMENT_BYTES} bytes")
                path = pack._attachment_name(row.category.lower(), row.id, row.filename)
                archive.writestr(path, content)
                file_manifest.append({"path": path, "sha256": row.sha256, "size_bytes": len(content), "kind": "DOCUMENT_EVIDENCE_ASSET", "asset_id": row.id, "category": row.category})

            manifest = {
                "schema": "amo-portal.document-control-evidence-pack.v1",
                "generation_mode": "DURABLE_ASYNC_JOB",
                "job_id": job.id,
                "generated_at": generated_at.isoformat(),
                "tenant": {"id": tenant.amo_id, "slug": tenant.slug},
                "document": {"id": manual.id, "code": manual.code, "title": manual.title},
                "revision_scope": revision_id or "ALL",
                "dataset_manifest": dataset_manifest,
                "files": file_manifest,
                "bounds": {
                    "max_attachment_bytes": ASYNC_MAX_ATTACHMENT_BYTES,
                    "max_attachments": ASYNC_MAX_ATTACHMENTS,
                    "max_rows_per_dataset": ASYNC_MAX_ROWS,
                },
            }
            pack._write_json(archive, "manifest.json", manifest)
        os.replace(temporary, output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    sha256 = _sha256_file(output)
    size_bytes = output.stat().st_size
    filename = f"{str(manual.code).replace('/', '-')}_evidence_pack_async{f'_{selected_revision.rev_number}' if selected_revision else ''}.zip"
    output_uri = _persist_completed_output(
        output=output,
        amo_id=tenant.amo_id,
        manual_id=manual.id,
        job_id=job.id,
    )
    return {
        "manual_id": manual.id,
        "revision_id": revision_id,
        "filename": filename,
        "output_uri": output_uri,
        "sha256": sha256,
        "size_bytes": size_bytes,
        "attachments": attachment_count,
        "generated_at": generated_at.isoformat(),
    }


def _worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:document-control-evidence-pack"[:128]


def process_one_pending_job() -> bool:
    db = WriteSessionLocal()
    identity = _worker_id()
    try:
        jobs = saas_queue.claim_jobs(
            db,
            worker_id=identity,
            queue_names=(QUEUE_NAME,),
            batch_size=1,
            lease_seconds=LEASE_SECONDS,
        )
        if not jobs:
            return False
        job = jobs[0]
        if job.job_type != JOB_TYPE:
            saas_queue.fail_job(db, job, f"Unsupported Document Control queue job type: {job.job_type}", retryable=False, worker_id=identity)
            return True
        try:
            with saas_lease.LeaseHeartbeat(job, worker_id=identity, lease_seconds=LEASE_SECONDS) as heartbeat:
                result = build_large_evidence_pack(db, job)
                heartbeat.raise_if_lost()
            saas_queue.complete_job(db, job, result, worker_id=identity)
        except saas_queue.LeaseLostError:
            db.rollback()
        except Exception as exc:
            try:
                saas_queue.fail_job(db, job, exc, retryable=True, worker_id=identity)
            except saas_queue.LeaseLostError:
                db.rollback()
        return True
    finally:
        close_session_safely(db)


def _worker_loop() -> None:
    while not _stop_event.is_set():
        try:
            processed = process_one_pending_job()
        except Exception:
            logger.exception("Document Control evidence-pack worker cycle failed")
            processed = False
        if not processed:
            _stop_event.wait(WORKER_INTERVAL_SECONDS)


def start_evidence_pack_job_worker() -> None:
    global _thread
    with _thread_lock:
        if _thread and _thread.is_alive():
            return
        _stop_event.clear()
        _thread = threading.Thread(target=_worker_loop, name="document-control-evidence-pack-worker", daemon=True)
        _thread.start()


def stop_evidence_pack_job_worker() -> None:
    global _thread
    _stop_event.set()
    thread = _thread
    if thread and thread.is_alive():
        thread.join(timeout=5)
    _thread = None


def verified_job_output(job: saas_models.SaaSJob) -> tuple[Path, dict[str, Any]]:
    if job.status != "SUCCEEDED" or not isinstance(job.result_json, dict):
        raise HTTPException(status_code=409, detail="Evidence pack job has not completed")

    result = dict(job.result_json)
    locator = str(result.get("output_uri") or result.get("output_path") or "").strip()
    expected = str(result.get("sha256") or "").strip()
    if not locator or not expected:
        raise HTTPException(status_code=409, detail="Retained evidence pack output is unavailable")

    if locator.startswith("s3://"):
        try:
            path = storage.materialize(locator, expected_sha256=expected)
        except Exception as exc:
            logger.warning("Unable to materialize retained evidence pack %s: %s", job.id, exc)
            raise HTTPException(status_code=409, detail="Retained evidence pack output is unavailable") from exc
    else:
        # Backwards-compatible local development/legacy completed jobs. Local
        # paths remain constrained to the evidence-pack staging root.
        path = Path(locator).resolve()
        if not path.exists() or not path.is_file() or (path != OUTPUT_ROOT and OUTPUT_ROOT not in path.parents):
            raise HTTPException(status_code=409, detail="Retained evidence pack output is unavailable")

    actual = _sha256_file(path)
    if actual.lower() != expected.lower():
        raise HTTPException(status_code=409, detail="Retained evidence pack checksum does not match its completed job record")
    return path, result
