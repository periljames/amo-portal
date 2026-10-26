"""Transactional tenant byte quotas and object accounting.

Callers own the DB transaction. A storage upload must reserve before writing,
finalize only after object storage confirms a durable object, and release on
failure. PostgreSQL row-level locks serialize writers across API processes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from .storage_quota_models import (
    DEFAULT_PAID_QUOTA_BYTES, TenantStorageLedgerEvent, TenantStorageObject,
    TenantStorageQuota, TenantStorageReservation,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value):
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _locked(db: Session, tenant_id: str, *, allow_drift: bool = False) -> TenantStorageQuota:
    q = db.query(TenantStorageQuota).filter(TenantStorageQuota.tenant_id == tenant_id)
    if db.get_bind().dialect.name == "postgresql":
        q = q.with_for_update()
    account = q.one_or_none()
    if not account:
        raise ValueError("Tenant has no activated storage allocation")
    if account.integrity_state != "OK" and not allow_drift:
        raise ValueError("Storage ledger reconciliation required; quota operations paused")
    return account


def _event(db, account, typ, actor_id, key=None, delta_used=0, delta_reserved=0, metadata=None):
    account.generation += 1
    account.updated_at = _now()
    account.updated_by = actor_id
    db.add(TenantStorageLedgerEvent(
        tenant_id=account.tenant_id, actor_id=actor_id, event_type=typ,
        object_key=key, delta_used_bytes=delta_used, delta_reserved_bytes=delta_reserved,
        quota_after_bytes=account.quota_bytes, used_after_bytes=account.used_bytes,
        reserved_after_bytes=account.reserved_bytes, metadata_json=metadata or {},
    ))


def _snapshot(account):
    return {
        "tenant_id": account.tenant_id, "quota_bytes": int(account.quota_bytes),
        "used_bytes": int(account.used_bytes), "reserved_bytes": int(account.reserved_bytes),
        "remaining_bytes": max(0, int(account.quota_bytes - account.used_bytes - account.reserved_bytes)),
        "generation": int(account.generation), "integrity_state": account.integrity_state,
        "last_reconciled_at": account.last_reconciled_at,
        "allocation_unit": "bytes", "five_decimal_tb_bytes": DEFAULT_PAID_QUOTA_BYTES,
    }


def read_quota(db: Session, tenant_id: str):
    account = db.get(TenantStorageQuota, tenant_id)
    return _snapshot(account) if account else {
        "tenant_id": tenant_id, "quota_bytes": 0, "used_bytes": 0,
        "reserved_bytes": 0, "remaining_bytes": 0,
        "integrity_state": "NOT_PROVISIONED", "allocation_unit": "bytes",
        "five_decimal_tb_bytes": DEFAULT_PAID_QUOTA_BYTES,
    }


def allocate(db: Session, *, tenant_id: str, quota_bytes: int, actor_id: str, reason: str):
    from amodb.apps.accounts.models import AMO
    if not reason.strip():
        raise ValueError("Quota change requires a recorded reason")
    if not isinstance(quota_bytes, int) or quota_bytes < 0 or quota_bytes > 9_000_000_000_000_000_000:
        raise ValueError("Invalid byte quota")
    # Serialize first allocation as well as subsequent changes. Locking only a
    # quota row cannot protect its creation while that row does not exist yet.
    tenant_query = db.query(AMO).filter(AMO.id == tenant_id)
    if db.get_bind().dialect.name == "postgresql":
        tenant_query = tenant_query.with_for_update()
    if tenant_query.one_or_none() is None:
        raise ValueError("Tenant not found")
    q = db.query(TenantStorageQuota).filter(TenantStorageQuota.tenant_id == tenant_id)
    if db.get_bind().dialect.name == "postgresql":
        q = q.with_for_update()
    account = q.one_or_none()
    if account is None:
        account = TenantStorageQuota(tenant_id=tenant_id, quota_bytes=0, used_bytes=0, reserved_bytes=0)
        db.add(account)
        db.flush()
    if quota_bytes < int(account.used_bytes) + int(account.reserved_bytes):
        raise ValueError("Allocation cannot fall below bytes already stored or reserved")
    old = int(account.quota_bytes)
    account.quota_bytes = quota_bytes
    _event(db, account, "QUOTA_CHANGED", actor_id, metadata={"before_bytes": old, "after_bytes": quota_bytes, "reason": reason.strip()})
    db.flush()
    return _snapshot(account)


def _expire_reservations(db: Session, account: TenantStorageQuota):
    expired = (
        db.query(TenantStorageReservation)
        .filter(TenantStorageReservation.tenant_id == account.tenant_id,
                TenantStorageReservation.state == "RESERVED",
                TenantStorageReservation.expires_at <= _now())
        .all()
    )
    for r in expired:
        r.state = "EXPIRED"
        account.reserved_bytes -= int(r.size_bytes)
        _event(db, account, "RESERVATION_EXPIRED", None, r.object_key, delta_reserved=-int(r.size_bytes))


def reserve(db: Session, *, tenant_id: str, object_key: str, size_bytes: int,
            idempotency_key: str, actor_id: str | None = None, ttl_minutes: int = 60):
    if not object_key.strip() or ".." in object_key.replace("\\", "/").split("/"):
        raise ValueError("Unsafe or empty storage object key")
    # The ledger must use the *same canonical key* as the S3 adapter.
    # Otherwise a//b and a/b can be billed twice while overwriting one object.
    from amodb import storage
    object_key = storage.normalise_key(object_key)
    if not idempotency_key or len(idempotency_key) > 160:
        raise ValueError("A valid upload idempotency key is required")
    if type(size_bytes) is not int or size_bytes < 1:
        raise ValueError("Upload size must be a positive exact byte count")
    if not 1 <= ttl_minutes <= 1440:
        raise ValueError("Reservation expiry must be between 1 and 1440 minutes")
    account = _locked(db, tenant_id)
    _expire_reservations(db, account)
    existing = db.query(TenantStorageReservation).filter(
        TenantStorageReservation.tenant_id == tenant_id,
        TenantStorageReservation.idempotency_key == idempotency_key,
    ).first()
    if existing:
        if existing.object_key != object_key or existing.size_bytes != size_bytes:
            raise ValueError("Upload idempotency key was already used for different content")
        if existing.state not in {"RESERVED", "FINALIZED"}:
            raise ValueError("Upload idempotency key expired or was cancelled")
        return existing
    pending_key = db.query(TenantStorageReservation.id).filter(
        TenantStorageReservation.tenant_id == tenant_id,
        TenantStorageReservation.object_key == object_key,
        TenantStorageReservation.state == "RESERVED",
    ).first()
    if pending_key:
        raise ValueError("Object key already exists in another pending reservation")
    stored = db.query(TenantStorageObject.id).filter(
        TenantStorageObject.tenant_id == tenant_id,
        TenantStorageObject.object_key == object_key,
    ).first()
    if stored:
        raise ValueError("Object key already exists; use a unique immutable object key")
    if int(account.used_bytes) + int(account.reserved_bytes) + size_bytes > int(account.quota_bytes):
        raise ValueError("Tenant storage quota exceeded")
    row = TenantStorageReservation(
        tenant_id=tenant_id, object_key=object_key,
        size_bytes=size_bytes, idempotency_key=idempotency_key,
        expires_at=_now() + timedelta(minutes=ttl_minutes),
    )
    account.reserved_bytes += size_bytes
    db.add(row)
    _event(db, account, "RESERVED", actor_id, object_key, delta_reserved=size_bytes)
    db.flush()
    return row


def finalize(db: Session, *, tenant_id: str, reservation_id: str,
             storage_uri: str, checksum_sha256: str, actor_id: str | None = None):
    account = _locked(db, tenant_id)
    reservation = db.query(TenantStorageReservation).filter(
        TenantStorageReservation.id == reservation_id,
        TenantStorageReservation.tenant_id == tenant_id,
    ).one_or_none()
    if not reservation:
        raise ValueError("Storage reservation not found")
    if reservation.state == "FINALIZED":
        obj = db.query(TenantStorageObject).filter(
            TenantStorageObject.reservation_id == reservation_id,
        ).one_or_none()
        if not obj or obj.storage_uri != storage_uri or obj.checksum_sha256 != checksum_sha256:
            raise ValueError("Finalized object details do not match")
        return obj
    if reservation.state != "RESERVED" or _utc(reservation.expires_at) <= _now():
        raise ValueError("Storage reservation is no longer valid")
    if not storage_uri.startswith("s3://") or len(checksum_sha256) != 64 or any(
        c not in "0123456789abcdef" for c in checksum_sha256.lower()
    ):
        raise ValueError("Invalid retained object URI or SHA-256")
    # Enforce binding between the reservation's canonical tenant key and the
    # actual S3 bucket/prefix. A syntactically valid foreign URI is not proof
    # that the object belongs to this tenant.
    from amodb import storage
    if storage.shared_storage_enabled() and storage_uri != storage.expected_s3_uri(reservation.object_key):
        raise ValueError("Stored object URI does not match the reserved key and bucket")
    existing = db.query(TenantStorageObject).filter(
        TenantStorageObject.tenant_id == tenant_id,
        TenantStorageObject.object_key == reservation.object_key,
    ).first()
    if existing:
        raise ValueError("An object already owns this immutable key")
    reservation.state = "FINALIZED"
    reservation.finalized_at = _now()
    account.reserved_bytes -= int(reservation.size_bytes)
    account.used_bytes += int(reservation.size_bytes)
    obj = TenantStorageObject(
        tenant_id=tenant_id, object_key=reservation.object_key,
        reservation_id=reservation.id, storage_uri=storage_uri,
        size_bytes=reservation.size_bytes, checksum_sha256=checksum_sha256.lower(),
    )
    db.add(obj)
    _event(db, account, "OBJECT_FINALIZED", actor_id, reservation.object_key,
           delta_reserved=-int(reservation.size_bytes), delta_used=int(reservation.size_bytes))
    db.flush()
    return obj


def cancel(db: Session, *, tenant_id: str, reservation_id: str, actor_id: str | None = None):
    account = _locked(db, tenant_id)
    r = db.query(TenantStorageReservation).filter(
        TenantStorageReservation.tenant_id == tenant_id,
        TenantStorageReservation.id == reservation_id,
    ).one_or_none()
    if r is None:
        raise ValueError("Reservation not found")
    if r.state in {"CANCELLED", "EXPIRED"}:
        return
    if r.state != "RESERVED":
        raise ValueError("Cannot cancel a finalized storage reservation")
    r.state = "CANCELLED"
    account.reserved_bytes -= int(r.size_bytes)
    _event(db, account, "RESERVATION_CANCELLED", actor_id, r.object_key,
           delta_reserved=-int(r.size_bytes))
    db.flush()


def recorded_delete(db: Session, *, tenant_id: str, object_key: str, actor_id: str | None = None):
    account = _locked(db, tenant_id)
    obj = db.query(TenantStorageObject).filter(
        TenantStorageObject.tenant_id == tenant_id, TenantStorageObject.object_key == object_key,
    ).one_or_none()
    if obj is None or obj.state == "DELETED":
        return False
    # Call only AFTER storage.delete() succeeds. On failure the quota remains used.
    account.used_bytes -= int(obj.size_bytes)
    obj.state = "DELETED"
    obj.deleted_at = _now()
    _event(db, account, "OBJECT_DELETED", actor_id, object_key, delta_used=-int(obj.size_bytes))
    db.flush()
    return True


def reconcile(db: Session, *, tenant_id: str, actor_id: str | None = None):
    account = _locked(db, tenant_id, allow_drift=True)
    _expire_reservations(db, account)
    active_bytes = int(db.query(func.coalesce(func.sum(TenantStorageObject.size_bytes), 0)).filter(
        TenantStorageObject.tenant_id == tenant_id, TenantStorageObject.state == "ACTIVE",
    ).scalar() or 0)
    pending_bytes = int(db.query(func.coalesce(func.sum(TenantStorageReservation.size_bytes), 0)).filter(
        TenantStorageReservation.tenant_id == tenant_id,
        TenantStorageReservation.state == "RESERVED",
    ).scalar() or 0)
    mismatch = (active_bytes != int(account.used_bytes) or pending_bytes != int(account.reserved_bytes))
    # A database-only recount cannot repair missing/corrupted physical objects.
    # Only a subsequent successful physical audit may clear REMOTE_DRIFT.
    account.integrity_state = "DRIFT" if mismatch else (
        "REMOTE_DRIFT" if account.integrity_state == "REMOTE_DRIFT" else "OK"
    )
    account.last_reconciled_at = _now()
    _event(db, account, "RECONCILIATION_CHECKED", actor_id,
           metadata={"object_bytes": active_bytes, "pending_bytes": pending_bytes, "drift": mismatch})
    db.flush()
    return {**_snapshot(account), "observed_object_bytes": active_bytes,
            "observed_pending_bytes": pending_bytes, "drift": mismatch}


def audit_retained_objects(db: Session, *, tenant_id: str, actor_id: str | None = None,
                           max_objects: int = 1000, verify_checksums: bool = False):
    """Bounded full-tenant physical S3 audit; never report partial scans as clean.

    Physical verification checks that each committed ledger URI belongs to the
    configured bucket/prefix, and that its actual retained bytes match the
    ledger. Optional checksum mode reads the whole object and is deliberately
    capped at 100 objects to avoid unbounded network/disk cost.
    """
    from amodb import storage

    if not storage.shared_storage_enabled():
        raise ValueError("A physical storage audit requires the configured S3 backend")
    if type(max_objects) is not int or not 1 <= max_objects <= 1000:
        raise ValueError("Physical audit limit must be between 1 and 1000 objects")
    if type(verify_checksums) is not bool:
        raise ValueError("verify_checksums must be a boolean")
    if verify_checksums and max_objects > 100:
        raise ValueError("Full checksum audits are limited to 100 objects per run")

    account = _locked(db, tenant_id, allow_drift=True)
    objects = db.query(TenantStorageObject).filter(
        TenantStorageObject.tenant_id == tenant_id, TenantStorageObject.state == "ACTIVE",
    ).order_by(TenantStorageObject.id).limit(max_objects + 1).all()
    if len(objects) > max_objects:
        raise ValueError("Physical audit would be incomplete: active object count exceeds the requested limit")

    failures = []
    for obj in objects:
        try:
            expected_uri = storage.expected_s3_uri(obj.object_key)
            if obj.storage_uri != expected_uri:
                raise ValueError("Object location differs from configured bucket or immutable key")
            if verify_checksums:
                retained = storage.materialize(obj.storage_uri, expected_sha256=obj.checksum_sha256, force_download=True)
                actual_size = retained.stat().st_size
            else:
                actual_size = storage.retained_object_size(obj.storage_uri)
            if int(actual_size) != int(obj.size_bytes):
                raise ValueError("Retained physical byte size does not match the object ledger")
        except Exception as exc:
            # Never conceal remote permission/network errors as successful
            # reconciliation; do not log credentials or raw storage URIs.
            failures.append({"object_id": str(obj.id), "reason": type(exc).__name__})

    active_bytes = sum(int(obj.size_bytes) for obj in objects)
    pending_bytes = int(db.query(func.coalesce(func.sum(TenantStorageReservation.size_bytes), 0)).filter(
        TenantStorageReservation.tenant_id == tenant_id,
        TenantStorageReservation.state == "RESERVED",
    ).scalar() or 0)
    ledger_drift = active_bytes != int(account.used_bytes) or pending_bytes != int(account.reserved_bytes)
    account.integrity_state = "REMOTE_DRIFT" if failures else ("DRIFT" if ledger_drift else "OK")
    account.last_reconciled_at = _now()
    _event(db, account, "PHYSICAL_STORAGE_AUDIT", actor_id, metadata={
        "checked_objects": len(objects), "checksum_verified": verify_checksums,
        "failures": len(failures), "ledger_drift": ledger_drift,
    })
    db.flush()
    return {
        **_snapshot(account), "checked_objects": len(objects),
        "physically_verified": not failures, "checksum_verified": verify_checksums,
        "ledger_drift": ledger_drift, "failures": failures[:20],
    }
