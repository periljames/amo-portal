"""Backfill legacy CAR attachment files to tenant-scoped shared storage.

Usage (on a node that still holds the original attachment files):
  python -m amodb.apps.quality.backfill_car_evidence --amo-id <tenant-uuid>
  python -m amodb.apps.quality.backfill_car_evidence --amo-id <tenant-uuid> --apply

Dry-run is the default. The original files are never removed; verified object
copies and database references are updated individually and can be re-run.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from amodb.database import WriteSessionLocal
from . import models
from .car_rca_storage import car_attachment_path, store_car_file
from .tenant_security import set_postgres_tenant_context
from amodb import storage


def backfill(*, amo_id: str, apply: bool, limit: int) -> dict:
    result = {"amo_id": amo_id, "mode": "APPLY" if apply else "DRY_RUN",
              "examined": 0, "migrated": 0, "already_shared": 0,
              "missing_or_invalid": [], "failed": []}
    with WriteSessionLocal() as db:
        set_postgres_tenant_context(
            db, amo_id=amo_id, user_id="00000000-0000-0000-0000-000000000000",
        )
        rows = (db.query(models.CARAttachment, models.CorrectiveActionRequest)
            .join(models.CorrectiveActionRequest, models.CARAttachment.car_id == models.CorrectiveActionRequest.id)
            .filter(models.CorrectiveActionRequest.amo_id == amo_id)
            .order_by(models.CARAttachment.uploaded_at, models.CARAttachment.id)
            .limit(limit).all())
        for attachment, car in rows:
            result["examined"] += 1
            uri = str(attachment.file_ref or "")
            if uri.startswith("s3://") or (uri and storage.exists(uri)):
                # A pre-existing local object inside the shared storage root
                # needs no migration; legacy paths are handled below.
                if uri.startswith("s3://"):
                    result["already_shared"] += 1
                    continue
                root = storage.local_root().resolve()
                try:
                    Path(uri).resolve().relative_to(root)
                    result["already_shared"] += 1
                    continue
                except ValueError:
                    pass
            try:
                source = car_attachment_path(
                    uri, car_id=car.id, expected_sha256=attachment.sha256,
                )
            except Exception as exc:
                result["missing_or_invalid"].append({"attachment_id": str(attachment.id), "reason": type(exc).__name__})
                continue
            if not apply:
                continue
            try:
                stored_uri = store_car_file(
                    source, amo_id=amo_id, car_id=car.id, content_type=attachment.content_type,
                )
                # Verify the destination before changing the authoritative DB URI.
                storage.materialize(stored_uri, expected_sha256=attachment.sha256)
                attachment.file_ref = stored_uri
                db.commit()
                result["migrated"] += 1
            except Exception as exc:
                db.rollback()
                set_postgres_tenant_context(
                    db, amo_id=amo_id, user_id="00000000-0000-0000-0000-000000000000",
                )
                result["failed"].append({"attachment_id": str(attachment.id), "reason": type(exc).__name__})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--amo-id", required=True, help="Tenant AMO UUID; tenant isolation is never optional")
    parser.add_argument("--apply", action="store_true", help="Apply verified database changes (dry-run otherwise)")
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 10000:
        parser.error("--limit must be between 1 and 10000")
    print(json.dumps(backfill(amo_id=args.amo_id, apply=args.apply, limit=args.limit), indent=2))


if __name__ == "__main__":
    main()
