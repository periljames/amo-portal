# backend/amodb/apps/accounts/router_amo_assets.py

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from amodb import storage
from amodb.database import get_db
from amodb.security import get_current_active_user
from . import models, schemas, services

router = APIRouter(prefix="/accounts/amo-assets", tags=["accounts_amo_assets"])

_MAX_UPLOAD_BYTES = int(os.getenv("AMO_ASSET_MAX_UPLOAD_BYTES", "0") or "0")
_ALLOWED_LOGO_EXTS = {".png", ".jpg", ".jpeg", ".svg"}
_ALLOWED_TEMPLATE_EXTS = {".pdf"}
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._ -]+")


def _require_amo_admin(current_user: models.User) -> models.User:
    if getattr(current_user, "is_system_account", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="System/service accounts cannot manage AMO assets.")
    if getattr(current_user, "is_superuser", False) or getattr(current_user, "is_amo_admin", False) or current_user.role == models.AccountRole.AMO_ADMIN:
        return current_user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="AMO admin privileges required.")


def _resolve_target_amo_id(current_user: models.User, amo_id: Optional[str]) -> str:
    if amo_id and not current_user.is_superuser and amo_id != current_user.amo_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot manage assets for another AMO.")
    return amo_id if amo_id and current_user.is_superuser else current_user.amo_id


def _get_latest_asset(db: Session, amo_id: str, kind: models.AMOAssetKind) -> Optional[models.AMOAsset]:
    return (
        db.query(models.AMOAsset)
        .filter(models.AMOAsset.amo_id == amo_id, models.AMOAsset.kind == kind, models.AMOAsset.is_active.is_(True))
        .order_by(models.AMOAsset.created_at.desc())
        .first()
    )


def _build_asset_summary(db: Session, amo_id: str) -> schemas.AMOAssetSummary:
    logo = _get_latest_asset(db, amo_id, models.AMOAssetKind.CRS_LOGO)
    template = _get_latest_asset(db, amo_id, models.AMOAssetKind.CRS_TEMPLATE)
    return schemas.AMOAssetSummary(
        amo_id=amo_id,
        crs_logo_filename=logo.original_filename if logo else None,
        crs_logo_content_type=logo.content_type if logo else None,
        crs_logo_uploaded_at=logo.created_at if logo else None,
        crs_template_filename=template.original_filename if template else None,
        crs_template_content_type=template.content_type if template else None,
        crs_template_uploaded_at=template.created_at if template else None,
    )


def _safe_filename(value: str | None, fallback: str) -> str:
    name = Path(value or fallback).name.strip()
    name = _SAFE_FILENAME.sub("_", name).strip(" .")
    return name[:180] or fallback


def _stage_upload(file: UploadFile) -> tuple[Path, int, str]:
    root = storage.cache_root()
    root.mkdir(parents=True, exist_ok=True)
    fd, raw_path = tempfile.mkstemp(prefix="amo-asset-", dir=str(root))
    os.close(fd)
    path = Path(raw_path)
    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("wb") as out:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if _MAX_UPLOAD_BYTES and total > _MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Upload exceeds maximum file size.")
                digest.update(chunk)
                out.write(chunk)
        if total <= 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Uploaded asset is empty.")
        return path, total, digest.hexdigest()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        try:
            file.file.close()
        except Exception:
            pass


def _persist_asset(
    db: Session,
    *,
    file: UploadFile,
    target_amo_id: str,
    kind: models.AMOAssetKind,
    extension: str,
    current_user: models.User,
    original_filename: str,
) -> schemas.AMOAssetSummary:
    staged, size_bytes, sha256 = _stage_upload(file)
    asset_id = models.generate_user_id()
    key = f"amo-assets/{target_amo_id}/{kind.value.lower()}/{asset_id}{extension}"
    stored: storage.StoredObject | None = None
    previous_uri: str | None = None
    try:
        stored = storage.put_file(staged, key=key, content_type=file.content_type)
        asset = _get_latest_asset(db, target_amo_id, kind)
        if asset is None:
            asset = models.AMOAsset(amo_id=target_amo_id, kind=kind)
        else:
            previous_uri = asset.storage_path

        asset.original_filename = original_filename
        asset.storage_path = stored.uri
        asset.content_type = file.content_type
        asset.size_bytes = stored.size_bytes or size_bytes
        asset.sha256 = sha256
        asset.uploaded_by_user_id = current_user.id
        asset.is_active = True

        services.record_usage(
            db,
            amo_id=target_amo_id,
            meter_key=services.METER_KEY_STORAGE_MB,
            quantity=services.megabytes_from_bytes(asset.size_bytes or 0),
            commit=False,
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)
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
            storage.delete(previous_uri)
        except Exception:
            # The database now points at the committed replacement. A stale object
            # is safer than rolling back to a deleted file; lifecycle cleanup may
            # remove the old object later.
            pass
    return _build_asset_summary(db, target_amo_id)


def _materialize_asset(asset: models.AMOAsset, *, missing_detail: str) -> Path:
    if not asset.storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=missing_detail)
    try:
        return storage.materialize(asset.storage_path, expected_sha256=asset.sha256)
    except (FileNotFoundError, ValueError, OSError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=missing_detail) from exc


@router.get("/me", response_model=schemas.AMOAssetSummary, summary="Get AMO asset configuration for the current AMO")
def get_amo_assets(amo_id: Optional[str] = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    return _build_asset_summary(db, _resolve_target_amo_id(current_user, amo_id))


@router.post("/logo", response_model=schemas.AMOAssetSummary, status_code=status.HTTP_201_CREATED, summary="Upload CRS logo asset (AMO admin only)")
def upload_crs_logo(file: UploadFile = File(...), amo_id: Optional[str] = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    _require_amo_admin(current_user)
    target_amo_id = _resolve_target_amo_id(current_user, amo_id)
    filename = _safe_filename(file.filename, "logo")
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_LOGO_EXTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Logo must be one of: .png, .jpg, .jpeg, .svg")
    return _persist_asset(db, file=file, target_amo_id=target_amo_id, kind=models.AMOAssetKind.CRS_LOGO, extension=ext, current_user=current_user, original_filename=filename)


@router.post("/template", response_model=schemas.AMOAssetSummary, status_code=status.HTTP_201_CREATED, summary="Upload CRS PDF template (AMO admin only)")
def upload_crs_template(file: UploadFile = File(...), amo_id: Optional[str] = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    _require_amo_admin(current_user)
    target_amo_id = _resolve_target_amo_id(current_user, amo_id)
    filename = _safe_filename(file.filename, "template.pdf")
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_TEMPLATE_EXTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Template must be a .pdf file")
    return _persist_asset(db, file=file, target_amo_id=target_amo_id, kind=models.AMOAssetKind.CRS_TEMPLATE, extension=ext, current_user=current_user, original_filename=filename)


@router.get("/logo", response_class=FileResponse, summary="Download CRS logo for the current AMO")
def download_crs_logo(amo_id: Optional[str] = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    target_amo_id = _resolve_target_amo_id(current_user, amo_id)
    asset = _get_latest_asset(db, target_amo_id, models.AMOAssetKind.CRS_LOGO)
    if not asset or not asset.storage_path:
        return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"Cache-Control": "private, max-age=60"})
    try:
        path = _materialize_asset(asset, missing_detail="Logo asset not found.")
    except HTTPException:
        return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"Cache-Control": "private, max-age=60"})
    etag = f'"{asset.sha256 or f"{asset.id}:{asset.size_bytes or 0}"}"'
    return FileResponse(path=str(path), media_type=asset.content_type or "application/octet-stream", filename=asset.original_filename or path.name, headers={"ETag": etag, "Cache-Control": "private, max-age=300"})


@router.get("/template", response_class=FileResponse, summary="Download CRS template for the current AMO")
def download_crs_template(amo_id: Optional[str] = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)):
    target_amo_id = _resolve_target_amo_id(current_user, amo_id)
    asset = _get_latest_asset(db, target_amo_id, models.AMOAssetKind.CRS_TEMPLATE)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No template uploaded for this AMO.")
    path = _materialize_asset(asset, missing_detail="Template asset not found.")
    return FileResponse(path=str(path), media_type=asset.content_type or "application/pdf", filename=asset.original_filename or path.name, headers={"ETag": f'"{asset.sha256 or asset.id}"', "Cache-Control": "private, max-age=300"})
