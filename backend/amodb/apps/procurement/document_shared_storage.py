from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException

from amodb import storage

from . import document_service


_INSTALLED = False
_ORIGINAL_CREATE = document_service.create_document
_LEGACY_ROOT = document_service.DOCUMENT_ROOT.resolve()
_STAGING_ROOT = (storage.cache_root() / "procurement-staging").resolve()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
        return True
    except ValueError:
        return False


def _shared_create(*args: Any, **kwargs: Any):
    record = _ORIGINAL_CREATE(*args, **kwargs)
    raw_path = str(getattr(record, "stored_path", "") or "")
    if not raw_path:
        return record
    staged = Path(raw_path).resolve()
    entity_type = str(getattr(getattr(record, "entity_type", None), "value", getattr(record, "entity_type", "document"))).lower()
    key = (
        f"procurement/{record.amo_id}/{entity_type}/{record.entity_id}/"
        f"{record.id}_{record.original_filename or staged.name}"
    )
    stored = None
    try:
        stored = storage.put_file(staged, key=key, content_type=getattr(record, "mime_type", None))
        record.stored_path = stored.uri
        record.size_bytes = stored.size_bytes or record.size_bytes
        return record
    except Exception:
        if stored is not None:
            try:
                storage.delete(stored.uri)
            except Exception:
                pass
        raise
    finally:
        staged.unlink(missing_ok=True)


def _shared_get_file(record):
    raw = str(getattr(record, "stored_path", "") or "")
    if not raw:
        raise HTTPException(status_code=409, detail="This evidence record is a reference link and has no retained file to download.")
    if raw.startswith("s3://"):
        try:
            return storage.materialize(raw, expected_sha256=getattr(record, "sha256", None))
        except (FileNotFoundError, ValueError, OSError) as exc:
            raise HTTPException(status_code=404, detail="The retained document file is unavailable.") from exc

    path = Path(raw).resolve()
    if not (_inside(path, _LEGACY_ROOT) or _inside(path, _STAGING_ROOT) or _inside(path, storage.local_root())):
        raise HTTPException(status_code=500, detail="The retained document path is outside controlled storage.")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="The retained document file is unavailable.")
    return path


def _shared_discard(record) -> None:
    raw = str(getattr(record, "stored_path", "") or "")
    if not raw:
        return
    if raw.startswith("s3://"):
        try:
            storage.delete(raw)
        except Exception:
            pass
        return
    path = Path(raw).resolve()
    if _inside(path, _LEGACY_ROOT) or _inside(path, _STAGING_ROOT) or _inside(path, storage.local_root()):
        path.unlink(missing_ok=True)


def install_procurement_shared_storage() -> None:
    """Preserve Procurement validation/audit semantics while changing persistence.

    The existing service still performs MIME, file-signature, size, duplicate and
    Quality-evidence checks against a node-local staging file. Before control
    returns to the router that staged file is atomically promoted to the portal's
    configured shared object store and the DB row carries the durable object URI.
    """

    global _INSTALLED
    if _INSTALLED:
        return
    _STAGING_ROOT.mkdir(parents=True, exist_ok=True)
    document_service.DOCUMENT_ROOT = _STAGING_ROOT
    document_service.create_document = _shared_create
    document_service.get_document_file = _shared_get_file
    document_service.discard_document_file = _shared_discard
    _INSTALLED = True
