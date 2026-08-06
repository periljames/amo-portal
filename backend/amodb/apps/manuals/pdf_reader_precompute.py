from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from amodb.apps.doc_control.pdfium_service import PdfEngineError, PdfInspection
from amodb.database import WriteSessionLocal

from . import models
from .pdf_reader_form_override_router import (
    _SAFE_READER_CACHE_ROOT,
    _capability_inspection,
    _safe_reader_cache_path,
)


LOGGER = logging.getLogger(__name__)
_INSPECTION_CACHE_ROOT = Path(
    os.getenv(
        "PDF_READER_CAPABILITY_CACHE_DIR",
        str(_SAFE_READER_CACHE_ROOT / "capabilities"),
    )
).resolve()
_CACHE_LOCK = threading.RLock()


def _inspection_cache_path(source_sha256: str) -> Path:
    _INSPECTION_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    root = _INSPECTION_CACHE_ROOT.resolve()
    target = (root / f"{source_sha256.lower()}.json").resolve()
    if target.parent != root:
        raise PdfEngineError(
            "PDF_CAPABILITY_CACHE_PATH_INVALID",
            "Unsafe PDF capability cache path",
            status_code=500,
        )
    return target


def _validated_checksum(revision: models.ManualRevision) -> str:
    checksum = str(getattr(revision, "source_sha256", "") or "").strip().lower()
    if not checksum:
        raise PdfEngineError(
            "PDF_SOURCE_CHECKSUM_MISSING",
            "The immutable revision does not have a recorded source checksum",
            status_code=409,
        )
    return checksum


def _deserialize_inspection(payload: dict[str, Any], expected_sha256: str) -> PdfInspection:
    if str(payload.get("source_sha256") or "").lower() != expected_sha256:
        raise ValueError("cached checksum mismatch")
    return PdfInspection(
        engine=str(payload["engine"]),
        engine_version=str(payload["engine_version"]),
        source_sha256=expected_sha256,
        page_count=int(payload["page_count"]),
        form_type=int(payload["form_type"]),
        has_acroform=bool(payload["has_acroform"]),
        has_javascript=bool(payload["has_javascript"]),
        is_dynamic_xfa=bool(payload["is_dynamic_xfa"]),
        encrypted=bool(payload["encrypted"]),
        can_flatten=bool(payload["can_flatten"]),
        unsupported_reason=payload.get("unsupported_reason"),
        template_fingerprint=payload.get("template_fingerprint"),
    )


def _read_cached_inspection(
    revision: models.ManualRevision,
    source_sha256: str,
) -> PdfInspection | None:
    target = _inspection_cache_path(source_sha256)
    if not target.exists() or not target.is_file():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        inspection = _deserialize_inspection(payload, source_sha256)
        recorded_pages = int(getattr(revision, "source_page_count", 0) or 0)
        if recorded_pages and inspection.page_count != recorded_pages:
            return None
        return inspection
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        target.unlink(missing_ok=True)
        return None


def _write_cached_inspection(inspection: PdfInspection) -> None:
    target = _inspection_cache_path(inspection.source_sha256)
    payload = json.dumps(
        asdict(inspection),
        sort_keys=True,
        separators=(",", ":"),
    )
    with tempfile.NamedTemporaryFile(
        prefix=f"{inspection.source_sha256}-",
        suffix=".tmp",
        dir=target.parent,
        delete=False,
        mode="w",
        encoding="utf-8",
    ) as handle:
        temporary = Path(handle.name).resolve()
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def cached_pdf_inspection(
    revision: models.ManualRevision,
    *,
    prepare_safe_reader: bool = True,
) -> PdfInspection:
    """Return checksum-keyed inspection and materialize any safe derivative once."""

    source_sha256 = _validated_checksum(revision)
    with _CACHE_LOCK:
        inspection = _read_cached_inspection(revision, source_sha256)
        if inspection is None:
            inspection = _capability_inspection(revision)
            _write_cached_inspection(inspection)

        if prepare_safe_reader and inspection.has_javascript:
            _safe_reader_cache_path(revision, inspection.source_sha256)
        return inspection


def precompute_pdf_reader_assets(revision_id: str) -> None:
    """Background upload/approval task for immutable reader capability assets."""

    db = WriteSessionLocal()
    try:
        revision = (
            db.query(models.ManualRevision)
            .filter(models.ManualRevision.id == revision_id)
            .first()
        )
        if revision is None:
            LOGGER.warning("PDF reader precompute skipped: revision %s not found", revision_id)
            return
        source_type = str(
            getattr(
                getattr(revision, "source_type_enum", None),
                "value",
                getattr(revision, "source_type_enum", ""),
            )
            or ""
        ).upper()
        if source_type != "PDF":
            return
        cached_pdf_inspection(revision, prepare_safe_reader=True)
    except Exception:
        # Upload/index completion must remain independently observable. The
        # capability route retries synchronously and records a precise failure.
        LOGGER.exception("PDF reader precompute failed for revision %s", revision_id)
    finally:
        db.close()
