"""Run or resume the governed Document Control reconciliation job.

Examples:
  python -m amodb.jobs.document_governance_backfill --tenant safarilink --dry-run
  python -m amodb.jobs.document_governance_backfill --tenant safarilink --execute --document MANUAL_ID
  python -m amodb.jobs.document_governance_backfill --tenant safarilink --resume RUN_ID
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from amodb.apps.doc_control.governance_backfill import create_run, process_batch, serialize_run
from amodb.apps.manuals import models as manual_models
from amodb.database import WriteSessionLocal


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile existing Document Control governance metadata")
    parser.add_argument("--tenant", required=True, help="Manual tenant slug")
    parser.add_argument("--document", action="append", default=[], dest="manual_ids", help="Limit to one document ID; repeatable")
    parser.add_argument("--resume", help="Resume an existing backfill run ID")
    parser.add_argument("--idempotency-key", help="Stable caller-provided idempotency key")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True)
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--batch-limit", type=int, default=50)
    parser.add_argument("--no-retry-failed", action="store_true")
    parser.add_argument("--skip-hierarchy", action="store_true")
    args = parser.parse_args()

    db = WriteSessionLocal()
    try:
        tenant = db.query(manual_models.Tenant).filter(manual_models.Tenant.slug == args.tenant).first()
        if not tenant:
            raise SystemExit(f"Unknown manual tenant slug: {args.tenant}")
        if args.resume:
            run_id = args.resume
        else:
            key = args.idempotency_key or f"cli:{tenant.amo_id}:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}:{'execute' if args.execute else 'dry-run'}"
            run = create_run(
                db,
                tenant=tenant,
                actor_id=None,
                idempotency_key=key,
                dry_run=not args.execute,
                manual_ids=args.manual_ids,
                reconcile_hierarchy=not args.skip_hierarchy,
            )
            run_id = run.id
        while True:
            run = process_batch(
                db,
                tenant=tenant,
                run_id=run_id,
                batch_limit=max(1, min(250, args.batch_limit)),
                retry_failed=not args.no_retry_failed,
            )
            if run.status in {"COMPLETED", "PARTIAL"}:
                break
        print(json.dumps(serialize_run(db, run), indent=2, default=str))
        return 0 if run.status == "COMPLETED" else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
