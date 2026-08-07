from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from amodb.apps.manuals import models as manual_models

from . import governance_models as gm
from .governance_service import process_backfill_document
from .knowledge_service import reconcile_documentation_hierarchy


def utcnow() -> datetime:
    return datetime.utcnow()


def serialize_run(db: Session, run: gm.DocumentGovernanceBackfillRun) -> dict[str, Any]:
    items = db.query(gm.DocumentGovernanceBackfillItem).filter(
        gm.DocumentGovernanceBackfillItem.run_id == run.id,
    ).order_by(gm.DocumentGovernanceBackfillItem.sequence.asc()).limit(500).all()
    return {
        "id": run.id,
        "tenant_id": run.tenant_id,
        "idempotency_key": run.idempotency_key,
        "scope": dict(run.scope_json or {}),
        "status": run.status,
        "dry_run": run.dry_run,
        "total_count": run.total_count,
        "processed_count": run.processed_count,
        "succeeded_count": run.succeeded_count,
        "failed_count": run.failed_count,
        "skipped_count": run.skipped_count,
        "reconciliation": dict(run.reconciliation_json or {}),
        "last_error": run.last_error,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "heartbeat_at": run.heartbeat_at.isoformat() if run.heartbeat_at else None,
        "items": [
            {
                "id": item.id,
                "manual_id": item.manual_id,
                "revision_id": item.revision_id,
                "sequence": item.sequence,
                "status": item.status,
                "attempt_count": item.attempt_count,
                "actions": dict(item.action_json or {}),
                "result": dict(item.result_json or {}),
                "error_summary": item.error_summary,
            }
            for item in items
        ],
    }


def create_run(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    actor_id: str | None,
    idempotency_key: str,
    dry_run: bool,
    manual_ids: list[str],
    reconcile_hierarchy: bool,
) -> gm.DocumentGovernanceBackfillRun:
    existing = db.query(gm.DocumentGovernanceBackfillRun).filter(
        gm.DocumentGovernanceBackfillRun.tenant_id == tenant.amo_id,
        gm.DocumentGovernanceBackfillRun.idempotency_key == idempotency_key,
    ).first()
    if existing:
        return existing

    query = db.query(manual_models.Manual).filter(manual_models.Manual.tenant_id == tenant.id)
    if manual_ids:
        query = query.filter(manual_models.Manual.id.in_(manual_ids))
    manuals = query.order_by(manual_models.Manual.code.asc(), manual_models.Manual.id.asc()).all()
    if manual_ids and len(manuals) != len(set(manual_ids)):
        raise HTTPException(status_code=404, detail="One or more selected documents are outside this tenant or do not exist")

    run = gm.DocumentGovernanceBackfillRun(
        tenant_id=tenant.amo_id,
        idempotency_key=idempotency_key,
        scope_json={
            "manual_ids": [row.id for row in manuals],
            "reconcile_hierarchy": reconcile_hierarchy,
        },
        status="QUEUED",
        dry_run=dry_run,
        total_count=len(manuals),
        created_by_user_id=actor_id,
    )
    db.add(run)
    db.flush()
    latest_revision = {
        row.manual_id: row.id
        for row in db.query(manual_models.ManualRevision).filter(
            manual_models.ManualRevision.manual_id.in_([manual.id for manual in manuals] or ["-"])
        ).order_by(manual_models.ManualRevision.created_at.asc()).all()
    }
    for sequence, manual in enumerate(manuals):
        db.add(gm.DocumentGovernanceBackfillItem(
            run_id=run.id,
            tenant_id=tenant.amo_id,
            manual_id=manual.id,
            revision_id=latest_revision.get(manual.id),
            sequence=sequence,
        ))
    db.commit()
    db.refresh(run)
    return run


def process_batch(
    db: Session,
    *,
    tenant: manual_models.Tenant,
    run_id: str,
    batch_limit: int,
    retry_failed: bool,
) -> gm.DocumentGovernanceBackfillRun:
    run = db.query(gm.DocumentGovernanceBackfillRun).filter(
        gm.DocumentGovernanceBackfillRun.id == run_id,
        gm.DocumentGovernanceBackfillRun.tenant_id == tenant.amo_id,
    ).with_for_update().first()
    if not run:
        raise HTTPException(status_code=404, detail="Backfill run not found")
    if run.status == "COMPLETED":
        return run

    now = utcnow()
    run.status = "RUNNING"
    run.started_at = run.started_at or now
    run.heartbeat_at = now
    run.completed_at = None
    run.last_error = None
    scope = dict(run.scope_json or {})
    if not run.dry_run and scope.get("reconcile_hierarchy") and not scope.get("hierarchy_reconciled"):
        reconcile_documentation_hierarchy(db, manual_tenant=tenant, actor_id=run.created_by_user_id)
        scope["hierarchy_reconciled"] = True
        run.scope_json = scope
    db.commit()

    statuses = ["PENDING"] + (["FAILED"] if retry_failed else [])
    item_ids = [
        row[0]
        for row in db.query(gm.DocumentGovernanceBackfillItem.id).filter(
            gm.DocumentGovernanceBackfillItem.run_id == run.id,
            gm.DocumentGovernanceBackfillItem.status.in_(statuses),
        ).order_by(gm.DocumentGovernanceBackfillItem.sequence.asc()).limit(batch_limit).all()
    ]

    for item_id in item_ids:
        item = db.query(gm.DocumentGovernanceBackfillItem).filter(
            gm.DocumentGovernanceBackfillItem.id == item_id,
            gm.DocumentGovernanceBackfillItem.run_id == run.id,
        ).with_for_update().first()
        if not item:
            continue
        item.status = "RUNNING"
        item.attempt_count = int(item.attempt_count or 0) + 1
        item.started_at = utcnow()
        item.error_summary = None
        db.commit()
        try:
            manual = db.query(manual_models.Manual).filter(
                manual_models.Manual.id == item.manual_id,
                manual_models.Manual.tenant_id == tenant.id,
            ).first()
            if not manual:
                raise RuntimeError("Document no longer exists in the selected tenant")
            result = process_backfill_document(
                db,
                tenant=tenant,
                manual=manual,
                actor_id=run.created_by_user_id,
                dry_run=run.dry_run,
            )
            item.result_json = result
            item.action_json = {"action_count": len(result.get("actions") or [])}
            item.status = "SUCCEEDED"
            item.completed_at = utcnow()
            db.commit()
        except Exception as exc:  # retained failure evidence; subsequent items continue
            db.rollback()
            item = db.query(gm.DocumentGovernanceBackfillItem).filter(
                gm.DocumentGovernanceBackfillItem.id == item_id,
            ).first()
            if item:
                item.status = "FAILED"
                item.error_summary = str(exc)[:4000]
                item.completed_at = utcnow()
                db.commit()

    run = db.query(gm.DocumentGovernanceBackfillRun).filter(gm.DocumentGovernanceBackfillRun.id == run_id).with_for_update().first()
    counts = dict(
        db.query(gm.DocumentGovernanceBackfillItem.status, func.count(gm.DocumentGovernanceBackfillItem.id))
        .filter(gm.DocumentGovernanceBackfillItem.run_id == run.id)
        .group_by(gm.DocumentGovernanceBackfillItem.status)
        .all()
    )
    run.succeeded_count = int(counts.get("SUCCEEDED", 0))
    run.failed_count = int(counts.get("FAILED", 0))
    run.skipped_count = int(counts.get("SKIPPED", 0))
    run.processed_count = run.succeeded_count + run.failed_count + run.skipped_count
    pending = int(counts.get("PENDING", 0)) + int(counts.get("RUNNING", 0))
    run.status = "COMPLETED" if pending == 0 and run.failed_count == 0 else "PARTIAL" if pending == 0 else "RUNNING"
    run.heartbeat_at = utcnow()
    run.completed_at = utcnow() if pending == 0 else None
    run.reconciliation_json = {
        "processed": run.processed_count,
        "succeeded": run.succeeded_count,
        "failed": run.failed_count,
        "skipped": run.skipped_count,
        "remaining": pending,
        "dry_run": run.dry_run,
    }
    db.commit()
    db.refresh(run)
    return run
