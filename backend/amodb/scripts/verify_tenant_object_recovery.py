"""Read-only, full-tenant S3 retention / recovery acceptance.

Unlike the bounded interactive audit, this cursor scan covers every active
object, including tenants with many more than 1,000 files. Use --restore-bytes
to force a fresh download and checksum check of EVERY object. A successful
HEAD-only check proves object presence and size, not content integrity or a
database disaster restore. No ledger or regulatory reference is mutated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re

from sqlalchemy import func

from amodb import storage
from amodb.database import WriteSessionLocal
from amodb.apps.platform.storage_quota_models import (
    TenantStorageObject,
    TenantStorageQuota,
    TenantStorageReservation,
)
from amodb.apps.quality.tenant_security import set_postgres_tenant_context


def verify_retained_object(obj, *, restore_bytes: bool) -> None:
    """Fail closed before contacting S3 if the receipt targets another key."""
    if obj.storage_uri != storage.expected_s3_uri(obj.object_key):
        raise ValueError("Receipt URI does not match the managed bucket and key")
    if int(obj.size_bytes) < 0 or not re.fullmatch(r"[a-fA-F0-9]{64}", obj.checksum_sha256 or ""):
        raise ValueError("Invalid retained byte count or SHA-256 receipt")
    if not restore_bytes:
        size = storage.retained_object_size(obj.storage_uri)
        if int(size) != int(obj.size_bytes):
            raise IOError("Physical object size differs from the receipt")
        return
    # Always bypass the local cache: recovery must work on a fresh node.
    path = storage.materialize(
        obj.storage_uri, expected_sha256=obj.checksum_sha256, force_download=True,
    )
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            size += len(block)
            digest.update(block)
    if size != int(obj.size_bytes) or digest.hexdigest() != obj.checksum_sha256.lower():
        raise IOError("Freshly restored content differs from the authoritative receipt")


def inspect_tenant(db, *, tenant_id: str, batch_size: int = 500, restore_bytes: bool = False):
    """Read all committed objects; concurrent quota changes invalidate the proof."""
    set_postgres_tenant_context(db, amo_id=tenant_id, user_id="")
    account = db.get(TenantStorageQuota, tenant_id)
    if account is None:
        raise ValueError("No activated tenant quota exists")
    initial_generation = int(account.generation)
    count = 0
    bytes_verified = 0
    failures = 0
    failure_samples = []
    last_id = None
    while True:
        query = db.query(TenantStorageObject).filter(
            TenantStorageObject.tenant_id == tenant_id,
            TenantStorageObject.state == "ACTIVE",
        )
        if last_id is not None:
            query = query.filter(TenantStorageObject.id > last_id)
        batch = query.order_by(TenantStorageObject.id).limit(batch_size).all()
        if not batch:
            break
        for obj in batch:
            try:
                verify_retained_object(obj, restore_bytes=restore_bytes)
            except Exception as exc:
                failures += 1
                if len(failure_samples) < 20:
                    failure_samples.append({
                        "object_id": str(obj.id), "reason": type(exc).__name__,
                    })
            count += 1
            bytes_verified += int(obj.size_bytes)
            last_id = obj.id
    # Expire the SQLAlchemy identity map to avoid comparing the cached account
    # with itself after another API process has inserted or deleted objects.
    db.expire_all()
    latest = db.get(TenantStorageQuota, tenant_id)
    live_count, live_bytes = db.query(
        func.count(TenantStorageObject.id),
        func.coalesce(func.sum(TenantStorageObject.size_bytes), 0),
    ).filter(
        TenantStorageObject.tenant_id == tenant_id,
        TenantStorageObject.state == "ACTIVE",
    ).one()
    reserved = db.query(func.coalesce(func.sum(TenantStorageReservation.size_bytes), 0)).filter(
        TenantStorageReservation.tenant_id == tenant_id,
        TenantStorageReservation.state == "RESERVED",
    ).scalar()
    stable = latest is not None and int(latest.generation) == initial_generation
    ledger_ok = bool(latest and count == int(live_count)
        and bytes_verified == int(live_bytes) == int(latest.used_bytes)
        and int(reserved or 0) == int(latest.reserved_bytes)
        and int(latest.used_bytes) + int(latest.reserved_bytes) <= int(latest.quota_bytes))
    verified = stable and ledger_ok and failures == 0
    return {
        "tenant_id": tenant_id,
        "result": "VERIFIED" if verified else "BLOCKED",
        "mode": "FRESH_RESTORE_SHA256" if restore_bytes else "REMOTE_SIZE_ONLY",
        "checked_objects": count,
        "receipt_bytes": bytes_verified,
        "ledger_bytes": int(latest.used_bytes) if latest else None,
        "reserved_bytes": int(latest.reserved_bytes) if latest else None,
        "ledger_generation_stable": stable,
        "ledger_consistent": ledger_ok,
        "failed_objects": failures,
        "failure_samples": failure_samples,
        "limitations": (
            "Verifies physical object integrity; full PostgreSQL restore, role/RLS "
            "isolation, failover and capacity economics need separate acceptance."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--restore-bytes", action="store_true",
                        help="Download and SHA-256 every object from remote S3; potentially terabytes")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,64}", args.tenant_id):
        parser.error("A valid tenant ID is required")
    if not 1 <= args.batch_size <= 5000:
        parser.error("Batch size must be between 1 and 5000")
    if not storage.shared_storage_enabled():
        parser.error("A configured S3 backend is required")
    with WriteSessionLocal() as db:
        try:
            report = inspect_tenant(db, tenant_id=args.tenant_id,
                                    batch_size=args.batch_size,
                                    restore_bytes=args.restore_bytes)
        except Exception as exc:
            report = {"tenant_id": args.tenant_id, "result": "BLOCKED",
                      "reason": type(exc).__name__}
        finally:
            db.rollback()
    print(json.dumps(report, sort_keys=True))
    return 0 if report["result"] == "VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
