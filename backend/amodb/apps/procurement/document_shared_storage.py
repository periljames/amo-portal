from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from amodb import storage

from . import document_service


LEGACY_ROOT = document_service.DOCUMENT_ROOT.resolve()


def promote_document_file(record) -> None:
    """Promote a validated Procurement staging file into shared storage."""
    raw = str(getattr(record, "stored_path", "") or "")
    if not raw or raw.startswith("s3://"):
        return
    staged = Path(raw).resolve()
    if not staged.is_file():
        raise HTTPException(status_code=404, detail="The retained document file is unavailable.")
    try:
        staged.relative_to(LEGACY_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="The retained document path is outside controlled Procurement staging.") from exc

    entity_type = str(getattr(getattr(record, "entity_type", None), "value", getattr(record, "entity_type", "document"))).lower()
    stored = storage.put_file(
        staged,
        key=(
            f"procurement/{record.amo_id}/{entity_type}/{record.entity_id}/"
            f"{record.id}_{record.original_filename or staged.name}"
        ),
        content_type=getattr(record, "mime_type", None),
    )
    record.stored_path = stored.uri
    record.size_bytes = stored.size_bytes or record.size_bytes
    staged.unlink(missing_ok=True)


def materialize_document_file(record) -> Path:
    raw = str(getattr(record, "stored_path", "") or "")
    if not raw:
        raise HTTPException(status_code=409, detail="This evidence record is a reference link and has no retained file to download.")
    if raw.startswith("s3://"):
        try:
            return storage.materialize(raw, expected_sha256=getattr(record, "sha256", None))
        except (FileNotFoundError, ValueError, OSError) as exc:
            raise HTTPException(status_code=404, detail="The retained document file is unavailable.") from exc
    return document_service.get_document_file(record)


def discard_promoted_file(record) -> None:
    raw = str(getattr(record, "stored_path", "") or "")
    if raw.startswith("s3://"):
        try:
            storage.delete(raw)
        except Exception:
            pass
