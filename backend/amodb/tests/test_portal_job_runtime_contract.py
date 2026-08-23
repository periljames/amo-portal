from pathlib import Path


AMODB = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (AMODB / relative).read_text(encoding="utf-8")


def test_api_lifecycle_starts_and_stops_embedded_durable_workers() -> None:
    main = source("main.py")
    runtime = source("jobs/portal_job_supervisor.py")
    assert "start_portal_job_supervisor()" in main
    assert "stop_portal_job_supervisor" in main
    assert '"jobs": job_runtime' in main
    assert 'PORTAL_EMBEDDED_JOB_WORKER' in runtime
    for family in (
        '"workforce"',
        '"platform-commands"',
        '"saas"',
        '"training-workbooks"',
        '"training-reports"',
        '"document-indexing"',
        '"training-plans"',
    ):
        assert family in runtime
    # Worker imports are lazy so one optional family cannot abort API startup.
    assert "def _run_training_plans_once()" in runtime
    assert "from amodb.jobs import training_plan_automation" in runtime


def test_monthly_training_plan_worker_is_present_and_tenant_safe() -> None:
    worker = source("jobs/training_plan_automation.py")
    assert "def run_once(" in worker
    assert 'plan_automation_enabled.is_(True)' in worker
    assert 'idempotency_key = f"monthly-plan:' in worker
    assert 'trigger="SCHEDULED"' in worker
    assert "account_models.User.amo_id == settings.amo_id" in worker
    assert "account_models.User.is_system_account.is_(False)" in worker


def test_queue_families_use_atomic_claims_and_stale_recovery() -> None:
    workforce = source("apps/workforce/worker_main.py")
    workbooks = source("apps/training/workbook_import.py")
    workbook_worker = source("apps/training/workbook_worker.py")
    document_indexer = source("apps/doc_control/knowledge_indexer.py")
    document_worker = source("apps/doc_control/knowledge_worker.py")
    assert "_recover_stale_operations" in workforce
    assert 'WorkforceBulkOperation.status == "RUNNING"' in workforce
    assert 'TrainingWorkbookImportJob.status == "QUEUED"' in workbooks
    assert "claimed != 1" in workbooks
    assert '"PARSING", "COMMITTING"' in workbook_worker
    assert 'km.DocumentationIndexJob.status == "PENDING"' in document_indexer
    assert 'km.DocumentationIndexJob.status == "RUNNING"' in document_worker


def test_workforce_item_claim_only_locks_the_nonnullable_item_table() -> None:
    worker = source("apps/workforce/bulk_worker.py")
    assert "lazyload(bulk_models.WorkforceBulkOperationItem.operation)" in worker
    assert "of=bulk_models.WorkforceBulkOperationItem" in worker
    assert "skip_locked=True" in worker


def test_workforce_bulk_progress_is_committed_per_person() -> None:
    worker = source("apps/workforce/bulk_worker.py")
    claimed = worker.index('item.status = "RUNNING"')
    processor = worker.index('if operation.operation_type == "CREATE_CONTRACTS"')
    assert "db.commit()" in worker[claimed:processor]
    assert 'item.outcome_code = "PROCESSING"' in worker[claimed:processor]
    completed = worker.index("_refresh_counts(db, operation)", processor)
    assert "db.commit()" in worker[completed:]
    assert "operation.heartbeat_at = _utcnow()" in worker[completed:]


def test_manual_processing_routes_create_real_saas_jobs() -> None:
    manual_router = source("apps/manuals/core_router.py")
    safe_worker = source("jobs/saas_worker_safe.py")
    handler = source("jobs/manual_revision_jobs.py")
    assert 'job_type="MANUAL_REVISION_PROCESS"' in manual_router
    assert 'job_type="MANUAL_REVISION_OCR"' in manual_router
    assert 'return {"status": "queued", "job_id": str(uuid4())}' not in manual_router
    assert 'MANUAL_REVISION_PROCESS' in safe_worker
    assert "cached_pdf_inspection" in handler
    assert "_extract_text_from_pdf_bytes" in handler


def test_training_report_jobs_are_processed_and_retryable_from_the_portal() -> None:
    runtime = source("jobs/portal_job_supervisor.py")
    router = source("apps/training/operating_router.py")
    service = source("apps/training/readiness_service.py")
    assert '"training-reports"' in runtime
    assert '@router.post("/report-jobs/{job_id}/retry"' in router
    assert "def retry_report_job(" in service
    assert 'job.status = "QUEUED"' in service
