from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from amodb import storage
from amodb.apps.accounts import services as account_services

from . import models as training_models


_INSTALLED = False
_ALLOWED_EVIDENCE_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".webp",
    ".doc", ".docx", ".xls", ".xlsx", ".xlsm", ".csv", ".txt",
}
_BLOCKED_CONTENT_TYPES = {
    "text/html", "application/xhtml+xml", "application/javascript",
    "text/javascript", "application/x-msdownload", "application/x-executable",
}


def install_training_shared_storage(router_module) -> None:
    """Replace only Training evidence upload persistence.

    Download remains an explicit FastAPI endpoint in the authoritative Training
    router so its path parameters and dependencies cannot drift after route
    registration. New upload bytes are stored through the shared object store.
    """

    global _INSTALLED
    if _INSTALLED:
        return

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
        linked: dict[str, Any] = {}
        for identifier, model, label in checks:
            if identifier:
                row = db.query(model).filter(model.id == identifier, model.amo_id == current_user.amo_id).first()
                if not row:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {label} for this AMO.")
                linked[label] = row

        linked_record = linked.get("record_id")
        linked_event = linked.get("event_id")
        linked_deferral = linked.get("deferral_request_id")
        if linked_record and str(linked_record.user_id) != str(owner.id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The selected training record belongs to a different person.")
        if linked_record and course_id and str(linked_record.course_id) != str(course_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The selected training record belongs to a different course.")
        if linked_record and event_id and linked_record.event_id and str(linked_record.event_id) != str(event_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The selected training record belongs to a different session.")
        if linked_event and course_id and str(linked_event.course_id) != str(course_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The selected session belongs to a different course.")
        if linked_deferral and str(linked_deferral.user_id) != str(owner.id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The selected deferral belongs to a different person.")
        if linked_deferral and course_id and str(linked_deferral.course_id) != str(course_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The selected deferral belongs to a different course.")

        original_name = Path(file.filename or "upload.bin").name
        ext = Path(original_name).suffix.lower()
        if ext not in _ALLOWED_EVIDENCE_EXTENSIONS:
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported training evidence file type.")
        if str(file.content_type or "").lower() in _BLOCKED_CONTENT_TYPES:
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsafe training evidence content type.")
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

    replacements = {
        "/training/files/upload": upload_training_file_shared,
    }
    for route in router_module.router.routes:
        replacement = replacements.get(getattr(route, "path", ""))
        if replacement is None:
            continue
        route.endpoint = replacement
        if getattr(route, "dependant", None) is not None:
            route.dependant.call = replacement

    _INSTALLED = True
