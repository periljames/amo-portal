from pathlib import Path
import ast


def replace_function(path: str, name: str, replacement: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    tree = ast.parse(text)
    node = next((n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name), None)
    if node is None:
        raise RuntimeError(f"missing {name} in {path}")
    lines = text.splitlines(True)
    p.write_text("".join(lines[:node.lineno - 1] + [replacement.rstrip() + "\n\n"] + lines[node.end_lineno :]), encoding="utf-8")


services = Path("backend/amodb/apps/platform/services.py")
text = services.read_text(encoding="utf-8")
if "from . import diagnostics, metrics, models, saas_queue" not in text:
    text = text.replace("from . import diagnostics, metrics, models\n", "from . import diagnostics, metrics, models, saas_queue\n")
services.write_text(text, encoding="utf-8")

replace_function("backend/amodb/apps/platform/services.py", "create_command_job", '''def create_command_job(db: Session, *, payload: dict[str, Any], actor_id: str) -> models.PlatformCommandJob:
    name = str(payload.get("command_name") or "").strip().upper()
    definition = get_definition(name)
    if not definition:
        job = models.PlatformCommandJob(
            command_name=name or "UNKNOWN",
            risk_level="LOW",
            status="UNSUPPORTED",
            actor_user_id=actor_id,
            requested_by_user_id=actor_id,
            reason=payload.get("reason"),
            input_json=payload,
            output_json={"detail": "Unsupported command."},
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    tenant_id = payload.get("tenant_id")
    reason = payload.get("reason")
    if definition.requires_tenant_id and not tenant_id:
        raise ValueError("This command requires tenant_id.")
    if definition.requires_reason and not str(reason or "").strip():
        raise ValueError("A reason is required for this command.")

    needs_approval = definition.requires_approval and not payload.get("approved")
    status = "NEEDS_APPROVAL" if needs_approval else "PENDING"
    job = models.PlatformCommandJob(
        command_name=definition.command_name,
        risk_level=definition.risk_level,
        status=status,
        tenant_id=tenant_id,
        actor_user_id=actor_id,
        requested_by_user_id=actor_id,
        reason=reason,
        idempotency_key=payload.get("idempotency_key"),
        input_json=payload.get("input") or {},
        dry_run=bool(payload.get("dry_run", False)),
        max_retries=definition.max_retries,
        timeout_seconds=definition.timeout_seconds,
    )
    db.add(job)
    db.flush()
    add_job_event(db, job, status, "Command job created.")
    audit(
        db,
        actor_user_id=actor_id,
        action="platform.command.created",
        tenant_id=tenant_id,
        entity_type="platform_command_job",
        entity_id=job.id,
        reason=reason,
        details={"command_name": definition.command_name, "risk_level": definition.risk_level, "execution": "durable_queue"},
    )
    if not needs_approval:
        queue_command_job(db, job, actor_id=actor_id)
    db.commit()
    db.refresh(job)
    return job''')

# Rename the synchronous executor; it is worker-only after this cleanup.
p = Path("backend/amodb/apps/platform/services.py")
text = p.read_text(encoding="utf-8")
text = text.replace("def execute_command_job(db: Session, job: models.PlatformCommandJob, *, actor_id: str) -> None:", "def _execute_command_action(db: Session, job: models.PlatformCommandJob, *, actor_id: str) -> None:", 1)
marker = "def list_jobs("
insert = '''def queue_command_job(db: Session, job: models.PlatformCommandJob, *, actor_id: str) -> None:
    if job.status in {"QUEUED", "RUNNING", "SUCCEEDED", "CANCELLED"}:
        return
    job.status = "QUEUED"
    add_job_event(db, job, "QUEUED", "Command queued for asynchronous worker execution.")
    saas_queue.enqueue_job(
        db,
        job_type="PLATFORM_COMMAND_JOB",
        queue_name="platform",
        tenant_id=job.tenant_id,
        payload={"command_job_id": job.id, "actor_id": actor_id},
        idempotency_key=f"command:{job.id}:{int(job.attempt_count or 0)}",
        correlation_id=job.id,
        created_by=actor_id,
        max_attempts=max(1, int(job.max_retries or 0) + 1),
        priority=20 if job.risk_level in {"HIGH", "CRITICAL"} else 80,
        commit=False,
    )


def process_command_queue_job(db: Session, queue_job) -> dict[str, Any]:
    payload = queue_job.payload_json or {}
    command_job_id = str(payload.get("command_job_id") or "").strip()
    actor_id = str(payload.get("actor_id") or "").strip()
    if not command_job_id or not actor_id:
        raise ValueError("Command queue job is missing command_job_id or actor_id")
    job = db.get(models.PlatformCommandJob, command_job_id)
    if job is None:
        raise ValueError("Platform command job not found")
    if job.status == "SUCCEEDED":
        return {"command_job_id": job.id, "status": job.status, "result": job.output_json or {}}
    if job.status == "CANCELLED":
        return {"command_job_id": job.id, "status": job.status, "result": {}}
    _execute_command_action(db, job, actor_id=actor_id)
    db.flush()
    if job.status in {"FAILED", "UNSUPPORTED"}:
        raise RuntimeError(job.error_detail or (job.output_json or {}).get("detail") or f"Command ended with {job.status}")
    return {"command_job_id": job.id, "status": job.status, "result": job.output_json or {}}


'''
if "def queue_command_job(" not in text:
    text = text.replace(marker, insert + marker, 1)
p.write_text(text, encoding="utf-8")

# Approval/retry routes enqueue; they never execute the action in the request thread.
router = Path("backend/amodb/apps/platform/router.py")
text = router.read_text(encoding="utf-8")
text = text.replace("services.execute_command_job(db, row, actor_id=_actor_id(user))", "services.queue_command_job(db, row, actor_id=_actor_id(user))")
router.write_text(text, encoding="utf-8")

# Safe worker owns the platform queue directly.
worker = Path("backend/amodb/jobs/saas_worker_safe.py")
text = worker.read_text(encoding="utf-8")
if "job.job_type == \"PLATFORM_COMMAND_JOB\"" not in text:
    text = text.replace(
        "    if job.job_type in commercial_services.COMMERCIAL_JOB_TYPES:\n        return commercial_services.process_job(db, job)\n",
        "    if job.job_type in commercial_services.COMMERCIAL_JOB_TYPES:\n        return commercial_services.process_job(db, job)\n    if job.job_type == \"PLATFORM_COMMAND_JOB\":\n        from amodb.apps.platform import services as platform_services\n        return platform_services.process_command_queue_job(db, job)\n",
        1,
    )
text = text.replace('queue_names=("billing", "integrations", "fiscalization", "ai", "default")', 'queue_names=("billing", "integrations", "fiscalization", "ai", "platform", "default")')
worker.write_text(text, encoding="utf-8")

# Remove bridge install/import from platform package.
init = Path("backend/amodb/apps/platform/__init__.py")
text = init.read_text(encoding="utf-8")
text = text.replace("from .saas_legacy_bridge import install_legacy_command_queue  # noqa: E402\n", "")
text = text.replace("install_legacy_command_queue()\n", "")
init.write_text(text, encoding="utf-8")

bridge = Path("backend/amodb/apps/platform/saas_legacy_bridge.py")
if bridge.exists():
    bridge.unlink()

for path in [services, router, worker, init]:
    path.write_text(path.read_text(encoding="utf-8").rstrip() + "\n", encoding="utf-8")
