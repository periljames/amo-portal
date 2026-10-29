"""Shared CAR evidence storage with compatibility for already issued local paths.

CAR evidence is tenant-bound by the API/DB authorization layer. This module only
handles durable objects and never exposes a public bucket URL.
"""
from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from amodb import storage
from .car_rca_models import QualityCarRcaAction, QualityCarRcaDocument

logger = logging.getLogger(__name__)


def store_car_file(path: Path, *, amo_id: str, car_id: UUID, content_type: str | None) -> str:
    # A separate directory for each tenant prevents cross-tenant object-key
    # collision and makes selective tenant restore/backfill possible.
    key = f"tenants/{amo_id}/qms/cars/{car_id}/attachments/{path.name}"
    try:
        obj = storage.put_file(path, key=key, content_type=content_type)
    except Exception as exc:
        # Keep the public error generic, but retain the actual storage failure
        # server-side (for example: an unwritable volume or invalid S3 setup).
        logger.exception("CAR evidence upload failed for tenant %s, CAR %s", amo_id, car_id)
        raise HTTPException(
            status_code=503,
            detail="CAR evidence storage is unavailable. The attachment was not recorded.",
        ) from exc
    return obj.uri


def car_attachment_path(uri: str, *, car_id: UUID, expected_sha256: str | None = None) -> Path:
    """Resolve new shared objects or old CAR attachment paths safely."""
    if uri.startswith("s3://"):
        try:
            return storage.materialize(uri, expected_sha256=expected_sha256)
        except (OSError, ValueError, RuntimeError, FileNotFoundError) as exc:
            raise HTTPException(status_code=503, detail="Stored CAR evidence could not be retrieved or verified.") from exc
    # Local-object backend paths live under storage.local_root; old CAR paths
    # remain in the original directory, without allowing arbitrary path reads.
    path = Path(uri).resolve()
    legacy_root = (Path(__file__).resolve().parents[2] / "generated" / "quality" / "car_attachments" / str(car_id)).resolve()
    for root in (legacy_root, storage.local_root().resolve()):
        try:
            path.relative_to(root)
            if path.is_file():
                if expected_sha256:
                    import hashlib
                    digest = hashlib.sha256()
                    with path.open("rb") as handle:
                        for block in iter(lambda: handle.read(1024 * 1024), b""):
                            digest.update(block)
                    if digest.hexdigest().lower() != expected_sha256.lower():
                        raise HTTPException(status_code=503, detail="CAR evidence integrity verification failed.")
                return path
            raise HTTPException(status_code=404, detail="CAR evidence is missing in the configured storage.")
        except ValueError:
            continue
    raise HTTPException(status_code=404, detail="CAR evidence file reference is outside controlled storage.")


def retained_car_attachment(db: Session, car_id: UUID, attachment_id: UUID, *, amo_id: str) -> bool:
    """Do not destroy evidence referenced by submitted investigations or actions."""
    from .tenant_security import set_postgres_tenant_context
    set_postgres_tenant_context(db, amo_id=amo_id, user_id="00000000-0000-0000-0000-000000000000")
    ref = f"CAR-ATTACHMENT:{attachment_id}"
    docs = db.query(QualityCarRcaDocument.submitted_snapshot).filter(
        QualityCarRcaDocument.car_id == car_id,
        QualityCarRcaDocument.amo_id == amo_id,
        QualityCarRcaDocument.submitted_snapshot.is_not(None),
    ).all()
    if any(ref in str(item[0]) for item in docs):
        return True
    actions = db.query(QualityCarRcaAction.evidence_references).filter(
        QualityCarRcaAction.car_id == car_id,
        QualityCarRcaAction.amo_id == amo_id,
    ).all()
    if any(ref in (item[0] or []) for item in actions):
        return True
    # Future implementation revisions remain in the immutable action ledger.
    from .car_rca_models import QualityCarRcaActionEvent, QualityCarRcaRevision
    for row in db.query(QualityCarRcaActionEvent.snapshot).filter(
        QualityCarRcaActionEvent.car_id == car_id,
        QualityCarRcaActionEvent.amo_id == amo_id
    ).all():
        if ref in str(row[0]):
            return True
    for row in db.query(QualityCarRcaRevision.snapshot).filter(
        QualityCarRcaRevision.car_id == car_id,
        QualityCarRcaRevision.amo_id == amo_id
    ).all():
        if ref in str(row[0]):
            return True
    return False


def delete_unretained_car_file(uri: str, *, car_id: UUID) -> None:
    """Delete an unreferenced CAR blob, including a legacy local file."""
    if uri.startswith("s3://"):
        storage.delete(uri)
        return
    path = car_attachment_path(uri, car_id=car_id)
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise HTTPException(status_code=503, detail="Unable to delete the CAR evidence file safely.") from exc
