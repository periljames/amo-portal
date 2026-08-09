from __future__ import annotations

import hashlib
import importlib
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from fastapi.responses import FileResponse

from amodb import storage
from amodb.apps.accounts import services as account_services


_INSTALLED = False


def _replace_route_call(router, path: str, replacement) -> bool:
    replaced = False
    for route in router.routes:
        if getattr(route, "path", "") != path:
            continue
        route.endpoint = replacement
        if getattr(route, "dependant", None) is not None:
            route.dependant.call = replacement
        replaced = True
    return replaced


def _stage_upload(upload, *, max_bytes: int, prefix: str) -> tuple[Path, int, str]:
    root = storage.cache_root()
    root.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=prefix, dir=str(root))
    os.close(fd)
    path = Path(raw)
    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("wb") as handle:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if max_bytes and total > max_bytes:
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Upload exceeds maximum file size.")
                digest.update(chunk)
                handle.write(chunk)
        if total <= 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Uploaded file is empty.")
        return path, total, digest.hexdigest()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        try:
            upload.file.close()
        except Exception:
            pass


def _install_fleet() -> None:
    fleet_models = importlib.import_module("amodb.apps.fleet.models")
    fleet_router = importlib.import_module("amodb.apps.fleet.router")

    legacy_root = Path(fleet_router.DOC_UPLOAD_DIR).resolve()

    def upload_document_evidence_shared(**values: Any):
        document_id = values["document_id"]
        upload = values["file"]
        db = values["db"]
        current_user = values["current_user"]
        doc = fleet_router._get_document_or_404(db, document_id, current_user.amo_id)
        filename = upload.filename or "document"
        ext = Path(filename).suffix.lower()
        if ext not in fleet_router.ALLOWED_DOC_EXTS:
            raise HTTPException(status_code=400, detail="Upload must be a PDF or image file (.pdf, .png, .jpg, .jpeg).")

        staged, size_bytes, sha256 = _stage_upload(upload, max_bytes=int(fleet_router.DOC_MAX_UPLOAD_BYTES or 0), prefix="aircraft-doc-")
        stored = None
        previous_uri = str(doc.file_storage_path or "") or None
        try:
            stored = storage.put_file(
                staged,
                key=f"aircraft-documents/{current_user.amo_id}/{doc.aircraft_serial_number}/{doc.id}/{uuid4().hex}{ext}",
                content_type=upload.content_type,
            )
            doc.file_storage_path = stored.uri
            doc.file_original_name = filename
            doc.file_content_type = upload.content_type
            doc.last_uploaded_at = fleet_router.datetime.utcnow()
            doc.last_uploaded_by_user_id = current_user.id
            doc.updated_at = fleet_router.datetime.utcnow()
            evaluation = fleet_router.services.refresh_document_status(doc)
            account_services.record_usage(
                db,
                amo_id=current_user.amo_id,
                meter_key=account_services.METER_KEY_STORAGE_MB,
                quantity=account_services.megabytes_from_bytes(stored.size_bytes or size_bytes),
                commit=False,
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)
        except Exception:
            db.rollback()
            if stored is not None:
                try:
                    storage.delete(stored.uri)
                except Exception:
                    pass
            raise
        finally:
            staged.unlink(missing_ok=True)

        if previous_uri and previous_uri != stored.uri:
            try:
                if previous_uri.startswith("s3://"):
                    storage.delete(previous_uri)
                else:
                    old = Path(previous_uri).resolve()
                    if old.is_file() and (str(old).startswith(str(legacy_root)) or str(old).startswith(str(storage.local_root()))):
                        old.unlink(missing_ok=True)
            except Exception:
                pass
        _ = sha256
        return fleet_router._document_to_schema(doc, evaluation)

    def _fleet_file(doc):
        raw = str(doc.file_storage_path or "")
        if not raw:
            raise HTTPException(status_code=404, detail="No evidence uploaded for this document.")
        try:
            if raw.startswith("s3://"):
                return storage.materialize(raw)
            path = Path(raw).resolve()
            if path.is_file() and (str(path).startswith(str(legacy_root)) or str(path).startswith(str(storage.local_root()))):
                return path
        except Exception:
            pass
        raise HTTPException(status_code=404, detail="Document evidence not found.")

    def download_document_evidence_shared(**values: Any):
        document_id = values["document_id"]
        db = values["db"]
        current_user = values["current_user"]
        doc = fleet_router._get_document_or_404(db, document_id, current_user.amo_id)
        path = _fleet_file(doc)
        return FileResponse(path=str(path), media_type=doc.file_content_type or "application/octet-stream", filename=doc.file_original_name or path.name, headers={"Cache-Control": "private, max-age=300"})

    def download_document_evidence_zip_shared(**values: Any):
        payload = values["payload"]
        background_tasks = values["background_tasks"]
        db = values["db"]
        current_user = values["current_user"]
        doc_ids = list({int(doc_id) for doc_id in payload.document_ids})
        if not doc_ids:
            raise HTTPException(status_code=400, detail="No document IDs supplied.")
        docs = (
            db.query(fleet_models.AircraftDocument)
            .join(fleet_models.Aircraft)
            .filter(fleet_models.AircraftDocument.id.in_(doc_ids), fleet_models.Aircraft.amo_id == current_user.amo_id)
            .all()
        )
        if len(docs) != len(doc_ids):
            raise HTTPException(status_code=404, detail="One or more documents were not found in your AMO.")

        root = storage.cache_root()
        root.mkdir(parents=True, exist_ok=True)
        fd, raw = tempfile.mkstemp(prefix="aircraft-evidence-", suffix=".zip", dir=str(root))
        os.close(fd)
        temp_path = Path(raw)
        try:
            with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                used: set[str] = set()
                for doc in docs:
                    path = _fleet_file(doc)
                    requested = Path(doc.file_original_name or path.name).name
                    arcname = requested
                    if arcname in used:
                        arcname = f"{doc.id}_{requested}"
                    used.add(arcname)
                    archive.write(path, arcname=arcname)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        background_tasks.add_task(temp_path.unlink, missing_ok=True)
        return FileResponse(path=str(temp_path), media_type="application/zip", filename="aircraft_documents.zip")

    required = {
        "/aircraft/documents/{document_id}/upload": upload_document_evidence_shared,
        "/aircraft/documents/{document_id}/download": download_document_evidence_shared,
        "/aircraft/documents/download-zip": download_document_evidence_zip_shared,
    }
    missing = [path for path, call in required.items() if not _replace_route_call(fleet_router.router, path, call)]
    if missing:
        raise RuntimeError(f"Unable to install Fleet shared-storage routes: {missing}")


def _install_ehm() -> None:
    reliability_models = importlib.import_module("amodb.apps.reliability.models")
    reliability_router = importlib.import_module("amodb.apps.reliability.router")
    reliability_schemas = importlib.import_module("amodb.apps.reliability.schemas")

    def upload_ehm_log_shared(**values: Any):
        background_tasks = values["background_tasks"]
        upload = values["file"]
        aircraft_serial_number = values.get("aircraft_serial_number") or values.get("tail") or values.get("aircraft_id")
        engine_position = values["engine_position"]
        engine_serial_number = values.get("engine_serial_number")
        source = values.get("source")
        notes = values.get("notes")
        current_user = values["current_user"]
        db = values["db"]
        if not aircraft_serial_number:
            raise HTTPException(status_code=400, detail="Aircraft identifier is required.")

        filename = upload.filename or "ehm.log"
        ext = Path(filename).suffix.lower()
        if ext not in reliability_router.EHM_ALLOWED_EXTS:
            raise HTTPException(status_code=400, detail="Upload must be a .log file.")
        if upload.content_type and upload.content_type not in reliability_router.EHM_ALLOWED_CONTENT_TYPES:
            raise HTTPException(status_code=400, detail="Unsupported content type for EHM log.")

        amo_id = reliability_router._amo_id(current_user)
        log_id = reliability_router.generate_uuid7()
        staged, total, sha256 = _stage_upload(upload, max_bytes=int(reliability_router.EHM_MAX_UPLOAD_BYTES or 0), prefix="ehm-log-")
        existing = (
            db.query(reliability_models.EhmRawLog)
            .filter(
                reliability_models.EhmRawLog.amo_id == amo_id,
                reliability_models.EhmRawLog.sha256_hash == sha256,
                reliability_models.EhmRawLog.aircraft_serial_number == aircraft_serial_number,
                reliability_models.EhmRawLog.engine_position == engine_position,
            )
            .first()
        )
        if existing:
            staged.unlink(missing_ok=True)
            return reliability_schemas.EhmLogIngestResult(log=existing, deduplicated=True)

        stored = None
        try:
            stored = storage.put_file(
                staged,
                key=f"ehm/{amo_id}/{aircraft_serial_number}/{engine_position}/{log_id}{ext}",
                content_type=upload.content_type,
            )
            log = reliability_models.EhmRawLog(
                id=log_id,
                amo_id=amo_id,
                aircraft_serial_number=aircraft_serial_number,
                engine_position=engine_position,
                engine_serial_number=engine_serial_number,
                source=source,
                notes=notes,
                original_filename=filename,
                content_type=upload.content_type,
                storage_path=stored.uri,
                size_bytes=stored.size_bytes or total,
                sha256_hash=sha256,
                parse_status=reliability_models.EhmParseStatusEnum.PENDING,
                uploaded_by_user_id=current_user.id,
            )
            db.add(log)
            db.commit()
            db.refresh(log)
        except Exception:
            db.rollback()
            if stored is not None:
                try:
                    storage.delete(stored.uri)
                except Exception:
                    pass
            raise
        finally:
            staged.unlink(missing_ok=True)
        background_tasks.add_task(reliability_router.ehm_services.parse_log_in_background, log.id)
        return reliability_schemas.EhmLogIngestResult(log=log, deduplicated=False)

    path = "/reliability/ehm/logs/upload"
    if not _replace_route_call(reliability_router.router, path, upload_ehm_log_shared):
        raise RuntimeError(f"Unable to install EHM shared-storage route: {path}")


def install_shared_storage_route_hardening() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_fleet()
    _install_ehm()
    _INSTALLED = True
