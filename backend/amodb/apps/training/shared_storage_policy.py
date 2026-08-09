from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from fastapi.responses import FileResponse

from amodb import storage
from amodb.apps.accounts import services as account_services

from . import models as training_models


_INSTALLED = False


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def install_training_shared_storage(router_module) -> None:
    """Replace only Training evidence upload/download persistence.

    Course, compliance, review, notification and audit behavior stays in the
    authoritative Training router; the two file-transfer endpoints retain their
    existing FastAPI dependency model and permissions while storing bytes through
    the shared portal object store.
    """

    global _INSTALLED
    if _INSTALLED:
        return

    legacy_root = Path(router_module._TRAINING_UPLOAD_DIR).resolve()
    max_upload_bytes = int(router_module._MAX_UPLOAD_BYTES or 0)

    def upload_training_file_shared(**values: Any):
        background_tasks = values["background_tasks"]
        kind = values["kind"]
        owner_user_id = values.get("owner_user_id")
        course_id = values.get("course_id")
        event_id = values.get("event_id")
        record_id = values.get("record_id")
        deferral_request_id = values.get("deferral_request_id")
        file = values["file"]
        db = values["db"]
        current_user = values["current_user"]
        is_editor = router_module._is_training_editor(current_user)

        if owner_user_id is None:
            owner_user_id = current_user.id
        if not is_editor and owner_user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only upload evidence for your own account.")

        owner = (
            db.query(router_module.accounts_models.User)
            .filter(router_module.accounts_models.User.id == owner_user_id, router_module.accounts_models.User.amo_id == current_user.amo_id)
            .first()
        )
        if not owner:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Owner user not found in your AMO.")

        checks = (
            (course_id, training_models.TrainingCourse, "course_id"),
            (event_id, training_models.TrainingEvent, "event_id"),
            (record_id, training_models.TrainingRecord, "record_id"),
            (deferral_request_id, training_models.TrainingDeferralRequest, "deferral_request_id"),
        )
        for identifier, model, label in checks:
            if identifier:
                ok = db.query(model).filter(model.id == identifier, model.amo_id == current_user.amo_id).first()
                if not ok:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {label} for this AMO.")

        original_name = file.filename or "upload.bin"
        ext = "".join(Path(original_name).suffixes)[-20:]
        file_id = training_models.generate_user_id()
        cache = storage.cache_root()
        cache.mkdir(parents=True, exist_ok=True)
        fd, raw_path = tempfile.mkstemp(prefix="training-evidence-", dir=str(cache))
        os.close(fd)
        staged = Path(raw_path)
        sha = hashlib.sha256()
        total = 0
        stored = None
        try:
            with staged.open("wb") as out:
                while True:
                    chunk = file.file.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if max_upload_bytes and total > max_upload_bytes:
                        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File too large.")
                    sha.update(chunk)
                    out.write(chunk)
            if total <= 0:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Uploaded training evidence is empty.")

            stored = storage.put_file(
                staged,
                key=f"training/{current_user.amo_id}/{owner.id}/{file_id}{ext}",
                content_type=file.content_type,
            )
            auto_approved = bool(is_editor)
            record = training_models.TrainingFile(
                id=file_id,
                amo_id=current_user.amo_id,
                owner_user_id=owner.id,
                kind=kind,
                course_id=course_id,
                event_id=event_id,
                record_id=record_id,
                deferral_request_id=deferral_request_id,
                original_filename=original_name,
                storage_path=stored.uri,
                content_type=file.content_type,
                size_bytes=stored.size_bytes or total,
                sha256=sha.hexdigest(),
                review_status=training_models.TrainingFileReviewStatus.APPROVED if auto_approved else training_models.TrainingFileReviewStatus.PENDING,
                reviewed_at=router_module.datetime.now(router_module.timezone.utc) if auto_approved else None,
                reviewed_by_user_id=current_user.id if auto_approved else None,
                review_comment="Uploaded by authorized training editor." if auto_approved else None,
                uploaded_by_user_id=current_user.id,
            )
            db.add(record)
            account_services.record_usage(
                db,
                amo_id=current_user.amo_id,
                meter_key=account_services.METER_KEY_STORAGE_MB,
                quantity=account_services.megabytes_from_bytes(record.size_bytes or total),
                commit=False,
            )
            router_module._create_notification(
                db,
                amo_id=current_user.amo_id,
                user_id=owner.id,
                title="Evidence uploaded",
                body=(f"Your document '{original_name}' was uploaded and approved." if auto_approved else f"Your document '{original_name}' was uploaded and is pending review."),
                severity=training_models.TrainingNotificationSeverity.INFO,
                link_path="/profile/training",
                dedupe_key=f"file:{file_id}:uploaded",
                created_by_user_id=current_user.id,
            )
            router_module._audit(
                db,
                amo_id=current_user.amo_id,
                actor_user_id=current_user.id,
                action="FILE_UPLOAD",
                entity_type="TrainingFile",
                entity_id=file_id,
                details={"owner_user_id": owner.id, "kind": str(kind), "filename": original_name, "storage_backend": stored.backend},
            )
            db.commit()
            db.refresh(record)
            return router_module._file_to_read(record)
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
            try:
                file.file.close()
            except Exception:
                pass

    def download_training_file_shared(**values: Any):
        file_id = values["file_id"]
        db = values["db"]
        current_user = values["current_user"]
        record = (
            db.query(training_models.TrainingFile)
            .filter(training_models.TrainingFile.id == file_id, training_models.TrainingFile.amo_id == current_user.amo_id)
            .first()
        )
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training file not found.")
        if not router_module._is_training_editor(current_user) and record.owner_user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to download this file.")

        raw = str(record.storage_path or "")
        try:
            if raw.startswith("s3://") or _inside(Path(raw), storage.local_root()):
                path = storage.materialize(raw, expected_sha256=record.sha256)
            else:
                # Controlled read compatibility for evidence uploaded before the
                # shared-storage migration. New writes never use this path.
                legacy = Path(raw).resolve()
                if not _inside(legacy, legacy_root) or not legacy.is_file():
                    raise FileNotFoundError(raw)
                path = legacy
        except (FileNotFoundError, ValueError, OSError) as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing from controlled storage.") from exc

        return FileResponse(
            path=str(path),
            media_type=record.content_type or "application/octet-stream",
            filename=record.original_filename,
            headers={"ETag": f'"{record.sha256 or record.id}"', "Cache-Control": "private, max-age=300"},
        )

    replacements = {
        "/training/files/upload": upload_training_file_shared,
        "/training/files/{file_id}/download": download_training_file_shared,
    }
    for route in router_module.router.routes:
        replacement = replacements.get(getattr(route, "path", ""))
        if replacement is None:
            continue
        route.endpoint = replacement
        if getattr(route, "dependant", None) is not None:
            route.dependant.call = replacement

    _INSTALLED = True
