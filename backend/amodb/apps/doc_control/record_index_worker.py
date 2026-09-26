"""Recover retained-record indexing after an API process exits mid-upload.

Run with ``python -m amodb.apps.doc_control.record_index_worker`` alongside the
existing Documentation indexing worker. Job claims use database row locks.
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from amodb.database import WriteSessionLocal

from . import records_vault_models as rm
from .record_file_indexer import index_record


def run_once(limit: int = 2) -> int:
    with WriteSessionLocal() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(120, int(os.getenv("RECORD_INDEX_STALE_SECONDS", "1800"))))
        stale = db.query(rm.TenantRecordIndexJob).filter(
            rm.TenantRecordIndexJob.status == "RUNNING",
            rm.TenantRecordIndexJob.updated_at < cutoff,
        ).order_by(rm.TenantRecordIndexJob.updated_at.asc()).limit(limit)
        if db.get_bind().dialect.name == "postgresql":
            stale = stale.with_for_update(skip_locked=True)
        for job in stale.all():
            job.status = "PENDING"
            job.error_summary = "Recovering interrupted extraction"
        db.commit()
        queued = db.query(rm.TenantRecordIndexJob.tenant_id, rm.TenantRecordIndexJob.record_asset_id).filter(
            rm.TenantRecordIndexJob.status == "PENDING",
        ).order_by(rm.TenantRecordIndexJob.created_at.asc()).limit(max(1, min(limit, 20))).all()
    root = Path(os.getenv("DOCUMENT_RECORD_VAULT_DIR", "uploads/document-record-vault")).resolve()
    for tenant_id, record_id in queued:
        index_record(str(tenant_id), str(record_id), root)
    return len(queued)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run retained-record extraction worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--poll-seconds", type=float, default=3)
    args = parser.parse_args()
    while True:
        processed = run_once(args.limit)
        if args.once:
            return
        if not processed:
            time.sleep(max(1, min(args.poll_seconds, 30)))


if __name__ == "__main__":
    main()
