from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

from amodb.apps.manuals import models as manual_models
from amodb.database import WriteSessionLocal

from .pdf_capability_service import inspect_pdf_capabilities_bytes


def warm_pdf_capability_cache_background(revision_id: str) -> None:
    """Precompute immutable PDF capability metadata after upload.

    This is an acceleration-only background task. Reader authorization still
    happens on every live capability request, but the expensive PDFium/object
    inspection is reused by source SHA-256 instead of delaying the first user.
    """

    db = WriteSessionLocal()
    try:
        revision = (
            db.query(manual_models.ManualRevision)
            .filter(manual_models.ManualRevision.id == revision_id)
            .first()
        )
        if not revision:
            return
        source_type = str(
            getattr(revision.source_type_enum, "value", revision.source_type_enum or "")
        ).upper()
        if source_type != "PDF":
            return

        raw_path = str(revision.source_storage_path or "").strip()
        if not raw_path:
            return
        path = Path(raw_path).resolve()
        if not path.exists() or not path.is_file() or path.suffix.lower() != ".pdf":
            return

        content = path.read_bytes()
        recorded = str(revision.source_sha256 or "").strip().lower()
        actual = hashlib.sha256(content).hexdigest()
        if not recorded or not hmac.compare_digest(recorded, actual):
            return

        inspection = inspect_pdf_capabilities_bytes(content)
        if not hmac.compare_digest(inspection.source_sha256.lower(), recorded):
            return
    except Exception:
        # Upload/reference indexing must not fail because an acceleration cache
        # volume is unavailable. The live reader retains the same fail-closed
        # capability verification path.
        return
    finally:
        db.close()
