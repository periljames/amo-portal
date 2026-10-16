"""Safeguarded S3 object writes that reserve bytes against the tenant contract.

The caller owns the Session transaction. Failed uploads are removed, and the
session is left for its owner to roll back. Object content is never returned
before checksum-verified durable retention and quota finalization.
"""
from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from amodb import storage
from . import storage_quota_service


def _quota_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    return HTTPException(
        status_code=413 if "quota exceeded" in detail.lower() else 409,
        detail=detail,
    )


def put_bytes(db, *, tenant_id: str, key: str, content: bytes,
              content_type: str | None, actor_id: str | None = None,
              operation_id: str | None = None):
    if not storage.shared_storage_enabled():
        raise HTTPException(status_code=503, detail="Shared object storage must be enabled")
    from amodb.apps.quality.tenant_security import set_postgres_tenant_context
    set_postgres_tenant_context(db, amo_id=tenant_id, user_id=actor_id or "")
    digest = hashlib.sha256(content).hexdigest()
    try:
        reservation = storage_quota_service.reserve(
            db, tenant_id=tenant_id, object_key=key, size_bytes=len(content),
            idempotency_key=operation_id or f"upload:{uuid4().hex}",
            actor_id=actor_id,
        )
    except ValueError as exc:
        raise _quota_error(exc) from exc
    retained = None
    try:
        retained = storage.put_stream(BytesIO(content), key=key, content_type=content_type)
        if int(retained.size_bytes) != len(content):
            raise IOError("Object storage retained incorrect byte count")
        storage_quota_service.finalize(
            db, tenant_id=tenant_id, reservation_id=reservation.id,
            storage_uri=retained.uri, checksum_sha256=digest, actor_id=actor_id,
        )
        return retained
    except Exception:
        if retained is not None:
            try:
                storage.delete(retained.uri)
            except Exception:
                pass
        raise


def put_local_file(db, *, tenant_id: str, key: str, path: Path,
                   content_type: str | None, actor_id: str | None = None,
                   operation_id: str | None = None):
    if not storage.shared_storage_enabled():
        raise HTTPException(status_code=503, detail="Shared object storage must be enabled")
    from amodb.apps.quality.tenant_security import set_postgres_tenant_context
    set_postgres_tenant_context(db, amo_id=tenant_id, user_id=actor_id or "")
    size = path.stat().st_size
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    try:
        reservation = storage_quota_service.reserve(
            db, tenant_id=tenant_id, object_key=key, size_bytes=size,
            idempotency_key=operation_id or f"upload:{uuid4().hex}",
            actor_id=actor_id,
        )
    except ValueError as exc:
        raise _quota_error(exc) from exc
    retained = None
    try:
        retained = storage.put_file(path, key=key, content_type=content_type)
        if int(retained.size_bytes) != size:
            raise IOError("Object storage retained incorrect byte count")
        storage_quota_service.finalize(
            db, tenant_id=tenant_id, reservation_id=reservation.id,
            storage_uri=retained.uri, checksum_sha256=digest.hexdigest(), actor_id=actor_id,
        )
        return retained
    except Exception:
        if retained is not None:
            try:
                storage.delete(retained.uri)
            except Exception:
                pass
        raise
