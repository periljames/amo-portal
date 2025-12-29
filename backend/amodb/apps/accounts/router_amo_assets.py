# backend/amodb/apps/accounts/router_amo_assets.py

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user
from . import models, schemas, services

router = APIRouter(prefix="/accounts/amo-assets", tags=["accounts_amo_assets"])

# You can override this per environment:
#   AMO_ASSET_UPLOAD_DIR=/var/lib/amodb/uploads/amo_assets
_AMO_ASSET_UPLOAD_DIR = Path(os.getenv("AMO_ASSET_UPLOAD_DIR", "uploads/amo_assets")).resolve()
_AMO_ASSET_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_MAX_UPLOAD_BYTES = int(os.getenv("AMO_ASSET_MAX_UPLOAD_BYTES", "0") or "0")

_ALLOWED_LOGO_EXTS = {".png", ".jpg", ".jpeg", ".svg"}
_ALLOWED_TEMPLATE_EXTS = {".pdf"}


def _require_amo_admin(current_user: models.User) -> models.User:
    if getattr(current_user, "is_system_account", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System/service accounts cannot manage AMO assets.",
        )

    if getattr(current_user, "is_superuser", False):
        return current_user

    if getattr(current_user, "is_amo_admin", False):
        return current_user

    if current_user.role == models.AccountRole.AMO_ADMIN:
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="AMO admin privileges required.",
    )


def _resolve_target_amo_id(current_user: models.User, amo_id: Optional[str]) -> str:
    if amo_id and not current_user.is_superuser and amo_id != current_user.amo_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot manage assets for another AMO.",
        )
    return amo_id if amo_id and current_user.is_superuser else current_user.amo_id


def _get_latest_asset(
    db: Session,
    amo_id: str,
    kind: models.AMOAssetKind,
) -> Optional[models.AMOAsset]:
    return (
        db.query(models.AMOAsset)
        .filter(
            models.AMOAsset.amo_id == amo_id,
            models.AMOAsset.kind == kind,
            models.AMOAsset.is_active.is_(True),
        )
        .order_by(models.AMOAsset.created_at.desc())
        .first()
    )


def _ensure_safe_path(path: Path) -> Path:
    resolved = path.resolve()
    if not str(resolved).startswith(str(_AMO_ASSET_UPLOAD_DIR)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid asset path.",
        )
    return resolved


def _save_upload(
    *,
    file: UploadFile,
    dest_path: Path,
) -> None:
    total = 0
    with dest_path.open("wb") as out:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if _MAX_UPLOAD_BYTES and total > _MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Upload exceeds maximum file size.",
                )
            out.write(chunk)


def _delete_if_exists(path: Optional[str]) -> None:
    if not path:
        return
    try:
        p = Path(path)
        if p.exists():
            p.unlink()
    except Exception:
        return


@router.get(
    "/me",
    response_model=List[schemas.AMOAssetRead],
    summary="Get AMO asset configuration for the current AMO",
)
def get_amo_assets(
    amo_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    target_amo_id = _resolve_target_amo_id(current_user, amo_id)
    return (
        db.query(models.AMOAsset)
        .filter(models.AMOAsset.amo_id == target_amo_id)
        .order_by(models.AMOAsset.created_at.desc())
        .all()
    )


@router.post(
    "/logo",
    response_model=schemas.AMOAssetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload CRS logo asset (AMO admin only)",
)
def upload_crs_logo(
    file: UploadFile = File(...),
    amo_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_amo_admin(current_user)
    target_amo_id = _resolve_target_amo_id(current_user, amo_id)

    filename = file.filename or "logo"
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_LOGO_EXTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Logo must be one of: .png, .jpg, .jpeg, .svg",
        )

    folder = (_AMO_ASSET_UPLOAD_DIR / target_amo_id).resolve()
    folder.mkdir(parents=True, exist_ok=True)

    asset_id = models.generate_user_id()
    dest_path = _ensure_safe_path(folder / f"crs_logo_{asset_id}{ext}")

    _save_upload(file=file, dest_path=dest_path)

    asset = _get_latest_asset(db, target_amo_id, models.AMOAssetKind.CRS_LOGO)
    if asset:
        _delete_if_exists(asset.storage_path)
    else:
        asset = models.AMOAsset(
            amo_id=target_amo_id,
            kind=models.AMOAssetKind.CRS_LOGO,
        )

    asset.original_filename = filename
    asset.storage_path = str(dest_path)
    asset.content_type = file.content_type
    asset.size_bytes = dest_path.stat().st_size
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
    return asset


@router.post(
    "/template",
    response_model=schemas.AMOAssetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload CRS PDF template (AMO admin only)",
)
def upload_crs_template(
    file: UploadFile = File(...),
    amo_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_amo_admin(current_user)
    target_amo_id = _resolve_target_amo_id(current_user, amo_id)

    filename = file.filename or "template.pdf"
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_TEMPLATE_EXTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Template must be a .pdf file",
        )

    folder = (_AMO_ASSET_UPLOAD_DIR / target_amo_id).resolve()
    folder.mkdir(parents=True, exist_ok=True)

    asset_id = models.generate_user_id()
    dest_path = _ensure_safe_path(folder / f"crs_template_{asset_id}{ext}")

    _save_upload(file=file, dest_path=dest_path)

    asset = _get_latest_asset(db, target_amo_id, models.AMOAssetKind.CRS_TEMPLATE)
    if asset:
        _delete_if_exists(asset.storage_path)
    else:
        asset = models.AMOAsset(
            amo_id=target_amo_id,
            kind=models.AMOAssetKind.CRS_TEMPLATE,
        )

    asset.original_filename = filename
    asset.storage_path = str(dest_path)
    asset.content_type = file.content_type
    asset.size_bytes = dest_path.stat().st_size
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
    return asset


@router.get(
    "/logo",
    response_class=FileResponse,
    summary="Download CRS logo for the current AMO",
)
def download_crs_logo(
    amo_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    target_amo_id = _resolve_target_amo_id(current_user, amo_id)
    asset = _get_latest_asset(db, target_amo_id, models.AMOAssetKind.CRS_LOGO)
    if not asset or not asset.storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No logo uploaded for this AMO.")

    path = _ensure_safe_path(Path(asset.storage_path))
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Logo asset not found.")

    return FileResponse(
        path=str(path),
        media_type=asset.content_type or "application/octet-stream",
        filename=asset.original_filename or path.name,
    )


@router.get(
    "/template",
    response_class=FileResponse,
    summary="Download CRS template for the current AMO",
)
def download_crs_template(
    amo_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    target_amo_id = _resolve_target_amo_id(current_user, amo_id)
    asset = _get_latest_asset(db, target_amo_id, models.AMOAssetKind.CRS_TEMPLATE)
    if not asset or not asset.storage_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No template uploaded for this AMO.")

    path = _ensure_safe_path(Path(asset.storage_path))
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template asset not found.")

    return FileResponse(
        path=str(path),
        media_type=asset.content_type or "application/pdf",
        filename=asset.original_filename or path.name,
    )
