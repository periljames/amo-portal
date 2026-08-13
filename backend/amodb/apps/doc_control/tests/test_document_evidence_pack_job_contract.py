from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "amodb" / "apps" / "doc_control"
FRONTEND = ROOT.parent / "frontend" / "src"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_large_pack_uses_existing_durable_lease_fenced_queue() -> None:
    service = _text(APP / "evidence_pack_job_service.py")
    router = _text(APP / "workspace_evidence_pack_job_router.py")
    assert 'JOB_TYPE = "DOCUMENT_EVIDENCE_PACK"' in service
    assert 'QUEUE_NAME = "document-control"' in service
    assert "saas_queue.claim_jobs(" in service
    assert "saas_lease.LeaseHeartbeat" in service
    assert "saas_queue.complete_job" in service
    assert "saas_queue.fail_job" in service
    assert "saas_queue.enqueue_job(" in router
    assert "max_attempts=3" in router
    assert "commit=False" in router


def test_large_pack_is_bounded_and_written_to_controlled_retained_storage() -> None:
    service = _text(APP / "evidence_pack_job_service.py")
    assert "DOCUMENT_EVIDENCE_PACK_ASYNC_MAX_BYTES" in service
    assert "DOCUMENT_EVIDENCE_PACK_ASYNC_MAX_ATTACHMENTS" in service
    assert "DOCUMENT_EVIDENCE_PACK_ASYNC_MAX_ROWS" in service
    assert "DOCUMENT_EVIDENCE_PACK_JOB_DIR" in service
    assert "allowZip64=True" in service
    assert "os.replace(temporary, output)" in service
    assert "_read_verified_file" in service
    assert "_sha256_file(output)" in service
    assert "OUTPUT_ROOT not in path.parents" in service
    assert "Retained evidence pack checksum does not match" in service


def test_large_pack_preserves_document_scope_and_audit_evidence() -> None:
    service = _text(APP / "evidence_pack_job_service.py")
    router = _text(APP / "workspace_evidence_pack_job_router.py")
    assert "manual_models.ManualAuditLog.tenant_id == tenant.id" in service
    assert "rm.DocumentRetentionDisposition" in service
    assert '"generation_mode": "DURABLE_ASYNC_JOB"' in service
    assert '"job_id": job.id' in service
    assert '"generated_by_user_id": requester_id' in service
    assert '"document.evidence_pack.queued"' in router
    assert '"document.evidence_pack.job_downloaded"' in router
    assert "require_manual_access" in router
    assert "saas_models.SaaSJob.tenant_id == tenant_id" in router


def test_job_api_exposes_queue_status_and_verified_download_not_storage_paths() -> None:
    router = _text(APP / "workspace_evidence_pack_job_router.py")
    assert '@router.post("/t/{tenant_slug}/documents/{manual_id}/evidence-pack-jobs")' in router
    assert '@router.get("/t/{tenant_slug}/documents/{manual_id}/evidence-pack-jobs/{job_id}")' in router
    assert '@router.get("/t/{tenant_slug}/documents/{manual_id}/evidence-pack-jobs/{job_id}/download")' in router
    assert '"output_path"' not in router
    assert "verified_job_output(job)" in router
    assert '"Cache-Control": "private, no-store"' in router
    assert '"X-Evidence-Pack-SHA256"' in router


def test_worker_and_job_routes_are_registered_in_document_control() -> None:
    router = _text(APP / "router.py")
    assert "evidence_pack_job_lifecycle_router" in router
    assert "router.include_router(evidence_pack_job_lifecycle_router)" in router
    assert "workspace_evidence_pack_job_router" in router
    assert router.index("workspace_evidence_pack_job_router,") < router.index("workspace_evidence_pack_router,")


def test_frontend_can_queue_poll_and_download_large_pack_without_job_ids() -> None:
    service = _text(FRONTEND / "services" / "documentControlEvidence.ts")
    action = _text(FRONTEND / "pages" / "documentControl" / "DocumentEvidencePackAction.tsx")
    assert "queueDocumentEvidencePackJob" in service
    assert "getDocumentEvidencePackJob" in service
    assert "downloadDocumentEvidencePackJob" in service
    assert "/evidence-pack-jobs" in service
    assert "Queue large complete pack" in action
    assert "Queue large latest revision" in action
    assert "ACTIVE_JOB_STATUSES" in action
    assert "window.setInterval" in action
    assert "Download completed large pack" in action
    assert "The durable worker will continue without keeping this page open" in action
