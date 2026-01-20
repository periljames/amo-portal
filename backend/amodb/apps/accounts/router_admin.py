# backend/amodb/apps/accounts/router_admin.py

from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.security import get_current_active_user, require_admin, require_roles
from . import models, schemas, services

router = APIRouter(prefix="/accounts/admin", tags=["accounts_admin"])
RESERVED_PLATFORM_SLUGS = {"system", "root"}
AMO_ASSET_UPLOAD_DIR = Path(os.getenv("AMO_ASSET_UPLOAD_DIR", "uploads/amo_assets")).resolve()
TRAINING_UPLOAD_DIR = Path(os.getenv("TRAINING_UPLOAD_DIR", "uploads/training")).resolve()
AIRCRAFT_DOC_UPLOAD_DIR = Path(
    os.getenv("AIRCRAFT_DOC_UPLOAD_DIR", "/tmp/amo_aircraft_documents")
).resolve()
AIRCRAFT_DOC_AMO_SUBDIR = "aircraft"


def _ensure_amo_storage_dirs(amo_id: str) -> None:
    for base in (AMO_ASSET_UPLOAD_DIR, TRAINING_UPLOAD_DIR, AIRCRAFT_DOC_UPLOAD_DIR):
        base.mkdir(parents=True, exist_ok=True)

    (AMO_ASSET_UPLOAD_DIR / amo_id).mkdir(parents=True, exist_ok=True)
    (TRAINING_UPLOAD_DIR / amo_id).mkdir(parents=True, exist_ok=True)
    (AIRCRAFT_DOC_UPLOAD_DIR / amo_id / AIRCRAFT_DOC_AMO_SUBDIR).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# AMO MANAGEMENT (SUPERUSER ONLY)
# ---------------------------------------------------------------------------


def _require_superuser(current_user: models.User) -> models.User:
    """
    Internal helper: platform superuser gate.

    - Blocks system/service accounts even if they somehow had is_superuser=True.
    - Requires is_superuser=True (platform owner).
    """
    if getattr(current_user, "is_system_account", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System/service accounts cannot use superuser endpoints.",
        )

    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser privileges required.",
        )
    return current_user


def _parse_env_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _platform_settings_defaults() -> dict:
    return {
        "api_base_url": os.getenv("PLATFORM_API_BASE_URL"),
        "acme_directory_url": os.getenv("ACME_DIRECTORY_URL"),
        "acme_client": os.getenv("ACME_CLIENT"),
        "certificate_status": os.getenv("ACME_CERT_STATUS"),
        "certificate_issuer": os.getenv("ACME_CERT_ISSUER"),
        "certificate_expires_at": _parse_env_datetime(
            os.getenv("ACME_CERT_EXPIRES_AT")
        ),
        "last_renewed_at": _parse_env_datetime(os.getenv("ACME_CERT_RENEWED_AT")),
        "notes": os.getenv("PLATFORM_NOTES"),
    }


def _get_or_create_platform_settings(db: Session) -> models.PlatformSettings:
    settings = db.query(models.PlatformSettings).first()
    if not settings:
        settings = models.PlatformSettings(**_platform_settings_defaults())
        db.add(settings)
        db.commit()
        db.refresh(settings)
        return settings

    defaults = _platform_settings_defaults()
    updated = False
    for key, value in defaults.items():
        if value is not None and getattr(settings, key) in (None, ""):
            setattr(settings, key, value)
            updated = True
    if updated:
        db.commit()
        db.refresh(settings)
    return settings


@router.post(
    "/amos",
    response_model=schemas.AMORead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new AMO (platform superuser only)",
)
def create_amo(
    payload: schemas.AMOCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Create a new AMO.

    Only the platform SUPERUSER can call this. Normal AMO admins cannot
    create new organisations.
    """
    _require_superuser(current_user)

    login_slug = payload.login_slug.strip().lower()

    if login_slug in RESERVED_PLATFORM_SLUGS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Login slug is reserved for platform support.",
        )

    existing = (
        db.query(models.AMO)
        .filter(
            (models.AMO.amo_code == payload.amo_code)
            | (models.AMO.login_slug == login_slug)
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="AMO with this code or login_slug already exists.",
        )

    amo = models.AMO(
        amo_code=payload.amo_code,
        name=payload.name,
        icao_code=payload.icao_code,
        country=payload.country,
        login_slug=login_slug,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        time_zone=payload.time_zone,
        is_active=True,
    )
    db.add(amo)
    db.commit()
    db.refresh(amo)
    _ensure_amo_storage_dirs(amo.id)
    return amo


@router.get(
    "/amos",
    response_model=List[schemas.AMORead],
    summary="List all AMOs (platform superuser only)",
)
def list_amos(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    List all AMOs in the platform.

    Only SUPERUSER can see the full list.
    """
    _require_superuser(current_user)
    return db.query(models.AMO).order_by(models.AMO.amo_code.asc()).all()


# ---------------------------------------------------------------------------
# DEPARTMENTS (AMO ADMIN / SUPERUSER)
# ---------------------------------------------------------------------------


@router.post(
    "/departments",
    response_model=schemas.DepartmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create department within current user's AMO (or any AMO for superuser)",
)
def create_department(
    payload: schemas.DepartmentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """
    Create a department.

    - Normal AMO admins: can only create departments in their own AMO.
    - SUPERUSER: can create departments in any AMO.
    """
    if payload.amo_id != current_user.amo_id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create department for another AMO.",
        )

    dup = (
        db.query(models.Department)
        .filter(
            models.Department.amo_id == payload.amo_id,
            models.Department.code == payload.code,
        )
        .first()
    )
    if dup:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Department code already exists for this AMO.",
        )

    dept = models.Department(
        amo_id=payload.amo_id,
        code=payload.code,
        name=payload.name,
        default_route=payload.default_route,
        sort_order=payload.sort_order,
        is_active=True,
    )
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


@router.get(
    "/departments",
    response_model=List[schemas.DepartmentRead],
    summary="List departments (current AMO by default; any AMO for superuser)",
)
def list_departments(
    amo_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    List departments.

    - Normal users / AMO admins: always scoped to their own AMO.
    - SUPERUSER: can optionally pass `amo_id` to inspect another AMO;
      if omitted, sees departments for their own (ROOT/system) AMO.
    """
    q = db.query(models.Department)

    if current_user.is_superuser:
        if amo_id:
            q = q.filter(models.Department.amo_id == amo_id)
    else:
        q = q.filter(models.Department.amo_id == current_user.amo_id)

    return q.order_by(models.Department.sort_order.asc()).all()


# ---------------------------------------------------------------------------
# AMO ASSETS (AMO ADMIN / SUPERUSER)
# ---------------------------------------------------------------------------


@router.post(
    "/assets",
    response_model=schemas.AMOAssetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an AMO asset (AMO admin or superuser)",
)
def create_amo_asset(
    payload: schemas.AMOAssetCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """
    Create an AMO asset.

    - Normal AMO admins: can only create assets for their own AMO.
    - SUPERUSER: can create assets for any AMO.
    """
    if payload.amo_id != current_user.amo_id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create assets for another AMO.",
        )

    asset = models.AMOAsset(
        **payload.model_dump(exclude={"is_active"}),
        is_active=payload.is_active if payload.is_active is not None else True,
        uploaded_by_user_id=current_user.id,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.get(
    "/assets",
    response_model=List[schemas.AMOAssetRead],
    summary="List AMO assets (current AMO by default; any AMO for superuser)",
)
def list_amo_assets(
    amo_id: Optional[str] = None,
    kind: Optional[models.AMOAssetKind] = None,
    only_active: bool = True,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    List assets.

    - Normal users / AMO admins: always scoped to their own AMO.
    - SUPERUSER: can optionally pass `amo_id` to inspect another AMO;
      if omitted, sees assets for their own (ROOT/system) AMO.
    """
    q = db.query(models.AMOAsset)

    if current_user.is_superuser:
        if amo_id:
            q = q.filter(models.AMOAsset.amo_id == amo_id)
    else:
        q = q.filter(models.AMOAsset.amo_id == current_user.amo_id)

    if kind:
        q = q.filter(models.AMOAsset.kind == kind)
    if only_active:
        q = q.filter(models.AMOAsset.is_active.is_(True))

    return q.order_by(models.AMOAsset.created_at.desc()).all()


@router.get(
    "/assets/{asset_id}",
    response_model=schemas.AMOAssetRead,
    summary="Get an AMO asset by id",
)
def get_amo_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    asset = db.query(models.AMOAsset).filter(models.AMOAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.")

    if not current_user.is_superuser and asset.amo_id != current_user.amo_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to access this asset.")

    return asset


@router.put(
    "/assets/{asset_id}",
    response_model=schemas.AMOAssetRead,
    summary="Update an AMO asset (AMO admin or superuser)",
)
def update_amo_asset(
    asset_id: str,
    payload: schemas.AMOAssetUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    asset = db.query(models.AMOAsset).filter(models.AMOAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.")

    if not current_user.is_superuser and asset.amo_id != current_user.amo_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this asset.")

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(asset, field, value)

    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.delete(
    "/assets/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate an AMO asset (AMO admin or superuser)",
)
def deactivate_amo_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    asset = db.query(models.AMOAsset).filter(models.AMOAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found.")

    if not current_user.is_superuser and asset.amo_id != current_user.amo_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this asset.")

    asset.is_active = False
    db.add(asset)
    db.commit()
    return


# ---------------------------------------------------------------------------
# USER MANAGEMENT (AMO ADMIN / SUPERUSER)
# ---------------------------------------------------------------------------


@router.post(
    "/users",
    response_model=schemas.UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create user in current AMO (or any AMO for superuser)",
)
def create_user_admin(
    payload: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """
    Create a user.

    - Normal AMO admins: payload.amo_id is forced to their AMO.
    - SUPERUSER: can set any amo_id in payload.
    - Only SUPERUSER can create SUPERUSER role.
    - Enforces uniqueness for email OR staff_code within the AMO.
    """
    if not current_user.is_superuser:
        payload = payload.copy(update={"amo_id": current_user.amo_id})

    if (not current_user.is_superuser) and (payload.role == models.AccountRole.SUPERUSER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only platform superuser can create superuser accounts.",
        )

    existing = (
        db.query(models.User)
        .filter(
            models.User.amo_id == payload.amo_id,
            (models.User.email == payload.email)
            | (models.User.staff_code == payload.staff_code),
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email or staff code already exists in the AMO.",
        )

    try:
        user = services.create_user(db, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    return user


@router.get(
    "/users",
    response_model=List[schemas.UserRead],
    summary="List users (current AMO by default; any AMO for superuser)",
)
def list_users_admin(
    amo_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 200,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    """
    List users.

    - Normal AMO admins: see only users in their own AMO.
    - SUPERUSER: can optionally pass `amo_id` to list users for that AMO;
      if omitted, sees users for their own (ROOT/system) AMO.
    - Supports skip/limit/search for frontend paging and filtering.
    """
    q = db.query(models.User)

    if current_user.is_superuser:
        if amo_id:
            q = q.filter(models.User.amo_id == amo_id)
    else:
        q = q.filter(models.User.amo_id == current_user.amo_id)

    if search and search.strip():
        s = f"%{search.strip()}%"
        q = q.filter(
            or_(
                models.User.full_name.ilike(s),
                models.User.email.ilike(s),
                models.User.staff_code.ilike(s),
            )
        )

    q = q.order_by(models.User.full_name.asc()).offset(skip).limit(limit)
    return q.all()


@router.put(
    "/users/{user_id}",
    response_model=schemas.UserRead,
    summary="Update user (scoped to current AMO for admins; any AMO for superuser)",
)
def update_user_admin(
    user_id: str,
    payload: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_roles(models.AccountRole.SUPERUSER, models.AccountRole.AMO_ADMIN)
    ),
):
    """
    Update a user.

    - AMO_ADMIN: can only update users in their AMO.
    - SUPERUSER: can update any user by id.
    - Blocks non-superusers from role escalation to SUPERUSER and from changing amo_id.
    """
    q = db.query(models.User).filter(models.User.id == user_id)

    if not current_user.is_superuser:
        q = q.filter(models.User.amo_id == current_user.amo_id)

    user = q.first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found or not in your AMO.",
        )

    update_data = payload.model_dump(exclude_unset=True)

    if not current_user.is_superuser:
        if "amo_id" in update_data or "is_superuser" in update_data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot modify amo_id or superuser status.",
            )
        if "role" in update_data and update_data["role"] == models.AccountRole.SUPERUSER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot assign SUPERUSER role.",
            )

    # NOTE: services.update_user() should also enforce what fields are allowed.
    user = services.update_user(db, user, payload)
    return user


# ---------------------------------------------------------------------------
# AUTHORISATIONS (AMO ADMIN / QUALITY MANAGER / SUPERUSER)
# ---------------------------------------------------------------------------


def _require_quality_or_admin(user: models.User) -> models.User:
    """
    Helper gate for authorisation management.

    - SUPERUSER or AMO admin always allowed.
    - QUALITY_MANAGER allowed for their AMO.
    - System/service accounts are blocked even if flags are set.
    """
    if getattr(user, "is_system_account", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System/service accounts cannot manage authorisations.",
        )

    if user.is_superuser or user.is_amo_admin:
        return user
    if user.role == models.AccountRole.QUALITY_MANAGER:
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Quality Manager or AMO Admin required.",
    )


@router.post(
    "/authorisation-types",
    response_model=schemas.AuthorisationTypeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create authorisation type for an AMO",
)
def create_authorisation_type(
    payload: schemas.AuthorisationTypeCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Create an authorisation type.

    - Normal admins / QMs: can only create for their AMO.
    - SUPERUSER: can create for any AMO by setting payload.amo_id.
    """
    _require_quality_or_admin(current_user)

    if not current_user.is_superuser and payload.amo_id != current_user.amo_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create authorisation type for another AMO.",
        )

    dup = (
        db.query(models.AuthorisationType)
        .filter(
            models.AuthorisationType.amo_id == payload.amo_id,
            models.AuthorisationType.code == payload.code,
        )
        .first()
    )
    if dup:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Authorisation code already exists for this AMO.",
        )

    atype = models.AuthorisationType(
        amo_id=payload.amo_id,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        maintenance_scope=payload.maintenance_scope,
        regulation_reference=payload.regulation_reference,
        can_issue_crs=payload.can_issue_crs,
        requires_dual_sign=payload.requires_dual_sign,
        requires_valid_licence=payload.requires_valid_licence,
        is_active=True,
    )
    db.add(atype)
    db.commit()
    db.refresh(atype)
    return atype


@router.get(
    "/authorisation-types",
    response_model=List[schemas.AuthorisationTypeRead],
    summary="List authorisation types (current AMO by default; any AMO for superuser)",
)
def list_authorisation_types(
    amo_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    List authorisation types.

    - Normal users / admins: see types only for their AMO.
    - SUPERUSER: can optionally pass `amo_id` to view another AMO; if omitted,
      sees types for their own (ROOT/system) AMO.
    """
    q = db.query(models.AuthorisationType)

    if current_user.is_superuser:
        if amo_id:
            q = q.filter(models.AuthorisationType.amo_id == amo_id)
    else:
        q = q.filter(models.AuthorisationType.amo_id == current_user.amo_id)

    return q.order_by(models.AuthorisationType.code.asc()).all()


@router.post(
    "/user-authorisations",
    response_model=schemas.UserAuthorisationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Grant authorisation to user",
)
def grant_user_authorisation(
    payload: schemas.UserAuthorisationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Grant a specific authorisation type to a user.

    - SUPERUSER: can grant for any AMO as long as user and type share the same AMO.
    - AMO Admin / QM: can only grant within their AMO.

    Security hardening:
    - granted_by_user_id is ALWAYS set to the authenticated current_user.id
      (client is not allowed to spoof this).
    """
    _require_quality_or_admin(current_user)

    user = db.query(models.User).filter(models.User.id == payload.user_id).first()
    atype = (
        db.query(models.AuthorisationType)
        .filter(models.AuthorisationType.id == payload.authorisation_type_id)
        .first()
    )

    if not user or not atype:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User or authorisation type not found.",
        )

    if user.amo_id != atype.amo_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User and authorisation type must belong to the same AMO.",
        )

    if not current_user.is_superuser and user.amo_id != current_user.amo_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User or authorisation type invalid for this AMO.",
        )

    ua = models.UserAuthorisation(
        user_id=user.id,
        authorisation_type_id=atype.id,
        scope_text=payload.scope_text,
        effective_from=payload.effective_from,
        expires_at=payload.expires_at,
        granted_by_user_id=current_user.id,
    )
    db.add(ua)
    db.commit()
    db.refresh(ua)
    return ua


# ---------------------------------------------------------------------------
# PLATFORM SETTINGS (SUPERUSER)
# ---------------------------------------------------------------------------


@router.get(
    "/platform-settings",
    response_model=schemas.PlatformSettingsRead,
    summary="Get platform settings (superuser only)",
)
def get_platform_settings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    return _get_or_create_platform_settings(db)


@router.put(
    "/platform-settings",
    response_model=schemas.PlatformSettingsRead,
    summary="Update platform settings (superuser only)",
)
def update_platform_settings(
    payload: schemas.PlatformSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    settings = _get_or_create_platform_settings(db)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(settings, key, value)
    db.commit()
    db.refresh(settings)
    return settings
