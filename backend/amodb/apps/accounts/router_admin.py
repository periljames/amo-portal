# backend/amodb/apps/accounts/router_admin.py

from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import List, Optional
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from amodb.database import get_db
from amodb.apps.audit import services as audit_services
from amodb.apps.audit import models as audit_models
from amodb.apps.audit import schemas as audit_schemas
from amodb.apps.notifications import service as notification_service
from amodb.apps.tasks import services as task_services
from amodb.security import get_current_active_user, require_admin, require_roles
from . import models, schemas, services

router = APIRouter(prefix="/accounts/admin", tags=["accounts_admin"])
RESERVED_PLATFORM_SLUGS = {"system", "root"}
AMO_ASSET_UPLOAD_DIR = Path(os.getenv("AMO_ASSET_UPLOAD_DIR", "uploads/amo_assets")).resolve()
PLATFORM_ASSET_UPLOAD_DIR = Path(
    os.getenv("PLATFORM_ASSET_UPLOAD_DIR", "uploads/platform_assets")
).resolve()
TRAINING_UPLOAD_DIR = Path(os.getenv("TRAINING_UPLOAD_DIR", "uploads/training")).resolve()
AIRCRAFT_DOC_UPLOAD_DIR = Path(
    os.getenv("AIRCRAFT_DOC_UPLOAD_DIR", "/tmp/amo_aircraft_documents")
).resolve()
AIRCRAFT_DOC_AMO_SUBDIR = "aircraft"

ALLOWED_PLATFORM_LOGO_EXTS = {".png", ".jpg", ".jpeg", ".svg"}



def _get_managed_user_or_404(db: Session, *, current_user: models.User, user_id: str) -> models.User:
    query = db.query(models.User).filter(models.User.id == user_id)
    if not current_user.is_superuser:
        query = query.filter(models.User.amo_id == current_user.amo_id)
    user = query.first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found or not in your AMO.",
        )
    return user


def _emit_user_command_event(
    db: Session,
    *,
    actor_user_id: str,
    user: models.User,
    action: str,
    after: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> None:
    audit_services.log_event(
        db,
        amo_id=user.amo_id,
        actor_user_id=actor_user_id,
        entity_type="accounts.user.command",
        entity_id=str(user.id),
        action=action,
        after=after or {},
        metadata={"module": "accounts", **(metadata or {})},
    )


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


def _parse_env_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        return None


def _platform_settings_defaults() -> dict:
    return {
        "api_base_url": os.getenv("PLATFORM_API_BASE_URL"),
        "platform_name": os.getenv("PLATFORM_BRAND_NAME", "AMO Portal"),
        "platform_tagline": os.getenv("PLATFORM_BRAND_TAGLINE"),
        "brand_accent": os.getenv("PLATFORM_BRAND_ACCENT"),
        "brand_accent_soft": os.getenv("PLATFORM_BRAND_ACCENT_SOFT"),
        "brand_accent_secondary": os.getenv("PLATFORM_BRAND_ACCENT_SECONDARY"),
        "gzip_minimum_size": _parse_env_int(os.getenv("GZIP_MINIMUM_SIZE")),
        "gzip_compresslevel": _parse_env_int(os.getenv("GZIP_COMPRESSLEVEL")),
        "max_request_body_bytes": _parse_env_int(os.getenv("MAX_REQUEST_BODY_BYTES")),
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


def _ensure_platform_storage_dir() -> None:
    PLATFORM_ASSET_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_safe_platform_path(path: Path) -> Path:
    resolved = path.resolve()
    if not str(resolved).startswith(str(PLATFORM_ASSET_UPLOAD_DIR)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid platform asset path.",
        )
    return resolved


def _save_platform_upload(*, file: UploadFile, dest_path: Path) -> None:
    with dest_path.open("wb") as out:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)


def _delete_platform_asset(path: Optional[str]) -> None:
    if not path:
        return
    try:
        p = Path(path)
        if p.exists():
            p.unlink()
    except Exception:
        return


# ---------------------------------------------------------------------------
# SUPERUSER CONTEXT (DEMO / REAL)
# ---------------------------------------------------------------------------


@router.get(
    "/context",
    response_model=schemas.UserActiveContextRead,
    summary="Get the active demo/real context (superuser only)",
)
def get_admin_context(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    context = services.get_or_create_user_active_context(db, user=current_user)
    db.commit()
    db.refresh(context)
    return context


@router.post(
    "/context",
    response_model=schemas.UserActiveContextRead,
    summary="Set the active demo/real context (superuser only)",
)
def set_admin_context(
    payload: schemas.UserActiveContextUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    context = services.set_user_active_context(
        db,
        user=current_user,
        data_mode=payload.data_mode,
        active_amo_id=payload.active_amo_id,
    )
    db.commit()
    db.refresh(context)
    return context


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
        is_demo=bool(payload.is_demo),
        is_active=True,
    )
    db.add(amo)
    db.commit()
    db.refresh(amo)
    _ensure_amo_storage_dirs(amo.id)

    try:
        default_sku = os.getenv("AMODB_DEFAULT_TRIAL_SKU", "").strip()
        if not default_sku:
            skus = services.list_catalog_skus(db, include_inactive=False)
            if not skus:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No active SKU available to start a subscription trial.",
                )
            default_sku = skus[0].code

        services.start_trial(
            db,
            amo_id=amo.id,
            sku_code=default_sku,
            idempotency_key=f"amo-create-{amo.id}-{uuid4().hex}",
        )
    except HTTPException:
        db.delete(amo)
        db.commit()
        raise
    except ValueError as exc:
        db.delete(amo)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    audit_services.create_audit_event(
        db,
        amo_id=amo.id,
        data=audit_schemas.AuditEventCreate(
            entity_type="AMO",
            entity_id=str(amo.id),
            action="create",
            actor_user_id=current_user.id,
            before_json=None,
            after_json={
                "amo_code": amo.amo_code,
                "login_slug": amo.login_slug,
                "name": amo.name,
            },
        ),
    )
    db.commit()
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


@router.put(
    "/amos/{amo_id}",
    response_model=schemas.AMORead,
    summary="Update an AMO (platform superuser only)",
)
def update_amo(
    amo_id: str,
    payload: schemas.AMOUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    amo = db.query(models.AMO).filter(models.AMO.id == amo_id).first()
    if not amo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AMO not found.")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(amo, field, value)
    db.add(amo)
    db.commit()
    db.refresh(amo)

    audit_services.create_audit_event(
        db,
        amo_id=amo.id,
        data=audit_schemas.AuditEventCreate(
            entity_type="AMO",
            entity_id=str(amo.id),
            action="update",
            actor_user_id=current_user.id,
            before_json=None,
            after_json=update_data,
        ),
    )
    db.commit()
    return amo


@router.delete(
    "/amos/{amo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate an AMO (platform superuser only)",
)
def deactivate_amo(
    amo_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    amo = db.query(models.AMO).filter(models.AMO.id == amo_id).first()
    if not amo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AMO not found.")
    amo.is_active = False
    db.add(amo)
    db.commit()
    audit_services.create_audit_event(
        db,
        amo_id=amo.id,
        data=audit_schemas.AuditEventCreate(
            entity_type="AMO",
            entity_id=str(amo.id),
            action="deactivate",
            actor_user_id=current_user.id,
            before_json=None,
            after_json={"is_active": False},
        ),
    )
    db.commit()
    return


@router.post(
    "/amos/{amo_id}/trial-extend",
    response_model=schemas.SubscriptionRead,
    summary="Extend AMO trial period (platform superuser only)",
)
def extend_amo_trial(
    amo_id: str,
    payload: schemas.TrialExtendRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    license = services.get_current_subscription(db, amo_id=amo_id)
    if not license:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active or trialing subscription found for this AMO.",
        )
    if license.status not in (
        models.LicenseStatus.TRIALING,
        models.LicenseStatus.EXPIRED,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only trial or expired subscriptions can be extended.",
        )

    now = datetime.now(timezone.utc)
    extend_delta = timedelta(days=payload.extend_days)
    existing_end = license.trial_ends_at or license.current_period_end
    base = existing_end if existing_end and existing_end > now else now
    license.trial_ends_at = base + extend_delta
    license.current_period_end = license.trial_ends_at
    license.trial_grace_expires_at = None
    license.status = models.LicenseStatus.TRIALING
    license.is_read_only = False
    if not license.trial_started_at:
        license.trial_started_at = now

    db.add(license)
    db.commit()
    db.refresh(license)

    audit_services.create_audit_event(
        db,
        amo_id=amo_id,
        data=audit_schemas.AuditEventCreate(
            entity_type="TenantLicense",
            entity_id=str(license.id),
            action="trial_extend",
            actor_user_id=current_user.id,
            before_json=None,
            after_json={"extend_days": payload.extend_days},
        ),
    )
    db.commit()
    return license


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
    target_amo_id = None

    if current_user.is_superuser:
        target_amo_id = amo_id or current_user.amo_id
    else:
        target_amo_id = current_user.amo_id

    if target_amo_id:
        q = q.filter(models.Department.amo_id == target_amo_id)

    departments = q.order_by(models.Department.sort_order.asc()).all()
    if not departments and target_amo_id:
        created = services.seed_default_departments(db, amo_id=target_amo_id)
        if created:
            db.commit()
            departments = (
                db.query(models.Department)
                .filter(models.Department.amo_id == target_amo_id)
                .order_by(models.Department.sort_order.asc())
                .all()
            )

    return departments


@router.get(
    "/staff-code-suggestions",
    response_model=schemas.StaffCodeSuggestions,
    summary="Suggest staff codes based on first/last name",
)
def staff_code_suggestions(
    first_name: str,
    last_name: str,
    amo_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    if not first_name.strip() or not last_name.strip():
        raise HTTPException(status_code=400, detail="First and last name are required.")

    target_amo_id = amo_id if current_user.is_superuser and amo_id else current_user.amo_id

    def _clean(value: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", value.strip().upper())

    first = _clean(first_name)
    last = _clean(last_name)
    if not first or not last:
        raise HTTPException(status_code=400, detail="Name cannot be empty.")

    base_candidates = [
        f"{first[0]}{last}",
        f"{first}{last[0]}",
        f"{first}{last}",
        f"{first[0]}{last[:6]}",
        f"{last}{first[0]}",
    ]

    existing = {
        row[0]
        for row in db.query(models.User.staff_code)
        .filter(models.User.amo_id == target_amo_id)
        .all()
    }

    suggestions: List[str] = []
    for candidate in base_candidates:
        if candidate and candidate not in existing and candidate not in suggestions:
            suggestions.append(candidate)

    suffix = 1
    while len(suggestions) < 5:
        base = base_candidates[0]
        candidate = f"{base}{suffix}"
        suffix += 1
        if candidate in existing or candidate in suggestions:
            continue
        suggestions.append(candidate)

    return schemas.StaffCodeSuggestions(suggestions=suggestions)


@router.put(
    "/departments/{department_id}",
    response_model=schemas.DepartmentRead,
    summary="Update a department (AMO admin or superuser)",
)
def update_department(
    department_id: str,
    payload: schemas.DepartmentUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    dept = db.query(models.Department).filter(models.Department.id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found.")

    if not current_user.is_superuser and dept.amo_id != current_user.amo_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot update department for another AMO.",
        )

    if payload.name is not None:
        dept.name = payload.name
    if payload.default_route is not None:
        dept.default_route = payload.default_route
    if payload.sort_order is not None:
        dept.sort_order = payload.sort_order
    if payload.is_active is not None:
        dept.is_active = payload.is_active

    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


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
    audit_services.log_event(
        db,
        amo_id=user.amo_id,
        actor_user_id=str(current_user.id),
        entity_type="accounts.user",
        entity_id=str(user.id),
        action="CREATED",
        after={"email": user.email, "role": user.role, "is_active": user.is_active},
        metadata={"module": "accounts"},
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


@router.get(
    "/users/{user_id}",
    response_model=schemas.UserRead,
    summary="Get one user (scoped to current AMO for admins; any AMO for superuser)",
)
def get_user_admin(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    return _get_managed_user_or_404(db, current_user=current_user, user_id=user_id)


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
    try:
        user = services.update_user(db, user, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    audit_services.log_event(
        db,
        amo_id=user.amo_id,
        actor_user_id=str(current_user.id),
        entity_type="accounts.user",
        entity_id=str(user.id),
        action="UPDATED",
        after=update_data,
        metadata={"module": "accounts"},
    )
    return user


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate user (scoped to current AMO for admins; any AMO for superuser)",
)
def deactivate_user_admin(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user = _get_managed_user_or_404(db, current_user=current_user, user_id=user_id)

    user.is_active = False
    user.deactivated_at = datetime.now(timezone.utc)
    user.deactivated_reason = "deactivated_by_admin"
    db.add(user)
    db.commit()
    audit_services.log_event(
        db,
        amo_id=user.amo_id,
        actor_user_id=str(current_user.id),
        entity_type="accounts.user",
        entity_id=str(user.id),
        action="DEACTIVATED",
        after={"is_active": False},
        metadata={"module": "accounts"},
    )
    return


@router.post("/users/{user_id}/commands/disable", response_model=schemas.UserCommandResult)
def command_disable_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user = _get_managed_user_or_404(db, current_user=current_user, user_id=user_id)
    user.is_active = False
    user.deactivated_at = datetime.now(timezone.utc)
    user.deactivated_reason = "disabled_by_admin_command"
    db.add(user)
    _emit_user_command_event(
        db,
        actor_user_id=str(current_user.id),
        user=user,
        action="DISABLED",
        after={"is_active": False},
    )
    db.commit()
    return schemas.UserCommandResult(user_id=user.id, command="disable", status="ok", effective_at=datetime.now(timezone.utc))


@router.post("/users/{user_id}/commands/enable", response_model=schemas.UserCommandResult)
def command_enable_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user = _get_managed_user_or_404(db, current_user=current_user, user_id=user_id)
    user.is_active = True
    user.deactivated_at = None
    user.deactivated_reason = None
    db.add(user)
    _emit_user_command_event(
        db,
        actor_user_id=str(current_user.id),
        user=user,
        action="ENABLED",
        after={"is_active": True},
    )
    db.commit()
    return schemas.UserCommandResult(user_id=user.id, command="enable", status="ok", effective_at=datetime.now(timezone.utc))


@router.post("/users/{user_id}/commands/revoke-access", response_model=schemas.UserCommandResult)
def command_revoke_access(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user = _get_managed_user_or_404(db, current_user=current_user, user_id=user_id)
    now = datetime.now(timezone.utc)
    user.token_revoked_at = now
    db.add(user)
    _emit_user_command_event(
        db,
        actor_user_id=str(current_user.id),
        user=user,
        action="ACCESS_REVOKED",
        after={"token_revoked_at": now.isoformat()},
    )
    db.commit()
    return schemas.UserCommandResult(user_id=user.id, command="revoke-access", status="ok", effective_at=now)


@router.post("/users/{user_id}/commands/force-password-reset", response_model=schemas.UserCommandResult)
def command_force_password_reset(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user = _get_managed_user_or_404(db, current_user=current_user, user_id=user_id)
    now = datetime.now(timezone.utc)
    user.must_change_password = True
    user.token_revoked_at = now
    db.add(user)
    _emit_user_command_event(
        db,
        actor_user_id=str(current_user.id),
        user=user,
        action="PASSWORD_RESET_FORCED",
        after={"must_change_password": True, "token_revoked_at": now.isoformat()},
    )
    db.commit()
    return schemas.UserCommandResult(user_id=user.id, command="force-password-reset", status="ok", effective_at=now)


@router.post("/users/{user_id}/commands/notify", response_model=schemas.UserCommandResult)
def command_notify_user(
    user_id: str,
    payload: schemas.UserCommandNotifyPayload,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user = _get_managed_user_or_404(db, current_user=current_user, user_id=user_id)
    now = datetime.now(timezone.utc)
    notification_service.send_email(
        template_key="accounts.user.command.notify",
        recipient=user.email,
        subject=payload.subject,
        context={"message": payload.message, "user_id": user.id, "actor_user_id": current_user.id},
        correlation_id=f"user-notify-{user.id}-{int(now.timestamp())}",
        amo_id=user.amo_id,
        db=db,
    )
    _emit_user_command_event(
        db,
        actor_user_id=str(current_user.id),
        user=user,
        action="NOTIFIED",
        after={"subject": payload.subject},
    )
    db.commit()
    return schemas.UserCommandResult(user_id=user.id, command="notify", status="ok", effective_at=now)


@router.post("/users/{user_id}/commands/schedule-review", response_model=schemas.UserCommandResult)
def command_schedule_review(
    user_id: str,
    payload: schemas.UserCommandSchedulePayload,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    user = _get_managed_user_or_404(db, current_user=current_user, user_id=user_id)
    now = datetime.now(timezone.utc)
    task = task_services.create_task(
        db,
        amo_id=user.amo_id,
        title=payload.title,
        description=payload.description,
        owner_user_id=user.id,
        supervisor_user_id=current_user.id,
        due_at=payload.due_at,
        entity_type="accounts.user",
        entity_id=user.id,
        priority=payload.priority,
        metadata={"scheduled_by": current_user.id, "command": "schedule-review"},
    )
    _emit_user_command_event(
        db,
        actor_user_id=str(current_user.id),
        user=user,
        action="REVIEW_SCHEDULED",
        after={"task_id": task.id, "due_at": payload.due_at.isoformat() if payload.due_at else None},
        metadata={"task_id": task.id},
    )
    db.commit()
    return schemas.UserCommandResult(user_id=user.id, command="schedule-review", status="ok", effective_at=now, task_id=task.id)


# ---------------------------------------------------------------------------
# ADMIN OVERVIEW SUMMARY
# ---------------------------------------------------------------------------


@router.get(
    "/overview-summary",
    response_model=schemas.OverviewSummary,
    summary="Overview summary for admin dashboard (AMO admin or superuser)",
)
def get_overview_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin),
):
    is_superuser = current_user.is_superuser
    amo_scope = None if is_superuser else current_user.amo_id
    now = datetime.now(timezone.utc)
    errors: List[str] = []

    def scoped(query, model_field):
        if amo_scope is None:
            return query
        return query.filter(model_field == amo_scope)

    def safe_count(query, label: str) -> Optional[int]:
        try:
            return query.scalar() or 0
        except Exception:
            errors.append(label)
            return None

    users_missing_department = safe_count(
        scoped(
            db.query(func.count(models.User.id)).filter(
                models.User.department_id.is_(None)
            ),
            models.User.amo_id,
        ),
        "users_missing_department",
    )
    inactive_users = safe_count(
        scoped(
            db.query(func.count(models.User.id)).filter(
                models.User.is_active.is_(False)
            ),
            models.User.amo_id,
        ),
        "inactive_users",
    )
    inactive_assets = safe_count(
        scoped(
            db.query(func.count(models.AMOAsset.id)).filter(
                models.AMOAsset.is_active.is_(False)
            ),
            models.AMOAsset.amo_id,
        ),
        "inactive_assets",
    )
    inactive_amos = None
    if is_superuser:
        inactive_amos = safe_count(
            db.query(func.count(models.AMO.id)).filter(
                models.AMO.is_active.is_(False)
            ),
            "inactive_amos",
        )

    badges: dict[str, schemas.OverviewBadge] = {}
    issues: List[schemas.OverviewIssue] = []

    def badge(
        key: str,
        count: Optional[int],
        severity: str,
        route: str,
        available: bool = True,
    ) -> None:
        badges[key] = schemas.OverviewBadge(
            count=count,
            severity=severity,
            route=route,
            available=available,
        )

    def issue(
        key: str,
        label: str,
        count: Optional[int],
        severity: str,
        route: str,
    ) -> None:
        if count is None or count == 0:
            return
        issues.append(
            schemas.OverviewIssue(
                key=key,
                label=label,
                count=count,
                severity=severity,
                route=route,
            )
        )

    users_attention = safe_count(
        scoped(
            db.query(func.count(func.distinct(models.User.id))).filter(
                or_(
                    models.User.department_id.is_(None),
                    models.User.is_active.is_(False),
                )
            ),
            models.User.amo_id,
        ),
        "users_attention",
    )
    users_available = users_attention is not None
    badge(
        "users",
        users_attention,
        "warning" if (users_attention or 0) > 0 else "info",
        "/admin/users?filter=attention",
        available=users_available,
    )
    badge(
        "assets",
        inactive_assets,
        "warning" if (inactive_assets or 0) > 0 else "info",
        "/admin/amo-assets?filter=inactive",
        available=inactive_assets is not None,
    )
    if is_superuser:
        badge(
            "amos",
            inactive_amos,
            "warning" if (inactive_amos or 0) > 0 else "info",
            "/admin/amos?filter=inactive",
            available=inactive_amos is not None,
        )

    badge(
        "billing",
        None,
        "info",
        "/admin/billing?filter=issues",
        available=False,
    )

    issue(
        "users_missing_department",
        "Users missing department",
        users_missing_department,
        "warning",
        "/admin/users?filter=missing_department",
    )
    issue(
        "inactive_users",
        "Inactive users",
        inactive_users,
        "warning",
        "/admin/users?filter=inactive",
    )
    if is_superuser:
        issue(
            "inactive_amos",
            "Inactive AMOs",
            inactive_amos,
            "warning",
            "/admin/amos?filter=inactive",
        )
    issue(
        "inactive_assets",
        "Inactive assets",
        inactive_assets,
        "warning",
        "/admin/amo-assets?filter=inactive",
    )

    recent_activity: List[schemas.OverviewActivity] = []
    recent_activity_available = True
    try:
        query = db.query(audit_models.AuditEvent)
        if amo_scope is not None:
            query = query.filter(audit_models.AuditEvent.amo_id == amo_scope)
        events = query.order_by(audit_models.AuditEvent.occurred_at.desc()).limit(5).all()
        for event in events:
            recent_activity.append(
                schemas.OverviewActivity(
                    occurred_at=event.occurred_at,
                    action=event.action,
                    entity_type=event.entity_type,
                    actor_user_id=event.actor_user_id,
                )
            )
    except Exception:
        recent_activity_available = False
        errors.append("recent_activity")

    system_status = "healthy"
    if errors:
        system_status = "degraded"

    return schemas.OverviewSummary(
        system=schemas.OverviewSystemStatus(
            status=system_status,
            last_checked_at=now,
            refresh_paused=False,
            errors=errors,
        ),
        badges=badges,
        issues=issues,
        recent_activity=recent_activity,
        recent_activity_available=recent_activity_available,
    )


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


@router.post(
    "/platform-assets/logo",
    response_model=schemas.PlatformSettingsRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload platform logo (superuser only)",
)
def upload_platform_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    _ensure_platform_storage_dir()

    filename = file.filename or "platform-logo"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_PLATFORM_LOGO_EXTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Logo must be one of: .png, .jpg, .jpeg, .svg",
        )

    settings = _get_or_create_platform_settings(db)
    asset_id = uuid4().hex
    dest_path = _ensure_safe_platform_path(
        PLATFORM_ASSET_UPLOAD_DIR / f"platform_logo_{asset_id}{ext}"
    )

    _save_platform_upload(file=file, dest_path=dest_path)

    if settings.platform_logo_path:
        _delete_platform_asset(settings.platform_logo_path)

    settings.platform_logo_path = str(dest_path)
    settings.platform_logo_filename = filename
    settings.platform_logo_content_type = file.content_type
    settings.platform_logo_uploaded_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(settings)
    return settings


@router.get(
    "/platform-assets/logo",
    response_class=FileResponse,
    summary="Download platform logo (superuser only)",
)
def download_platform_logo(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
):
    _require_superuser(current_user)
    settings = _get_or_create_platform_settings(db)
    if not settings.platform_logo_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No platform logo configured.",
        )

    path = _ensure_safe_platform_path(Path(settings.platform_logo_path))
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform logo asset not found.",
        )

    return FileResponse(
        path=str(path),
        media_type=settings.platform_logo_content_type or "application/octet-stream",
        filename=settings.platform_logo_filename or path.name,
    )
