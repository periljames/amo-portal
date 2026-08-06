from __future__ import annotations

import os
import time
from pathlib import Path

from amodb.database import WriteSessionLocal

from .pdf_capability_service import CAPABILITY_CACHE_ROOT, PdfEngineError, _safe_cache_root, warm_pdf_revision_capabilities


_LOCK_STALE_SECONDS = 30 * 60


def _acquire_prewarm_lock() -> Path | None:
    try:
        root = _safe_cache_root()
    except PdfEngineError:
        return None

    lock_path = (root / "prewarm.lock").resolve()
    if lock_path.parent != root:
        return None
    try:
        if lock_path.exists() and lock_path.stat().st_mtime + _LOCK_STALE_SECONDS < time.time():
            lock_path.unlink(missing_ok=True)
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except (FileExistsError, OSError):
        return None

    try:
        os.write(descriptor, str(os.getpid()).encode("ascii", errors="ignore"))
    finally:
        os.close(descriptor)
    return lock_path


def warm_existing_pdf_revision_capabilities(limit: int = 100) -> None:
    """Prepare recent existing PDF revisions without delaying API startup."""

    from amodb.apps.manuals import models as manual_models

    lock_path = _acquire_prewarm_lock()
    if lock_path is None:
        return

    db = WriteSessionLocal()
    try:
        rows = (
            db.query(manual_models.ManualRevision.id)
            .filter(
                manual_models.ManualRevision.source_type_enum == manual_models.ManualSourceType.PDF,
                manual_models.ManualRevision.source_storage_path.isnot(None),
                manual_models.ManualRevision.source_sha256.isnot(None),
            )
            .order_by(
                (manual_models.ManualRevision.status_enum == manual_models.ManualRevisionStatus.PUBLISHED).desc(),
                manual_models.ManualRevision.published_at.desc(),
                manual_models.ManualRevision.created_at.desc(),
            )
            .limit(max(1, min(int(limit or 100), 1000)))
            .all()
        )
        revision_ids = [str(row[0]) for row in rows if row and row[0]]
    except Exception:
        revision_ids = []
    finally:
        db.close()

    try:
        for revision_id in revision_ids:
            warm_pdf_revision_capabilities(revision_id)
    finally:
        lock_path.unlink(missing_ok=True)
