# backend/amodb/apps/accounts/router_amo_assets.py

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user
from . import models, schemas

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


def _load_or_create_asset(db: Session, amo_id: str) -> models.AMOAsset:
    asset = db.query(models.AMOAsset).filter(models.AMOAsset.amo_id == amo_id).first()
    if asset:
        return asset
    asset = models.AMOAsset(amo_id=amo_id)
    db.add(asset)
    return asset


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
    response_model=schemas.AMOAssetRead,
    summary="Get AMO asset configuration for the current AMO",
)
def get_amo_assets(
    amo_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    target_amo_id = _resolve_target_amo_id(current_user, amo_id)
    asset = db.query(models.AMOAsset).filter(models.AMOAsset.amo_id == target_amo_id).first()
    if not asset:
        asset = models.AMOAsset(amo_id=target_amo_id)
    return asset


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

    asset = _load_or_create_asset(db, target_amo_id)
    _delete_if_exists(asset.crs_logo_path)

    asset.crs_logo_path = str(dest_path)
    asset.crs_logo_filename = filename
    asset.crs_logo_content_type = file.content_type
    asset.crs_logo_uploaded_at = datetime.utcnow()

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

    asset = _load_or_create_asset(db, target_amo_id)
    _delete_if_exists(asset.crs_template_path)

    asset.crs_template_path = str(dest_path)
    asset.crs_template_filename = filename
    asset.crs_template_content_type = file.content_type
    asset.crs_template_uploaded_at = datetime.utcnow()

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
    asset = db.query(models.AMOAsset).filter(models.AMOAsset.amo_id == target_amo_id).first()
    if not asset or not asset.crs_logo_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No logo uploaded for this AMO.")

    path = _ensure_safe_path(Path(asset.crs_logo_path))
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Logo asset not found.")

    return FileResponse(
        path=str(path),
        media_type=asset.crs_logo_content_type or "application/octet-stream",
        filename=asset.crs_logo_filename or path.name,
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
    asset = db.query(models.AMOAsset).filter(models.AMOAsset.amo_id == target_amo_id).first()
    if not asset or not asset.crs_template_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No template uploaded for this AMO.")

    path = _ensure_safe_path(Path(asset.crs_template_path))
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template asset not found.")

    return FileResponse(
        path=str(path),
        media_type=asset.crs_template_content_type or "application/pdf",
        filename=asset.crs_template_filename or path.name,
    )